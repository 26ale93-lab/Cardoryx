#!/usr/bin/env python3
# Cardoryx - test L'Antro dei Fumetti V2
# READ-ONLY: non modifica retail_prices.json e non tocca Cardmarket.
#
# Obiettivo:
# - riusare solo prodotti tecnicamente utili
# - estrarre il set dal prodotto
# - fare matching ESATTO con le identità già presenti in retail_prices.json
# - misurare quanti nuovi reliable potrebbero nascere aggiungendo L'Antro
#
# Nessuna identità nuova viene creata.

import json
import re
import time
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from html import unescape
from pathlib import Path
from urllib.parse import urljoin

BASE = "https://lantrodeifumetti.it"
CATEGORY = BASE + "/categoria-prodotto/trading-card/tgc-pokemon/"
RETAIL = Path("data/retail_prices.json")
REPORT = Path("antro_test_report.json")

UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/2.0)"
TIMEOUT = 15
MAX_PAGES = 30
MAX_PRODUCTS_TO_OPEN = 260

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

def build_card_indexes(data):
    exact = defaultdict(list)
    by_number_name_variant = defaultdict(list)

    for card in data.get("cards", {}).values():
        cp = collector_parts(card.get("number"))
        if not cp:
            continue

        exact[
            (
                norm(card.get("set")),
                cp,
                norm(card.get("name")),
                card.get("variant"),
            )
        ].append(card)

        by_number_name_variant[
            (
                cp,
                norm(card.get("name")),
                card.get("variant"),
            )
        ].append(card)

    return exact, by_number_name_variant

def product_links(html):
    links = re.findall(
        r'href=["\']([^"\']+/shop/trading-card/tgc-pokemon/[^"\']+/?)["\']',
        html,
        flags=re.I,
    )
    seen, out = set(), []
    for link in links:
        link = urljoin(BASE, link)
        if link not in seen:
            seen.add(link)
            out.append(link)
    return out

def page_count(html):
    text = plain(html)
    m = re.search(r"Visualizzazione di .*? di\s+(\d+)\s+risultati", text, re.I)
    total = int(m.group(1)) if m else None
    pages = (total + 19) // 20 if total else None
    return total, pages

def extract_title(html):
    m = re.search(r"<h1[^>]*>(.*?)</h1>", html, re.I | re.S)
    return plain(m.group(1)) if m else ""

def extract_sku(text):
    m = re.search(r"\bCOD:\s*([A-Za-z0-9_-]+)", text, re.I)
    return m.group(1).strip() if m else ""

def extract_set_candidates(html, text):
    candidates = []

    # WooCommerce meta/categorie/tag: spesso il nome set compare nei link.
    for m in re.finditer(
        r'href=["\'][^"\']+["\'][^>]*>([^<]{2,80})</a>',
        html,
        re.I | re.S,
    ):
        label = plain(m.group(1))
        if label:
            candidates.append(label)

    # Breadcrumb/schema visibile.
    for pattern in [
        r"\bEspansione:\s*([A-Za-zÀ-ÿ0-9&'’.\- ]{2,80})",
        r"\bSet:\s*([A-Za-zÀ-ÿ0-9&'’.\- ]{2,80})",
        r"\bSerie:\s*([A-Za-zÀ-ÿ0-9&'’.\- ]{2,80})",
    ]:
        for m in re.finditer(pattern, text, re.I):
            candidates.append(m.group(1).strip())

    # Dedup normalizzato
    seen = set()
    out = []
    for c in candidates:
        nc = norm(c)
        if not nc or nc in seen:
            continue
        seen.add(nc)
        out.append(c)
    return out

def parse_product(html, url):
    text = plain(html)
    title = extract_title(html)

    prices = re.findall(r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)", text)
    price = float(prices[0].replace(",", ".")) if prices else None

    sku = extract_sku(text)
    condition = "NM" if re.search(r"\bNear Mint\b", text, re.I) else ""

    available = not bool(re.search(r"\bOut of stock\b|\bEsaurito\b", text, re.I))
    if re.search(r"\bSolo\s+\d+\s+pezz[oi]\s+disponibil", text, re.I):
        available = True

    language = "IT" if re.search(r"\bITA\b", title, re.I) else ""

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

    # Rimuovi suffissi noti dal nome.
    name = re.sub(r"\b(?:Reverse Holo|Holo)\b.*$", "", name, flags=re.I).strip()
    name = re.sub(r"\bITA\b.*$", "", name, flags=re.I).strip()

    return {
        "url": url,
        "title": title,
        "name": name,
        "number": number,
        "variant": variant,
        "language": language,
        "condition": condition,
        "available": available,
        "price": price,
        "sku": sku,
        "setCandidates": extract_set_candidates(html, text),
    }

