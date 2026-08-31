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
REPORT_FILE = "timetwister_matching_report.json"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Cardoryx TimeTwister diagnostic)",
    "Accept": "application/json,text/plain,*/*",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
    "Connection": "close",
}

# Alias già usati in produzione V22.
SET_ALIASES = {
    "brilliant stars": "Astri Lucenti",
    "evolving skies": "Evoluzioni Eteree",
    "fusion strike": "Colpo Fusione",
    "darkness ablaze": "Fiamme Oscure",
    "astral radiance": "Lucentezza Siderale",
    "pokemon go": "Pokémon GO",
    "celebrations": "Gran Festa",
    "battle styles": "Stili di Lotta",
    "crown zenith": "Zenit Regale",
    "151": "151",
    "twilight masquerade": "Crepuscolo Mascherato",
    "mega evolution": "Megaevoluzione",
    "ascended heroes": "Ascesa Eroica",
    "lost origin": "Origine Perduta",
    "chilling reign": "Regno Glaciale",
    "shining fates": "Destino Splendente",
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
    value = str(value or "").strip().upper()
    value = value.replace(" ", "")
    return value

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

print("=== TIMETWISTER - TEST MATCHING V4 ===", flush=True)
print("Nessuna modifica a Cardoryx, Cardmarket o retail.", flush=True)

# ------------------------------------------------------------
# 1. Carica indice retail attuale
# ------------------------------------------------------------
with open(RETAIL_FILE, "r", encoding="utf-8") as f:
    retail = json.load(f)

cards = retail.get("cards") or {}
if not isinstance(cards, dict) or not cards:
    raise SystemExit("ERRORE: data/retail_prices.json non contiene cards")

print(f"Carte indice retail: {len(cards)}", flush=True)

# Indici delle identità già conosciute da Cardoryx.
# A) completo: set + collector + nome + variante
identity_full = defaultdict(list)

# B) senza set: collector + nome + variante.
# Usato SOLO per imparare un codice set quando conduce a un unico set.
identity_without_set = defaultdict(list)

for key, card in cards.items():
    set_name = str(card.get("set") or "").strip()
    name = str(card.get("name") or "").strip()
    variant = str(card.get("variant") or "").strip()
    coll = collector_left(card.get("number"))

    full = (norm(set_name), coll, norm(name), variant)
    identity_full[full].append((key, card))

    loose = (coll, norm(name), variant)
    identity_without_set[loose].append((key, card))

# ------------------------------------------------------------
# 2. Scarica catalogo TimeTwister
# ------------------------------------------------------------
products = []
for page in range(1, 101):
    payload = fetch_json(COLLECTION_URL.format(page=page))
    batch = payload.get("products") if isinstance(payload, dict) else None
    if not isinstance(batch, list):
        raise SystemExit(f"ERRORE: pagina {page} senza lista products")
    print(f"Pagina {page}: {len(batch)} prodotti", flush=True)
    if not batch:
        break
    products.extend(batch)
    if len(batch) < 250:
        break
    time.sleep(0.25)

print(f"Prodotti TimeTwister: {len(products)}", flush=True)

parsed_products = []
for product in products:
    parsed = parse_title(product.get("title"))
    if parsed:
        parsed_products.append((product, parsed))

# ------------------------------------------------------------
# 3. Impara setCode -> set Cardoryx SENZA servizi esterni
#
# Voto ammesso solo se una variante IT+NM+disponibile trova, ignorando
# temporaneamente il set, UNA SOLA identità Cardoryx per:
# collector + nome esatto + variante esatta.
#
# Il codice viene accettato solo con:
# - almeno 2 prove indipendenti
# - 100% delle prove sullo stesso set
#
# Questo è diagnostico e fail-closed.
# ------------------------------------------------------------
code_votes = defaultdict(Counter)
code_examples = defaultdict(list)

for product, parsed in parsed_products:
    for cv, price, shop_variant in usable_variants(product):
        loose = (
            parsed["collector"],
            norm(parsed["name"]),
            cv,
        )
        matches = identity_without_set.get(loose, [])
        sets = {norm(card.get("set")): card.get("set") for _, card in matches}

        if len(matches) == 1 and len(sets) == 1:
            _, card = matches[0]
            set_name = str(card.get("set") or "").strip()
            code_votes[parsed["setCode"]][set_name] += 1
            if len(code_examples[parsed["setCode"]]) < 5:
                code_examples[parsed["setCode"]].append({
                    "title": product.get("title"),
                    "matchedSet": set_name,
                    "variant": cv,
                })

learned_codes = {}
rejected_codes = {}

for code, counts in code_votes.items():
    ranked = counts.most_common()
    total = sum(counts.values())
    if len(ranked) == 1 and ranked[0][1] >= 2:
        learned_codes[code] = ranked[0][0]
    else:
        rejected_codes[code] = {
            "votes": dict(counts),
            "total": total,
        }

# Gli alias manuali hanno priorità.
# Se un codice appreso contraddice un alias del titolo, il singolo prodotto
# verrà scartato come conflitto.
print(f"Codici set appresi con prove univoche: {len(learned_codes)}", flush=True)

# ------------------------------------------------------------
# 4. Confronta V22 attuale vs matching esteso
# ------------------------------------------------------------
stats = Counter()
strict_matches = {}
expanded_matches = {}
examples_new = []
conflicts = []

for product, parsed in parsed_products:
    stats["parsedProducts"] += 1

    alias_set = SET_ALIASES.get(norm(parsed["setLabel"]))
    learned_set = learned_codes.get(parsed["setCode"])

    if alias_set and learned_set and norm(alias_set) != norm(learned_set):
        stats["setConflict"] += 1
        if len(conflicts) < 30:
            conflicts.append({
                "title": product.get("title"),
                "aliasSet": alias_set,
                "learnedSet": learned_set,
                "setCode": parsed["setCode"],
            })
        continue

    for cv, price, shop_variant in usable_variants(product):
        stats["usableVariants"] += 1

        # -------- Metodo V22 attuale --------
        if alias_set:
            full = (
                norm(alias_set),
                parsed["collector"],
                norm(parsed["name"]),
                cv,
            )
            current = identity_full.get(full, [])
            if len(current) == 1:
                key, card = current[0]
                strict_matches[key] = {
                    "card": card,
                    "price": price,
                    "product": product,
                    "parsed": parsed,
                    "variant": cv,
                }

        # -------- Metodo esteso --------
        target_set = alias_set or learned_set
        if not target_set:
            stats["noSetResolution"] += 1
            continue

        full = (
            norm(target_set),
            parsed["collector"],
            norm(parsed["name"]),
            cv,
        )
        matches = identity_full.get(full, [])

        if len(matches) != 1:
            stats["identityRejected"] += 1
            continue

        key, card = matches[0]
        expanded_matches[key] = {
            "card": card,
            "price": price,
            "product": product,
            "parsed": parsed,
            "variant": cv,
            "resolution": "alias" if alias_set else "learned-code",
        }

# ------------------------------------------------------------
# 5. Impatto sulle carte affidabili
# Calcoliamo da zero escludendo TimeTwister già presente.
# ------------------------------------------------------------
def other_stores(card):
    return {
        norm(o.get("store"))
        for o in (card.get("offers") or [])
        if norm(o.get("store")) != norm("TimeTwister Games")
    }

baseline_reliable = 0
current_reliable = 0
expanded_reliable = 0
newly_reliable_current = []
newly_reliable_expanded = []

for key, card in cards.items():
    stores = other_stores(card)
    base_count = len(stores)

    if base_count >= 3:
        baseline_reliable += 1

    with_current = base_count + (1 if key in strict_matches else 0)
    with_expanded = base_count + (1 if key in expanded_matches else 0)

    if with_current >= 3:
        current_reliable += 1
    if with_expanded >= 3:
        expanded_reliable += 1

    if base_count == 2 and key in strict_matches:
        newly_reliable_current.append(key)

    if base_count == 2 and key in expanded_matches:
        newly_reliable_expanded.append(key)

new_keys = sorted(set(expanded_matches) - set(strict_matches))

for key in new_keys[:100]:
    item = expanded_matches[key]
    card = item["card"]
    examples_new.append({
        "set": card.get("set"),
        "number": card.get("number"),
        "name": card.get("name"),
        "variant": card.get("variant"),
        "price": item["price"],
        "setCode": item["parsed"]["setCode"],
        "setLabelTimeTwister": item["parsed"]["setLabel"],
        "resolution": item["resolution"],
        "storesWithoutTimeTwister": len(other_stores(card)),
        "wouldBecomeReliable": len(other_stores(card)) == 2,
        "url": BASE + "/products/" + str(item["product"].get("handle") or ""),
    })

report = {
    "testVersion": 4,
    "method": "local retail identities + conservative learned set codes; no TCGdex",
    "safety": {
        "cardmarketModified": False,
        "retailModified": False,
        "requiresItalian": True,
        "requiresNearMint": True,
        "requiresAvailable": True,
        "requiresPositivePrice": True,
        "requiresExactCollector": True,
        "requiresExactName": True,
        "requiresExactVariant": True,
        "learnedCodeMinimumVotes": 2,
        "learnedCodeMustBeUnanimous": True,
    },
    "stats": {
        "products": len(products),
        "parsedProducts": stats["parsedProducts"],
        "usableVariants": stats["usableVariants"],
        "strictV22Matches": len(strict_matches),
        "expandedMatches": len(expanded_matches),
        "additionalMatches": len(new_keys),
        "learnedSetCodes": len(learned_codes),
        "setConflicts": stats["setConflict"],
        "identityRejected": stats["identityRejected"],
        "noSetResolution": stats["noSetResolution"],
        "baselineReliableWithoutTimeTwister": baseline_reliable,
        "reliableWithCurrentV22Matching": current_reliable,
        "reliableWithExpandedMatching": expanded_reliable,
        "currentV22NewReliable": len(newly_reliable_current),
        "expandedNewReliable": len(newly_reliable_expanded),
        "additionalReliableVsV22": expanded_reliable - current_reliable,
    },
    "learnedSetCodes": dict(sorted(learned_codes.items())),
    "rejectedSetCodes": dict(sorted(rejected_codes.items())),
    "setCodeEvidenceExamples": dict(sorted(code_examples.items())),
    "conflicts": conflicts,
    "additionalMatchExamples": examples_new,
}

with open(REPORT_FILE, "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)

print("\n=== CONFRONTO ===", flush=True)
for k, v in report["stats"].items():
    print(f"{k}: {v}", flush=True)

print("\n=== CODICI SET APPRESI ===", flush=True)
for code, set_name in sorted(learned_codes.items()):
    print(f"{code}: {set_name}", flush=True)

print("\n=== NUOVI MATCH POTENZIALI - PRIMI 40 ===", flush=True)
for item in examples_new[:40]:
    print(json.dumps(item, ensure_ascii=False), flush=True)

print("\n=== CONFLITTI SET - NON ACCETTATI ===", flush=True)
if conflicts:
    for item in conflicts[:20]:
        print(json.dumps(item, ensure_ascii=False), flush=True)
else:
    print("0", flush=True)

print(f"\nReport completo: {REPORT_FILE}", flush=True)
print("SOLO TEST - NESSUNA MODIFICA A CARDMARKET O RETAIL", flush=True)
print("=== FINE TEST TIMETWISTER V4 ===", flush=True)
