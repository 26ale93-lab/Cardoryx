#!/usr/bin/env python3
import json
import re
import urllib.error
import urllib.request

SITE = "https://www.cardpioneer.it"
API_JS = SITE + "/api.js"
UA = "Mozilla/5.0 (compatible; CardoryxRetailTest/2.0)"

def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json,text/plain,*/*",
        "Referer": SITE + "/acquista.html",
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()

def txt(data):
    return data.decode("utf-8", errors="replace")

def compact(s, limit=3000):
    return re.sub(r"\s+", " ", s)[:limit]

def show_json(data):
    s = txt(data)
    try:
        obj = json.loads(s)
    except Exception:
        print("NON JSON:", compact(s, 1800))
        return
    if isinstance(obj, dict):
        print("JSON dict - CHIAVI:", list(obj.keys())[:100])
        for k, v in obj.items():
            if isinstance(v, list):
                print("LISTA:", k, "ELEMENTI:", len(v))
                if v and isinstance(v[0], dict):
                    print("PRIMO ELEMENTO CHIAVI:", list(v[0].keys())[:120])
                    print("PRIMO ELEMENTO:", json.dumps(v[0], ensure_ascii=False)[:4000])
                return
        print("CONTENUTO:", json.dumps(obj, ensure_ascii=False)[:4000])
    elif isinstance(obj, list):
        print("JSON list - ELEMENTI:", len(obj))
        if obj and isinstance(obj[0], dict):
            print("PRIMO ELEMENTO CHIAVI:", list(obj[0].keys())[:120])
            print("PRIMO ELEMENTO:", json.dumps(obj[0], ensure_ascii=False)[:4000])

print("=== CARDPIONEER - TEST API CATALOGO V3 ===")

status, ctype, raw = get(API_JS)
js = txt(raw)
print("api.js:", status, ctype, "bytes:", len(raw))

print("\n--- RIGHE API IMPORTANTI ---")
for line in js.splitlines():
    low = line.lower()
    if ("getprodotti" in low or "prodotti.php" in low or
        "carte/cerca.php" in low or "carte/espansioni.php" in low or
        "_fetch" in low):
        safe = re.sub(
            r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}",
            "[JWT_REDACTED]", line
        )
        print(compact(safe, 2500))

tests = [
    "/prodotti.php?",
    "/api/prodotti.php?",
    "/prodotti.php?disponibili=1",
    "/api/prodotti.php?disponibili=1",
    "/prodotti.php?categoria=carte&disponibili=1",
    "/api/prodotti.php?categoria=carte&disponibili=1",
    "/carte/espansioni.php",
    "/api/carte/espansioni.php",
    "/carte/cerca.php?",
    "/api/carte/cerca.php?",
]

for path in tests:
    url = SITE + path
    print("\n=== GET", url, "===")
    try:
        st, ct, data = get(url)
        print("HTTP:", st, "Content-Type:", ct, "bytes:", len(data))
        show_json(data)
    except urllib.error.HTTPError as e:
        body = e.read()
        print("HTTP ERROR:", e.code, e.reason)
        if body:
            print("BODY:", compact(txt(body), 1200))
    except Exception as e:
        print("ERRORE:", repr(e))

print("\n=== FINE TEST CARDPIONEER V3 ===")
print("SOLO GET - NESSUNA MODIFICA A CARDMARKET O RETAIL")