def main():
    data = json.loads(RETAIL.read_text(encoding="utf-8"))
    exact_index, loose_index = build_card_indexes(data)

    known_sets = {}
    for card in data.get("cards", {}).values():
        s = card.get("set")
        if s:
            known_sets[norm(s)] = s

    stats = Counter()
    pages_info = []
    all_links = []

    first_html, _, _ = get(CATEGORY)
    total, pages = page_count(first_html)
    if total is not None:
        stats["categoryReportedProducts"] = total
    if pages is not None:
        stats["categoryReportedPages"] = pages

    pages_to_fetch = min(pages or 1, MAX_PAGES)

    for p in range(1, pages_to_fetch + 1):
        url = CATEGORY if p == 1 else CATEGORY + f"page/{p}/"
        try:
            html, final, status = get(url)
            links = product_links(html)
            stats["pagesFetched"] += 1
            all_links.extend(links)
            pages_info.append({"page": p, "status": status, "links": len(links)})
            time.sleep(0.04)
        except Exception as e:
            stats["pageErrors"] += 1
            pages_info.append({"page": p, "error": repr(e)})

    seen = set()
    links = []
    for u in all_links:
        if u not in seen:
            seen.add(u)
            links.append(u)
    stats["uniqueProductLinks"] = len(links)

    examples = []
    rejected_examples = []
    accepted_ids = set()

    for url in links[:MAX_PRODUCTS_TO_OPEN]:
        stats["productPagesAttempted"] += 1
        try:
            html, final, status = get(url)
            stats["productPagesFetched"] += 1
            item = parse_product(html, final)

            if not all([
                item["language"] == "IT",
                item["condition"] == "NM",
                item["available"],
                item["number"],
                item["variant"],
                item["price"] is not None,
            ]):
                stats["preFilterRejected"] += 1
                continue

            stats["usableBeforeSetMatching"] += 1
            cp = collector_parts(item["number"])
            if not cp:
                stats["identityRejected"] += 1
                continue

            # Individua il set SOLO se uno dei candidati pagina coincide
            # esattamente con un set già noto a Cardoryx.
            matched_sets = []
            for c in item["setCandidates"]:
                nc = norm(c)
                if nc in known_sets:
                    matched_sets.append(known_sets[nc])

            # Dedup
            matched_sets = list(dict.fromkeys(matched_sets))

            if len(matched_sets) == 1:
                stats["setResolved"] += 1
                set_name = matched_sets[0]

                candidates = exact_index.get(
                    (norm(set_name), cp, norm(item["name"]), item["variant"]),
                    [],
                )

                if len(candidates) == 1:
                    card = candidates[0]
                    stats["exactMatches"] += 1

                    card_key = (
                        norm(card.get("set")),
                        card.get("number"),
                        norm(card.get("name")),
                        card.get("variant"),
                    )
                    if card_key in accepted_ids:
                        stats["duplicateIdentity"] += 1
                        continue
                    accepted_ids.add(card_key)

                    stores = {
                        o.get("store")
                        for o in card.get("offers", [])
                        if o.get("store")
                    }

                    reliable_before = bool(card.get("stats", {}).get("reliable"))
                    reliable_after = len(stores | {"L'Antro dei Fumetti"}) >= 3

                    if reliable_before:
                        stats["alreadyReliableMatched"] += 1
                    elif reliable_after:
                        stats["newReliablePotential"] += 1
                    else:
                        stats["matchedButStillNotReliable"] += 1

                    if len(examples) < 80:
                        examples.append({
                            "set": card.get("set"),
                            "number": card.get("number"),
                            "name": card.get("name"),
                            "variant": card.get("variant"),
                            "price": item["price"],
                            "existingStores": sorted(stores),
                            "reliableBefore": reliable_before,
                            "newReliablePotential": (not reliable_before and reliable_after),
                            "sourceUrl": item["url"],
                            "sku": item["sku"],
                        })
                else:
                    stats["identityRejected"] += 1
                    if len(rejected_examples) < 30:
                        rejected_examples.append({
                            "reason": "exact identity not unique",
                            "title": item["title"],
                            "nameParsed": item["name"],
                            "number": item["number"],
                            "variant": item["variant"],
                            "resolvedSet": set_name,
                            "candidateCount": len(candidates),
                            "url": item["url"],
                        })

            elif len(matched_sets) == 0:
                stats["setUnresolved"] += 1

                # Solo diagnostica: se numero+nome+variante produce un solo set
                # Cardoryx, segnaliamo che il match sarebbe potenzialmente risolvibile,
                # ma NON lo accettiamo.
                loose = loose_index.get((cp, norm(item["name"]), item["variant"]), [])
                if len(loose) == 1:
                    stats["singleLooseIdentity"] += 1
                    if len(rejected_examples) < 30:
                        rejected_examples.append({
                            "reason": "set missing on page; unique loose Cardoryx candidate",
                            "title": item["title"],
                            "number": item["number"],
                            "variant": item["variant"],
                            "possibleSet": loose[0].get("set"),
                            "url": item["url"],
                        })
            else:
                stats["setAmbiguous"] += 1

            time.sleep(0.03)

        except Exception as e:
            stats["productErrors"] += 1
            if len(rejected_examples) < 30:
                rejected_examples.append({"reason": "fetch/parse error", "url": url, "error": repr(e)})

    report = {
        "schema": 2,
        "source": "L'Antro dei Fumetti",
        "mode": "read-only diagnostic",
        "ok": True,
        "rules": {
            "language": "ITA only",
            "condition": "Near Mint only",
            "availability": "available only",
            "variantsTrusted": ["Holo", "Reverse Holo"],
            "setRule": "accept only exact page set label matching an existing Cardoryx set",
            "identityRule": "exact set + full collector number + exact normalized name + exact variant",
            "createsNewIdentity": False,
            "reliabilityRule": "independent-any-3-stores",
            "cardmarketTouched": False,
            "retailPricesModified": False,
        },
        "stats": dict(stats),
        "pages": pages_info,
        "acceptedExamples": examples,
        "rejectedExamples": rejected_examples,
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
    print("Report:", REPORT)

if __name__ == "__main__":
    main()
