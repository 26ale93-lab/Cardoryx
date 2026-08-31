#!/usr/bin/env python3
# Cardoryx - Collector Store Cards V3
# Diagnostica read-only: usa solo Shopify products.json.
# Non modifica data/retail_prices.json e non tocca Cardmarket.

import json
import re
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from html import unescape
from pathlib import Path

BASE = "https://collectorstorecards.it"
COLL = BASE + "/collections/carte-singole-pokemon"
RETAIL = Path("data/retail_prices.json")
REPORT = Path("collectorstorecards_test_report.json")
UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/3.0)"
MAX_PAGES = 8

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = unescape(s).lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def plain(html):
    html = re.sub(r"<script\b.*?</script>", " ", str(html or ""), flags=re.I | re.S)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()

def get_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Language": "it-IT,it;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def collector_parts(number):
    m = re.match(
        r"^\s*([A-Za-z]*)(\d+)\s*[/\-]\s*([A-Za-z]*)(\d+)\s*$",
        str(number or ""),
    )
    if not m:
        return None
    return (
        m.group(1).upper(),
        int(m.group(2)),
        m.group(3).upper(),
        int(m.group(4)),
    )

def parse_title(title):
    t = str(title or "").strip()
    m = re.search(r"\b([A-Za-z]*\d{1,3})\s*[/\-]\s*([A-Za-z]*\d{1,3})\b", t)
    if not m:
        return None

    number = f"{m.group(1)}/{m.group(2)}"
    before = t[:m.start()].strip(" -–—")
    before = re.sub(r"^\s*Pok[eé]mon\s+", "", before, flags=re.I).strip()

    tail = t[m.end():]
    tail = re.sub(r"\bITA\b.*$", "", tail, flags=re.I).strip(" -–—")

    return {
        "name": before,
        "number": number,
        "setFromTitle": tail,
        "language": "IT" if re.search(r"\bITA\b", t, re.I) else None,
    }

def set_from_tags(tags):
    vals = []
    for tag in tags or []:
        m = re.match(r"^\s*(.+?)\s*\[([A-Za-z0-9]+)\]\s*$", str(tag))
        if m:
            vals.append((m.group(1).strip(), m.group(2).upper()))
    return vals

def condition_from_body(body):
    n = norm(body)
    if re.search(r"\bnear mint\b", n) or re.search(r"\bcondizione nm\b", n):
        return "NM"
    return None

def variant_from_body(body):
    n = norm(body)

    # Ordine importante: Reverse prima di Holo.
    if re.search(r"\breverse holo\b", n) or re.search(r"\bholo reverse\b", n):
        return "Reverse Holo", "explicit reverse holo"

    # Normal solo se esplicitamente dichiarato.
    if re.search(r"\bnon holo\b", n) or re.search(r"\bnon olografica\b", n) or re.search(r"\bnormal\b", n):
        return "Normal", "explicit non-holo/normal"

    # Holo solo se esplicito e non parte di nomi di rarità ambigui.
    if re.search(r"\bholo\b", n) or re.search(r"\bolografica\b", n):
        return "Holo", "explicit holo"

    return None, None

def build_exact_index(data):
    idx = defaultdict(list)
    for c in data.get("cards", {}).values():
        cp = collector_parts(c.get("number"))
        if not cp:
            continue
        idx[
            (
                norm(c.get("set")),
                cp,
                norm(c.get("name")),
                c.get("variant"),
            )
        ].append(c)
    return idx

