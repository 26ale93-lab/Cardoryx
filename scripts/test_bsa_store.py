#!/usr/bin/env python3
import re
import time
import html
import urllib.request
import urllib.error

URL = "https://www.bsastore.it/collections/pokemon-carte-singole-ita"

def fetch(url):
    last = None
    for attempt in range(1, 3):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 (Cardoryx BSA connectivity test)",
                    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                    "Accept-Language": "it-IT,it;q=0.9,en;q=0.6",
                    "Connection": "close",
                },
            )
            with urllib.request.urlopen(req, timeout=15) as r:
                return r.status, r.read().decode("utf-8", errors="replace")
        except Exception as exc:
            last = exc
            print(f"Tentativo {attempt}/2 fallito: {exc}", flush=True)
            if attempt < 2:
                time.sleep(2)
    raise last

print("=== CARDORYX — TEST BSA STORE ===", flush=True)
start = time.time()

try:
    status, raw = fetch(URL)
    elapsed = time.time() - start

    # Conserviamo anche gli alt delle immagini, utili sui cataloghi Shopify.
    raw = re.sub(
        r'<img\b[^>]*\balt\s*=\s*["\']([^"\']+)["\'][^>]*>',
        r' \1 ',
        raw,
        flags=re.I | re.S,
    )
    text = re.sub(r"<[^>]+>", " ", raw)
    text = html.unescape(re.sub(r"\s+", " ", text))

    numbers = re.findall(r"\b[A-Z0-9]{0,4}\d{1,3}/[A-Z0-9]{0,4}\d{1,3}\b", text, re.I)
    near_mint = len(re.findall(r"\bNear Mint\b", text, re.I))
    ita = len(re.findall(r"(?:^|\s)ITA(?:\s|$)", text, re.I))
    prices = re.findall(r"€\s*[0-9]{1,5}(?:[.,][0-9]{1,2})?", text)

    print(f"HTTP: {status}", flush=True)
    print(f"Tempo: {elapsed:.1f}s", flush=True)
    print(f"Numeri carta trovati: {len(numbers)}", flush=True)
    print(f"'Near Mint' trovati: {near_mint}", flush=True)
    print(f"'ITA' trovati: {ita}", flush=True)
    print(f"Prezzi trovati: {len(prices)}", flush=True)

    if status == 200 and (numbers or near_mint or prices):
        print("RISULTATO: BSA_STORE_OK", flush=True)
    else:
        raise RuntimeError("Pagina raggiunta ma catalogo non riconosciuto")

except Exception as exc:
    elapsed = time.time() - start
    print(f"Tempo: {elapsed:.1f}s", flush=True)
    print(f"RISULTATO: BSA_STORE_FAIL — {exc}", flush=True)
    raise
