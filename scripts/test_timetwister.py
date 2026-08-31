#!/usr/bin/env python3
import json
import re
import time
import urllib.request
import unicodedata
from collections import Counter, defaultdict

BASE = "https://timetwistergames.it"
COLLECTION_URL = BASE + "/collections/pok-mon-single/products.json?limit=250&page={page}"
RETAIL_FILE = "data/retail_prices.json"
REPORT_FILE = "timetwister_mapping_audit_v5.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Cardoryx TimeTwister audit V5)",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
    "Connection": "close",
}

# Mapping esplicito e auditato. Non viene "imparato" da collisioni di carte.
# XBLK era il caso pericoloso del test V4:
# "Black Bolt: Additionals" NON è Avventure Insieme; in italiano è Luce Nera.
TRUSTED_SET_CODE_MAP = {
    "ASR": "Lucentezza Siderale",
    "BRS": "Astri Lucenti",
    "CRZ": "Zenit Regale",
    "DAA": "Fiamme Oscure",
    "DRI": "Rivali Predestinati",
    "FST": "Colpo Fusione",
    "LOR": "Origine Perduta",
    "PAL": "Evoluzioni a Paldea",
    "PAR": "Paradosso Temporale",
    "PRE": "Evoluzioni Prismatiche",
    "SCR": "Corona Astrale",
    "SFA": "Segreto Fiabesco",
    "SIT": "Tempesta Argentata",
    "SSP": "Scintille Folgoranti",
    "SVI": "Scarlatto e Violetto",
    "TEF": "CronoForze",
    "TWM": "Crepuscolo Mascherato",
    "XPRE": "Evoluzioni Prismatiche",
    "XBLK": "Luce Nera",
}

# Controllo aggiuntivo: il testo espansione TimeTwister deve essere compatibile
# col codice. Serve a impedire che un codice corretto venga usato su un titolo
# semanticamente incompatibile.
TRUSTED_LABEL_HINTS = {
    "ASR": {"astral radiance"},
    "BRS": {"brilliant stars"},
    "CRZ": {"crown zenith"},
    "DAA": {"darkness ablaze"},
    "DRI": {"destined rivals"},
    "FST": {"fusion strike"},
    "LOR": {"lost origin"},
    "PAL": {"paldea evolved"},
    "PAR": {"paradox rift"},
    "PRE": {"prismatic evolutions"},
    "SCR": {"stellar crown"},
    "SFA": {"shrouded fable"},
    "SIT": {"silver tempest"},
    "SSP": {"surging sparks"},
    "SVI": {"scarlet violet", "scarlet and violet"},
    "TEF": {"temporal forces"},
    "TWM": {"twilight masquerade"},
    "XPRE": {"prismatic evolutions additionals"},
    "XBLK": {"black bolt additionals"},
}

SUPPORTED_EDITIONS = {
    "normal": "Normal",
    "reverse holo": "Reverse Holo",
    "reverseholo": "Reverse Holo",
    "reverse-holo": "Reverse Holo",
    "holo": "Holo",
}

def fetch_json(url, retries=3, timeout=30):
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:
            last = exc
            print(f"Tentativo {attempt}/{retries} fallito: {exc}", flush=True)
            if attempt < retries:
                time.sleep(2 * attempt)
    raise last

def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower().replace("&", " and ").replace("’", "'")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def norm_number(value):
    return str(value or "").strip().upper().replace(" ", "")

def collector_left(number):
    left = norm_number(number).split("/", 1)[0]
    m = re.fullmatch(r"([A-Z]{0,3})(\d{1,4})", left)
    if not m:
        return left
    prefix, digits = m.groups()
    return prefix + str(int(digits))

def parse_title(title):
    title = str(title or "").strip()
    m = re.fullmatch(
        r"(.+?)\s+-\s+(.+?)\s+\(([^()]*)\)\s+\[([A-Za-z0-9]+)-((?:TG|GG|SV)?\d{1,4})\]",
        title,
        flags=re.I,
    )
    if not m:
        return None
    name, set_label, rarity, set_code, collector = m.groups()
    return {
        "name": name.strip(),
        "setLabel": set_label.strip(),
        "rarity": rarity.strip(),
        "setCode": set_code.upper(),
        "collector": collector_left(collector),
    }

def variant_fields(product, variant):
    options = product.get("options") or []
    pos = {
        norm(o.get("name")): i + 1
        for i, o in enumerate(options)
        if isinstance(o, dict)
    }
    vals = {
        1: str(variant.get("option1") or "").strip(),
        2: str(variant.get("option2") or "").strip(),
        3: str(variant.get("option3") or "").strip(),
    }
    return (
        vals.get(pos.get("language"), ""),
        vals.get(pos.get("condition"), ""),
        vals.get(pos.get("edition"), ""),
    )

