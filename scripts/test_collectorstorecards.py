#!/usr/bin/env python3
# Cardoryx - Collector Store Cards V4
# Diagnostica read-only.
# Obiettivi:
# 1) separare Holo / Holo Reverse dal nome quando presenti nel titolo
# 2) misurare i casi con rarità speciali usando solo identità Cardoryx già esistenti
# 3) NON accettare automaticamente rarità speciali come variant
# 4) NON modificare retail_prices.json e NON toccare Cardmarket

import json
import re
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from html import unescape
from pathlib import Path

BASE = "https://collectorstorecards.it"
COLL = BASE + "/collections/carte-singole-pokemon"
RETAIL = Path("data/retail_prices.json")
REPORT = Path("collectorstorecards_test_report.json")
UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/4.0)"
MAX_PAGES = 8

SPECIAL_RARITIES = {
    "illustration rare",
    "special illustration rare",
    "ultra rare",
    "double rare",
    "ace rare",
    "shiny rare",
    "hyper rare",
    "rare secret",
    "trainer gallery",
    "galarian gallery",
}

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = unescape(s).lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def plain(html):
    html = re.sub(r"<script\b.*?</script>", " ", str(html or ""), flags=re.I | re.S)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<[^>]+>", " ", html)
    return re.sub(r"\s+", " ", unescape(html)).strip()

