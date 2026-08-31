#!/usr/bin/env python3
import json
import re
import time
import urllib.request
import unicodedata
from collections import Counter, defaultdict
from difflib import SequenceMatcher

BASE = "https://timetwistergames.it"
COLLECTION_URL = BASE + "/collections/pok-mon-single/products.json?limit=250&page={page}"

TCGDEX_BASE = "https://api.tcgdex.net/v2"
TCGDEX_EN_SETS = TCGDEX_BASE + "/en/sets"
TCGDEX_IT_SETS = TCGDEX_BASE + "/it/sets"
TCGDEX_EN_SET = TCGDEX_BASE + "/en/sets/{set_id}"
TCGDEX_IT_SET = TCGDEX_BASE + "/it/sets/{set_id}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Cardoryx TimeTwister identity validation)",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
    "Connection": "close",
}

REPORT_FILE = "timetwister_identity_report.json"

SUPPORTED_EDITIONS = {
    "normal": "Normal",
    "reverse-holo": "Reverse Holo",
    "reverse holo": "Reverse Holo",
    "reverse": "Reverse Holo",
    "holo": "Holo",
}

# Alias volutamente piccoli e controllati.
# La risoluzione principale resta il nome set TCGdex esatto oppure
# un codice set TimeTwister appreso da prodotti già risolti in modo esatto.
SET_NAME_ALIASES = {
    "pokemon 151": "151",
    "scarlet violet 151": "151",
    "pokemon go": "Pokémon GO",
}

def fetch_json(url, retries=3, timeout=30):
    last = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, timeout=timeout) as response:
                raw = response.read()
                return json.loads(raw.decode("utf-8"))
        except Exception as exc:
            last = exc
            print(f"Tentativo {attempt}/{retries} fallito: {url} -> {exc}", flush=True)
            if attempt < retries:
                time.sleep(2 * attempt)
    raise last

def norm_space(value):
    return re.sub(r"\s+", " ", str(value or "").strip())