def canonical_variant(value):
    return SUPPORTED_EDITIONS.get(norm(value))

def usable_variants(product):
    out = []
    for v in product.get("variants") or []:
        language, condition, edition = variant_fields(product, v)
        if norm(language) not in {"italian", "italiano", "ita"}:
            continue
        if norm(condition) not in {"near mint", "nm"}:
            continue
        if v.get("available") is not True:
            continue
        cv = canonical_variant(edition)
        if not cv:
            continue
        try:
            price = round(float(v.get("price")), 2)
        except Exception:
            continue
        if price <= 0:
            continue
        out.append((cv, price, v))
    return out

def label_compatible(code, label):
    hints = TRUSTED_LABEL_HINTS.get(code)
    if not hints:
        return False
    nl = norm(label)
    return any(norm(h) in nl for h in hints)

print("=== TIMETWISTER - AUDIT MAPPING V5 ===", flush=True)
print("SOLO TEST: non modifica Cardmarket né retail_prices.json.", flush=True)

with open(RETAIL_FILE, "r", encoding="utf-8") as f:
    retail = json.load(f)

cards = retail.get("cards") or {}
if not isinstance(cards, dict) or not cards:
    raise SystemExit("ERRORE: data/retail_prices.json privo di cards")

identity_full = defaultdict(list)
for key, card in cards.items():
    ident = (
        norm(card.get("set")),
        collector_left(card.get("number")),
        norm(card.get("name")),
        str(card.get("variant") or ""),
    )
    identity_full[ident].append((key, card))

products = []
for page in range(1, 101):
    payload = fetch_json(COLLECTION_URL.format(page=page))
    batch = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(batch, list):
        raise SystemExit(f"ERRORE: pagina {page} senza products")
    print(f"Pagina {page}: {len(batch)} prodotti", flush=True)
    if not batch:
        break
    products.extend(batch)
    if len(batch) < 250:
        break
    time.sleep(0.25)

stats = Counter()
matches = {}
per_code = Counter()
per_code_reliable = Counter()
unknown_codes = Counter()
label_conflicts = Counter()
ambiguous_examples = []
secret_examples = []
xblk_examples = []

for product in products:
    parsed = parse_title(product.get("title"))
    if not parsed:
        stats["invalidTitle"] += 1
        continue

    stats["parsedProducts"] += 1
    code = parsed["setCode"]
    target_set = TRUSTED_SET_CODE_MAP.get(code)

    if not target_set:
        unknown_codes[code] += 1
        continue

    if not label_compatible(code, parsed["setLabel"]):
        label_conflicts[(code, parsed["setLabel"])] += 1
        continue

    for cv, price, shop_variant in usable_variants(product):
        stats["usableVariants"] += 1
        ident = (
            norm(target_set),
            parsed["collector"],
            norm(parsed["name"]),
            cv,
        )
        found = identity_full.get(ident, [])
        if len(found) != 1:
            stats["identityRejected"] += 1
            if len(ambiguous_examples) < 30:
                ambiguous_examples.append({
                    "title": product.get("title"),
                    "targetSet": target_set,
                    "collector": parsed["collector"],
                    "name": parsed["name"],
                    "variant": cv,
                    "matches": len(found),
                })
            continue

        key, card = found[0]

        # massimo una offerta TimeTwister per identità
        if key in matches:
            stats["duplicateIdentity"] += 1
            continue

        matches[key] = {
            "card": card,
            "price": price,
            "code": code,
            "setLabel": parsed["setLabel"],
            "url": BASE + "/products/" + str(product.get("handle") or ""),
        }
        per_code[code] += 1

        # Esempi carte oltre il totale set, per verificare che restino valide.
        num = str(card.get("number") or "")
        m = re.fullmatch(r"(\d{1,4})/(\d{1,4})", num)
        if m and int(m.group(1)) > int(m.group(2)) and len(secret_examples) < 40:
            secret_examples.append({
                "set": card.get("set"),
                "number": card.get("number"),
                "name": card.get("name"),
                "variant": card.get("variant"),
                "price": price,
                "code": code,
            })

        if code == "XBLK" and len(xblk_examples) < 40:
            xblk_examples.append({
                "set": card.get("set"),
                "number": card.get("number"),
                "name": card.get("name"),
                "variant": card.get("variant"),
                "price": price,
                "setLabel": parsed["setLabel"],
                "url": BASE + "/products/" + str(product.get("handle") or ""),
            })

