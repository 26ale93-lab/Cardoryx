#!/usr/bin/env python3
import json
import re
import urllib.request
from urllib.parse import urljoin

BASE = "https://www.cardpioneer.it/"
UA = "Mozilla/5.0 (Cardoryx CardPioneer compatibility test; GitHub Actions)"

def get(url, timeout=30):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.geturl(), r.read()

def clean(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", s or "")).strip()

def main():
    print("=== CARDPIONEER - TEST APPROFONDITO ===")
    status, final_url, body = get(BASE)
    html = body.decode("utf-8", "ignore")

    print("Homepage HTTP:", status)
    print("URL finale:", final_url)
    print("HTML bytes:", len(body))

    hrefs = re.findall(r'href=["\\\']([^"\\\']+)["\\\']', html, re.I)
    links, seen = [], set()
    for href in hrefs:
        url = urljoin(BASE, href)
        low = url.lower()
        if url not in seen and any(x in low for x in ("card", "carta", "product", "prodot", "market", "catalog")):
            seen.add(url)
            links.append(url)

    print("Link candidati trovati:", len(links))
    for url in links[:30]:
        print("LINK:", url)

    checks = {
        "ITA": bool(re.search(r"\bITA\b|Italiano", html, re.I)),
        "NM": bool(re.search(r"\bNM\b|Near Mint", html, re.I)),
        "EUR": ("€" in html or "&euro;" in html.lower()),
        "collector_number": bool(re.search(r"\b\d{1,3}\s*/\s*\d{1,3}\b", html)),
        "availability": bool(re.search(r"disponibil|available|in stock|esaurit|sold out", html, re.I)),
        "variant": bool(re.search(r"\breverse\b|\bholo\b|\bfoil\b|pok[eéè] ?ball|master ?ball", html, re.I)),
    }
    print("Segnali homepage:", json.dumps(checks, ensure_ascii=False))

    text = clean(html)
    matches = list(re.finditer(r"\b\d{1,3}\s*/\s*\d{1,3}\b", text))
    print("Occorrenze numero carta:", len(matches))
    for m in matches[:15]:
        print("ESEMPIO:", text[max(0,m.start()-160):min(len(text),m.end()+220)])

    inspected = 0
    for url in links:
        if inspected >= 8:
            break
        try:
            st, fu, data = get(url)
            page = data.decode("utf-8", "ignore")
            page_text = clean(page)
            flags = {
                "numero": bool(re.search(r"\b\d{1,3}\s*/\s*\d{1,3}\b", page_text)),
                "prezzo": ("€" in page or "&euro;" in page.lower()),
                "lingua": bool(re.search(r"\bITA\b|Italiano", page_text, re.I)),
                "condizione": bool(re.search(r"\bNM\b|Near Mint", page_text, re.I)),
                "variante": bool(re.search(r"\breverse\b|\bholo\b|\bfoil\b|pok[eéè] ?ball|master ?ball", page_text, re.I)),
                "disponibilita": bool(re.search(r"disponibil|available|in stock|esaurit|sold out", page_text, re.I)),
            }
            if flags["numero"] or flags["prezzo"]:
                inspected += 1
                print("\nPAGINA:", fu)
                print("HTTP:", st, "bytes:", len(data))
                print("Campi:", json.dumps(flags, ensure_ascii=False))
                print("Numeri esempio:", re.findall(r"\b\d{1,3}\s*/\s*\d{1,3}\b", page_text)[:5])
                print("TESTO:", page_text[:800])
        except Exception as e:
            print("ERRORE pagina:", url, repr(e))

    print("\nPagine candidate analizzate:", inspected)
    print("=== FINE TEST ===")

if __name__ == "__main__":
    main()