def get_json(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "application/json",
            "Accept-Language": "it-IT,it;q=0.9",
        },
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def collector_parts(number):
    m = re.match(
        r"^\s*([A-Za-z]*)(\d+)\s*[/\-]\s*([A-Za-z]*)(\d+)\s*$",
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

def parse_title(title):
    t = str(title or "").strip()
    m = re.search(r"\b([A-Za-z]*\d{1,3})\s*[/\-]\s*([A-Za-z]*\d{1,3})\b", t)
    if not m:
        return None

    number = f"{m.group(1)}/{m.group(2)}"

    before = t[:m.start()].strip(" -–—")
    before = re.sub(r"^\s*Pok[eé]mon\s+", "", before, flags=re.I).strip()

    title_variant = None

    # Stacca i marker variante dal NOME, senza usarli se non espliciti nel titolo.
    if re.search(r"\bholo\s+reverse$", before, re.I):
        title_variant = "Reverse Holo"
        before = re.sub(r"\bholo\s+reverse$", "", before, flags=re.I).strip()
    elif re.search(r"\breverse\s+holo$", before, re.I):
        title_variant = "Reverse Holo"
        before = re.sub(r"\breverse\s+holo$", "", before, flags=re.I).strip()
    elif re.search(r"\bholo$", before, re.I):
        title_variant = "Holo"
        before = re.sub(r"\bholo$", "", before, flags=re.I).strip()
    elif re.search(r"\bnormal$", before, re.I):
        title_variant = "Normal"
        before = re.sub(r"\bnormal$", "", before, flags=re.I).strip()

    tail = t[m.end():]
    tail = re.sub(r"\bITA\b.*$", "", tail, flags=re.I).strip(" -–—")

    return {
        "name": before,
        "number": number,
        "setFromTitle": tail,
        "language": "IT" if re.search(r"\bITA\b", t, re.I) else None,
        "titleVariant": title_variant,
    }

def set_from_tags(tags):
    vals = []
    for tag in tags or []:
        m = re.match(r"^\s*(.+?)\s*\[([A-Za-z0-9]+)\]\s*$", str(tag))
        if m:
            vals.append((m.group(1).strip(), m.group(2).upper()))
    return vals

def extract_body_fields(body):
    t = plain(body)

    def field(label, following):
        m = re.search(
            rf"\b{re.escape(label)}:\s*(.+?)(?=\s+(?:{following})\s*:|$)",
            t,
            re.I,
        )
        return m.group(1).strip() if m else ""

    condition = field("Condizione", "Set|Rarità|Numerazione|Lingua")
    set_name = field("Set", "Rarità|Numerazione|Lingua")
    rarity = field("Rarità", "Numerazione|Lingua")
    number = field("Numerazione", "Lingua")
    language = field("Lingua", "ZZZ_NEVER_MATCH")

    return {
        "text": t,
        "condition": condition,
        "set": set_name,
        "rarity": rarity,
        "number": number,
        "language": language,
    }

def variant_from_body(body_text):
    n = norm(body_text)

    if re.search(r"\breverse holo\b", n) or re.search(r"\bholo reverse\b", n):
        return "Reverse Holo", "explicit body reverse holo"

    if re.search(r"\bnon holo\b", n) or re.search(r"\bnon olografica\b", n) or re.search(r"\bnormal\b", n):
        return "Normal", "explicit body normal"

    if re.search(r"\bholo rare\b", n) or re.search(r"\brara holo\b", n):
        return "Holo", "explicit body holo"

    return None, None

def build_indexes(data):
    exact = defaultdict(list)
    base_identity = defaultdict(list)

    for c in data.get("cards", {}).values():
        cp = collector_parts(c.get("number"))
        if not cp:
            continue

        key_base = (
            norm(c.get("set")),
            cp,
            norm(c.get("name")),
        )
        base_identity[key_base].append(c)

        key_exact = key_base + (c.get("variant"),)
        exact[key_exact].append(c)

    return exact, base_identity

def is_special_rarity(rarity):
    nr = norm(rarity)
    return any(x in nr for x in SPECIAL_RARITIES)

def main():
    retail = json.loads(RETAIL.read_text(encoding="utf-8"))
    exact_index, base_index = build_indexes(retail)

    stats = Counter()
    products = []
    page_errors = []

    for page in range(1, MAX_PAGES + 1):
        url = f"{COLL}/products.json?limit=250&page={page}"
        try:
            obj = get_json(url)
            batch = obj.get("products", [])
            stats["catalogPagesFetched"] += 1
            products.extend(batch)
            if len(batch) < 250:
                break
        except Exception as e:
            stats["catalogPageErrors"] += 1
            page_errors.append({"page": page, "error": repr(e)})
            break

    stats["products"] = len(products)

    exact_examples = []
    special_examples = []
    ambiguous_examples = []
    conflicts = []

    for p in products:
        stats["productsInspected"] += 1

        parsed = parse_title(p.get("title", ""))
        if not parsed or parsed["language"] != "IT":
            stats["titleRejected"] += 1
            continue

        tags = p.get("tags") or []
        if isinstance(tags, str):
            tags = [x.strip() for x in tags.split(",") if x.strip()]

        set_tags = set_from_tags(tags)
        if len(set_tags) != 1:
            stats["setTagRejected"] += 1
            continue

        set_name, set_code = set_tags[0]
        if norm(set_name) != norm(parsed["setFromTitle"]):
            stats["setTitleConflict"] += 1
            if len(conflicts) < 20:
                conflicts.append({
                    "title": p.get("title"),
                    "setFromTitle": parsed["setFromTitle"],
                    "setFromTag": set_name,
                })
            continue

        variants = p.get("variants") or []
        available = [v for v in variants if v.get("available")]
        if not available:
            stats["unavailable"] += 1
            continue

        prices = {
            float(v["price"])
            for v in available
            if v.get("price") not in (None, "")
        }
        if len(prices) != 1:
            stats["priceRejected"] += 1
            continue
        price = next(iter(prices))

        body_fields = extract_body_fields(p.get("body_html", ""))

        if norm(body_fields["condition"]) != "near mint":
            stats["conditionUnconfirmed"] += 1
            continue
        stats["nearMintConfirmed"] += 1

        cp = collector_parts(parsed["number"])
        if not cp:
            stats["numberRejected"] += 1
            continue

        key_base = (norm(set_name), cp, norm(parsed["name"]))
        base_candidates = base_index.get(key_base, [])

        # 1) variante esplicita: titolo ha precedenza come segnale fisico
        explicit_variant = parsed["titleVariant"]
        variant_signal = None

        if explicit_variant:
            variant_signal = "explicit title variant"
        else:
            explicit_variant, variant_signal = variant_from_body(body_fields["text"])

        if explicit_variant:
            stats["explicitVariantConfirmed"] += 1
            matches = exact_index.get(key_base + (explicit_variant,), [])

            if len(matches) == 1:
                stats["exactMatches"] += 1
                card = matches[0]
                if bool((card.get("stats") or {}).get("reliable")):
                    stats["matchedAlreadyReliable"] += 1
                else:
                    stats["matchedCurrentlyNotReliable"] += 1
            else:
                stats["explicitVariantIdentityRejected"] += 1

            if len(exact_examples) < 40:
                exact_examples.append({
                    "title": p.get("title"),
                    "name": parsed["name"],
                    "number": parsed["number"],
                    "set": set_name,
                    "setCode": set_code,
                    "condition": "NM",
                    "variant": explicit_variant,
                    "variantSignal": variant_signal,
                    "rarity": body_fields["rarity"],
                    "price": price,
                    "baseCandidateCount": len(base_candidates),
                    "exactMatch": len(matches) == 1,
                    "url": f"{BASE}/products/{p.get('handle')}",
                })
            continue

        # 2) rarità speciale: NON convertire in variant.
        if is_special_rarity(body_fields["rarity"]):
            stats["specialRarityProducts"] += 1

            variant_set = sorted({
                c.get("variant")
                for c in base_candidates
                if c.get("variant")
            })

            if len(base_candidates) == 1:
                stats["specialUniquePhysicalIdentity"] += 1
                c = base_candidates[0]
                if bool((c.get("stats") or {}).get("reliable")):
                    stats["specialUniqueAlreadyReliable"] += 1
                else:
                    stats["specialUniqueCurrentlyNotReliable"] += 1
            elif len(base_candidates) > 1 and len(variant_set) == 1:
                # Più record ma tutti concordano sulla stessa variant.
                # SOLO misura diagnostica, NON accettata.
                stats["specialMultipleRecordsSameVariant"] += 1
            elif len(base_candidates) > 1:
                stats["specialAmbiguousVariants"] += 1
            else:
                stats["specialNoCardoryxIdentity"] += 1

            if len(special_examples) < 60:
                special_examples.append({
                    "title": p.get("title"),
                    "name": parsed["name"],
                    "number": parsed["number"],
                    "set": set_name,
                    "rarity": body_fields["rarity"],
                    "price": price,
                    "baseCandidateCount": len(base_candidates),
                    "candidateVariants": variant_set,
                    "uniquePhysicalIdentity": len(base_candidates) == 1,
                    "url": f"{BASE}/products/{p.get('handle')}",
                })
            continue

        # 3) tutto il resto resta non verificato.
        stats["variantStillUnconfirmed"] += 1

        if len(ambiguous_examples) < 30:
            ambiguous_examples.append({
                "title": p.get("title"),
                "name": parsed["name"],
                "number": parsed["number"],
                "set": set_name,
                "rarity": body_fields["rarity"],
                "price": price,
                "baseCandidateCount": len(base_candidates),
                "candidateVariants": sorted({
                    c.get("variant") for c in base_candidates if c.get("variant")
                }),
                "url": f"{BASE}/products/{p.get('handle')}",
            })

    report = {
        "schema": 4,
        "source": "Collector Store Cards",
        "mode": "read-only diagnostic",
        "ok": True,
        "rules": {
            "shopifyCatalogOnly": True,
            "productPagesOpened": False,
            "language": "ITA title required",
            "condition": "Near Mint explicit in body_html",
            "availability": "available Shopify variant required",
            "price": "one unique price across available variants",
            "set": "title/tag agreement required",
            "explicitVariant": "accepted only when stated in title/body",
            "specialRarity": "diagnostic only; never auto-converted to Holo/Normal/Reverse",
            "specialIdentityRule": "measure existing Cardoryx base identity only",
            "identity": "set + full number + exact normalized name; variant exact only when explicit",
            "createsNewIdentity": False,
            "cardmarketTouched": False,
            "retailPricesModified": False,
        },
        "stats": dict(stats),
        "pageErrors": page_errors,
        "exactExamples": exact_examples,
        "specialRarityExamples": special_examples,
        "ambiguousExamples": ambiguous_examples,
        "setConflicts": conflicts,
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
    print("Report:", REPORT)

if __name__ == "__main__":
    main()
