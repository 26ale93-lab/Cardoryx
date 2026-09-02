#!/usr/bin/env python3
"""Audit read-only: MagoMatto, MyComics e Divertilandia Pro.

Non modifica l'indice retail, non usa Cardmarket e non crea identita. Le tre
fonti vengono interrogate in parallelo; ogni match deve risolvere una sola
identita IT/NM-MINT gia presente in ``data/retail_prices.json``.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
RETAIL = ROOT / "data" / "retail_prices.json"
REPORT = ROOT / "data" / "final_retail_block_audit_report.json"
BUILDER_PATH = ROOT / "scripts" / "build_retail_index.py"

UA = "Mozilla/5.0 (compatible; CardoryxFinalRetailAudit/1.0; +https://github.com/)"
TIMEOUT = 12
MAX_SECONDS = 360
MAX_EXAMPLES = 40

MAGO_BASE = "https://magoalbum.gaborgalazzo.com/search"
MYCOMICS_BASE = "https://mycomics.it"
DIVERTILANDIA_BASE = "https://divertilandiapro.com"


def load_builder():
    spec = importlib.util.spec_from_file_location("cardoryx_retail_builder", BUILDER_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


BUILDER = load_builder()
norm = BUILDER.norm
norm_number = BUILDER.norm_number


def sha256(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def request(url, *, timeout=TIMEOUT):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json,text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return (
            response.read().decode("utf-8", "replace"),
            dict(response.headers.items()),
            getattr(response, "status", None),
            response.geturl(),
        )


def get_json(url, *, timeout=TIMEOUT):
    body, headers, status, final_url = request(url, timeout=timeout)
    return json.loads(body), headers, status, final_url


def iter_cards(data):
    cards = data.get("cards", {})
    return list(cards.values()) if isinstance(cards, dict) else list(cards)


def store_count(card):
    return len({norm(o.get("store")) for o in card.get("offers", []) if o.get("store")})


def has_store(card, store):
    target = norm(store)
    return any(norm(o.get("store")) == target for o in card.get("offers", []))


def indexes(cards):
    by_set_number = defaultdict(list)
    known_sets = {}
    for card in cards:
        if norm(card.get("language")) != "it" or norm(card.get("condition")) != "nm mint":
            continue
        sk = norm(card.get("set"))
        nk = norm_number(card.get("number"))
        if not sk or not nk:
            continue
        by_set_number[(sk, nk)].append(card)
        known_sets[sk] = card.get("set")
    return by_set_number, known_sets


def variant_from_text(value):
    text = norm(value)
    if "master ball reverse" in text or "masterball reverse" in text:
        return "Master Ball Reverse Holo"
    if "poke ball reverse" in text or "pokeball reverse" in text:
        return "Poké Ball Reverse Holo"
    if "energy reverse" in text or "energia reverse" in text:
        return "Energy Reverse Holo"
    if "reverse" in text:
        return "Reverse Holo"
    if re.search(r"\bholo\b", text):
        return "Holo"
    return None


def collector_numbers(value, *, allow_short=False):
    raw = str(value or "")
    found = re.findall(r"(?<![A-Za-z0-9])([A-Za-z]{0,4}\d{1,4}\s*/\s*[A-Za-z]{0,4}\d{1,4})(?![A-Za-z0-9])", raw)
    if not found and allow_short:
        found = re.findall(r"(?<![A-Za-z0-9])([A-Za-z]{0,4}\d{1,4})(?![A-Za-z0-9])", raw)
    return list(dict.fromkeys(norm_number(x) for x in found if norm_number(x)))


def text_set(value, known_sets):
    text = norm(value)
    hits = [(len(sk), sk) for sk in known_sets if sk and re.search(rf"(?:^| ){re.escape(sk)}(?: |$)", text)]
    if not hits:
        return None
    hits.sort(reverse=True)
    best_len = hits[0][0]
    best = {sk for length, sk in hits if length == best_len}
    return next(iter(best)) if len(best) == 1 else None


def exact_candidate(by_set_number, set_key, number, explicit_variant):
    candidates = list(by_set_number.get((norm(set_key), norm_number(number)), []))
    if explicit_variant:
        candidates = [c for c in candidates if norm(c.get("variant")) == norm(explicit_variant)]
    else:
        candidates = [c for c in candidates if "reverse" not in norm(c.get("variant"))]
    return candidates[0] if len(candidates) == 1 else None


def price_from_wc(product):
    prices = product.get("prices") or {}
    raw = prices.get("price")
    minor = prices.get("currency_minor_unit", 2)
    try:
        price = float(raw) / (10 ** int(minor))
    except (TypeError, ValueError, OverflowError):
        return None
    return round(price, 2) if price > 0 else None


def flatten_product(product):
    pieces = [
        product.get("name"), product.get("description"), product.get("short_description"),
        product.get("sku"), product.get("permalink"),
    ]
    for key in ("categories", "tags", "attributes"):
        for item in product.get(key) or []:
            if isinstance(item, dict):
                pieces.extend(item.values())
            else:
                pieces.append(item)
    return " ".join(str(x or "") for x in pieces)


def fetch_wc_products(base, searches, *, max_pages=20):
    products = {}
    calls = []
    for search in searches:
        for page in range(1, max_pages + 1):
            query = urllib.parse.urlencode({"search": search, "per_page": 100, "page": page})
            url = f"{base}/wp-json/wc/store/v1/products?{query}"
            try:
                payload, headers, status, final_url = get_json(url)
            except urllib.error.HTTPError as exc:
                if exc.code in {400, 404} and page > 1:
                    break
                raise
            if not isinstance(payload, list):
                raise ValueError("Store API non ha restituito una lista")
            calls.append({"search": search, "page": page, "status": status, "items": len(payload)})
            for product in payload:
                if isinstance(product, dict):
                    key = str(product.get("id") or product.get("permalink") or product.get("name"))
                    products[key] = product
            total_pages = int(headers.get("X-WP-TotalPages", "0") or 0)
            if not payload or len(payload) < 100 or (total_pages and page >= total_pages):
                break
    return list(products.values()), calls


def base_stats(source):
    return {
        "source": source,
        "ok": True,
        "access": False,
        "products": 0,
        "eligibleMetadata": 0,
        "uniqueCandidates": 0,
        "oneToTwo": 0,
        "twoToThree": 0,
        "threeToFourOrMore": 0,
        "duplicateStore": 0,
        "ambiguousIdentity": 0,
        "examples": [],
    }


def add_candidate(stats, seen, card, store, price, url, raw):
    if has_store(card, store):
        stats["duplicateStore"] += 1
        return
    identity = (norm(card.get("set")), norm_number(card.get("number")), norm(card.get("variant")))
    if identity in seen:
        return
    seen.add(identity)
    before = store_count(card)
    stats["uniqueCandidates"] += 1
    if before == 1:
        stats["oneToTwo"] += 1
    elif before == 2:
        stats["twoToThree"] += 1
    elif before >= 3:
        stats["threeToFourOrMore"] += 1
    if len(stats["examples"]) < MAX_EXAMPLES:
        stats["examples"].append({
            "set": card.get("set"), "number": card.get("number"), "name": card.get("name"),
            "variant": card.get("variant"), "storesBefore": before, "price": price,
            "url": url, "sourceLabel": str(raw)[:500],
        })


def audit_wc(source, base, searches, cards, by_set_number, known_sets, *, require_single_signal):
    stats = base_stats(source)
    seen = set()
    try:
        products, calls = fetch_wc_products(base, searches)
        stats["access"] = True
        stats["products"] = len(products)
        stats["apiCalls"] = calls
        rejection = Counter()
        for product in products:
            text = flatten_product(product)
            normalized = norm(text)
            if not product.get("is_in_stock"):
                rejection["notInStock"] += 1
                continue
            price = price_from_wc(product)
            if price is None:
                rejection["price"] += 1
                continue
            if require_single_signal and not (
                "carta singola" in normalized or "carte singole" in normalized or collector_numbers(text)
            ):
                rejection["notSingle"] += 1
                continue
            if not any(x in normalized for x in ("italiano", "italiana", " lingua it ", " ita ", "prodotto in italiano")):
                rejection["language"] += 1
                continue
            if not any(x in normalized for x in ("near mint", "nm mint", "condizione nm", " nm ")):
                rejection["condition"] += 1
                continue
            set_key = text_set(text, known_sets)
            numbers = collector_numbers(text)
            if not set_key or len(numbers) != 1:
                rejection["identityMetadata"] += 1
                continue
            stats["eligibleMetadata"] += 1
            variant = variant_from_text(text)
            card = exact_candidate(by_set_number, set_key, numbers[0], variant)
            if card is None:
                stats["ambiguousIdentity"] += 1
                continue
            add_candidate(
                stats, seen, card, source, price, product.get("permalink") or base,
                product.get("name") or "",
            )
        stats["rejections"] = dict(rejection)
    except Exception as exc:
        stats["error"] = f"{type(exc).__name__}: {exc}"
    return stats


def first_value(obj, keys):
    for key in keys:
        value = obj.get(key)
        if value not in (None, "", []):
            return value
    return None


def audit_magomatto(cards, by_set_number, known_sets):
    stats = base_stats("MagoMatto")
    seen = set()
    code_map = {str(k).upper().lstrip("X"): v for k, v in BUILDER.TIMETWISTER_SET_CODE_MAP.items()}
    code_map.update({"PFL": "Fiamme Spettrali", "ASC": "Ascesa Eroica", "BLK": "Luce Nera", "MEG": "Megaevoluzione"})
    samples = []
    try:
        page = 0
        total_pages = 1
        rejection = Counter()
        while page < total_pages and page < 100:
            params = urllib.parse.urlencode({"page": page, "size": 200, "sort": "price,desc", "filter": "quantity>0"})
            payload, _, _, _ = get_json(f"{MAGO_BASE}/pokemon?{params}")
            stats["access"] = True
            content = payload.get("content") if isinstance(payload, dict) else payload
            if not isinstance(content, list):
                raise ValueError("Risposta inventario non riconosciuta")
            if isinstance(payload, dict):
                total_pages = int(payload.get("totalPages") or 1)
            stats["products"] += len(content)
            for item in content:
                if not isinstance(item, dict):
                    continue
                if len(samples) < 3:
                    samples.append({"keys": sorted(item.keys()), "sample": {k: item.get(k) for k in sorted(item) if k not in {"image", "description"}}})
                language = norm(first_value(item, ("language", "languageName", "lang", "cardLanguage")))
                condition = norm(first_value(item, ("condition", "conditionName", "cardCondition")))
                quantity = first_value(item, ("quantity", "stock", "availableQuantity"))
                note = str(first_value(item, ("note", "notes", "comment", "description")) or "")
                if language not in {"it", "ita", "italian", "italiano"}:
                    rejection["language"] += 1
                    continue
                if condition not in {"nm", "near mint", "mt", "mint", "nm mint"}:
                    rejection["condition"] += 1
                    continue
                if "slab" in norm(note) or any(x in norm(note) for x in ("psa ", "bgs ", "graded")):
                    rejection["graded"] += 1
                    continue
                try:
                    if float(quantity) <= 0:
                        rejection["notInStock"] += 1
                        continue
                except (TypeError, ValueError):
                    rejection["quantity"] += 1
                    continue
                raw_price = first_value(item, ("price", "sellPrice", "unitPrice"))
                try:
                    price = round(float(raw_price), 2)
                except (TypeError, ValueError):
                    rejection["price"] += 1
                    continue
                if price <= 0:
                    rejection["price"] += 1
                    continue
                set_code = str(first_value(item, ("setCode", "set", "expansionCode")) or "").upper().strip()
                set_name = code_map.get(set_code) or known_sets.get(norm(first_value(item, ("setName", "expansionName"))))
                number_value = first_value(item, ("number", "cardNumber", "collectorNumber", "localId"))
                numbers = collector_numbers(number_value, allow_short=True)
                if not set_name or len(numbers) != 1:
                    rejection["identityMetadata"] += 1
                    continue
                stats["eligibleMetadata"] += 1
                variant = variant_from_text(" ".join(str(first_value(item, (k,)) or "") for k in ("variant", "finish", "rarity", "note")))
                card = exact_candidate(by_set_number, set_name, numbers[0], variant)
                if card is None:
                    stats["ambiguousIdentity"] += 1
                    continue
                add_candidate(stats, seen, card, "MagoMatto", price, "https://magomatto-toolbox.web.app/album/pokemon", first_value(item, ("nameIt", "name", "nameEn")))
            page += 1
        stats["pages"] = page
        stats["totalPages"] = total_pages
        stats["schemaSamples"] = samples
        stats["rejections"] = dict(rejection)
    except Exception as exc:
        stats["error"] = f"{type(exc).__name__}: {exc}"
        stats["schemaSamples"] = samples
    return stats


def audit_mycomics(cards, by_set_number, known_sets):
    stats = audit_wc(
        "MyComics", MYCOMICS_BASE, ("near mint", "pokemon"), cards,
        by_set_number, known_sets, require_single_signal=False,
    )
    stats["mode"] = "woocommerce-store-api"
    # Se la Store API non e disponibile, misuriamo l'adapter di produzione su
    # una copia profonda: nessuna modifica puo raggiungere il file reale.
    if not stats.get("access"):
        copied = {BUILDER.make_key(c["set"], c["number"], c["variant"], c["language"], c["condition"]): copy.deepcopy(c) for c in cards}
        try:
            legacy = BUILDER.collect_mycomics(copied)
            stats["legacyAdapter"] = legacy
            stats["access"] = legacy.get("archivePages", 0) > 0
            stats["mode"] = "production-adapter-copy"
            stats["uniqueCandidates"] = legacy.get("accepted", 0)
            stats["oneToTwo"] = legacy.get("matchedAsSecondStore", 0)
            stats["twoToThree"] = legacy.get("matchedAsThirdStore", 0)
        except Exception as exc:
            stats["legacyError"] = f"{type(exc).__name__}: {exc}"
    return stats


def audit_divertilandia(cards, by_set_number, known_sets):
    stats = audit_wc(
        "Divertilandia Pro", DIVERTILANDIA_BASE, ("pokemon",), cards,
        by_set_number, known_sets, require_single_signal=True,
    )
    stats["mode"] = "woocommerce-store-api"
    return stats


def main():
    started = time.monotonic()
    before = sha256(RETAIL)
    data = json.loads(RETAIL.read_text(encoding="utf-8"))
    cards = iter_cards(data)
    by_set_number, known_sets = indexes(cards)

    jobs = {
        "MagoMatto": lambda: audit_magomatto(cards, by_set_number, known_sets),
        "MyComics": lambda: audit_mycomics(cards, by_set_number, known_sets),
        "Divertilandia Pro": lambda: audit_divertilandia(cards, by_set_number, known_sets),
    }
    sources = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {pool.submit(job): name for name, job in jobs.items()}
        for future in as_completed(futures, timeout=MAX_SECONDS):
            name = futures[future]
            try:
                sources.append(future.result())
            except Exception as exc:
                source = base_stats(name)
                source["error"] = f"{type(exc).__name__}: {exc}"
                sources.append(source)

    sources.sort(key=lambda x: x["source"])
    after = sha256(RETAIL)
    report = {
        "schema": 1,
        "audit": "final-retail-block",
        "durationSeconds": round(time.monotonic() - started, 2),
        "rules": {
            "retailPricesModified": before != after,
            "cardmarketTouched": False,
            "newIdentitiesCreated": False,
            "productionDataModified": False,
            "exactExistingIdentityOnly": True,
            "italianOnly": True,
            "nearMintOrMintOnly": True,
            "availableOnly": True,
            "positivePriceOnly": True,
            "priorityTwoToThree": True,
            "failClosed": True,
            "parallelSources": True,
        },
        "retailHashBefore": before,
        "retailHashAfter": after,
        "sources": sources,
        "totals": {
            "uniqueCandidates": sum(x.get("uniqueCandidates", 0) for x in sources),
            "oneToTwo": sum(x.get("oneToTwo", 0) for x in sources),
            "twoToThree": sum(x.get("twoToThree", 0) for x in sources),
            "threeToFourOrMore": sum(x.get("threeToFourOrMore", 0) for x in sources),
        },
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    if before != after:
        raise SystemExit("ERRORE: retail_prices.json e stato modificato")


if __name__ == "__main__":
    main()
