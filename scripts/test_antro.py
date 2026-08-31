#!/usr/bin/env python3
# Cardoryx - test L'Antro dei Fumetti V3
# READ-ONLY: non modifica retail_prices.json e non tocca Cardmarket.
#
# V3:
# - filtra solo URL reali del dominio lantrodeifumetti.it
# - evita link Pinterest/social
# - campiona un numero ridotto di prodotti tecnicamente interessanti
# - ispeziona dati strutturati (JSON-LD, meta, tassonomie, classi/body)
# - cerca segnali di set senza accettare loose match come identità valida

import json
import re
import time
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

BASE = "https://lantrodeifumetti.it"
CATEGORY = BASE + "/categoria-prodotto/trading-card/tgc-pokemon/"
RETAIL = Path("data/retail_prices.json")
REPORT = Path("antro_test_report.json")

UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/3.0)"
TIMEOUT = 15
MAX_CATEGORY_PAGES = 9
MAX_PRODUCT_PAGES = 80

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = unescape(s).lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def get(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "it-IT,it;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace"), r.geturl(), getattr(r, "status", None)

def plain(html):
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()

def collector_parts(number):
    m = re.match(
        r"^\s*([A-Za-z]*)(\d+)\s*[-/]\s*([A-Za-z]*)(\d+)\s*$",
        str(number or ""),
    )
    if not m:
        return None
    return (
        m.group(1).upper(),
        int(m.group(2)),
        m.group(3).upper(),
        int(m.group(4)),
    )

def build_indexes(data):
    by_loose = defaultdict(list)
    known_sets = {}

    for card in data.get("cards", {}).values():
        cp = collector_parts(card.get("number"))
        if not cp:
            continue
        by_loose[
            (
                cp,
                norm(card.get("name")),
                card.get("variant"),
            )
        ].append(card)
        s = card.get("set")
        if s:
            known_sets[norm(s)] = s

    return by_loose, known_sets

def product_links(html):
    found = re.findall(r'href=["\']([^"\']+)["\']', html, flags=re.I)
    seen, out = set(), []

    for href in found:
        href = unescape(href)
        url = urljoin(BASE, href)

        p = urlparse(url)
        if p.netloc.lower() not in {"lantrodeifumetti.it", "www.lantrodeifumetti.it"}:
            continue
        if "/shop/trading-card/tgc-pokemon/" not in p.path:
            continue

        clean = f"{p.scheme or 'https'}://{p.netloc}{p.path}"
        if not clean.endswith("/"):
            clean += "/"

        if clean not in seen:
            seen.add(clean)
            out.append(clean)

    return out

def extract_title(html):
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    return plain(m.group(1)) if m else ""

def parse_identity(title, html):
    text = plain(html)

    sku_m = re.search(r"\bCOD:\s*([A-Za-z0-9_-]+)", text, re.I)
    sku = sku_m.group(1).strip() if sku_m else ""

    num_m = re.search(r"\b([A-Za-z]*\d{1,3})[-/]([A-Za-z]*\d{1,3})\b", title)
    number = f"{num_m.group(1)}/{num_m.group(2)}" if num_m else ""

    nt = norm(title)
    ns = norm(sku)
    variant = None
    if "reverse holo" in nt or ns.endswith("rh"):
        variant = "Reverse Holo"
    elif re.search(r"\bholo\b", nt) or ns.endswith("h"):
        variant = "Holo"

    name = title
    if num_m:
        name = re.split(re.escape(num_m.group(0)), title, maxsplit=1)[0].strip()
    name = re.sub(r"\b(?:Reverse Holo|Holo)\b.*$", "", name, flags=re.I).strip()
    name = re.sub(r"\bITA\b.*$", "", name, flags=re.I).strip()

    lang = "IT" if re.search(r"\bITA\b", title, re.I) else ""
    cond = "NM" if re.search(r"\bNear Mint\b", text, re.I) else ""
    available = not bool(re.search(r"\bOut of stock\b|\bEsaurito\b", text, re.I))

    prices = re.findall(r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)", text)
    price = float(prices[0].replace(",", ".")) if prices else None

    return {
        "title": title,
        "name": name,
        "number": number,
        "variant": variant,
        "sku": sku,
        "language": lang,
        "condition": cond,
        "available": available,
        "price": price,
    }

def jsonld_objects(html):
    objs = []
    for m in re.finditer(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>',
        html,
        re.I | re.S,
    ):
        raw = unescape(m.group(1)).strip()
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                objs.extend(data)
            else:
                objs.append(data)
        except Exception:
            pass
    return objs

def flatten_strings(obj):
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.append(str(k))
            out.extend(flatten_strings(v))
    elif isinstance(obj, list):
        for x in obj:
            out.extend(flatten_strings(x))
    elif isinstance(obj, (str, int, float)):
        out.append(str(obj))
    return out