def main():
    retail = json.loads(RETAIL.read_text(encoding="utf-8"))
    exact_index = build_exact_index(retail)

    stats = Counter()
    products = []
    page_errors = []

    for page in range(1, MAX_PAGES + 1):
        url = f"{COLL}/products.json?limit=250&page={page}"
        try:
            obj = get_json(url)
            batch = obj.get("products", [])
            stats["catalogPagesFetched"] += 1
            products.extend(batch)
            if len(batch) < 250:
                break
        except Exception as e:
            stats["catalogPageErrors"] += 1
            page_errors.append({"page": page, "error": repr(e)})
            break

    stats["products"] = len(products)

    examples = []
    rejected_examples = []

    for p in products:
        stats["productsInspected"] += 1

        parsed = parse_title(p.get("title", ""))
        if not parsed or parsed["language"] != "IT":
            stats["titleRejected"] += 1
            continue

        tags = p.get("tags") or []
        if isinstance(tags, str):
            tags = [x.strip() for x in tags.split(",") if x.strip()]

        set_tags = set_from_tags(tags)
        if len(set_tags) != 1:
            stats["setTagRejected"] += 1
            continue

        set_name, set_code = set_tags[0]
        if norm(set_name) != norm(parsed["setFromTitle"]):
            stats["setTitleConflict"] += 1
            if len(rejected_examples) < 20:
                rejected_examples.append({
                    "reason": "set title/tag conflict",
                    "title": p.get("title"),
                    "setFromTitle": parsed["setFromTitle"],
                    "setFromTag": set_name,
                })
            continue

        variants = p.get("variants") or []
        available = [v for v in variants if v.get("available")]
        if not available:
            stats["unavailable"] += 1
            continue

        prices = {
            float(v["price"])
            for v in available
            if v.get("price") not in (None, "")
        }
        if len(prices) != 1:
            stats["priceRejected"] += 1
            continue
        price = next(iter(prices))

        body = plain(p.get("body_html", ""))
        condition = condition_from_body(body)
        if condition != "NM":
            stats["conditionUnconfirmed"] += 1
            continue
        stats["nearMintConfirmed"] += 1

        variant, variant_signal = variant_from_body(body)
        if not variant:
            stats["variantUnconfirmed"] += 1
            if len(rejected_examples) < 20:
                rejected_examples.append({
                    "reason": "variant unconfirmed",
                    "title": p.get("title"),
                    "bodyPreview": body[:300],
                })
            continue
        stats["variantConfirmed"] += 1

        cp = collector_parts(parsed["number"])
        if not cp:
            stats["numberRejected"] += 1
            continue

        matches = exact_index.get(
            (norm(set_name), cp, norm(parsed["name"]), variant),
            [],
        )

        stats["fullyUsable"] += 1

        if len(matches) == 1:
            stats["exactMatches"] += 1
            card = matches[0]
            if not bool((card.get("stats") or {}).get("reliable")):
                stats["matchedCurrentlyNotReliable"] += 1
            else:
                stats["matchedAlreadyReliable"] += 1
        else:
            stats["identityRejected"] += 1

        if len(examples) < 40:
            examples.append({
                "title": p.get("title"),
                "name": parsed["name"],
                "number": parsed["number"],
                "set": set_name,
                "setCode": set_code,
                "condition": condition,
                "variant": variant,
                "variantSignal": variant_signal,
                "price": price,
                "availableVariants": len(available),
                "exactMatch": len(matches) == 1,
                "url": f"{BASE}/products/{p.get('handle')}",
                "bodyPreview": body[:300],
            })

    report = {
        "schema": 3,
        "source": "Collector Store Cards",
        "mode": "read-only diagnostic",
        "ok": True,
        "rules": {
            "shopifyCatalogOnly": True,
            "productPagesOpened": False,
            "language": "ITA title required",
            "condition": "Near Mint explicitly confirmed in body_html",
            "availability": "at least one available Shopify variant",
            "price": "one unique price across available variants",
            "set": "exact title/tag agreement required",
            "variant": "explicit body_html signal only",
            "identity": "exact set + full collector number + exact normalized name + exact variant",
            "createsNewIdentity": False,
            "cardmarketTouched": False,
            "retailPricesModified": False,
        },
        "stats": dict(stats),
        "pageErrors": page_errors,
        "examples": examples,
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