def stores_without_timetwister(card):
    return {
        norm(o.get("store"))
        for o in (card.get("offers") or [])
        if norm(o.get("store")) != norm("TimeTwister Games")
    }

baseline_reliable = 0
reliable_with_v5 = 0
newly_reliable = []
already_reliable_matches = 0

for key, card in cards.items():
    stores = stores_without_timetwister(card)
    if len(stores) >= 3:
        baseline_reliable += 1
    if key in matches:
        if len(stores) >= 3:
            already_reliable_matches += 1
        if len(stores) == 2:
            newly_reliable.append(key)
            per_code_reliable[matches[key]["code"]] += 1
    if len(stores) + (1 if key in matches else 0) >= 3:
        reliable_with_v5 += 1

new_reliable_examples = []
for key in newly_reliable[:100]:
    m = matches[key]
    c = m["card"]
    new_reliable_examples.append({
        "set": c.get("set"),
        "number": c.get("number"),
        "name": c.get("name"),
        "variant": c.get("variant"),
        "timeTwisterPrice": m["price"],
        "setCode": m["code"],
        "setLabelTimeTwister": m["setLabel"],
        "url": m["url"],
    })

report = {
    "testVersion": 5,
    "safety": {
        "cardmarketModified": False,
        "retailModified": False,
        "setMappingMode": "explicit-audited-code-map",
        "exactIdentity": "set+collector+name+variant",
        "language": "Italian",
        "condition": "Near Mint",
        "availableOnly": True,
        "positivePriceOnly": True,
        "specialNumbersAllowed": True,
    },
    "importantCorrection": {
        "V4WrongMapping": "XBLK -> Avventure Insieme",
        "V5Mapping": "XBLK -> Luce Nera",
        "reason": "TimeTwister label is Black Bolt: Additionals",
    },
    "stats": {
        "products": len(products),
        "parsedProducts": stats["parsedProducts"],
        "usableVariantsOnTrustedCodes": stats["usableVariants"],
        "acceptedMatches": len(matches),
        "identityRejected": stats["identityRejected"],
        "invalidTitle": stats["invalidTitle"],
        "duplicateIdentity": stats["duplicateIdentity"],
        "unknownSetCodes": sum(unknown_codes.values()),
        "labelConflicts": sum(label_conflicts.values()),
        "baselineReliableWithoutTimeTwister": baseline_reliable,
        "reliableWithV5": reliable_with_v5,
        "newReliableFromTimeTwisterV5": len(newly_reliable),
        "alreadyReliableMatched": already_reliable_matches,
    },
    "trustedSetCodeMap": TRUSTED_SET_CODE_MAP,
    "matchesPerCode": dict(sorted(per_code.items())),
    "newReliablePerCode": dict(sorted(per_code_reliable.items())),
    "unknownCodes": dict(sorted(unknown_codes.items())),
    "labelConflicts": [
        {"code": code, "label": label, "count": count}
        for (code, label), count in sorted(label_conflicts.items())
    ],
    "xblkCorrectedExamples": xblk_examples,
    "secretNumberExamples": secret_examples,
    "newReliableExamples": new_reliable_examples,
    "identityRejectedExamples": ambiguous_examples,
}

with open(REPORT_FILE, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RISULTATO V5 ===", flush=True)
for k, v in report["stats"].items():
    print(f"{k}: {v}", flush=True)

print("\n=== MATCH PER CODICE SET ===", flush=True)
for code, count in sorted(per_code.items()):
    print(f"{code}: {count}", flush=True)

print("\n=== NUOVE CARTE AFFIDABILI PER CODICE ===", flush=True)
for code, count in sorted(per_code_reliable.items()):
    print(f"{code}: {count}", flush=True)

print("\n=== XBLK CORRETTO: DEVE ESSERE LUCE NERA ===", flush=True)
if xblk_examples:
    for item in xblk_examples[:20]:
        print(json.dumps(item, ensure_ascii=False), flush=True)
else:
    print("Nessun match XBLK trovato.", flush=True)

print("\n=== CARTE OLTRE IL TOTALE SET ===", flush=True)
for item in secret_examples[:20]:
    print(json.dumps(item, ensure_ascii=False), flush=True)

print("\n=== CONFLITTI LABEL/CODICE ===", flush=True)
if label_conflicts:
    for (code, label), count in sorted(label_conflicts.items()):
        print(f"{code} | {label} | {count}", flush=True)
else:
    print("0", flush=True)

print(f"\nReport completo: {REPORT_FILE}", flush=True)
print("SOLO TEST - NESSUNA MODIFICA A CARDMARKET O RETAIL", flush=True)
print("=== FINE AUDIT TIMETWISTER V5 ===", flush=True)
