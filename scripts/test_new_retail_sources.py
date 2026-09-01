#!/usr/bin/env python3
"""Cardoryx — audit read-only di tre nuove sorgenti retail.

Sorgenti: Gemcard Infinity Collection, LPP Collecting e Nerd Fumetti.
Il test non modifica retail_prices.json, non crea identita e non legge dati
Cardmarket. Ogni adapter fallisce in sicurezza e produce diagnostica autonoma.
"""

import hashlib
import json
import re
import runpy
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from html import unescape
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_retail_index.py"
RETAIL = ROOT / "data" / "retail_prices.json"
REPORT = ROOT / "data" / "new_retail_sources_audit_report.json"

UA = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
TIMEOUT = 35


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def utc_now():
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace(
        "+00:00", "Z"
    )


def _get_text_once(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "it-IT,it;q=0.9,en;q=0.5",
            "Cache-Control": "no-cache",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            raw = response.read()
            return {
                "ok": True,
                "status": getattr(response, "status", 200),
                "url": response.geturl(),
                "server": response.headers.get("Server", ""),
                "text": raw.decode("utf-8", "replace"),
                "bytes": len(raw),
            }
    except urllib.error.HTTPError as error:
        body = error.read(12000).decode("utf-8", "replace")
        return {
            "ok": False,
            "status": error.code,
            "url": error.geturl(),
            "server": error.headers.get("Server", ""),
            "text": body,
            "bytes": len(body.encode("utf-8")),
            "error": repr(error),
        }
    except Exception as error:
        return {
            "ok": False,
            "status": None,
            "url": url,
            "server": "",
            "text": "",
            "bytes": 0,
            "error": repr(error),
        }


def get_text(url):
    first = _get_text_once(url)
    if first.get("ok") or first.get("status") not in {403, 429, 500, 502, 503, 504}:
        return first

    # Un solo retry lento per errori HTTP potenzialmente transitori. Non usa
    # proxy, cookie di sfida o tecniche di aggiramento delle protezioni.
    time.sleep(4)
    second = _get_text_once(url)
    second["retryAttempted"] = True
    second["firstStatus"] = first.get("status")
    return second


if not BUILDER.exists() or not RETAIL.exists():
    raise SystemExit("Builder o indice retail non trovato")

retail_hash_before = sha256(RETAIL)
ns = runpy.run_path(str(BUILDER), run_name="__new_sources_read_only_audit__")
for required in ("norm", "norm_number", "strip_html", "detect_variant"):
    if not callable(ns.get(required)):
        raise SystemExit(f"Builder incompatibile: manca {required}")

norm = ns["norm"]
norm_number = ns["norm_number"]
strip_html = ns["strip_html"]
detect_variant = ns["detect_variant"]

with RETAIL.open("r", encoding="utf-8") as stream:
    retail = json.load(stream)

if retail.get("rules", {}).get("cardmarketExcluded") is not True:
    raise SystemExit("Safety check fallito: Cardmarket non risulta escluso")

cards = retail.get("cards")
if not isinstance(cards, dict) or not cards:
    raise SystemExit("Indice retail vuoto o non valido")

exact_index = defaultdict(list)
two_store_set_priority = Counter()
for card_key, card in cards.items():
    exact_index[
        (
            norm(card.get("set")),
            norm_number(card.get("number")),
            norm(card.get("name")),
            card.get("variant"),
        )
    ].append((card_key, card))
    if len(
        {
            str(offer.get("store") or "").strip()
            for offer in (card.get("offers") or [])
            if str(offer.get("store") or "").strip()
        }
    ) == 2:
        two_store_set_priority[norm(card.get("set"))] += 1


def stores_for(card):
    return {
        str(offer.get("store") or "").strip()
        for offer in (card.get("offers") or [])
        if str(offer.get("store") or "").strip()
    }


def impact_for(stores):
    count = len(stores)
    return f"{count}->{count + 1}"


def parse_price(text):
    values = re.findall(r"(?:€\s*)?(\d{1,5}(?:[.,]\d{1,2})?)\s*€?", text)
    if not values:
        return None
    try:
        value = float(values[-1].replace(".", "").replace(",", "."))
    except ValueError:
        return None
    return round(value, 2) if 0 < value < 100000 else None


def add_exact_candidate(result, *, store, set_name, number, name, variant, price, url, raw):
    stats = result["stats"]
    key = (norm(set_name), norm_number(number), norm(name), variant)
    matches = exact_index.get(key, [])
    if len(matches) != 1:
        stats["exactIdentityNotUnique"] += 1
        if len(result["rejectionExamples"]) < 80:
            result["rejectionExamples"].append(
                {
                    "reason": "exactIdentityNotUnique",
                    "set": set_name,
                    "number": number,
                    "name": name,
                    "variant": variant,
                    "matches": len(matches),
                    "raw": raw,
                    "url": url,
                }
            )
        return

    card_key, card = matches[0]
    existing_stores = stores_for(card)
    if store in existing_stores:
        stats["alreadyPresent"] += 1
        return

    candidate_key = (store, card_key, url)
    if candidate_key in result["_seen"]:
        stats["duplicateCandidate"] += 1
        return
    result["_seen"].add(candidate_key)

    stats["safeCandidates"] += 1
    impact = impact_for(existing_stores)
    stats[f"impact{impact.replace('->', 'To')}"] += 1
    candidate = {
        "cardKey": card_key,
        "set": card.get("set"),
        "number": card.get("number"),
        "name": card.get("name"),
        "variant": card.get("variant"),
        "language": "IT",
        "condition": "NM/MINT",
        "price": price,
        "url": url,
        "existingStores": sorted(existing_stores),
        "impact": impact,
        "raw": raw,
    }
    if len(result["candidates"]) < 400:
        result["candidates"].append(candidate)
    if len(existing_stores) == 2 and len(result["priorityTwoToThree"]) < 300:
        result["priorityTwoToThree"].append(candidate)


def source_result(source, rules):
    return {
        "source": source,
        "ok": True,
        "mode": "read-only diagnostic",
        "rules": rules,
        "access": [],
        "stats": Counter(),
        "candidates": [],
        "priorityTwoToThree": [],
        "rejectionExamples": [],
        "_seen": set(),
    }


def finish(result):
    result["stats"] = dict(result["stats"])
    result.pop("_seen", None)
    return result


def product_variant(title):
    text = norm(title)
    if "master ball reverse" in text or "masterball reverse" in text:
        return "Master Ball Reverse Holo"
    if "poke ball reverse" in text or "pokeball reverse" in text:
        return "Poké Ball Reverse Holo"
    if "energy reverse" in text or "energia reverse" in text:
        return "Energy Reverse Holo"
    if "reverse" in text:
        return "Reverse Holo"
    if "non holo" in text or "nonholo" in text:
        return "Normal"
    if "holo" in text or "olograf" in text:
        return "Holo"
    return None


GEMCARD_CATEGORIES = [
    ("Zenit Regale", "https://www.gemcardinfinitycollection.it/it/zenit-regale"),
    ("Tempesta Argentata", "https://www.gemcardinfinitycollection.it/it/tempesta-argentata-it-2"),
    ("Origine Perduta", "https://www.gemcardinfinitycollection.it/it/origini-perdute-it"),
    ("Pokémon GO", "https://www.gemcardinfinitycollection.it/it/pokemon-go-it"),
    ("Colpo Fusione", "https://www.gemcardinfinitycollection.it/it/colpo-fusione-it-2"),
    ("Astri Lucenti", "https://www.gemcardinfinitycollection.it/it/astri-lucenti-it-2"),
    ("Gran Festa", "https://www.gemcardinfinitycollection.it/it/gran-festa-it-2"),
    ("Evoluzioni Eteree", "https://www.gemcardinfinitycollection.it/it/evoluzioni-eteree-it"),
    ("Regno Glaciale", "https://www.gemcardinfinitycollection.it/it/regno-glaciale-it-2"),
    ("Scarlatto e Violetto", "https://www.gemcardinfinitycollection.it/it/scarlatto-e-violetto-it"),
    ("Evoluzioni Prismatiche", "https://www.gemcardinfinitycollection.it/it/evoluzioni-prismatiche"),
]


def gemcard_products(html, page_url):
    anchors = list(
        re.finditer(
            r'<h2[^>]*class=["\'][^"\']*product-title[^"\']*["\'][^>]*>\s*'
            r'<a[^>]+href=["\']([^"\']+)["\'][^>]*>(.*?)</a>\s*</h2>',
            html,
            re.I | re.S,
        )
    )
    products = []
    for index, match in enumerate(anchors):
        end = anchors[index + 1].start() if index + 1 < len(anchors) else min(
            len(html), match.end() + 5000
        )
        block = html[match.start():end]
        price_match = re.search(
            r'class=["\'][^"\']*actual-price[^"\']*["\'][^>]*>(.*?)<',
            block,
            re.I | re.S,
        )
        product_url = urllib.parse.urljoin(page_url, unescape(match.group(1)))
        products.append(
            {
                "title": strip_html(match.group(2)),
                "url": product_url,
                "price": parse_price(strip_html(price_match.group(1))) if price_match else None,
                "available": not bool(re.search(r"esaurito|out[ -]?of[ -]?stock", block, re.I)),
            }
        )
    return products


def parse_gemcard_title(title):
    if not re.search(r"\b(?:ita|it|italiano)\b", title, re.I):
        return None, "language"
    if not re.search(r"\b(?:near\s*mint|mint)\b", title, re.I):
        return None, "condition"
    number_match = re.search(r"\b([A-Z]*\d+\s*/\s*[A-Z]*\d+)\b", title, re.I)
    if not number_match:
        return None, "number"
    variant = product_variant(title)
    if not variant:
        return None, "variantAmbiguous"
    name = title[: number_match.start()].strip(" -–—")
    name = re.sub(
        r"\s+(?:master\s*ball|poke\s*ball|energy|energia)?\s*reverse(?:\s+holo)?\s*$",
        "",
        name,
        flags=re.I,
    ).strip(" -–—")
    name = re.sub(r"\s+(?:non\s*holo|holo)\s*$", "", name, flags=re.I).strip(" -–—")
    if not name:
        return None, "name"
    return {"name": name, "number": number_match.group(1), "variant": variant}, None


def audit_gemcard():
    result = source_result(
        "Gemcard Infinity Collection",
        {
            "scope": "11 explicit Italian set categories, maximum 8 pages each",
            "identity": "exact set + full number + exact normalized name + explicit variant",
            "language": "explicit IT/ITA/Italiano",
            "condition": "explicit Near Mint or Mint",
            "availability": "reject Esaurito/out-of-stock",
            "createsNewIdentity": False,
        },
    )

    def fetch_category(item):
        set_name, base_url = item
        pages = []
        for page_number in range(1, 9):
            url = base_url if page_number == 1 else f"{base_url}?pagenumber={page_number}"
            response = get_text(url)
            pages.append((url, response))
            if not response["ok"]:
                break
            products = gemcard_products(response["text"], url)
            if not products:
                break
            max_page = max(
                [int(value) for value in re.findall(r"pagenumber=(\d+)", response["text"])]
                or [1]
            )
            if page_number >= max_page:
                break
        return set_name, pages

    with ThreadPoolExecutor(max_workers=6) as pool:
        futures = [pool.submit(fetch_category, item) for item in GEMCARD_CATEGORIES]
        for future in as_completed(futures):
            set_name, pages = future.result()
            for url, response in pages:
                result["access"].append(
                    {key: response.get(key) for key in ("ok", "status", "url", "server", "bytes", "error", "retryAttempted", "firstStatus") if response.get(key) is not None}
                )
                result["stats"]["pagesAttempted"] += 1
                if not response["ok"]:
                    result["stats"]["pagesBlockedOrFailed"] += 1
                    continue
                result["stats"]["pagesOk"] += 1
                products = gemcard_products(response["text"], url)
                result["stats"]["productsParsed"] += len(products)
                for product in products:
                    if not product["available"]:
                        result["stats"]["unavailable"] += 1
                        continue
                    if product["price"] is None:
                        result["stats"]["priceRejected"] += 1
                        continue
                    parsed, reason = parse_gemcard_title(product["title"])
                    if not parsed:
                        result["stats"][reason] += 1
                        continue
                    add_exact_candidate(
                        result,
                        store="Gemcard Infinity Collection",
                        set_name=set_name,
                        price=product["price"],
                        url=product["url"],
                        raw=product["title"],
                        **parsed,
                    )
    return finish(result)


def lpp_set_options(html):
    select = re.search(
        r"<select\b[^>]*name\s*=\s*['\"]?poke_idserie['\"]?[^>]*>(.*?)</select>",
        html,
        re.I | re.S,
    )
    if not select:
        return []
    options = []
    for match in re.finditer(
        r"<option\b[^>]*value\s*=\s*['\"]?(\d+)['\"]?[^>]*>(.*?)</option>",
        select.group(1),
        re.I | re.S,
    ):
        set_name = strip_html(match.group(2)).split("/")[0].strip()
        if match.group(1) != "0" and set_name:
            options.append((match.group(1), set_name))
    return options


def lpp_rows(html):
    rows = []
    for row_match in re.finditer(r"<tr\b[^>]*>(.*?)</tr>", html, re.I | re.S):
        row_html = row_match.group(1)
        cells = [
            strip_html(cell)
            for cell in re.findall(r"<td\b[^>]*>(.*?)</td>", row_html, re.I | re.S)
        ]
        sku_match = re.search(r"\b(PO-[A-Z0-9-]+_(?:ita|eng))\b", row_html, re.I)
        if not sku_match or len(cells) < 9:
            continue
        number_match = re.search(r"\b([A-Z]*\d+\s*/\s*[A-Z]*\d+)\b", cells[4], re.I)
        price_match = re.search(r"€\s*(\d+(?:[.,]\d{1,2})?)", cells[8])
        if not number_match or not price_match:
            continue
        rows.append(
            {
                "name": cells[2].strip(),
                "sku": sku_match.group(1),
                "number": number_match.group(1),
                "rarity": cells[5].strip(),
                "condition": cells[6].strip(),
                "price": float(price_match.group(1).replace(",", ".")),
                "available": "non disponibile" not in norm(row_html) and "basketin.php" in row_html,
                "raw": " | ".join(cells[2:9]),
            }
        )
    return rows


def lpp_variant(rarity, sku):
    text = norm(f"{rarity} {sku}")
    if "reverse" in text or re.search(r"(?:^|\s)rh(?:\s|$)", text):
        return "Reverse Holo"
    if norm(rarity) in {"h", "holo", "olografica", "olografiche"}:
        return "Holo"
    return None


def audit_lpp():
    result = source_result(
        "LPP Collecting",
        {
            "scope": "48 live set IDs prioritized by existing two-store Cardoryx identities",
            "identity": "exact Italian set + full number + exact normalized name + explicit H/RH variant",
            "language": "SKU suffix _ita",
            "condition": "mint/near mint, near mint or mint only",
            "availability": "purchase form present and no non-disponibile label",
            "createsNewIdentity": False,
        },
    )
    discovery_url = (
        "https://www.lppcollecting.it/pokemon/ricercacarte.php?"
        "poke_idrarita=0&poke_idserie=103&poke_ricerca=&poke_tipocarta=tutte"
    )
    discovery = get_text(discovery_url)
    result["access"].append(
        {key: discovery.get(key) for key in ("ok", "status", "url", "server", "bytes", "error", "retryAttempted", "firstStatus") if discovery.get(key) is not None}
    )
    result["stats"]["discoveryAttempted"] += 1
    if not discovery["ok"]:
        result["stats"]["discoveryFailed"] += 1
        return finish(result)

    options = lpp_set_options(discovery["text"])
    result["stats"]["setIdsDiscovered"] = len(options)
    selected = sorted(
        enumerate(options),
        key=lambda item: (
            -two_store_set_priority.get(norm(item[1][1]), 0),
            item[0],
        ),
    )[:48]
    selected = [item for _, item in selected]
    result["stats"]["prioritizedSetPages"] = sum(
        two_store_set_priority.get(norm(set_name), 0) > 0
        for _, set_name in selected
    )

    def fetch_set(item):
        set_id, set_name = item
        url = "https://www.lppcollecting.it/pokemon/ricercacarte.php?" + urllib.parse.urlencode(
            {
                "poke_idrarita": "0",
                "poke_idserie": set_id,
                "poke_ricerca": "",
                "poke_tipocarta": "tutte",
            }
        )
        return set_id, set_name, url, get_text(url)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_set, item) for item in selected]
        for future in as_completed(futures):
            set_id, set_name, url, response = future.result()
            result["access"].append(
                {key: response.get(key) for key in ("ok", "status", "url", "server", "bytes", "error", "retryAttempted", "firstStatus") if response.get(key) is not None}
            )
            result["stats"]["setPagesAttempted"] += 1
            if not response["ok"]:
                result["stats"]["setPagesFailed"] += 1
                continue
            result["stats"]["setPagesOk"] += 1
            rows = lpp_rows(response["text"])
            result["stats"]["rowsParsed"] += len(rows)
            for row in rows:
                if not row["sku"].lower().endswith("_ita"):
                    result["stats"]["languageRejected"] += 1
                    continue
                if norm(row["condition"]) not in {"mint near mint", "near mint", "mint"}:
                    result["stats"]["conditionRejected"] += 1
                    continue
                if not row["available"]:
                    result["stats"]["unavailable"] += 1
                    continue
                if row["price"] <= 0:
                    result["stats"]["priceRejected"] += 1
                    continue
                variant = lpp_variant(row["rarity"], row["sku"])
                if not variant:
                    result["stats"]["variantAmbiguous"] += 1
                    continue
                add_exact_candidate(
                    result,
                    store="LPP Collecting",
                    set_name=set_name,
                    number=row["number"],
                    name=row["name"],
                    variant=variant,
                    price=round(row["price"], 2),
                    url=url,
                    raw=row["raw"],
                )
    return finish(result)


