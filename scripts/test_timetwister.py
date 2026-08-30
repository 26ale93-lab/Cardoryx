#!/usr/bin/env python3
import json
import re
import time
import urllib.request
from collections import Counter

BASE = "https://timetwistergames.it"
COLLECTION_URL = BASE + "/collections/pok-mon-single/products.json?limit=250&page={page}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Cardoryx TimeTwister full catalog test)",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.6",
    "Connection": "close",
}

def fetch_json(url):
    last = None
    for attempt in range(1, 4):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read()
                return response.status, response.headers.get("content-type", ""), json.loads(raw.decode("utf-8"))
        except Exception as exc:
            last = exc
            print(f"Tentativo {attempt}/3 fallito: {exc}", flush=True)
            if attempt < 3:
                time.sleep(2 * attempt)
    raise last

def norm(s):
    return re.sub(r"\s+", " ", str(s or "").strip())

def has_card_code(title):
    # Supporta codici classici e gallerie tipo BRS-TG19, CRZ-GGxx ecc.
    return bool(re.search(r"\b[A-Z0-9]{2,8}-(?:\d{1,3}|TG\d{1,3}|GG\d{1,3}|SV\d{1,3})\b", title, re.I))

def collector_number_from_title(title):
    m = re.search(r"\[(?:[A-Z0-9]{2,8})-((?:TG|GG|SV)?\d{1,3})\]", title, re.I)
    if m:
        return m.group(1).upper()
    m = re.search(r"\b[A-Z0-9]{2,8}-((?:TG|GG|SV)?\d{1,3})\b", title, re.I)
    if m:
        return m.group(1).upper()
    return None

print("=== TIMETWISTER GAMES - TEST CATALOGO COMPLETO V2 ===", flush=True)

all_products = []
page = 1
errors = []

while page <= 100:
    url = COLLECTION_URL.format(page=page)
    try:
        status, content_type, data = fetch_json(url)
        products = data.get("products") if isinstance(data, dict) else None
        if not isinstance(products, list):
            raise RuntimeError("Risposta JSON senza lista products")

        print(f"Pagina {page}: HTTP {status} - prodotti {len(products)}", flush=True)

        if not products:
            break

        all_products.extend(products)

        if len(products) < 250:
            break

        page += 1
        time.sleep(0.4)

    except Exception as exc:
        errors.append(f"Pagina {page}: {exc}")
        print(f"ERRORE pagina {page}: {exc}", flush=True)
        break

stats = {
    "pages": page,
    "products": len(all_products),
    "pokemonSingle": 0,
    "withRecognizableCode": 0,
    "withoutRecognizableCode": 0,
    "variants": 0,
    "availableVariants": 0,
    "italianVariants": 0,
    "nearMintVariants": 0,
    "italianNearMintAvailable": 0,
    "pricedVariants": 0,
    "potentiallyUsableVariants": 0,
}

edition_counts = Counter()
language_counts = Counter()
condition_counts = Counter()
product_type_counts = Counter()
unrecognized_titles = []
usable_examples = []
edition_examples = {}

