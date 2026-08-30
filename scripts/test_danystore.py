#!/usr/bin/env python3
import json
import re
import time
import urllib.request

BASE = "https://danystore.it"
COLLECTION = "carte-singole"
HTML_URL = f"{BASE}/collections/{COLLECTION}"
JSON_URL = f"{BASE}/collections/{COLLECTION}/products.json?limit=25&page=1"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Cardoryx DanyStore connectivity test)",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.6",
    "Connection": "close",
}

def fetch(url, accept):
    last = None
    for attempt in range(1, 3):
        try:
            req = urllib.request.Request(
                url,
                headers={**HEADERS, "Accept": accept},
            )
            with urllib.request.urlopen(req, timeout=20) as response:
                body = response.read()
                return response.status, body
        except Exception as exc:
            last = exc
            print(f"Tentativo {attempt}/2 fallito per {url}: {exc}", flush=True)
            if attempt < 2:
                time.sleep(2)
    raise last

print("=== CARDORYX — TEST DANYSTORE ===", flush=True)
started = time.time()

# 1) Test pagina pubblica
status_html, html_raw = fetch(
    HTML_URL,
    "text/html,application/xhtml+xml,*/*;q=0.8",
)
html_text = html_raw.decode("utf-8", errors="replace")

print(f"HTML HTTP: {status_html}", flush=True)
print(f"HTML bytes: {len(html_raw)}", flush=True)

if status_html != 200:
    raise RuntimeError(f"Pagina catalogo non raggiungibile: HTTP {status_html}")

# 2) Test endpoint Shopify strutturato
status_json, json_raw = fetch(
    JSON_URL,
    "application/json,text/plain,*/*",
)
print(f"JSON HTTP: {status_json}", flush=True)
print(f"JSON bytes: {len(json_raw)}", flush=True)

if status_json != 200:
    raise RuntimeError(f"Endpoint products.json non raggiungibile: HTTP {status_json}")

payload = json.loads(json_raw.decode("utf-8"))
products = payload.get("products")

if not isinstance(products, list) or not products:
    raise RuntimeError("products.json raggiunto ma senza prodotti")

titles = [str(p.get("title") or "") for p in products]

ita_nm = [
    t for t in titles
    if re.search(r"\bITA\b", t, re.I) and re.search(r"\bNM\b", t, re.I)
]

numbered = [
    t for t in titles
    if re.search(r"\b\d{1,3}-\d{1,3}\b", t)
]

reverse_labels = [
    t for t in titles
    if re.search(r"\b(?:Reverse|Pok[eè]ball|Master\s*Ball)\b", t, re.I)
]

available_variants = 0
priced_variants = 0
for product in products:
    for variant in product.get("variants") or []:
        if variant.get("available") is True:
            available_variants += 1
        try:
            if float(variant.get("price")) > 0:
                priced_variants += 1
        except Exception:
            pass

print(f"Prodotti letti: {len(products)}", flush=True)
print(f"Titoli ITA + NM nel campione: {len(ita_nm)}", flush=True)
print(f"Titoli con numero carta nel campione: {len(numbered)}", flush=True)
print(f"Titoli con etichetta variante nel campione: {len(reverse_labels)}", flush=True)
print(f"Varianti Shopify disponibili: {available_variants}", flush=True)
print(f"Varianti con prezzo valido: {priced_variants}", flush=True)

print("Esempi titoli:", flush=True)
for title in titles[:8]:
    print(f" - {title}", flush=True)

# Per il test di connettività non pretendiamo che i primi 25 prodotti
# siano tutti italiani: il catalogo generale contiene anche altre lingue.
if len(products) >= 1 and priced_variants >= 1:
    print("RISULTATO: DANYSTORE_OK", flush=True)
else:
    raise RuntimeError("Catalogo raggiunto ma dati Shopify insufficienti")

print(f"Tempo totale: {time.time() - started:.1f}s", flush=True)