def nerd_products(html, page_url):
    title_matches = list(
        re.finditer(
            r'<h2[^>]*class=["\'][^"\']*woocommerce-loop-product__title[^"\']*["\'][^>]*>(.*?)</h2>',
            html,
            re.I | re.S,
        )
    )
    products = []
    for index, match in enumerate(title_matches):
        start = max(0, match.start() - 2000)
        end = title_matches[index + 1].start() if index + 1 < len(title_matches) else min(
            len(html), match.end() + 5000
        )
        block = html[start:end]
        links = re.findall(r'<a[^>]+href=["\']([^"\']+)["\']', block[: block.find(match.group(0)) + len(match.group(0))], re.I)
        prices = re.findall(
            r'<(?:bdi|span)[^>]*>\s*(?:<span[^>]*>)?€?\s*(\d+(?:[.,]\d{1,2})?)',
            block,
            re.I | re.S,
        )
        price = float(prices[-1].replace(",", ".")) if prices else None
        products.append(
            {
                "title": strip_html(match.group(1)),
                "url": urllib.parse.urljoin(page_url, links[-1]) if links else page_url,
                "price": round(price, 2) if price and price > 0 else None,
                "available": not bool(re.search(r"outofstock|esaurito", block, re.I)),
            }
        )
    return products


