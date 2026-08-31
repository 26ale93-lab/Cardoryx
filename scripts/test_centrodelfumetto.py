#!/usr/bin/env python3
# Cardoryx - Centro del Fumetto V3
# TEST ISOLATO READ-ONLY
# Obiettivo:
# - leggere le sitemap reali
# - individuare gli URL prodotto effettivi
# - salvare campioni utili per correggere definitivamente la discovery
# NON modifica retail_prices.json
# NON tocca Cardmarket
# NON integra alcuna offerta

import json
import re
import urllib.request
from collections import Counter
from html import unescape
from pathlib import Path

BASE = "https://www.centrodelfumetto.it"
START_SITEMAPS = [
    BASE + "/sitemap_index.xml",
    BASE + "/product-sitemap.xml",
]
REPORT = Path("centro_fumetto_test_report.json")

UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/3.0)"
TIMEOUT = 20
MAX_SITEMAPS = 120
SAMPLE_LIMIT = 120

POKEMON_HINTS = [
    "pokemon",
    "pokémon",
    "carta-pokemon",
    "pokemon-world",
    "card-universe",
]

def get(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "it-IT,it;q=0.9",
            "Accept": "application/xml,text/xml,text/html,*/*",
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
    return [
        unescape(x.strip())
        for x in re.findall(r"<loc>(.*?)</loc>", xml, re.I | re.S)
    ]

def looks_like_sitemap(url):
    low = url.lower()
    return low.endswith(".xml") or "sitemap" in low

def looks_like_product(url):
    low = url.lower()
    return "/shop/" in low

def pokemon_score(url):
    low = unescape(url).lower()
    return sum(1 for hint in POKEMON_HINTS if hint in low)

def classify_path(url):
    low = url.lower()

    if "/shop/" not in low:
        return "not-shop"

    path = re.sub(r"^https?://[^/]+", "", low)

    if "pokemon" in path or "pokémon" in path:
        return "shop-pokemon-hint"

    if "card-universe" in path:
        return "shop-card-universe"

    return "shop-other"

def main():
    queue = list(START_SITEMAPS)
    seen_maps = set()
    all_urls = []
    product_urls = []

    sitemap_stats = []
    path_classes = Counter()
    host_paths = Counter()

    while queue and len(seen_maps) < MAX_SITEMAPS:
        sm = queue.pop(0)
        if sm in seen_maps:
            continue

        seen_maps.add(sm)

        try:
            body, final, status = get(sm)
            locs = sitemap_urls(body)

            sitemap_stats.append({
                "url": sm,
                "finalUrl": final,
                "status": status,
                "locs": len(locs),
            })

            for u in locs:
                if looks_like_sitemap(u):
                    if u not in seen_maps:
                        queue.append(u)
                    continue

                all_urls.append(u)

                if looks_like_product(u):
                    product_urls.append(u)
                    path_classes[classify_path(u)] += 1

                    path = re.sub(r"^https?://[^/]+", "", u.lower())
                    parts = [p for p in path.split("/") if p]
                    if parts:
                        host_paths["/" + "/".join(parts[:3])] += 1

        except Exception as exc:
            sitemap_stats.append({
                "url": sm,
                "error": repr(exc),
            })

    # De-duplica mantenendo l'ordine
    all_urls = list(dict.fromkeys(all_urls))
    product_urls = list(dict.fromkeys(product_urls))

    scored = sorted(
        product_urls,
        key=lambda u: (-pokemon_score(u), u.lower())
    )

    pokemon_candidate_urls = [
        u for u in scored if pokemon_score(u) > 0
    ]

    # Campioni:
    # 1) URL con segnali Pokemon
    # 2) URL shop generici, per capire la struttura se i segnali non sono nel path
    pokemon_samples = pokemon_candidate_urls[:SAMPLE_LIMIT]
    generic_shop_samples = product_urls[:SAMPLE_LIMIT]

    report = {
        "schema": 3,
        "source": "Centro del Fumetto",
        "mode": "read-only URL discovery diagnostic",
        "rules": {
            "cardmarketTouched": False,
            "retailPricesModified": False,
            "createsNewIdentity": False,
            "productPagesFetched": False,
            "matchingPerformed": False,
        },
        "stats": {
            "sitemapsFetched": sum(1 for x in sitemap_stats if x.get("status") == 200),
            "sitemapErrors": sum(1 for x in sitemap_stats if "error" in x),
            "allUrls": len(all_urls),
            "shopUrls": len(product_urls),
            "pokemonCandidateUrls": len(pokemon_candidate_urls),
        },
        "pathClasses": dict(path_classes),
        "topPathPrefixes": host_paths.most_common(40),
        "sitemaps": sitemap_stats,
        "pokemonUrlSamples": pokemon_samples,
        "genericShopUrlSamples": generic_shop_samples,
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
    print("\nTop path prefixes:")
    for prefix, count in report["topPathPrefixes"][:20]:
        print(f"{count:6d}  {prefix}")

    print("\nPokemon URL samples:")
    for u in pokemon_samples[:30]:
        print(u)

    print("\nReport:", REPORT)

if __name__ == "__main__":
    main()