for product in all_products:
    title = norm(product.get("title"))
    product_type = norm(product.get("product_type"))
    options = product.get("options") or []
    variants = product.get("variants") or []

    product_type_counts[product_type or "(vuoto)"] += 1

    if "pokemon single" in product_type.lower() or "pokémon single" in product_type.lower():
        stats["pokemonSingle"] += 1

    code_ok = has_card_code(title)
    if code_ok:
        stats["withRecognizableCode"] += 1
    else:
        stats["withoutRecognizableCode"] += 1
        if len(unrecognized_titles) < 40:
            unrecognized_titles.append(title)

    option_names = [norm(o.get("name")) for o in options if isinstance(o, dict)]
    option_pos = {name.lower(): i + 1 for i, name in enumerate(option_names)}

    for variant in variants:
        stats["variants"] += 1

        option_values = {
            1: norm(variant.get("option1")),
            2: norm(variant.get("option2")),
            3: norm(variant.get("option3")),
        }

        language = ""
        condition = ""
        edition = ""

        for key, pos in option_pos.items():
            value = option_values.get(pos, "")
            if key == "language":
                language = value
            elif key == "condition":
                condition = value
            elif key == "edition":
                edition = value

        # fallback diagnostico se i nomi opzione cambiano
        if not language:
            joined = list(option_values.values())
            language = next((v for v in joined if v.lower() in {"italian", "italiano", "ita", "english", "inglese", "eng", "japanese", "jap"}), "")
        if not condition:
            joined = list(option_values.values())
            condition = next((v for v in joined if "near mint" in v.lower() or v.lower() == "nm"), "")
        if not edition:
            joined = list(option_values.values())
            edition = next((v for v in joined if any(k in v.lower() for k in ("normal", "reverse", "holo", "foil"))), "")

        if language:
            language_counts[language] += 1
        if condition:
            condition_counts[condition] += 1
        if edition:
            edition_counts[edition] += 1
            edition_examples.setdefault(edition, [])
            if len(edition_examples[edition]) < 5:
                edition_examples[edition].append({
                    "title": title,
                    "variantTitle": variant.get("title"),
                    "available": variant.get("available"),
                    "price": variant.get("price"),
                    "sku": variant.get("sku"),
                })

        available = variant.get("available") is True
        if available:
            stats["availableVariants"] += 1

        is_it = language.lower() in {"italian", "italiano", "ita"}
        if is_it:
            stats["italianVariants"] += 1

        is_nm = ("near mint" in condition.lower()) or condition.lower() == "nm"
        if is_nm:
            stats["nearMintVariants"] += 1

        price_ok = False
        try:
            price_ok = float(variant.get("price")) > 0
        except Exception:
            price_ok = False
        if price_ok:
            stats["pricedVariants"] += 1

        if is_it and is_nm and available:
            stats["italianNearMintAvailable"] += 1

        # Per produzione vogliamo solo edizioni esplicite e sicure
        edition_norm = edition.lower().replace("_", "-").strip()
        edition_supported = edition_norm in {
            "normal",
            "reverse-holo",
            "reverse holo",
            "holo",
        }

        if code_ok and is_it and is_nm and available and price_ok and edition_supported:
            stats["potentiallyUsableVariants"] += 1
            if len(usable_examples) < 30:
                usable_examples.append({
                    "title": title,
                    "collector": collector_number_from_title(title),
                    "language": language,
                    "condition": condition,
                    "edition": edition,
                    "price": variant.get("price"),
                    "available": variant.get("available"),
                    "sku": variant.get("sku"),
                    "handle": product.get("handle"),
                })

print("\n=== RISULTATI COMPLESSIVI ===", flush=True)
for k, v in stats.items():
    print(f"{k}: {v}", flush=True)

print("\n=== PRODUCT TYPE ===", flush=True)
for k, v in product_type_counts.most_common():
    print(f"{k}: {v}", flush=True)

print("\n=== LINGUE ===", flush=True)
for k, v in language_counts.most_common():
    print(f"{k}: {v}", flush=True)

print("\n=== CONDIZIONI ===", flush=True)
for k, v in condition_counts.most_common():
    print(f"{k}: {v}", flush=True)

print("\n=== EDITION / VARIANTI TROVATE ===", flush=True)
for k, v in edition_counts.most_common():
    print(f"{k}: {v}", flush=True)

print("\n=== ESEMPI PER OGNI EDITION ===", flush=True)
for edition, examples in sorted(edition_examples.items()):
    print(f"\n[{edition}]", flush=True)
    for ex in examples:
        print(json.dumps(ex, ensure_ascii=False), flush=True)

print("\n=== TITOLI SENZA CODICE RICONOSCIBILE ===", flush=True)
if unrecognized_titles:
    for t in unrecognized_titles:
        print(t, flush=True)
else:
    print("Nessuno", flush=True)

print("\n=== ESEMPI POTENZIALMENTE UTILIZZABILI DA CARDORYX ===", flush=True)
for ex in usable_examples:
    print(json.dumps(ex, ensure_ascii=False), flush=True)

print("\n=== ERRORI ===", flush=True)
if errors:
    for e in errors:
        print(e, flush=True)
else:
    print("0", flush=True)

print("\n=== CRITERIO PRODUZIONE PROPOSTO ===", flush=True)
print("Accetta solo se:", flush=True)
print("- codice/numero carta riconoscibile", flush=True)
print("- Language = Italian/Italiano/ITA", flush=True)
print("- Condition = Near Mint/NM", flush=True)
print("- available = true", flush=True)
print("- prezzo > 0", flush=True)
print("- Edition esplicita tra Normal / Reverse-Holo / Holo", flush=True)
print("- matching finale esatto su set + numero + nome + variante", flush=True)

print("\nSOLO GET - NESSUNA MODIFICA A CARDMARKET O RETAIL", flush=True)
print("=== FINE TEST TIMETWISTER V2 ===", flush=True)