def parse_nerd_title(title):
    number_match = re.search(r"\b([A-Z]*\d+\s*/\s*[A-Z]*\d+)\b", title, re.I)
    if not number_match:
        return None, "number"
    if not re.search(r"\b(?:italiano|ita)\b", title, re.I):
        return None, "language"
    if not re.search(r"\b(?:near\s*mint|mint)\b", title, re.I):
        return None, "condition"
    variant = product_variant(title)
    if not variant:
        return None, "variantAmbiguous"

    prefix = title[: number_match.start()].strip(" -–—")
    parts = [part.strip() for part in re.split(r"\s+[–—]\s+", prefix) if part.strip()]
    if len(parts) < 2:
        parts = [part.strip() for part in re.split(r"\s+-\s+", prefix) if part.strip()]
    variant_words = {"reverse", "reverse holo", "holo", "non holo"}
    parts = [part for part in parts if norm(part) not in variant_words]
    if len(parts) < 2:
        return None, "setOrName"
    set_name = parts[-1]
    name = " - ".join(parts[:-1]).strip()
    if not name or not set_name:
        return None, "setOrName"
    return {
        "set_name": set_name,
        "number": number_match.group(1),
        "name": name,
        "variant": variant,
    }, None


def audit_nerd():
    result = source_result(
        "Nerd Fumetti",
        {
            "scope": "first 40 live category pages",
            "identity": "exact set + full number + exact normalized name + explicit variant",
            "language": "explicit Italiano/ITA",
            "condition": "explicit Near Mint or Mint; Nuovo alone is rejected",
            "availability": "reject out-of-stock/Esaurito",
            "createsNewIdentity": False,
        },
    )
    base = "https://www.nerdfumetti.com/product-category/carte-singole-pokemon/"

    def fetch_page(page):
        url = base if page == 1 else f"{base}page/{page}/"
        return page, url, get_text(url)

    with ThreadPoolExecutor(max_workers=8) as pool:
        futures = [pool.submit(fetch_page, page) for page in range(1, 41)]
        for future in as_completed(futures):
            page, url, response = future.result()
            result["access"].append(
                {key: response.get(key) for key in ("ok", "status", "url", "server", "bytes", "error", "retryAttempted", "firstStatus") if response.get(key) is not None}
            )
            result["stats"]["pagesAttempted"] += 1
            if not response["ok"]:
                result["stats"]["pagesBlockedOrFailed"] += 1
                continue
            result["stats"]["pagesOk"] += 1
            products = nerd_products(response["text"], url)
            result["stats"]["productsParsed"] += len(products)
            for product in products:
                if not product["available"]:
                    result["stats"]["unavailable"] += 1
                    continue
                if product["price"] is None:
                    result["stats"]["priceRejected"] += 1
                    continue
                parsed, reason = parse_nerd_title(product["title"])
                if not parsed:
                    result["stats"][reason] += 1
                    continue
                add_exact_candidate(
                    result,
                    store="Nerd Fumetti",
                    price=product["price"],
                    url=product["url"],
                    raw=product["title"],
                    **parsed,
                )
    return finish(result)


