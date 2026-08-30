#!/usr/bin/env python3
import re
import urllib.request
import urllib.parse
from html import unescape

BASE = "https://www.cardpioneer.it"
START = BASE + "/acquista.html"
UA = "Mozilla/5.0 (compatible; CardoryxRetailTest/1.0)"

def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Accept": "*/*",
        "Referer": START,
    })
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.status, r.headers.get("Content-Type", ""), r.read()

def txt(data):
    return data.decode("utf-8", errors="replace")

def abs_url(src, base=START):
    return urllib.parse.urljoin(base, unescape(src))

print("=== CARDPIONEER - CERCA SORGENTE CATALOGO ===")

status, ctype, raw = get(START)
html = txt(raw)
print("Pagina:", START)
print("HTTP:", status, "Content-Type:", ctype, "bytes:", len(raw))

scripts = []
for src in re.findall(r"<script[^>]+src=[\"']([^\"']+)[\"']", html, re.I):
    u = abs_url(src)
    if "cardpioneer.it" in u and u not in scripts:
        scripts.append(u)

print("Script CardPioneer trovati:", len(scripts))

keywords = (
    "supabase", "fetch(", ".from(", "/api/", "prodot", "carte",
    "catalog", "prezzo", "lingua", "condizion", "disponib",
    "numero", "espansion", "wishlist"
)

def inspect(label, body):
    print("\n---", label, "---")
    low = body.lower()

    for kw in keywords:
        n = low.count(kw.lower())
        if n:
            print("KEYWORD:", kw, "occorrenze:", n)

    candidates = set()
    for pat in [
        r"https?://[^\s\"'`<>\\]+",
        r"fetch\s*\(\s*[\"'`]([^\"'`]+)",
        r"\.from\s*\(\s*[\"'`]([^\"'`]+)",
        r"/api/[A-Za-z0-9_./?=&${}-]+",
    ]:
        for m in re.finditer(pat, body, re.I):
            val = m.group(1) if m.lastindex else m.group(0)
            val = unescape(val).strip()
            if 2 < len(val) < 500:
                candidates.add(val)

    for v in sorted(candidates):
        vl = v.lower()
        if any(k in vl for k in (
            "supabase", "/api/", "product", "prodot", "cart", "catalog",
            "wishlist", "collection", "offert", "acquist"
        )):
            print("CANDIDATO:", v)

    for needle in ("fetch(", ".from(", "createClient", "supabaseUrl",
                   "supabaseKey", "anon", "select(", "rpc("):
        pos = 0
        shown = 0
        while shown < 8:
            i = body.find(needle, pos)
            if i < 0:
                break
            a = max(0, i - 220)
            b = min(len(body), i + 520)
            snippet = re.sub(r"\s+", " ", body[a:b])
            snippet = re.sub(
                r"eyJ[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}\.[A-Za-z0-9_-]{20,}",
                "[JWT_REDACTED]",
                snippet
            )
            print("CONTESTO", needle + ":", snippet)
            pos = i + len(needle)
            shown += 1

inspect("HTML acquista.html", html)

for url in scripts:
    try:
        st, ct, data = get(url)
        body = txt(data)
        print("\nSCRIPT:", url)
        print("HTTP:", st, "bytes:", len(data))
        inspect(url, body)
    except Exception as e:
        print("\nSCRIPT ERROR:", url, repr(e))

print("\n=== FINE TEST ===")
print("Obiettivo: individuare la chiamata reale al catalogo, senza modificare Cardmarket o l'indice retail.")
