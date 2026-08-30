#!/usr/bin/env python3
import re, json, urllib.request
from urllib.parse import urljoin

BASE = "https://www.cardpioneer.it/"
TARGET = urljoin(BASE, "acquista.html")
UA = "Mozilla/5.0 (Cardoryx CardPioneer endpoint test; GitHub Actions)"

def get(url, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/javascript,application/json,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.geturl(), r.headers.get("Content-Type",""), r.read()

def uniq(seq):
    out=[]; seen=set()
    for x in seq:
        if x not in seen:
            seen.add(x); out.append(x)
    return out

def main():
    print("=== CARDPIONEER - RICERCA ENDPOINT CATALOGO ===")
    status, final_url, ctype, body = get(TARGET)
    html = body.decode("utf-8", "ignore")
    print("Pagina:", final_url)
    print("HTTP:", status, "Content-Type:", ctype, "bytes:", len(body))

    # Script JS reali caricati dalla pagina
    srcs = re.findall(r'<script[^>]+src=["\']([^"\']+)["\']', html, re.I)
    scripts = uniq([urljoin(TARGET, s) for s in srcs])
    print("Script esterni:", len(scripts))
    for s in scripts:
        print("SCRIPT:", s)

    blobs = [("HTML acquista", html)]
    for s in scripts[:20]:
        try:
            st, fu, ct, data = get(s)
            txt = data.decode("utf-8", "ignore")
            print("SCRIPT HTTP:", st, "bytes:", len(data), fu)
            blobs.append((fu, txt))
        except Exception as e:
            print("SCRIPT ERRORE:", s, repr(e))

    # Cerca URL/API e chiamate fetch/XHR nei sorgenti.
    candidates=[]
    patterns = [
        r'fetch\s*\(\s*["\']([^"\']+)["\']',
        r'axios\.(?:get|post)\s*\(\s*["\']([^"\']+)["\']',
        r'["\']([^"\']*(?:api|catalog|market|card|carte|product|prodotti)[^"\']*\.(?:php|json)[^"\']*)["\']',
        r'["\']([^"\']*\.php(?:\?[^"\']*)?)["\']',
        r'["\']([^"\']*\.json(?:\?[^"\']*)?)["\']',
    ]
    for label, txt in blobs:
        for pat in patterns:
            for m in re.findall(pat, txt, re.I):
                if isinstance(m, tuple): m = m[0]
                if m and not m.startswith(("data:", "#")):
                    candidates.append(urljoin(TARGET, m))

    candidates = uniq(candidates)
    print("\nEndpoint/URL candidati:", len(candidates))
    for u in candidates[:80]:
        print("CANDIDATO:", u)

    # Mostra contesto delle parole utili nei JS.
    keywords = ["fetch(", "XMLHttpRequest", "api", "market", "cards", "carte", "price",
                "prezzo", "condition", "condizione", "language", "lingua",
                "variant", "reverse", "holo", "availability", "disponib"]
    for label, txt in blobs:
        hits=[]
        low=txt.lower()
        for kw in keywords:
            p=low.find(kw.lower())
            if p >= 0:
                hits.append((p, kw))
        if hits:
            print("\n--- CONTESTO:", label, "---")
            for p, kw in sorted(hits)[:20]:
                snippet=re.sub(r"\s+", " ", txt[max(0,p-180):p+420])
                print("KEY", kw, "=>", snippet[:650])

    # Prova solo endpoint same-origin non distruttivi, senza parametri sospetti.
    tested=0
    for u in candidates:
        if tested >= 20:
            break
        if not u.startswith(BASE):
            continue
        if any(x in u.lower() for x in ("login", "logout", "delete", "remove", "checkout", "ordine", "order")):
            continue
        try:
            st, fu, ct, data = get(u)
            tested += 1
            txt=data.decode("utf-8","ignore")
            print("\nENDPOINT TEST:", fu)
            print("HTTP:", st, "Content-Type:", ct, "bytes:", len(data))
            print("INIZIO:", re.sub(r"\s+"," ",txt[:1200]))
            try:
                obj=json.loads(txt)
                if isinstance(obj, dict):
                    print("JSON keys:", list(obj.keys())[:40])
                elif isinstance(obj, list):
                    print("JSON list length:", len(obj))
                    if obj and isinstance(obj[0], dict):
                        print("First item keys:", list(obj[0].keys())[:40])
            except Exception:
                pass
        except Exception as e:
            print("ENDPOINT ERRORE:", u, repr(e))

    print("\nEndpoint testati:", tested)
    print("=== FINE TEST ===")

if __name__ == "__main__":
    main()