def run_adapter(name, function):
    try:
        return function()
    except Exception as error:
        return {
            "source": name,
            "ok": False,
            "mode": "read-only diagnostic",
            "error": repr(error),
            "stats": {},
            "candidates": [],
            "priorityTwoToThree": [],
            "rejectionExamples": [],
        }


def main():
    adapters = [
        ("Gemcard Infinity Collection", audit_gemcard),
        ("LPP Collecting", audit_lpp),
        ("Nerd Fumetti", audit_nerd),
    ]
    sources = []
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = {
            pool.submit(run_adapter, name, function): name
            for name, function in adapters
        }
        for future in as_completed(futures):
            sources.append(future.result())

    sources.sort(key=lambda item: item.get("source", ""))
    retail_hash_after = sha256(RETAIL)

    report = {
        "schema": 1,
        "generatedAt": utc_now(),
        "mode": "three independent read-only retail source audits",
        "rules": {
            "retailPricesModified": retail_hash_before != retail_hash_after,
            "cardmarketTouched": False,
            "newIdentitiesCreated": False,
            "productionDataModified": False,
            "exactExistingIdentityOnly": True,
            "priorityTwoToThree": True,
            "failClosed": True,
            "sourcesRunConcurrently": True,
        },
        "retailHashBefore": retail_hash_before,
        "retailHashAfter": retail_hash_after,
        "sources": sources,
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    print(
        json.dumps(
            {source["source"]: source.get("stats", {}) for source in sources},
            ensure_ascii=False,
            indent=2,
        )
    )
    print("Report:", REPORT)


if __name__ == "__main__":
    main()
