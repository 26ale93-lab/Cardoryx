#!/usr/bin/env python3
import json
import re
import time
import urllib.request

BASE = "https://timetwistergames.it"

CANDIDATE_URLS = [
    BASE + "/collections/pok-mon-single/products.json?limit=50&page=1",
    BASE + "/collections/pokemon/products.json?limit=50&page=1",
]

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Cardoryx TimeTwister connectivity test)",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.6",
    "Connection": "close",
}

def fetch_json(url):
    last = None
    for attempt in range(1, 3):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=25) as response:
                raw = response.read()
                return response.status, response.headers.get("content-type", ""), raw
        except Exception as exc:
            last = exc
            print(f"Tentativo {attempt}/2 fallito: {exc}", flush=True)
            if attempt < 2:
                time.sleep(2)
    raise last

print("=== TIMETWISTER GAMES - TEST CATALOGO V1 ===", flush=True)

selected = None
payload = None

for url in CANDIDATE_URLS:
    print(f"\nTEST URL: {url}", flush=True)
    try:
        status, content_type, raw = fetch_json(url)
        print(f"HTTP: {status}", flush=True)
        print(f"Content-Type: {content_type}", flush=True)
        print(f"Bytes: {len(raw)}", flush=True)

        data = json.loads(raw.decode("utf-8"))
        products = data.get("products") if isinstance(data, dict) else None
        count = len(products) if isinstance(products, list) else 0
        print(f"Prodotti letti: {count}", flush=True)

        if count and selected is None:
            selected = url
            payload = data
    except Exception as exc:
        print(f"ERRORE: {exc}", flush=True)

if not payload:
    raise RuntimeError("Nessun endpoint Shopify products.json utilizzabile")

products = payload.get("products") or []
print(f"\nENDPOINT SELEZIONATO: {selected}", flush=True)

stats = {
    "products": len(products),
    "pokemon_single": 0,
    "with_code": 0,
    "variants": 0,
    "available_variants": 0,
    "italian_variants": 0,
    "near_mint_variants": 0,
    "reverse_variants": 0,
    "normal_variants": 0,
    "priced_variants": 0,
}

examples = []

for product in products:
    title = str(product.get("title") or "")
    product_type = str(product.get("product_type") or "")
    options = product.get("options") or []
    variants = product.get("variants") or []

    if "pokemon single" in product_type.lower() or "pokémon single" in product_type.lower():
        stats["pokemon_single"] += 1

    if re.search(r"\[[A-Za-z0-9]+-(?:\d+|TG\d+|GG\d+|SV\d+)\]", title, re.I):
        stats["with_code"] += 1

    option_names = [str(o.get("name") or "") for o in options if isinstance(o, dict)]

    for variant in variants:
        stats["variants"] += 1
        if variant.get("available") is True:
            stats["available_variants"] += 1

        values = [
            str(variant.get("option1") or ""),
            str(variant.get("option2") or ""),
            str(variant.get("option3") or ""),
        ]
        joined = " | ".join(values).lower()

        if "italian" in joined or "italiano" in joined or re.search(r"\bita\b", joined):
            stats["italian_variants"] += 1

        if "near mint" in joined or re.search(r"\bnm\b", joined):
            stats["near_mint_variants"] += 1

        if "reverse" in joined:
            stats["reverse_variants"] += 1

        if re.search(r"\bnormal\b", joined):
            stats["normal_variants"] += 1

        try:
            if float(variant.get("price")) > 0:
                stats["priced_variants"] += 1
        except Exception:
            pass

    if len(examples) < 10:
        examples.append({
            "title": title,
            "product_type": product_type,
            "handle": product.get("handle"),
            "options": option_names,
            "variants": [
                {
                    "title": v.get("title"),
                    "option1": v.get("option1"),
                    "option2": v.get("option2"),
                    "option3": v.get("option3"),
                    "available": v.get("available"),
                    "price": v.get("price"),
                    "sku": v.get("sku"),
                }
                for v in variants[:6]
            ],
        })

print("\n=== STATISTICHE CAMPIONE ===", flush=True)
for key, value in stats.items():
    print(f"{key}: {value}", flush=True)

print("\n=== ESEMPI STRUTTURA PRODOTTI ===", flush=True)
for i, item in enumerate(examples, 1):
    print(f"\n--- ESEMPIO {i} ---", flush=True)
    print(json.dumps(item, ensure_ascii=False, indent=2), flush=True)

print("\n=== CHECK CAMPI NECESSARI CARDORYX ===", flush=True)
print("Cerchiamo:", flush=True)
print("- nome carta + set + codice/numero nel titolo", flush=True)
print("- Language = Italian/ITA", flush=True)
print("- Condition = Near Mint/NM", flush=True)
print("- Edition = Normal / Reverse-Holo / altre varianti esplicite", flush=True)
print("- available = true", flush=True)
print("- prezzo > 0", flush=True)

print("\nSOLO GET - NESSUNA MODIFICA A CARDMARKET O RETAIL", flush=True)
print("=== FINE TEST TIMETWISTER V1 ===", flush=True)
