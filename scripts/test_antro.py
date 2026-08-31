#!/usr/bin/env python3
# Cardoryx - test L'Antro dei Fumetti V1
# READ-ONLY: non modifica retail_prices.json e non tocca Cardmarket.

import json
import re
import time
import unicodedata
import urllib.request
from collections import Counter
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

BASE = "https://lantrodeifumetti.it"
CATEGORY = BASE + "/categoria-prodotto/trading-card/tgc-pokemon/"
RETAIL = Path("data/retail_prices.json")
REPORT = Path("antro_test_report.json")

UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/1.0)"
TIMEOUT = 15
MAX_PAGES = 30
MAX_PRODUCTS_TO_OPEN = 300

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = unescape(s).lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def get(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "it-IT,it;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace"), r.geturl(), getattr(r, "status", None)

def plain(html):
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()

def collector_parts(number):
    m = re.match(r"^\s*([A-Za-z]*)(\d+)\s*[-/]\s*([A-Za-z]*)(\d+)\s*$", str(number or ""))
    if not m:
        return None
    return (m.group(1).upper(), int(m.group(2)), m.group(3).upper(), int(m.group(4)))

def build_card_index(data):
    idx = {}
    for card in data.get("cards", {}).values():
        key = (
            norm(card.get("set")),
            collector_parts(card.get("number")),
            norm(card.get("name")),
            card.get("variant"),
        )
        if key[1]:
            idx.setdefault(key, []).append(card)
    return idx

def product_links(html):
    links = re.findall(
        r'href=["\']([^"\']+/shop/trading-card/tgc-pokemon/[^"\']+/?)["\']',
        html,
        flags=re.I,
    )
    # de-dup mantenendo ordine
    seen, out = set(), []
    for link in links:
        link = urljoin(BASE, link)
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out

def page_count(html):
    text = plain(html)
    m = re.search(r"Visualizzazione di .*? di\s+(\d+)\s+risultati", text, re.I)
    total = int(m.group(1)) if m else None
    pages = None
    if total:
        pages = (total + 19) // 20
    return total, pages

def parse_product(html, url):
    text = plain(html)

    title_m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    title = plain(title_m.group(1)) if title_m else ""

    # prezzo corrente: preferisci ins/del finale se in offerta, altrimenti primo prezzo utile
    prices = re.findall(r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)", text)
    price = float(prices[0].replace(",", ".")) if prices else None

    sku_m = re.search(r"\bCOD:\s*([A-Za-z0-9_-]+)", text, re.I)
    sku = sku_m.group(1).strip() if sku_m else ""

    cond = ""
    if re.search(r"\bNear Mint\b", text, re.I):
        cond = "NM"

    available = not bool(re.search(r"\bOut of stock\b|\bEsaurito\b", text, re.I))
    if re.search(r"\bSolo\s+\d+\s+pezz[oi]\s+disponibil", text, re.I):
        available = True

    lang = "IT" if re.search(r"\bITA\b", title, re.I) else ""

    num_m = re.search(r"\b([A-Za-z]*\d{1,3})[-/]([A-Za-z]*\d{1,3})\b", title)
    number = f"{num_m.group(1)}/{num_m.group(2)}" if num_m else ""

    variant = None
    nt = norm(title)
    ns = norm(sku)
    if "reverse holo" in nt or ns.endswith("rh"):
        variant = "Reverse Holo"
    elif re.search(r"\bholo\b", nt) or ns.endswith("h"):
        variant = "Holo"
    elif re.search(r"\bnormal\b|\bcomune\b|\bnon comune\b", nt):
        variant = "Normal"

    name = title
    if number:
        name = re.split(re.escape(num_m.group(0)), title, maxsplit=1)[0].strip()

    # Il set non è sempre nel titolo: V1 non forza il matching se manca.
    return {
        "url": url,
        "title": title,
        "name": name,
        "number": number,
        "variant": variant,
        "language": lang,
        "condition": cond,
        "available": available,
        "price": price,
        "sku": sku,
    }

def main():
    stats = Counter()
    pages_info = []
    all_links = []

    try:
        first_html, final_url, status = get(CATEGORY)
        stats["categoryHttpOk"] = 1
        total, pages = page_count(first_html)
        if total is not None:
            stats["categoryReportedProducts"] = total
        if pages is not None:
            stats["categoryReportedPages"] = pages

        pages_to_fetch = min(pages or 1, MAX_PAGES)

        for p in range(1, pages_to_fetch + 1):
            url = CATEGORY if p == 1 else CATEGORY + f"page/{p}/"
            try:
                html, final, status = get(url)
                links = product_links(html)
                stats["pagesFetched"] += 1
                stats["catalogLinks"] += len(links)
                all_links.extend(links)
                pages_info.append({"page": p, "status": status, "links": len(links), "url": final})
                time.sleep(0.05)
            except Exception as e:
                stats["pageErrors"] += 1
                pages_info.append({"page": p, "error": repr(e), "url": url})

    except Exception as e:
        report = {
            "schema": 1,
            "source": "L'Antro dei Fumetti",
            "mode": "read-only diagnostic",
            "ok": False,
            "error": repr(e),
            "rules": {
                "cardmarketTouched": False,
                "retailPricesModified": False,
            },
        }
        REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    # de-dup
    seen = set()
    links = []
    for u in all_links:
        if u not in seen:
            seen.add(u)
            links.append(u)
    stats["uniqueProductLinks"] = len(links)

    data = json.loads(RETAIL.read_text(encoding="utf-8"))
    index = build_card_index(data)

    examples = []
    usable = []
    for url in links[:MAX_PRODUCTS_TO_OPEN]:
        stats["productPagesAttempted"] += 1
        try:
            html, final, status = get(url)
            stats["productPagesFetched"] += 1
            item = parse_product(html, final)

            if item["language"] == "IT":
                stats["italian"] += 1
            if item["condition"] == "NM":
                stats["nearMint"] += 1
            if item["available"]:
                stats["available"] += 1
            if item["number"]:
                stats["numberParsed"] += 1
            if item["variant"]:
                stats["variantParsed"] += 1
            if item["price"] is not None:
                stats["priceParsed"] += 1

            is_usable = all([
                item["language"] == "IT",
                item["condition"] == "NM",
                item["available"],
                item["number"],
                item["variant"],
                item["price"] is not None,
            ])
            if is_usable:
                stats["usableBeforeSetMatching"] += 1
                usable.append(item)

            if len(examples) < 40:
                examples.append(item)

            time.sleep(0.03)

        except Exception as e:
            stats["productErrors"] += 1
            if len(examples) < 40:
                examples.append({"url": url, "error": repr(e)})

    report = {
        "schema": 1,
        "source": "L'Antro dei Fumetti",
        "mode": "read-only diagnostic",
        "ok": True,
        "rules": {
            "scope": "Pokemon category public catalog",
            "language": "ITA only",
            "condition": "Near Mint only",
            "availability": "available only",
            "variantsTrusted": ["Holo", "Reverse Holo"],
            "cardmarketTouched": False,
            "retailPricesModified": False,
            "note": "V1 measures catalog size/parseability. Exact set matching is intentionally deferred until set identity is proven.",
        },
        "stats": dict(stats),
        "pages": pages_info,
        "examples": examples,
    }

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
    print("Report:", REPORT)

if __name__ == "__main__":
    main()
