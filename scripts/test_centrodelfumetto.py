#!/usr/bin/env python3
# Cardoryx - Centro del Fumetto V2
# TEST ISOLATO READ-ONLY:
# - non modifica data/retail_prices.json
# - non tocca Cardmarket
# - scopre prodotti via sitemap reali
# - considera solo schede Pokemon sotto /shop/card-universe/pokemon-world/pokemon/
# - misura match esatti e possibile impatto sui 3 negozi

import json
import re
import time
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from html import unescape
from pathlib import Path

BASE = "https://www.centrodelfumetto.it"
SITEMAPS = [
    BASE + "/wp-sitemap.xml",
    BASE + "/wp-sitemap-posts-product-1.xml",
    BASE + "/product-sitemap.xml",
    BASE + "/sitemap_index.xml",
]
PRODUCT_PATH = "/shop/card-universe/pokemon-world/pokemon/"
RETAIL = Path("data/retail_prices.json")
REPORT = Path("centro_fumetto_test_report.json")

UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/2.0)"
TIMEOUT = 20
MAX_SITEMAPS = 80
MAX_PRODUCTS = 250
SLEEP_SECONDS = 0.04

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = unescape(s).lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept-Language": "it-IT,it;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml,text/xml,*/*",
        "Connection": "close",
    })
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return (
            r.read().decode("utf-8", "replace"),
            r.geturl(),
            getattr(r, "status", None),
        )

def plain(html):
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()

def collector_parts(v):
    s = str(v or "").strip()
    m = re.match(
        r"^([A-Za-z]*)(\d{1,4})(?:\s*[/\-]\s*([A-Za-z]*)(\d{1,4}))?$",
        s,
    )
    if not m:
        return None
    return (
        m.group(1).upper(),
        int(m.group(2)),
        (m.group(3) or "").upper(),
        int(m.group(4)) if m.group(4) else None,
    )

def iter_cards(data):
    cards = data.get("cards", {})
    return cards if isinstance(cards, list) else cards.values()

def build_indexes(data):
    exact = defaultdict(list)
    known_sets = set()

    for c in iter_cards(data):
        cp = collector_parts(c.get("number"))
        if not cp:
            continue
        set_key = norm(c.get("set"))
        known_sets.add(set_key)
        exact[
            (
                set_key,
                cp,
                norm(c.get("name")),
                c.get("variant"),
            )
        ].append(c)

    return exact, known_sets

def sitemap_urls(xml):
    return [
        unescape(x.strip())
        for x in re.findall(r"<loc>(.*?)</loc>", xml, re.I | re.S)
    ]

def discover_products():
    products = []
    stats = []
    queue = list(SITEMAPS)
    seen_maps = set()
    seen_products = set()

    while queue and len(seen_maps) < MAX_SITEMAPS:
        sm = queue.pop(0)
        if sm in seen_maps:
            continue
        seen_maps.add(sm)

        try:
            body, final, status = get(sm)
            locs = sitemap_urls(body)
            stats.append({
                "url": sm,
                "finalUrl": final,
                "status": status,
                "locs": len(locs),
            })

            for u in locs:
                low = u.lower()
                if low.endswith(".xml") or "sitemap" in low:
                    if u not in seen_maps:
                        queue.append(u)
                    continue

                if PRODUCT_PATH in low and u not in seen_products:
                    seen_products.add(u)
                    products.append(u)

        except Exception as exc:
            stats.append({
                "url": sm,
                "error": repr(exc),
            })

    return products, stats

LABELS = (
    "Espansione",
    "Condizione",
    "Rarità",
    "Grading",
    "First Edition",
    "Foiling",
    "Reverse Holo",
    "Firmata",
    "Alterata",
    "Lingua",
    "N° Collezione",
    "Numero Collezione",
    "Costo Mana",
    "Legale nei Tornei",
    "Colore",
)

def field(text, label):
    next_labels = "|".join(re.escape(x) for x in LABELS)
    m = re.search(
        re.escape(label)
        + r"\s*:\s*(.*?)\s+(?=(?:"
        + next_labels
        + r")\s*:|$)",
        text,
        re.I,
    )
    return m.group(1).strip() if m else ""

def money_from_html(html, text):
    # Prefer structured WooCommerce/product price signals.
    patterns = [
        r'property=["\']product:price:amount["\'][^>]*content=["\']([0-9]+(?:[.,][0-9]{1,2})?)',
        r'class=["\'][^"\']*\bprice\b[^"\']*["\'][^>]*>.*?([0-9]+(?:[.,][0-9]{1,2})?)\s*€',
        r'€\s*([0-9]+(?:[.,][0-9]{1,2})?)',
    ]
    for pattern in patterns:
        m = re.search(pattern, html if "class=" in pattern or "property=" in pattern else text, re.I | re.S)
        if m:
            try:
                return float(m.group(1).replace(",", "."))
            except ValueError:
                pass
    return None

def availability(html, text):
    signals = {
        "inStockMeta": bool(re.search(
            r'(?:schema\.org/InStock|availability["\']?\s*[:=]\s*["\']?in[_ -]?stock)',
            html,
            re.I,
        )),
        "outOfStockMeta": bool(re.search(
            r'(?:schema\.org/OutOfStock|availability["\']?\s*[:=]\s*["\']?out[_ -]?of[_ -]?stock)',
            html,
            re.I,
        )),
        "addToCart": bool(re.search(
            r'(?:add_to_cart_button|single_add_to_cart_button|Aggiungi al carrello)',
            html,
            re.I,
        )),
        "visibleOut": bool(re.search(
            r'\b(?:Esaurito|Non disponibile|Out of stock)\b',
            text,
            re.I,
        )),
    }

    qty = None
    qm = re.search(r"\b(\d+)\s+disponibil[ie]\b", text, re.I)
    if qm:
        qty = int(qm.group(1))

    if signals["outOfStockMeta"] or signals["visibleOut"]:
        return False, qty, signals
    if signals["inStockMeta"] or signals["addToCart"] or (qty is not None and qty > 0):
        return True, qty, signals
    return None, qty, signals

def variant_from_fields(rarity, foiling, reverse):
    nr = norm(rarity)
    nf = norm(foiling)
    nv = norm(reverse)

    if nv in {"si", "yes", "true"}:
        return "Reverse Holo", "reverse-field"

    if "reverse holo" in nr or "reverse holo" in nf:
        return "Reverse Holo", "explicit-reverse"

    if nv in {"no", "false"} and ("holo" in nr or "holo" in nf):
        return "Holo", "explicit-holo"

    # Normal is accepted only when the structured fields explicitly rule out foil.
    if nv in {"no", "false"} and nf in {"no", "none", "non foil", "non holo", ""}:
        if "holo" not in nr and "reverse" not in nr:
            return "Normal", "explicit-non-reverse"

    return None, "variant-unconfirmed"

def clean_name(title):
    name = str(title or "")
    name = re.sub(r"^\s*Carta\s+Pok[eé]mon\s+", "", name, flags=re.I)
    # Remove structured identity tail only; do not guess card names.
    name = re.sub(
        r"\s*[—-]\s*(?:Near Mint|Mint)\b.*$",
        "",
        name,
        flags=re.I,
    ).strip()
    return name

def parse_page(html, url):
    text = plain(html)
    h = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    title = plain(h.group(1)) if h else ""

    expansion = field(text, "Espansione")
    condition = field(text, "Condizione")
    language = field(text, "Lingua")
    number = field(text, "N° Collezione") or field(text, "Numero Collezione")
    rarity = field(text, "Rarità")
    foiling = field(text, "Foiling")
    reverse = field(text, "Reverse Holo")
    price = money_from_html(html, text)
    available, qty, avail_signals = availability(html, text)
    variant, variant_signal = variant_from_fields(rarity, foiling, reverse)

    return {
        "url": url,
        "title": title,
        "name": clean_name(title),
        "set": expansion,
        "condition": condition,
        "language": language,
        "number": number,
        "rarity": rarity,
        "foiling": foiling,
        "reverseHolo": reverse,
        "variant": variant,
        "variantSignal": variant_signal,
        "price": price,
        "available": available,
        "quantity": qty,
        "availabilitySignals": avail_signals,
    }

def store_count(card):
    return len({
        norm(o.get("store"))
        for o in card.get("offers", [])
        if o.get("store")
    })

def main():
    retail = json.loads(RETAIL.read_text(encoding="utf-8"))
    exact, known_sets = build_indexes(retail)
    urls, sitemap_stats = discover_products()

    stats = Counter()
    stats["discoveredProductUrls"] = len(urls)

    exact_examples = []
    rejected_examples = []
    set_unknown = Counter()

    for url in urls[:MAX_PRODUCTS]:
        stats["attempted"] += 1

        try:
            html, final, status = get(url)
            stats["fetched"] += 1
            p = parse_page(html, final)

            if norm(p["language"]) != "italiano":
                stats["languageRejected"] += 1
                continue

            if norm(p["condition"]) != "near mint":
                stats["conditionRejected"] += 1
                continue

            if p["available"] is False:
                stats["unavailable"] += 1
                continue

            if p["available"] is None:
                stats["availabilityUnconfirmed"] += 1
                continue

            if p["price"] is None or p["price"] <= 0:
                stats["priceUnavailable"] += 1
                continue

            cp = collector_parts(p["number"])
            if not cp:
                stats["numberUnavailable"] += 1
                continue

            if not p["set"]:
                stats["setUnavailable"] += 1
                continue

            if not p["variant"]:
                stats["variantUnconfirmed"] += 1
                if len(rejected_examples) < 30:
                    rejected_examples.append(p)
                continue

            stats["usableBeforeIdentity"] += 1

            set_key = norm(p["set"])
            if set_key not in known_sets:
                stats["setNotExactCardoryx"] += 1
                set_unknown[p["set"]] += 1
                if len(rejected_examples) < 30:
                    rejected_examples.append(p)
                continue

            key = (
                set_key,
                cp,
                norm(p["name"]),
                p["variant"],
            )
            matches = exact.get(key, [])

            if len(matches) == 1:
                stats["exactMatches"] += 1
                card = matches[0]
                stores = store_count(card)

                if stores >= 3:
                    stats["matchedAlreadyReliable"] += 1
                elif stores == 2:
                    stats["newReliablePotential"] += 1
                else:
                    stats["matchedCurrentlyNotReliable"] += 1

                if len(exact_examples) < 40:
                    exact_examples.append({
                        "shop": p,
                        "cardoryx": {
                            "set": card.get("set"),
                            "number": card.get("number"),
                            "name": card.get("name"),
                            "variant": card.get("variant"),
                            "currentStores": stores,
                            "currentlyReliable": stores >= 3,
                        },
                    })

            elif len(matches) > 1:
                stats["identityAmbiguous"] += 1
            else:
                stats["identityRejected"] += 1
                if len(rejected_examples) < 30:
                    rejected_examples.append(p)

            time.sleep(SLEEP_SECONDS)

        except Exception as exc:
            stats["errors"] += 1
            if len(rejected_examples) < 30:
                rejected_examples.append({
                    "url": url,
                    "error": repr(exc),
                })

    report = {
        "schema": 2,
        "source": "Centro del Fumetto",
        "mode": "read-only diagnostic",
        "rules": {
            "language": "Italiano only",
            "condition": "Near Mint only",
            "availability": "explicit in-stock signal required",
            "setRule": "exact shop expansion vs existing Cardoryx set; no aliases",
            "variantRule": "only explicit structured Holo/Reverse/Normal signals; otherwise reject",
            "identityRule": "exact set + collector number + exact normalized name + exact variant",
            "createsNewIdentity": False,
            "cardmarketTouched": False,
            "retailPricesModified": False,
        },
        "stats": dict(stats),
        "sitemaps": sitemap_stats,
        "topUnmappedSets": set_unknown.most_common(30),
        "exactExamples": exact_examples,
        "rejectedExamples": rejected_examples,
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
    print("Report:", REPORT)

if __name__ == "__main__":
    main()
