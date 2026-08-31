#!/usr/bin/env python3
# Cardoryx - test isolato LPPCollecting V4
# READ-ONLY: non modifica retail_prices.json e non tocca Cardmarket.
#
# V4 non dipende dalla homepage per scoprire i set.
# Usa un piccolo gruppo di ID reali verificati pubblicamente per controllare
# parsing, disponibilità, lingua, condizione e matching Cardoryx.

import json
import re
import time
import unicodedata
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from html import unescape
from pathlib import Path

BASE = "https://www.lppcollecting.it"
SEARCH = BASE + "/pokemon/ricercacarte.php"
RETAIL = Path("data/retail_prices.json")
REPORT = Path("lppcollecting_test_report.json")

UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/4.0)"
TIMEOUT = 15

# ID reali verificati su pagine pubbliche LPPCollecting.
# Servono solo come campione diagnostico, non come mappa definitiva.
TEST_SET_IDS = [
    "103",      # Avventure Insieme
    "102",      # Scintille Folgoranti
    "1000009",  # Zenit Regale
    "1001004",  # Detective Pikachu
    "1001002",  # XY - Benvenuti a Kalos
    "4",        # Base Set 2
    "8",        # Neo Genesis
]

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
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8", "replace")

def plain(html):
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()

def collector_parts(number):
    m = re.match(
        r"^\s*([A-Za-z]*)(\d+)\s*/\s*([A-Za-z]*)(\d+)\s*$",
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

def rarity_variant(rarity, sku=""):
    r = norm(rarity)
    s = norm(sku)

    # LPP usa "RH" e spesso aggiunge "rh" anche nel codice.
    if " rh" in f" {r}" or "reverse" in r or s.endswith("rh ita"):
        return "Reverse Holo"

    # H = Holo semplice. Le diciture di prima edizione restano escluse.
    if r == "h":
        return "Holo"

    return None

def extract_set_names(html):
    text = plain(html)
    marker = re.search(
        r"([A-Za-zÀ-ÿ0-9&'’.\- ]{2,80})\s*/\s*"
        r"([A-Za-zÀ-ÿ0-9&'’.\- ]{2,80})\s+"
        r"carta\s+codice\s+numero\s+rarit",
        text,
        re.I,
    )
    if marker:
        return marker.group(1).strip(), marker.group(2).strip()

    # set solo italiano / senza slash
    marker = re.search(
        r"([A-Za-zÀ-ÿ0-9&'’.\- ]{2,100})\s+"
        r"carta\s+codice\s+numero\s+rarit",
        text,
        re.I,
    )
    if marker:
        return marker.group(1).strip(), ""

    return "", ""

# Parser di riga indipendente dalla presenza di immagini/input nel markup:
# usa la sequenza nome -> SKU -> numero -> rarità -> condizione -> prezzo.
ROW = re.compile(
    r"(?P<name>[A-Za-zÀ-ÿ0-9'’.:() -]+?)\s+"
    r"(?P<sku>PO-[A-Z0-9-]+(?:[A-Za-z0-9]+)?_(?P<lang>ita|eng))\s+"
    r"(?P<number>[A-Za-z]*\d+\s*/\s*[A-Za-z]*\d+)\s+"
    r"(?P<rarity>[A-Za-z0-9*+ .'-]{1,40})\s+"
    r"(?P<condition>mint/near mint|near mint|mint)\s+"
    r"€\s*(?P<price>\d+(?:[.,]\d{1,2})?)",
    re.I,
)

def parse_rows(html):
    text = plain(html)
    matches = list(ROW.finditer(text))
    rows = []

    for i, m in enumerate(matches):
        d = m.groupdict()
        d["price"] = float(d["price"].replace(",", "."))

        next_start = matches[i + 1].start() if i + 1 < len(matches) else min(len(text), m.end() + 500)
        tail = text[m.end():next_start]

        d["available"] = not bool(
            re.search(r"\bal momento\s+non disponibile\b", tail, re.I)
        )
        rows.append(d)

    return rows

def build_index(data):
    idx = defaultdict(list)
    for card in data.get("cards", {}).values():
        cp = collector_parts(card.get("number"))
        if not cp:
            continue
        idx[
            (
                norm(card.get("set")),
                cp,
                norm(card.get("name")),
                card.get("variant"),
            )
        ].append(card)
    return idx

def main():
    data = json.loads(RETAIL.read_text(encoding="utf-8"))
    index = build_index(data)

    stats = Counter()
    stats["testedSetIds"] = len(TEST_SET_IDS)

    pages = []
    examples = []
    seen = set()

    for sid in TEST_SET_IDS:
        url = SEARCH + "?" + urllib.parse.urlencode(
            {
                "poke_idrarita": "0",
                "poke_idserie": sid,
                "poke_ricerca": "",
                "poke_tipocarta": "tutte",
            }
        )

        page = {"id": sid, "url": url}

        try:
            html = get(url)
            rows = parse_rows(html)
            set_it, set_en = extract_set_names(html)

            page.update({
                "setIt": set_it,
                "setEn": set_en,
                "rows": len(rows),
            })

            stats["pagesOk"] += 1
            stats["rows"] += len(rows)

            if not rows:
                stats["pagesWithoutRows"] += 1
                pages.append(page)
                continue

            for row in rows:
                stats["variantsSeen"] += 1

                if row["lang"].lower() != "ita":
                    stats["languageRejected"] += 1
                    continue

                if row["price"] <= 0:
                    stats["priceRejected"] += 1
                    continue

                if not row["available"]:
                    stats["unavailable"] += 1
                    continue

                variant = rarity_variant(row["rarity"], row["sku"])
                if not variant:
                    stats["variantAmbiguous"] += 1
                    continue

                cp = collector_parts(row["number"])
                if not cp or not set_it:
                    stats["identityRejected"] += 1
                    continue

                candidates = index.get(
                    (norm(set_it), cp, norm(row["name"]), variant),
                    [],
                )

                if len(candidates) != 1:
                    stats["identityRejected"] += 1
                    continue

                card = candidates[0]
                identity = (
                    norm(card["set"]),
                    card["number"],
                    norm(card["name"]),
                    variant,
                )

                if identity in seen:
                    stats["duplicateIdentity"] += 1
                    continue

                seen.add(identity)
                stats["acceptedMatches"] += 1

                stores = {
                    offer.get("store")
                    for offer in card.get("offers", [])
                    if offer.get("store")
                }

                gain = (
                    not card.get("stats", {}).get("reliable")
                    and len(stores | {"LPPCollecting"}) >= 3
                )

                if gain:
                    stats["newReliablePotential"] += 1

                if len(examples) < 60:
                    examples.append({
                        "set": card["set"],
                        "number": card["number"],
                        "name": card["name"],
                        "variant": variant,
                        "price": row["price"],
                        "rarityRaw": row["rarity"],
                        "sku": row["sku"],
                        "existingStores": sorted(stores),
                        "newReliablePotential": gain,
                        "sourceUrl": url,
                    })

            pages.append(page)
            time.sleep(0.05)

        except Exception as e:
            stats["errors"] += 1
            page["error"] = str(e)
            pages.append(page)

    report = {
        "schema": 4,
        "source": "LPPCollecting",
        "mode": "read-only diagnostic",
        "rules": {
            "scope": "verified public set-id sample",
            "language": "ITA only",
            "condition": "near mint / mint-near mint / mint",
            "availability": "reject explicit 'al momento non disponibile'",
            "variantsAccepted": ["Holo", "Reverse Holo"],
            "identity": "exact Italian set + full collector number + exact normalized name + exact variant",
            "createsNewIdentity": False,
            "cardmarketTouched": False,
            "retailPricesModified": False,
        },
        "stats": dict(stats),
        "pages": pages,
        "examples": examples,
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
    print("Pages:")
    for page in pages:
        print(
            page.get("id"),
            "|",
            page.get("setIt", ""),
            "| rows:",
            page.get("rows", 0),
            "| error:",
            page.get("error", ""),
        )
    print("Report:", REPORT)

if __name__ == "__main__":
    main()
