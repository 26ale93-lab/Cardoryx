#!/usr/bin/env python3
import json, re, urllib.request, urllib.error

UA = "Mozilla/5.0 (Cardoryx retail source test; +GitHub Actions)"

def get(url, timeout=25):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
    })
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.status, r.read()

def test_cardpioneer():
    print("\n=== CARDPIONEER ===")
    urls = [
        "https://www.cardpioneer.it/",
        "https://www.cardpioneer.it/index.html",
    ]
    ok = False
    for url in urls:
        try:
            status, body = get(url)
            text = body.decode("utf-8", "ignore")
            print("URL:", url)
            print("HTTP:", status, "bytes:", len(body))
            print("Contiene ITA:", "ITA" in text)
            print("Contiene NM:", bool(re.search(r"\bNM\b|Near Mint", text, re.I)))
            print("Contiene prezzo €:", "€" in text or "&euro;" in text.lower())
            print("Contiene numero carta:", bool(re.search(r"\b\d{1,3}\s*/\s*\d{1,3}\b", text)))
            ok = ok or status == 200
        except Exception as e:
            print("ERRORE", url, ":", repr(e))
    print("RISULTATO CARDPIONEER:", "RAGGIUNGIBILE" if ok else "NON RAGGIUNGIBILE")

def test_pokevertu():
    print("\n=== POKEVERTU ===")
    urls = [
        "https://pokevertu.com/collections/carte-singole-ita/products.json?limit=250&page=1",
        "https://pokevertu.com/collections/carte-singole-it/products.json?limit=250&page=1",
        "https://pokevertu.com/pages/carte-singole-it",
    ]
    ok = False
    for url in urls:
        try:
            status, body = get(url)
            print("URL:", url)
            print("HTTP:", status, "bytes:", len(body))
            if "products.json" in url:
                try:
                    data = json.loads(body)
                    products = data.get("products", [])
                    print("Prodotti:", len(products))
                    for p in products[:5]:
                        print("-", p.get("title"))
                    if products:
                        ok = True
                except Exception as e:
                    print("JSON non valido:", repr(e))
            else:
                text = body.decode("utf-8", "ignore")
                print("Pagina leggibile:", bool(text))
                ok = ok or status == 200
        except Exception as e:
            print("ERRORE", url, ":", repr(e))
    print("RISULTATO POKEVERTU:", "RAGGIUNGIBILE" if ok else "NON RAGGIUNGIBILE")

if __name__ == "__main__":
    test_cardpioneer()
    test_pokevertu()