def norm_key(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.lower()
    value = value.replace("&", " and ")
    value = value.replace("’", "'")
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()

def norm_name(value):
    value = norm_key(value)
    # Normalizzazioni conservative che non cambiano l'identità della carta.
    value = re.sub(r"\b(v star|vstar)\b", "vstar", value)
    value = re.sub(r"\b(v max|vmax)\b", "vmax", value)
    value = re.sub(r"\b(ex)\b", "ex", value)
    return value

def parse_title(title):
    """
    Formato TimeTwister tipico:
    Card Name - Set Name (Rarity) [SETCODE-123]
    Supporta anche localId tipo TG19 / GG67 / SV107.
    """
    title = norm_space(title)
    m = re.search(
        r"^(.*?)\s+-\s+(.*?)\s+\(([^()]*)\)\s+\[([A-Z0-9]{2,12})-([A-Z]{0,3}\d{1,4})\]\s*$",
        title,
        re.I,
    )
    if not m:
        return None
    return {
        "card_name": norm_space(m.group(1)),
        "set_name": norm_space(m.group(2)),
        "rarity": norm_space(m.group(3)),
        "set_code": m.group(4).upper(),
        "local_id": m.group(5).upper(),
    }

def extract_variant_fields(product, variant):
    options = product.get("options") or []
    option_names = [norm_space(o.get("name")) for o in options if isinstance(o, dict)]
    option_pos = {name.lower(): i + 1 for i, name in enumerate(option_names)}

    option_values = {
        1: norm_space(variant.get("option1")),
        2: norm_space(variant.get("option2")),
        3: norm_space(variant.get("option3")),
    }

    language = ""
    condition = ""
    edition = ""

    for key, pos in option_pos.items():
        value = option_values.get(pos, "")
        if key == "language":
            language = value
        elif key == "condition":
            condition = value
        elif key == "edition":
            edition = value

    joined = list(option_values.values())

    if not language:
        language = next(
            (
                v for v in joined
                if v.lower() in {
                    "italian", "italiano", "ita",
                    "english", "inglese", "eng",
                    "japanese", "jap",
                }
            ),
            "",
        )

    if not condition:
        condition = next(
            (v for v in joined if "near mint" in v.lower() or v.lower() == "nm"),
            "",
        )

    if not edition:
        edition = next(
            (
                v for v in joined
                if any(k in v.lower() for k in ("normal", "reverse", "holo", "foil"))
            ),
            "",
        )

    return language, condition, edition

def get_price(value):
    try:
        price = float(value)
        return price if price > 0 else None
    except Exception:
        return None

def canonical_local_id(value):
    value = norm_space(value).upper()
    m = re.fullmatch(r"([A-Z]{0,3})(\d{1,4})", value)
    if not m:
        return value
    prefix, digits = m.groups()
    return prefix + str(int(digits))

def names_match(source_name, canonical_names):
    """
    Fail-closed:
    - match normalizzato esatto -> accetta
    - similitudine >= 0.94 SOLO se entrambi i nomi hanno almeno 6 caratteri
      e nessuno dei due introduce token alfabetici completamente estranei.
    """
    src = norm_name(source_name)
    if not src:
        return False, 0.0, None

    best_score = 0.0
    best_name = None

    for candidate in canonical_names:
        cand = norm_name(candidate)
        if not cand:
            continue

        if src == cand:
            return True, 1.0, candidate

        score = SequenceMatcher(None, src, cand).ratio()
        if score > best_score:
            best_score = score
            best_name = candidate

        if len(src) >= 6 and len(cand) >= 6 and score >= 0.94:
            src_tokens = {t for t in src.split() if len(t) > 1}
            cand_tokens = {t for t in cand.split() if len(t) > 1}
            # Richiediamo forte sovrapposizione dei token per evitare
            # collisioni tra carte con nomi simili.
            if src_tokens and cand_tokens:
                overlap = len(src_tokens & cand_tokens) / max(len(src_tokens), len(cand_tokens))
                if overlap >= 0.75:
                    return True, score, candidate

    return False, best_score, best_name

def build_set_index(items):
    by_name = {}
    by_id = {}
    for item in items if isinstance(items, list) else []:
        if not isinstance(item, dict):
            continue
        sid = norm_space(item.get("id"))
        name = norm_space(item.get("name"))
        if not sid or not name:
            continue
        by_id[sid] = item
        by_name[norm_key(name)] = sid
    return by_name, by_id

print("=== TIMETWISTER GAMES - TEST IDENTITA TCGDEX V3 ===", flush=True)

# 1) Catalogo TimeTwister
all_products = []
page = 1
errors = []

while page <= 100:
    url = COLLECTION_URL.format(page=page)
    try:
        data = fetch_json(url)
        products = data.get("products") if isinstance(data, dict) else None
        if not isinstance(products, list):
            raise RuntimeError("Risposta TimeTwister senza lista products")

        print(f"Pagina {page}: prodotti {len(products)}", flush=True)

        if not products:
            break

        all_products.extend(products)

        if len(products) < 250:
            break

        page += 1
        time.sleep(0.35)

    except Exception as exc:
        errors.append(f"TimeTwister pagina {page}: {exc}")
        print(f"ERRORE pagina {page}: {exc}", flush=True)
        break

# 2) Indice set TCGdex
try:
    en_sets_raw = fetch_json(TCGDEX_EN_SETS)
    it_sets_raw = fetch_json(TCGDEX_IT_SETS)
except Exception as exc:
    raise SystemExit(f"ERRORE BLOCCANTE TCGdex: {exc}")

en_by_name, en_by_id = build_set_index(en_sets_raw)
it_by_name, it_by_id = build_set_index(it_sets_raw)

# Alias -> TCGdex id usando prima il nome inglese e poi quello italiano
alias_to_set_id = {}
for alias, target_name in SET_NAME_ALIASES.items():
    target_key = norm_key(target_name)
    sid = en_by_name.get(target_key) or it_by_name.get(target_key)
    if sid:
        alias_to_set_id[norm_key(alias)] = sid

# 3) Prima passata: impariamo set_code -> TCGdex set_id SOLO da match esatti del nome set.
code_candidates = defaultdict(Counter)
parsed_products = []

for product in all_products:
    title = norm_space(product.get("title"))
    parsed = parse_title(title)
    parsed_products.append((product, parsed))

    if not parsed:
        continue

    set_key = norm_key(parsed["set_name"])
    set_id = en_by_name.get(set_key) or it_by_name.get(set_key) or alias_to_set_id.get(set_key)
    if set_id:
        code_candidates[parsed["set_code"]][set_id] += 1

code_to_set_id = {}
code_conflicts = {}

for code, counts in code_candidates.items():
    if not counts:
        continue
    ranked = counts.most_common()
    if len(ranked) == 1:
        code_to_set_id[code] = ranked[0][0]
    else:
        # Accettiamo il codice solo se il candidato dominante è inequivocabile.
        best_id, best_count = ranked[0]
        second_count = ranked[1][1]
        if best_count >= 3 and best_count >= second_count * 3:
            code_to_set_id[code] = best_id
        else:
            code_conflicts[code] = ranked[:5]

print(f"Set code appresi in sicurezza: {len(code_to_set_id)}", flush=True)
if code_conflicts:
    print(f"Set code in conflitto: {len(code_conflicts)}", flush=True)

# Cache dettagli set
set_cache = {}

def load_set_cards(set_id):
    if set_id in set_cache:
        return set_cache[set_id]

    en_detail = {}
    it_detail = {}

    try:
        en_detail = fetch_json(TCGDEX_EN_SET.format(set_id=set_id))
    except Exception as exc:
        errors.append(f"TCGdex EN set {set_id}: {exc}")

    try:
        it_detail = fetch_json(TCGDEX_IT_SET.format(set_id=set_id))
    except Exception as exc:
        # Non blocchiamo se la localizzazione IT manca: il titolo TimeTwister è inglese.
        errors.append(f"TCGdex IT set {set_id}: {exc}")

    cards = {}

    for source, lang in ((en_detail, "en"), (it_detail, "it")):
        for card in (source.get("cards") or []) if isinstance(source, dict) else []:
            if not isinstance(card, dict):
                continue
            local_id = canonical_local_id(card.get("localId"))
            if not local_id:
                continue
            entry = cards.setdefault(local_id, {"names": {}, "ids": set()})
            name = norm_space(card.get("name"))
            if name:
                entry["names"][lang] = name
            cid = norm_space(card.get("id"))
            if cid:
                entry["ids"].add(cid)

    set_cache[set_id] = {
        "en": en_detail,
        "it": it_detail,
        "cards": cards,
    }
    time.sleep(0.08)
    return set_cache[set_id]

stats = Counter()
reasons = Counter()
accepted = []
ambiguous = []
rejected_examples = defaultdict(list)

for product, parsed in parsed_products:
    stats["products"] += 1
    title = norm_space(product.get("title"))

    if not parsed:
        stats["invalidTitle"] += 1
        reasons["invalidTitle"] += 1
        if len(rejected_examples["invalidTitle"]) < 20:
            rejected_examples["invalidTitle"].append({"title": title})
        continue

    stats["parsedTitle"] += 1

    set_key = norm_key(parsed["set_name"])
    set_id_by_name = en_by_name.get(set_key) or it_by_name.get(set_key) or alias_to_set_id.get(set_key)
    set_id_by_code = code_to_set_id.get(parsed["set_code"])

    # Se nome e codice danno due set diversi, fail closed.
    if set_id_by_name and set_id_by_code and set_id_by_name != set_id_by_code:
        stats["setConflict"] += 1
        reasons["setConflict"] += 1
        if len(rejected_examples["setConflict"]) < 30:
            rejected_examples["setConflict"].append({
                "title": title,
                "setName": parsed["set_name"],
                "setCode": parsed["set_code"],
                "setByName": set_id_by_name,
                "setByCode": set_id_by_code,
            })
        continue

    set_id = set_id_by_name or set_id_by_code
    if not set_id:
        stats["setRejected"] += 1
        reasons["setRejected"] += 1
        if len(rejected_examples["setRejected"]) < 40:
            rejected_examples["setRejected"].append({
                "title": title,
                "setName": parsed["set_name"],
                "setCode": parsed["set_code"],
            })
        continue

    set_data = load_set_cards(set_id)
    local_id = canonical_local_id(parsed["local_id"])
    canonical = set_data["cards"].get(local_id)

    if not canonical:
        stats["numberRejected"] += 1
        reasons["numberRejected"] += 1
        if len(rejected_examples["numberRejected"]) < 40:
            rejected_examples["numberRejected"].append({
                "title": title,
                "setId": set_id,
                "localId": parsed["local_id"],
            })
        continue

    canonical_names = list(canonical["names"].values())
    name_ok, name_score, matched_name = names_match(parsed["card_name"], canonical_names)

    if not name_ok:
        stats["nameRejected"] += 1
        reasons["nameRejected"] += 1
        item = {
            "title": title,
            "setId": set_id,
            "localId": parsed["local_id"],
            "sourceName": parsed["card_name"],
            "canonicalNames": canonical_names,
            "bestScore": round(name_score, 4),
            "bestName": matched_name,
        }
        ambiguous.append(item)
        if len(rejected_examples["nameRejected"]) < 50:
            rejected_examples["nameRejected"].append(item)
        continue

    variants = product.get("variants") or []
    for variant in variants:
        stats["variants"] += 1

        language, condition, edition = extract_variant_fields(product, variant)

        if language.lower() not in {"italian", "italiano", "ita"}:
            stats["languageRejected"] += 1
            continue

        if not (("near mint" in condition.lower()) or condition.lower() == "nm"):
            stats["conditionRejected"] += 1
            continue

        if variant.get("available") is not True:
            stats["unavailable"] += 1
            continue

        price = get_price(variant.get("price"))
        if price is None:
            stats["priceUnavailable"] += 1
            continue

        edition_key = edition.lower().replace("_", "-").strip()
        canonical_variant = SUPPORTED_EDITIONS.get(edition_key)
        if not canonical_variant:
            stats["editionRejected"] += 1
            continue

        stats["accepted"] += 1
        accepted.append({
            "setId": set_id,
            "setNameTimeTwister": parsed["set_name"],
            "setCodeTimeTwister": parsed["set_code"],
            "localId": parsed["local_id"],
            "cardNameTimeTwister": parsed["card_name"],
            "cardNameCanonical": matched_name,
            "nameScore": round(name_score, 4),
            "rarityTimeTwister": parsed["rarity"],
            "variant": canonical_variant,
            "language": "IT",
            "condition": "NM/MINT",
            "price": price,
            "available": True,
            "sku": variant.get("sku"),
            "handle": product.get("handle"),
            "url": BASE + "/products/" + norm_space(product.get("handle")),
        })

report = {
    "source": "TimeTwister Games",
    "testVersion": 3,
    "strategy": [
        "parse titolo TimeTwister",
        "match set esatto TCGdex EN/IT oppure alias controllato",
        "apprendimento set_code solo da match set esatti",
        "verifica conflitto nome-set vs codice-set",
        "verifica localId/numero dentro il set TCGdex",
        "verifica nome carta conservativa",
        "Language IT",
        "Condition NM",
        "available true",
        "price > 0",
        "Edition esplicita supportata",
    ],
    "stats": dict(stats),
    "reasons": dict(reasons),
    "setCodeMap": dict(sorted(code_to_set_id.items())),
    "setCodeConflicts": code_conflicts,
    "acceptedExamples": accepted[:100],
    "identityAmbiguousExamples": ambiguous[:100],
    "rejectedExamples": dict(rejected_examples),
    "errors": errors,
}

with open(REPORT_FILE, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== RISULTATI ===", flush=True)
for key in (
    "products",
    "parsedTitle",
    "invalidTitle",
    "setRejected",
    "setConflict",
    "numberRejected",
    "nameRejected",
    "variants",
    "languageRejected",
    "conditionRejected",
    "unavailable",
    "priceUnavailable",
    "editionRejected",
    "accepted",
):
    print(f"{key}: {stats.get(key, 0)}", flush=True)

print("\n=== SET CODE -> TCGDEX APPRESI ===", flush=True)
for code, set_id in sorted(code_to_set_id.items()):
    print(f"{code}: {set_id}", flush=True)

if code_conflicts:
    print("\n=== SET CODE IN CONFLITTO - NON USATI ===", flush=True)
    for code, values in sorted(code_conflicts.items()):
        print(f"{code}: {values}", flush=True)

print("\n=== ESEMPI IDENTITY AMBIGUOUS / NAME REJECTED ===", flush=True)
for item in ambiguous[:30]:
    print(json.dumps(item, ensure_ascii=False), flush=True)

print("\n=== ERRORI NON BLOCCANTI ===", flush=True)
if errors:
    for error in errors:
        print(error, flush=True)
else:
    print("0", flush=True)

print(f"\nReport completo salvato in: {REPORT_FILE}", flush=True)
print("SOLO GET - NESSUNA MODIFICA A CARDORYX, CARDMARKET O RETAIL", flush=True)
print("=== FINE TEST TIMETWISTER V3 ===", flush=True)
