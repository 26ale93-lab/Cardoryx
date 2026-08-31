#!/usr/bin/env python3
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
HOME = BASE + "/pokemon/"
SEARCH = BASE + "/pokemon/ricercacarte.php"
RETAIL = Path("data/retail_prices.json")
REPORT = Path("lppcollecting_test_report.json")
UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/2.0)"
TIMEOUT = 12
MAX_SETS = 35


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = unescape(s).lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def get(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9"},
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


def rarity_variant(rarity):
    r = norm(rarity)
    if "reverse" in r:
        return "Reverse Holo"
    if r in {"h", "holo", "olografica", "olografiche"}:
        return "Holo"
    return None


def discover_ids(html):
    ids = []
    for m in re.finditer(r"poke_idserie(?:=|%3D)(\d{1,12})", html, re.I):
        sid = m.group(1)
        if sid != "0" and sid not in ids:
            ids.append(sid)
    for m in re.finditer(r'''<option[^>]+value=["'](\d{1,12})["']''', html, re.I):
        sid = m.group(1)
        if sid != "0" and sid not in ids:
            ids.append(sid)
    return ids[:MAX_SETS]


def set_name(html):
    text = plain(html[:180000])
    patterns = [
        r"in inglese\s+(.{2,120}?)\s+carta\s+codice\s+numero\s+rarit",
        r"Ricerca Carte Singole.*?\s+(.{2,120}?)\s+carta\s+codice\s+numero\s+rarit",
    ]
    for pattern in patterns:
        m = re.search(pattern, text, re.I)
        if m:
            return m.group(1).strip().split("/")[0].strip()
    return ""


ROW = re.compile(
    r"(?P<name>[A-Za-zÀ-ÿ0-9'’.: -]+?)\s+"
    r"(?P<sku>PO-[A-Z0-9-]+_(?P<lang>ita|eng))\s+"
    r"(?P<number>[A-Za-z]*\d+\s*/\s*[A-Za-z]*\d+)\s+"
    r"(?P<rarity>[A-Za-z0-9*+ -]{1,30})\s+"
    r"(?P<condition>mint/near mint|near mint|mint)\s+"
    r"€\s*(?P<price>\d+(?:[.,]\d{1,2})?)",
    re.I,
)


def parse_rows(html):
    text = plain(html)
    rows = []
    for m in ROW.finditer(text):
        d = m.groupdict()
        d["price"] = float(d["price"].replace(",", "."))
        tail = text[m.end():m.end() + 140]
        d["available"] = not bool(
            re.match(r"\s*al momento\s+non disponibile", tail, re.I)
        )
        rows.append(d)
    return rows


def main():
    data = json.loads(RETAIL.read_text(encoding="utf-8"))
    index = defaultdict(list)
    for card in data.get("cards", {}).values():
        cp = collector_parts(card.get("number"))
        if cp:
            key = (
                norm(card.get("set")),
                cp,
                norm(card.get("name")),
                card.get("variant"),
            )
            index[key].append(card)

    stats = Counter()
    examples = []
    seen = set()
    sets = []

    set_ids = discover_ids(get(HOME))
    stats["discoveredSetIds"] = len(set_ids)

    for sid in set_ids:
        try:
            url = SEARCH + "?" + urllib.parse.urlencode(
                {
                    "poke_idrarita": "0",
                    "poke_idserie": sid,
                    "poke_ricerca": "",
                    "poke_tipocarta": "tutte",
                }
            )
            html = get(url)
            rows = parse_rows(html)
            if not rows:
                continue

            current_set = set_name(html)
            stats["setPagesWithRows"] += 1
            stats["rows"] += len(rows)
            sets.append({"id": sid, "set": current_set, "rows": len(rows)})

            for row in rows:
                if row["lang"].lower() != "ita":
                    stats["languageRejected"] += 1
                    continue
                if not row["available"]:
                    stats["unavailable"] += 1
                    continue
                if row["price"] <= 0:
                    stats["priceRejected"] += 1
                    continue

                variant = rarity_variant(row["rarity"])
                if not variant:
                    stats["variantAmbiguous"] += 1
                    continue

                cp = collector_parts(row["number"])
                if not cp or not current_set:
                    stats["identityRejected"] += 1
                    continue

                key = (norm(current_set), cp, norm(row["name"]), variant)
                candidates = index.get(key, [])
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
                becomes_reliable = (
                    not card.get("stats", {}).get("reliable")
                    and len(stores | {"LPPCollecting"}) >= 3
                )
                if becomes_reliable:
                    stats["newReliablePotential"] += 1

                if len(examples) < 50:
                    examples.append(
                        {
                            "set": card["set"],
                            "number": card["number"],
                            "name": card["name"],
                            "variant": variant,
                            "price": row["price"],
                            "rarityRaw": row["rarity"],
                            "existingStores": sorted(stores),
                            "newReliablePotential": becomes_reliable,
                            "sourceUrl": url,
                        }
                    )
            time.sleep(0.03)
        except Exception as e:
            stats["errors"] += 1
            if len(examples) < 50:
                examples.append({"setId": sid, "error": str(e)})

    report = {
        "schema": 2,
        "source": "LPPCollecting",
        "mode": "read-only diagnostic fast sample",
        "rules": {
            "language": "ITA only",
            "condition": "mint/near mint / near mint / mint",
            "availability": "reject explicit al momento non disponibile",
            "variantsAccepted": ["Holo", "Reverse Holo"],
            "identity": "exact set + full collector number + exact normalized name + exact variant",
            "cardmarketTouched": False,
            "retailPricesModified": False,
        },
        "stats": dict(stats),
        "sets": sets,
        "examples": examples,
    }
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
    print("Report:", REPORT)


if __name__ == "__main__":
    main()