def structured_set_signals(html, known_sets):
    signals = []

    # 1) JSON-LD
    for obj in jsonld_objects(html):
        for s in flatten_strings(obj):
            ns = norm(s)
            if ns in known_sets:
                signals.append(("jsonld", known_sets[ns], s))

    # 2) meta content/name/property
    for m in re.finditer(
        r'<meta[^>]+(?:content|name|property)=["\']([^"\']+)["\'][^>]*>',
        html,
        re.I,
    ):
        s = unescape(m.group(1))
        ns = norm(s)
        if ns in known_sets:
            signals.append(("meta", known_sets[ns], s))

    # 3) categorie/tag/breadcrumb/link text
    for m in re.finditer(r'<a[^>]*>([^<]{2,120})</a>', html, re.I | re.S):
        s = plain(m.group(1))
        ns = norm(s)
        if ns in known_sets:
            signals.append(("link-text", known_sets[ns], s))

    # 4) attributi HTML / classi / body testuale: exact whole-set token only
    text = plain(html)
    nt = norm(text)
    for ns, canonical in known_sets.items():
        if len(ns) < 4:
            continue
        if re.search(rf"(?:^| ){re.escape(ns)}(?: |$)", nt):
            signals.append(("page-text", canonical, canonical))

    # dedup
    seen = set()
    out = []
    for src, canonical, raw in signals:
        key = (src, norm(canonical))
        if key in seen:
            continue
        seen.add(key)
        out.append({"source": src, "set": canonical, "raw": raw[:160]})

    return out

def main():
    data = json.loads(RETAIL.read_text(encoding="utf-8"))
    loose_index, known_sets = build_indexes(data)

    stats = Counter()
    all_links = []

    for p in range(1, MAX_CATEGORY_PAGES + 1):
        url = CATEGORY if p == 1 else CATEGORY + f"page/{p}/"
        try:
            html, _, status = get(url)
            links = product_links(html)
            stats["categoryPagesFetched"] += 1
            stats["catalogLinks"] += len(links)
            all_links.extend(links)
            time.sleep(0.04)
        except Exception:
            stats["categoryPageErrors"] += 1

    seen = set()
    links = []
    for u in all_links:
        if u not in seen:
            seen.add(u)
            links.append(u)

    stats["uniqueRealProductLinks"] = len(links)

    examined = []
    structured_resolved = []
    loose_candidates = []

    for url in links[:MAX_PRODUCT_PAGES]:
        stats["productPagesAttempted"] += 1
        try:
            html, final, status = get(url)
            stats["productPagesFetched"] += 1
            title = extract_title(html)
            ident = parse_identity(title, html)

            usable = all([
                ident["language"] == "IT",
                ident["condition"] == "NM",
                ident["available"],
                ident["number"],
                ident["variant"],
                ident["price"] is not None,
            ])
            if not usable:
                stats["preFilterRejected"] += 1
                continue

            stats["usable"] += 1
            cp = collector_parts(ident["number"])
            loose = loose_index.get((cp, norm(ident["name"]), ident["variant"]), [])
            signals = structured_set_signals(html, known_sets)

            unique_sets = sorted({x["set"] for x in signals})

            if len(unique_sets) == 1:
                stats["structuredSetResolved"] += 1
                if len(structured_resolved) < 40:
                    structured_resolved.append({
                        "url": final,
                        "title": title,
                        "number": ident["number"],
                        "name": ident["name"],
                        "variant": ident["variant"],
                        "set": unique_sets[0],
                        "signals": signals[:12],
                    })
            elif len(unique_sets) == 0:
                stats["structuredSetMissing"] += 1
            else:
                stats["structuredSetAmbiguous"] += 1

            if len(loose) == 1:
                stats["singleLooseIdentity"] += 1
                if len(loose_candidates) < 40:
                    loose_candidates.append({
                        "url": final,
                        "title": title,
                        "possibleSet": loose[0].get("set"),
                        "structuredSets": unique_sets,
                        "signals": signals[:12],
                    })

            if len(examined) < 50:
                examined.append({
                    "url": final,
                    "title": title,
                    "number": ident["number"],
                    "variant": ident["variant"],
                    "structuredSets": unique_sets,
                    "signalCount": len(signals),
                })

            time.sleep(0.03)

        except Exception as e:
            stats["productErrors"] += 1
            if len(examined) < 50:
                examined.append({"url": url, "error": repr(e)})

    report = {
        "schema": 3,
        "source": "L'Antro dei Fumetti",
        "mode": "read-only diagnostic",
        "ok": True,
        "rules": {
            "realDomainLinksOnly": True,
            "language": "ITA only",
            "condition": "Near Mint only",
            "availability": "available only",
            "variantsTrusted": ["Holo", "Reverse Holo"],
            "structuredSetOnly": True,
            "looseIdentityAccepted": False,
            "createsNewIdentity": False,
            "cardmarketTouched": False,
            "retailPricesModified": False,
        },
        "stats": dict(stats),
        "structuredResolvedExamples": structured_resolved,
        "singleLooseExamples": loose_candidates,
        "examinedExamples": examined,
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
    print("Report:", REPORT)

if __name__ == "__main__":
    main()
