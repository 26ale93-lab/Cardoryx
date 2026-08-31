#!/usr/bin/env python3
# Cardoryx - Centro del Fumetto V6
# TEST ISOLATO READ-ONLY - diagnostica struttura pagina
# NON modifica retail_prices.json
# NON tocca Cardmarket
# NON crea offerte
# NON esegue matching

import json
import re
import urllib.request
from html import unescape
from pathlib import Path

BASE = "https://www.centrodelfumetto.it"
SITEMAP_INDEX = BASE + "/sitemap_index.xml"
REPORT = Path("centro_fumetto_test_report.json")

UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/6.0)"
TIMEOUT = 10
MAX_PRODUCTS = 15
POKEMON_SINGLE_PATH = "/pokemon/pokemon-single/"

KEYWORDS = [
    "Collezione", "Numero", "N°", "Rarità", "Rarita", "Espansione",
    "Condizione", "Lingua", "Foiling", "Reverse", "Holo",
    "Disponibile", "Disponibilità", "In stock", "Out of stock",
    "Aggiungi al carrello", "price", "€"
]

def get(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "it-IT,it;q=0.9",
            "Accept": "text/html,application/xhtml+xml,application/xml,text/xml,*/*",
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return (
            r.read().decode("utf-8", "replace"),
            r.geturl(),
            getattr(r, "status", None),
        )

def sitemap_urls(xml):
    return [unescape(x.strip()) for x in re.findall(r"<loc>(.*?)</loc>", xml, re.I | re.S)]

def plain(html):
    x = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I | re.S)
    x = re.sub(r"<style\b.*?</style>", " ", x, flags=re.I | re.S)
    x = re.sub(r"<[^>]+>", " ", x)
    return re.sub(r"\s+", " ", unescape(x)).strip()

def discover():
    index_xml, _, _ = get(SITEMAP_INDEX)
    product_sitemaps = [u for u in sitemap_urls(index_xml) if "product-sitemap" in u.lower()]
    direct = BASE + "/product-sitemap.xml"
    if direct not in product_sitemaps:
        product_sitemaps.insert(0, direct)

    seen = set()
    urls = []

    for sm in product_sitemaps:
        try:
            body, _, _ = get(sm)
            for u in sitemap_urls(body):
                low = u.lower()
                if (
                    POKEMON_SINGLE_PATH in low
                    and "near-mint" in low
                    and "italiano" in low
                    and u not in seen
                ):
                    seen.add(u)
                    urls.append(u)
        except Exception:
            pass

    return sorted(urls)

def context_snippets(text, keyword, radius=220, limit=3):
    out = []
    low = text.lower()
    key = keyword.lower()
    start = 0
    while len(out) < limit:
        i = low.find(key, start)
        if i < 0:
            break
        a = max(0, i - radius)
        b = min(len(text), i + len(keyword) + radius)
        out.append(text[a:b])
        start = i + len(keyword)
    return out

def html_snippets(html, keyword, radius=350, limit=3):
    out = []
    low = html.lower()
    key = keyword.lower()
    start = 0
    while len(out) < limit:
        i = low.find(key, start)
        if i < 0:
            break
        a = max(0, i - radius)
        b = min(len(html), i + len(keyword) + radius)
        snippet = re.sub(r"\s+", " ", html[a:b])
        out.append(snippet)
        start = i + len(keyword)
    return out

def extract_structured_candidates(html):
    candidates = []
    patterns = [
        r'<meta[^>]+(?:property|name)=["\'][^"\']*(?:price|availability)[^"\']*["\'][^>]*>',
        r'<[^>]+itemprop=["\'](?:price|availability|sku|mpn|productID)["\'][^>]*>',
        r'"(?:price|availability|sku|mpn|productID|product_id)"\s*:\s*[^,}\n]+',
        r'(?:N°|Numero|Collezione|Espansione|Rarità|Rarita|Condizione|Lingua)[^<\n]{0,180}',
    ]
    for pat in patterns:
        for m in re.finditer(pat, html, re.I | re.S):
            s = re.sub(r"\s+", " ", m.group(0)).strip()
            if s not in candidates:
                candidates.append(s)
            if len(candidates) >= 30:
                return candidates
    return candidates

def main():
    urls = discover()
    samples = []
    stats = {
        "discoveredNearMintItaliano": len(urls),
        "attempted": 0,
        "fetched": 0,
        "errors": 0,
    }

    for url in urls[:MAX_PRODUCTS]:
        stats["attempted"] += 1
        try:
            html, final, status = get(url)
            stats["fetched"] += 1
            text = plain(html)

            h1 = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
            title = plain(h1.group(1)) if h1 else ""

            keyword_text = {}
            keyword_html = {}
            for kw in KEYWORDS:
                ts = context_snippets(text, kw)
                hs = html_snippets(html, kw)
                if ts:
                    keyword_text[kw] = ts
                if hs:
                    keyword_html[kw] = hs

            samples.append({
                "url": url,
                "finalUrl": final,
                "status": status,
                "title": title,
                "textStart": text[:2500],
                "keywordTextSnippets": keyword_text,
                "keywordHtmlSnippets": keyword_html,
                "structuredCandidates": extract_structured_candidates(html),
            })
        except Exception as exc:
            stats["errors"] += 1
            samples.append({"url": url, "error": repr(exc)})

    report = {
        "schema": 6,
        "source": "Centro del Fumetto",
        "mode": "read-only page structure diagnostic",
        "rules": {
            "catalogPath": POKEMON_SINGLE_PATH,
            "urlPrefilter": "near-mint + italiano",
            "productPagesFetched": True,
            "matchingPerformed": False,
            "createsNewIdentity": False,
            "cardmarketTouched": False,
            "retailPricesModified": False,
        },
        "limits": {"maxProductsFetched": MAX_PRODUCTS},
        "stats": stats,
        "samples": samples,
    }

    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(stats, ensure_ascii=False, indent=2))
    print("Report:", REPORT)

if __name__ == "__main__":
    main()
