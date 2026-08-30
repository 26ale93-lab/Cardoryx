#!/usr/bin/env python3
import json
import re
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict

SITE = "https://www.cardpioneer.it"
URL = SITE + "/api/prodotti.php?categoria=carte&disponibili=1"
UA = "Mozilla/5.0 (compatible; CardoryxRetailTest/3.0)"

def get_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json,text/plain,*/*",
            "Referer": SITE + "/acquista.html",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        return r.status, r.headers.get("Content-Type", ""), json.loads(
            raw.decode("utf-8", errors="replace")
        )

def norm(s):
    s = str(s or "")
    s = unicodedata.normalize("NFKD", s)
    s = "".join(ch for ch in s if not unicodedata.combining(ch))
    s = s.lower()
    s = re.sub(r"\s+", " ", s).strip()
    return s

def first_value(d, *keys):
    for key in keys:
        if key in d and d[key] not in (None, ""):
            return d[key]
    return None

def extract_products(payload):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in ("prodotti", "products", "items", "data", "results"):
            v = payload.get(key)
            if isinstance(v, list):
                return v
    return []

def classify_variant(text):
    n = norm(text)

    # Ordine dal più specifico al più generico.
    if re.search(r"\b(master\s*ball|masterball)\b", n):
        return "Master Ball"
    if re.search(r"\b(poke\s*ball|pokeball)\b", n) and "reverse" in n:
        return "Poké Ball Reverse"
    if ("energia" in n or "energy" in n) and "reverse" in n:
        return "Energy Reverse"
    if "reverse" in n and "stamp" in n:
        return "Reverse Stamped"
    if "reverse" in n:
        return "Reverse"
    if "holo" in n or "olograf" in n:
        return "Holo"
    return "No explicit variant"

def safe_card_view(p):
    return {
        "sku": first_value(p, "sku"),
        "set_name": first_value(p, "set_name", "set", "espansione"),
        "lingua": first_value(p, "lingua", "language"),
        "condizione": first_value(p, "condizione", "condition"),
        "prezzo": first_value(p, "prezzo", "price"),
        "disponibile": first_value(p, "disponibile", "available"),
        "nome": first_value(p, "nome", "name"),
        "nome_completo": first_value(p, "nome_completo", "full_name", "title"),
    }

print("=== CARDPIONEER - TEST VARIANTI CATALOGO V4 ===")

try:
    status, ctype, payload = get_json(URL)
except urllib.error.HTTPError as e:
    print("HTTP ERROR:", e.code, e.reason)
    raise SystemExit(1)
except Exception as e:
    print("ERRORE:", repr(e))
    raise SystemExit(1)

products = extract_products(payload)

print("HTTP:", status)
print("Content-Type:", ctype)
print("Prodotti/carte disponibili:", len(products))

if not products:
    print("ERRORE: nessuna carta trovata nel catalogo.")
    raise SystemExit(1)

# Campi realmente presenti.
field_counter = Counter()
for p in products:
    if isinstance(p, dict):
        field_counter.update(p.keys())

print("\n--- CAMPI PIU' FREQUENTI ---")
for key, count in field_counter.most_common(40):
    print(f"{key}: {count}/{len(products)}")

# Filtri minimi utili a Cardoryx.
ita_nm = []
for p in products:
    if not isinstance(p, dict):
        continue
    lingua = norm(first_value(p, "lingua", "language"))
    cond = norm(first_value(p, "condizione", "condition"))
    if lingua in ("ita", "it", "italiano", "italian") and (
        cond == "nm" or "near mint" in cond
    ):
        ita_nm.append(p)

print("\nCarte ITA + NM:", len(ita_nm))

variant_counts = Counter()
examples = defaultdict(list)
keyword_counts = Counter()

keywords = [
    "reverse",
    "holo",
    "pokeball",
    "poke ball",
    "pokéball",
    "poké ball",
    "master ball",
    "masterball",
    "stamp",
    "stamped",
    "energia",
    "energy",
]

for p in ita_nm:
    full = str(first_value(p, "nome_completo", "full_name", "title") or "")
    name = str(first_value(p, "nome", "name") or "")
    combined = (full + " " + name).strip()

    variant = classify_variant(combined)
    variant_counts[variant] += 1

    if len(examples[variant]) < 12:
        examples[variant].append(safe_card_view(p))

    n = norm(combined)
    for kw in keywords:
        if norm(kw) in n:
            keyword_counts[kw] += 1

print("\n--- CONTEGGIO DICITURE VARIANTE ---")
for variant, count in variant_counts.most_common():
    print(f"{variant}: {count}")

print("\n--- CONTEGGIO PAROLE CHIAVE ---")
for kw, count in keyword_counts.most_common():
    print(f"{kw}: {count}")

print("\n--- ESEMPI PER TIPO ---")
order = [
    "Master Ball",
    "Poké Ball Reverse",
    "Energy Reverse",
    "Reverse Stamped",
    "Reverse",
    "Holo",
    "No explicit variant",
]

for variant in order:
    print(f"\n### {variant} ({variant_counts.get(variant, 0)})")
    for item in examples.get(variant, []):
        print(json.dumps(item, ensure_ascii=False))

# Verifica presenza di numero collezionista nei campi testuali.
number_full = re.compile(r"\b(\d{1,3})\s*/\s*(\d{1,3})\b")
number_dash = re.compile(r"^\s*(\d{1,3})-(\d{1,3})\b")

with_number = 0
without_number_examples = []

for p in ita_nm:
    sku = str(first_value(p, "sku") or "")
    full = str(first_value(p, "nome_completo", "full_name", "title") or "")
    text = f"{sku} {full}"

    if number_full.search(text) or number_dash.search(text):
        with_number += 1
    elif len(without_number_examples) < 20:
        without_number_examples.append(safe_card_view(p))

print("\n--- NUMERO COLLEZIONISTA ---")
print("ITA+NM con numero riconoscibile:", with_number)
print("ITA+NM senza numero riconoscibile:", len(ita_nm) - with_number)

if without_number_examples:
    print("\nESEMPI SENZA NUMERO:")
    for item in without_number_examples:
        print(json.dumps(item, ensure_ascii=False))

# Verifica set_name.
with_set = sum(
    1 for p in ita_nm
    if str(first_value(p, "set_name", "set", "espansione") or "").strip()
)

print("\n--- SET ---")
print("ITA+NM con set_name:", with_set)
print("ITA+NM senza set_name:", len(ita_nm) - with_set)

print("\n=== ESITO TECNICO ===")
print("Il test NON integra CardPioneer.")
print("Serve solo a verificare se le varianti sono espresse in modo abbastanza preciso.")
print("Solo GET. Nessuna modifica a Cardmarket o al builder retail.")
