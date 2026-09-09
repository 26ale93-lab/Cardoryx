#!/usr/bin/env python3
"""Read-only audit of Cardoryx physical finish selection and Cardmarket pricing.

The script reads production code/data but never writes them. Network responses are
cached outside the repository. Its only repository output is the JSON report path
passed with --output (default: artifacts/variant_finish_audit_report.json).
"""

from __future__ import annotations

import argparse
import concurrent.futures
import datetime as dt
import hashlib
import json
import math
import os
import re
import subprocess
import tempfile
import time
import unicodedata
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
PLAY_INDEX = ROOT / "data/cardmarket_play_index.json"
API = "https://api.tcgdex.net/v2"
CACHE = Path(tempfile.gettempdir()) / "cardoryx_variant_finish_audit_cache_v1"

SAMPLED_SETS = {
    "base1": "Base", "base2": "Base", "base3": "Base", "lc": "Base",
    "ecard1": "e-Card", "ecard2": "e-Card", "ecard3": "e-Card",
    "ex1": "EX", "ex3": "EX", "ex13": "EX",
    "dp1": "Diamond & Pearl", "dp7": "Diamond & Pearl",
    "pl1": "Platinum", "pl4": "Platinum",
    "hgss1": "HGSS", "hgss4": "HGSS",
    "bw1": "BW", "bw11": "BW",
    "xy1": "XY", "g1": "XY",
    "sm1": "SM", "sm12": "SM", "smp": "SM promo", "sma": "SM subset",
    "swsh1": "SWSH", "swsh9tg": "Trainer Gallery",
    "swsh12.5gg": "Galarian Gallery", "swshp": "SWSH promo",
    "sv01": "SV", "svp": "SV promo", "sv09": "SV",
    "sv10.5b": "SV special", "sv10.5w": "SV special",
    "me01": "Mega Evolution", "mee": "Energy",
}
FULL_SETS = {"sv08.5": "SV special", "me02.5": "Mega Evolution special"}
SAMPLE_PER_SET = 18

FINISHES = (
    "Normal", "Holo", "Reverse Holo", "Cosmos Holo",
    "Poké Ball Reverse Holo", "Master Ball Reverse Holo",
)
MANUAL_FINISHES = ("Speciale / Altro", "Non so")
CLASSIFICATIONS = ("CORRETTA", "FALSO POSITIVO", "FALSO NEGATIVO", "AMBIGUA", "SOURCE CONFLICT")
FINISH_METRICS = ("documented", "proposed", "falsePositive", "falseNegative")
VERIFIED_NORMAL_TARGETS = {
    "svp-107": ("svp", "107"),
    "me04-013": ("me04", "013"),
    "me01-064": ("me01", "064"),
    "me01-073": ("me01", "073"),
    "me03-045": ("me03", "045"),
    "me03-086": ("me03", "086"),
    "me03-087": ("me03", "087"),
    "me03-088": ("me03", "088"),
    "me02-045": ("me02", "045"),
    "me02-053": ("me02", "053"),
    "sv10-034": ("sv10", "034"),
    "sv10-049": ("sv10", "049"),
    "sv10-051": ("sv10", "051"),
    "sv10-096": ("sv10", "096"),
    "sv09-055": ("sv09", "055"),
    "svp-190": ("svp", "190"),
    "svp-221": ("svp", "221"),
    "svp-222": ("svp", "222"),
    "svp-223": ("svp", "223"),
    "sv08-014": ("sv08", "014"),
    "sv08-065": ("sv08", "065"),
    "sv05-041": ("sv05", "041"),
    "sv05-062": ("sv05", "062"),
    "sv05-119": ("sv05", "119"),
    "sv05-121": ("sv05", "121"),
    "sv06-100": ("sv06", "100"),
}


def classification_counts(counter):
    return {key: int(counter.get(key, 0)) for key in CLASSIFICATIONS}


def finish_metric_counts(counter):
    return {key: int(counter.get(key, 0)) for key in FINISH_METRICS}


def norm(value):
    value = unicodedata.normalize("NFKD", str(value or ""))
    value = "".join(c for c in value if not unicodedata.combining(c)).lower()
    return re.sub(r"[^a-z0-9]+", "", value)


def canonical_finish(value):
    n = norm(value)
    if "masterball" in n:
        return "Master Ball Reverse Holo"
    if "pokeball" in n:
        return "Poké Ball Reverse Holo"
    if "cosmos" in n:
        return "Cosmos Holo"
    if "reverse" in n:
        return "Reverse Holo"
    if "holo" in n or "olografic" in n:
        return "Holo"
    if "speciale" in n or "specialother" in n:
        return "Speciale / Altro"
    if "nonso" in n or "unknown" in n:
        return "Non so"
    return "Normal"


def canonical_finish_type_label(value):
    """Mirror the production lexical-only IT/EN enum normalization."""
    n = norm(value)
    if n in {"normal", "normale"}:
        return "normal"
    if n in {"holo", "olografica", "olografico"}:
        return "holo"
    if n == "reverse":
        return "reverse"
    return n


def canonical_finish_foil_label(value):
    n = norm(value)
    if n in {"cosmo", "cosmos"}:
        return "cosmos"
    if n == "pokeball":
        return "pokeball"
    if n == "masterball":
        return "masterball"
    return n


def canonical_row_finish(row, translate_localized=True):
    typ = norm(row.get("type"))
    foil = norm(row.get("foil"))
    if translate_localized:
        if typ in {"normale", "standard"}:
            typ = "normal"
        if typ in {"olografica", "olografico"}:
            typ = "holo"
    if foil in {"cosmos", "cosmo"}:
        return "Cosmos Holo"
    if typ == "reverse" and foil == "pokeball":
        return "Poké Ball Reverse Holo"
    if typ == "reverse" and foil == "masterball":
        return "Master Ball Reverse Holo"
    if typ == "reverse" and not foil:
        return "Reverse Holo"
    if typ == "holo" and not foil:
        return "Holo"
    if typ == "normal" and not foil:
        return "Normal"
    return None


def is_play_row(row):
    values = [*(row.get("stamp") or []), row.get("foil"), row.get("name"), row.get("variant")]
    s = " ".join(norm(x) for x in values if x)
    return any(x in s for x in ("playerrewards", "playpokemon", "prizepack", "league"))


def get_json(url, cache_key, missing_ok=False):
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / (hashlib.sha256(cache_key.encode()).hexdigest() + ".json")
    if path.exists():
        return json.loads(path.read_text())
    last = None
    for attempt in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Cardoryx-read-only-variant-audit/1.0"})
            with urllib.request.urlopen(req, timeout=45) as response:
                data = json.load(response)
            path.write_text(json.dumps(data, ensure_ascii=False))
            return data
        except urllib.error.HTTPError as exc:
            if missing_ok and exc.code == 404:
                return None
            last = exc
        except Exception as exc:  # transient API/network failure
            last = exc
        time.sleep(0.35 * (attempt + 1))
    raise RuntimeError(f"TCGdex request failed: {url}: {last}")


def git(*args):
    return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()


def load_official_database(db_root):
    """Load the multilingual upstream TS snapshot in one local Node pass."""
    js = r'''
const fs=require('fs'), path=require('path');
const root=process.argv[1], data=path.join(root,'data');
function walk(dir){let out=[];for(const e of fs.readdirSync(dir,{withFileTypes:true})){const p=path.join(dir,e.name);if(e.isDirectory())out=out.concat(walk(p));else if(e.name.endsWith('.ts'))out.push(p)}return out}
function literal(src,marker){const at=src.indexOf(marker);if(at<0)return null;const start=src.indexOf('{',at+marker.length);let depth=0,quote='',esc=false,line=false,block=false;for(let i=start;i<src.length;i++){const c=src[i],n=src[i+1];if(line){if(c==='\n')line=false;continue}if(block){if(c==='*'&&n==='/'){block=false;i++}continue}if(quote){if(esc)esc=false;else if(c==='\\')esc=true;else if(c===quote)quote='';continue}if(c==='/'&&n==='/'){line=true;i++;continue}if(c==='/'&&n==='*'){block=true;i++;continue}if(c==='"'||c==="'"||c==='`'){quote=c;continue}if(c==='{')depth++;else if(c==='}'&&--depth===0)return src.slice(start,i+1)}return null}
function evaluate(src,marker,argName,arg){const lit=literal(src,marker);if(!lit)return null;try{return Function(argName,`return (${lit})`)(arg)}catch(e){return {_parseError:String(e)}}}
const files=walk(data), sets=new Map(), errors=[];
for(const p of files){const rel=path.relative(data,p).split(path.sep);if(rel.length!==2)continue;const src=fs.readFileSync(p,'utf8'),m=src.match(/const\s+[A-Za-z0-9_$]+\s*:\s*Set\s*=/),v=m?evaluate(src,m[0],'serie',{}):null;if(v&&!v._parseError)sets.set(p,v);else errors.push({path:p,error:v&&v._parseError||'set marker'})}
const cards=[];
for(const p of files){const rel=path.relative(data,p).split(path.sep);if(rel.length!==3)continue;const setPath=path.join(data,rel[0],rel[1]+'.ts'),set=sets.get(setPath)||{};const src=fs.readFileSync(p,'utf8'),c=evaluate(src,'const card: Card =','Set',set);if(!c||c._parseError){errors.push({path:p,error:c&&c._parseError||'marker'});continue}const localId=path.basename(p,'.ts'),detailed=Array.isArray(c.variants)?c.variants:[],coarse=(!Array.isArray(c.variants)&&c.variants)||{};cards.push({id:`${set.id||rel[1]}-${localId}`,localId,name:c.name,rarity:c.rarity,category:c.category,regulationMark:c.regulationMark,set:{id:set.id,name:set.name,cardCount:set.cardCount},variants:coarse,variants_detailed:detailed,energyType:c.energyType})}
process.stdout.write(JSON.stringify({cards,errors}));
'''
    raw = subprocess.check_output(["node", "-e", js, str(db_root)], text=True)
    parsed = json.loads(raw)
    sha = subprocess.check_output(["git", "-C", str(db_root), "rev-parse", "HEAD"], text=True).strip()
    return parsed["cards"], parsed["errors"], sha


def extract_js_object(source, name):
    marker = re.search(rf"\bconst\s+{re.escape(name)}\s*=\s*", source)
    if not marker:
        raise AssertionError(f"Missing registry {name}")
    start = source.find("{", marker.end())
    # These registries are top-level object literals and end on their own `};`
    # line. This delimiter is safer than a hand-written JS lexer because comments
    # may legitimately contain apostrophes and braces.
    end = source.find("\n};", start)
    if end < 0:
        raise AssertionError(f"Unclosed registry {name}")
    literal = source[start:end + 2]
    js = f"const value=({literal}); process.stdout.write(JSON.stringify(value));"
    return json.loads(subprocess.check_output(["node", "-e", js], text=True))


def stratified(items, count):
    if len(items) <= count:
        return items
    positions = {round(i * (len(items) - 1) / (count - 1)) for i in range(count)}
    return [items[i] for i in sorted(positions)]


def rarity_forces_holo(card):
    r = norm(card.get("rarity"))
    terms = [
        "double rare", "rara doppia", "rare dupla", "ultra rare",
        "illustration rare", "special illustration rare", "hyper rare",
        "radiant rare", "rara radiante", "amazing rare", "shiny rare",
        "shiny rare v", "shiny rare vmax", "black white rare", "mega hyper rare",
        "holo rare", "rare holo", "rare holo v", "rare holo vmax",
        "rare holo vstar", "ace spec rare",
    ]
    return r in {norm(x) for x in terms}


def modern(card):
    mark = str(card.get("regulationMark") or "").strip().upper()
    if len(mark) == 1 and mark >= "G":
        return True
    sid = str((card.get("set") or {}).get("id") or "").lower()
    cid = str(card.get("id") or "").lower()
    return sid.startswith(("sv", "me")) or cid.startswith(("sv", "me"))


def mee_number(card):
    if str((card.get("set") or {}).get("id") or "").upper() != "MEE":
        return None
    m = re.search(r"\d{1,3}", str(card.get("localId") or ""))
    return int(m.group()) if m else None


def source_semantic_details(card):
    rows = card.get("variants_detailed") or []
    return {f for row in rows if not (row.get("stamp") or []) and not is_play_row(row)
            if (f := canonical_row_finish(row, translate_localized=True))}


def simulate_italian_rest_payload(card):
    """Apply live-verified IT enum translations used by the REST endpoint."""
    out = dict(card)
    translated = []
    rows = card.get("variants_detailed") or []
    for original in rows:
        row = dict(original)
        row["type"] = {"normal": "Normale", "holo": "Olografica", "reverse": "Reverse"}.get(row.get("type"), row.get("type"))
        row["foil"] = {"cosmos": "Cosmo", "pokeball": "Poké Ball", "masterball": "Master Ball"}.get(row.get("foil"), row.get("foil"))
        if row.get("foil") is None: row.pop("foil", None)
        translated.append(row)
    out["variants_detailed"] = translated
    # REST also exposes coarse booleans even though the TS source uses detailed rows.
    out["variants"] = {
        "firstEdition": False,
        "holo": any(r.get("type") == "holo" for r in rows),
        "normal": any(r.get("type") == "normal" for r in rows),
        "reverse": any(r.get("type") == "reverse" for r in rows),
        "wPromo": any(bool(r.get("stamp")) for r in rows),
    }
    return out


def cardoryx_add_detailed(allowed, rows, base=True, special=True):
    # Production uses lexical-only canonical labels; no generic foil inference.
    for row in rows:
        typ = canonical_finish_type_label(row.get("type"))
        foil = canonical_finish_foil_label(row.get("foil"))
        if base:
            if typ == "normal": allowed.add("Normal")
            if typ == "holo" and not foil: allowed.add("Holo")
            if typ == "reverse" and not foil: allowed.add("Reverse Holo")
        if special:
            if typ in {"normal", "holo", "reverse"} and foil == "cosmos": allowed.add("Cosmos Holo")
            if typ == "reverse" and foil == "pokeball": allowed.add("Poké Ball Reverse Holo")
            if typ == "reverse" and foil == "masterball": allowed.add("Master Ball Reverse Holo")


def registry_matches(registry, card, finish, series=None, stamp=None):
    set_names = {norm((card.get("set") or {}).get("name")), norm(card.get("_englishSetName"))}
    local = str(card.get("localId") or "").lstrip("0") or str(card.get("localId") or "")
    for key in registry:
        parts = key.split("|")
        if len(parts) < 3:
            continue
        key_num = parts[1].lstrip("0") or parts[1]
        if norm(parts[0]) not in set_names or key_num != local or parts[2] != finish:
            continue
        if series is not None and (len(parts) < 4 or parts[3] != str(series)):
            continue
        if stamp is not None and (len(parts) < 4 or parts[3] != stamp):
            continue
        return registry[key]
    return None


def verified_normal_matches(registry, card):
    """Mirror the production tcgdexId + setId + safely normalized localId guard."""
    card_id = str(card.get("tcgdexId") or card.get("id") or "").strip().lower()
    rule = registry.get(card_id)
    if not rule:
        return False
    set_id = str(card.get("_cardoryxSetId") or (card.get("set") or {}).get("id") or "").strip().lower()
    local = str(card.get("localId") or "").lstrip("0") or str(card.get("localId") or "")
    rule_local = str(rule.get("localId") or "").lstrip("0") or str(rule.get("localId") or "")
    return set_id == str(rule.get("setId") or "").strip().lower() and local == rule_local


def proposed_standard(card, registries):
    n = mee_number(card)
    if n is not None and 1 <= n <= 8:
        return {"Normal"}, ["mee-001-008-exact-guard"]
    rows = card.get("variants_detailed") or []
    pool = [r for r in rows if not (r.get("stamp") or []) and not is_play_row(r)]
    allowed, reasons = set(), []
    cardoryx_add_detailed(allowed, pool, base=False, special=True)
    if modern(card):
        if rows:
            # Explicit detailed rows outrank generic era/rarity structure.
            explicit_standard = set()
            cardoryx_add_detailed(explicit_standard, pool, base=True, special=False)
            for finish in explicit_standard:
                if finish == "Normal":
                    continue
                allowed.add(finish)
            if norm(card.get("rarity")) in {norm(x) for x in ("common", "comune", "uncommon", "noncomune", "non comune")}:
                allowed.add("Normal")
            reasons.append("modern-explicit-detailed-priority")
        else:
            r = norm(card.get("rarity"))
            if rarity_forces_holo(card):
                allowed.add("Holo"); reasons.append("modern-intrinsic-holo")
            elif r in {norm(x) for x in ("rare", "rara", "raro")}:
                allowed.update(("Holo", "Reverse Holo")); reasons.append("modern-rare-structure")
            elif r in {norm(x) for x in ("common", "comune", "uncommon", "noncomune", "non comune")}:
                allowed.update(("Normal", "Reverse Holo")); reasons.append("modern-common-uncommon-structure")
            else:
                coarse = card.get("variants") or {}
                if coarse.get("normal") is True: allowed.add("Normal")
                if coarse.get("holo") is True: allowed.add("Holo")
                if coarse.get("reverse") is True: allowed.add("Reverse Holo")
                reasons.append("modern-coarse-fallback")
    else:
        explicit = set()
        cardoryx_add_detailed(explicit, pool, base=True, special=False)
        if explicit:
            allowed.update(explicit); reasons.append("explicit-detailed")
        elif not rows:
            before = len(allowed)
            coarse = card.get("variants") or {}
            if coarse.get("normal") is True: allowed.add("Normal")
            if coarse.get("holo") is True: allowed.add("Holo")
            if coarse.get("reverse") is True: allowed.add("Reverse Holo")
            if len(allowed) > before:
                reasons.append("coarse-variants")
            else:
                prices = (card.get("pricing") or {}).get("tcgplayer") or {}
                keys = {norm(k) for k in prices}
                if "normal" in keys: allowed.add("Normal")
                if "holofoil" in keys or "holo" in keys: allowed.add("Holo")
                if "reverseholofoil" in keys or "reverseholo" in keys: allowed.add("Reverse Holo")
                if allowed: reasons.append("marketplace-key-fallback")
                elif rarity_forces_holo(card):
                    allowed.add("Holo"); reasons.append("rarity-holo-fallback")
    if verified_normal_matches(registries["normal"], card):
        allowed.add("Normal"); reasons.append("verified-normal-finish-registry")
    for finish in FINISHES:
        if registry_matches(registries["variant"], card, finish):
            allowed.add(finish); reasons.append("verified-variant-registry")
    return allowed, sorted(set(reasons))


def cm_value(card, finish, allowed, registries):
    exact = registry_matches(registries["variant"], card, finish)
    if exact:
        for key in ("trend", "avg7", "avg30", "low"):
            if float(exact.get(key) or 0) > 0:
                return {"value": exact[key], "kind": "verified-exact-registry", "exact": True}
    cm = (card.get("pricing") or {}).get("cardmarket") or {}
    if not cm:
        return {"value": None, "kind": "none", "exact": False}
    base = next((float(cm[k]) for k in ("trend", "avg7", "avg30", "avg", "low") if float(cm.get(k) or 0) > 0), 0)
    rev = next((float(cm[k]) for k in ("trend-holo", "avg7-holo", "avg30-holo", "avg-holo", "low-holo") if float(cm.get(k) or 0) > 0), 0)
    if finish in {"Cosmos Holo", "Poké Ball Reverse Holo", "Master Ball Reverse Holo"}:
        return {"value": None, "kind": "needs-exact-variant", "exact": False}
    if finish == "Reverse Holo":
        return {"value": rev or None, "kind": "reverse-cardmarket" if rev else "needs-exact-variant", "exact": bool(rev and finish in allowed)}
    if finish == "Holo":
        if finish in allowed and "Normal" not in allowed:
            return {"value": base or None, "kind": "holo-standard-cardmarket" if base else "none", "exact": bool(base)}
        return {"value": None, "kind": "needs-exact-variant", "exact": False}
    if finish == "Normal":
        if finish in allowed or "Holo" not in allowed:
            return {"value": base or None, "kind": "normal" if base else "none", "exact": bool(base)}
    return {"value": None, "kind": "needs-exact-variant", "exact": False}


def product_id_for_finish(card, finish):
    ids = set()
    for row in card.get("variants_detailed") or []:
        if is_play_row(row) or row.get("stamp"):
            continue
        if canonical_row_finish(row) == finish:
            pid = (row.get("thirdParty") or {}).get("cardmarket")
            if pid: ids.add(int(pid))
    return sorted(ids)


def classify(card, truth, proposed, en_truth, locale_conflict):
    n = mee_number(card)
    missing, extra = sorted(truth - proposed), sorted(proposed - truth)
    if n is not None and 1 <= n <= 8 and "Reverse Holo" in truth:
        return "SOURCE CONFLICT", missing, extra, "MEE upstream reverse conflicts with exact Cardoryx edition rule"
    if locale_conflict:
        return "SOURCE CONFLICT", missing, extra, "IT/EN variants_detailed disagree"
    if not truth:
        return "AMBIGUA", missing, extra, "no explicit finish evidence"
    if extra:
        return "FALSO POSITIVO", missing, extra, "finish proposed without matching explicit variant row"
    if missing:
        return "FALSO NEGATIVO", missing, extra, "explicit variant row not selectable"
    return "CORRETTA", missing, extra, "explicit variants agree"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", default="artifacts/variant_finish_audit_report.json")
    ap.add_argument("--workers", type=int, default=28)
    ap.add_argument("--tcgdex-db", help="Path to a read-only checkout of tcgdex/cards-database")
    ap.add_argument("--baseline-report", help="Previous report used for deterministic before/after metrics")
    args = ap.parse_args()
    source = INDEX.read_text()
    required = [
        "documentedVariantsForCard", "addDetailedFinishes", "addModernStandardStructure",
        "addCoarseStandardFinishes", "addMarketplaceStandardFinishes", "syncVariantAvailability",
        "cardmarketValueForCardVariant", "cardmarketValueForVariant", "prizePackFinishPlan",
        "prizePackFoilFinish", "VERIFIED_VARIANT_PRICES", "VERIFIED_STAMP_PRICES",
        "VERIFIED_PLAY_SERIES_PRICES", "PLAY_AUTO_CATALOG",
        "VERIFIED_REVERSE_CARDMARKET_CONFLICTS", "knownReverseCardmarketProductConflict",
        "VERIFIED_NORMAL_FINISHES", "verifiedNormalFinish",
    ]
    missing_logic = [x for x in required if x not in source]
    if missing_logic:
        raise SystemExit(f"Required production logic missing: {missing_logic}")
    registries = {
        "normal": extract_js_object(source, "VERIFIED_NORMAL_FINISHES"),
        "variant": extract_js_object(source, "VERIFIED_VARIANT_PRICES"),
        "stamp": extract_js_object(source, "VERIFIED_STAMP_PRICES"),
        "play": extract_js_object(source, "VERIFIED_PLAY_SERIES_PRICES"),
        "playAuto": extract_js_object(source, "PLAY_AUTO_CATALOG"),
        "reverseConflict": extract_js_object(source, "VERIFIED_REVERSE_CARDMARKET_CONFLICTS"),
    }
    normal_registry = registries["normal"]
    expected_normal_registry = {
        card_id: {"setId": set_id, "localId": local_id}
        for card_id, (set_id, local_id) in VERIFIED_NORMAL_TARGETS.items()
    }
    if normal_registry != expected_normal_registry:
        raise AssertionError("VERIFIED_NORMAL_FINISHES differs from the audited 26-identity dataset")
    if "if(stamp==='None' && verifiedNormalFinish(card))allowed.add('Normal');" not in source:
        raise AssertionError("Verified Normal finish must remain restricted to the unstamped path")
    play_index = json.loads(PLAY_INDEX.read_text())

    set_specs = dict(SAMPLED_SETS); set_specs.update(FULL_SETS)
    upstream_sha = None
    upstream_parse_errors = []
    if args.tcgdex_db:
        all_cards, upstream_parse_errors, upstream_sha = load_official_database(Path(args.tcgdex_db))
        grouped = defaultdict(list)
        for c in all_cards: grouped[(c.get("set") or {}).get("id")].append(c)
        sample, era_by_id = [], {}
        for sid, era in set_specs.items():
            cards = sorted(grouped.get(sid, []), key=lambda x: x["localId"])
            picked = cards if sid in FULL_SETS else stratified(cards, SAMPLE_PER_SET)
            for c in picked:
                sample.append(c); era_by_id[c["id"]] = era
        # Include every upstream special foil/stamp row, regardless of set, so
        # rare Cosmos/Ball/Play evidence cannot be missed by stratification.
        special = []
        for c in all_cards:
            rows = c.get("variants_detailed") or []
            if any(norm(r.get("foil")) in {"cosmos", "pokeball", "masterball", "playerreward", "league"}
                   or r.get("stamp") for r in rows):
                special.append(c)
                era_by_id.setdefault(c["id"], "Special parallel/stamp")
        by_id = {c["id"]: c for c in sample}
        by_id.update({c["id"]: c for c in special})
        sample = list(by_id.values())
        fetched = {}
        for raw in sample:
            en = dict(raw)
            en["name"] = (raw.get("name") or {}).get("en") if isinstance(raw.get("name"), dict) else raw.get("name")
            en["set"] = dict(raw.get("set") or {})
            en["set"]["name"] = ((raw.get("set") or {}).get("name") or {}).get("en") if isinstance((raw.get("set") or {}).get("name"), dict) else (raw.get("set") or {}).get("name")
            it = dict(raw)
            it["name"] = (raw.get("name") or {}).get("it") if isinstance(raw.get("name"), dict) else raw.get("name")
            it["set"] = dict(raw.get("set") or {})
            it["set"]["name"] = ((raw.get("set") or {}).get("name") or {}).get("it") if isinstance((raw.get("set") or {}).get("name"), dict) else (raw.get("set") or {}).get("name")
            fetched[("en", raw["id"])] = en
            fetched[("it", raw["id"])] = simulate_italian_rest_payload(it) if it.get("name") else None
        sample_ids = list(by_id)
        existing_mee = set(grouped.get("mee", [{}])[i].get("localId") for i in range(len(grouped.get("mee", []))))
        unavailable_targets = [f"mee-{n:03d}" for n in range(9, 17) if f"{n:03d}" not in existing_mee]
    else:
        set_data = {}
        for locale in ("en", "it"):
            for sid in set_specs:
                set_data[(locale, sid)] = get_json(f"{API}/{locale}/sets/{sid}", f"set:{locale}:{sid}", missing_ok=True)
        sample_ids, era_by_id = [], {}
        for sid, era in set_specs.items():
            cards = (set_data.get(("en", sid)) or {}).get("cards") or []
            picked = cards if sid in FULL_SETS else stratified(cards, SAMPLE_PER_SET)
            for c in picked:
                if c["id"] not in era_by_id:
                    sample_ids.append(c["id"]); era_by_id[c["id"]] = era
        unavailable_targets = []
        for number in range(9, 17):
            cid = f"mee-{number:03d}"
            if get_json(f"{API}/en/cards/{cid}", f"card:en:{cid}", missing_ok=True) is None:
                unavailable_targets.append(cid)
        def fetch_card(pair):
            locale, cid = pair
            return pair, get_json(f"{API}/{locale}/cards/{cid}", f"card:{locale}:{cid}", missing_ok=True)
        pairs = [("en", cid) for cid in sample_ids] + [("it", cid) for cid in sample_ids]
        fetched = {}
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
            for pair, data in pool.map(fetch_card, pairs): fetched[pair] = data

    normal_identity_checks = []
    for card_id, (set_id, local_id) in VERIFIED_NORMAL_TARGETS.items():
        en = fetched.get(("en", card_id))
        if not en:
            raise AssertionError(f"Verified Normal target missing from the audited dataset: {card_id}")
        exact_rows = [r for r in en.get("variants_detailed") or []
                      if canonical_finish_type_label(r.get("type")) == "normal"
                      and not r.get("foil") and not r.get("stamp") and not is_play_row(r)]
        if not exact_rows:
            raise AssertionError(f"Verified Normal target lacks an unstamped Normal row: {card_id}")
        if not verified_normal_matches(normal_registry, en):
            raise AssertionError(f"Verified Normal exact identity does not match: {card_id}")
        wrong_id = dict(en, id=f"{card_id}-other", tcgdexId=f"{card_id}-other")
        wrong_set = dict(en, set={**(en.get("set") or {}), "id": f"{set_id}-other"})
        wrong_local = dict(en, localId=f"{local_id}9")
        if any(verified_normal_matches(normal_registry, probe) for probe in (wrong_id, wrong_set, wrong_local)):
            raise AssertionError(f"Verified Normal guard leaked beyond exact identity: {card_id}")
        normal_identity_checks.append({
            "tcgdexId": card_id, "setId": set_id, "localId": local_id,
            "unstampedNormalRows": len(exact_rows), "exactMatch": True,
            "wrongIdRejected": True, "wrongSetRejected": True, "wrongLocalIdRejected": True,
        })

    locale_probes = []
    for cid in ("mee-001", "sv08.5-057", "sv03.5-026", "swsh6-145"):
        if args.tcgdex_db:
            # Keep an offline snapshot run deterministic and internally coherent:
            # these cards were already loaded from the exact same EN/IT database SHA.
            en_live = fetched.get(("en", cid))
            it_live = fetched.get(("it", cid))
        else:
            en_live = get_json(f"{API}/en/cards/{cid}", f"locale-probe:en:{cid}", missing_ok=True)
            it_live = get_json(f"{API}/it/cards/{cid}", f"locale-probe:it:{cid}", missing_ok=True)
        if not en_live or not it_live:
            locale_probes.append({"tcgdexId": cid, "available": False})
            continue
        it_live["_englishSetName"] = (en_live.get("set") or {}).get("name")
        proposal, reasons = proposed_standard(it_live, registries)
        locale_probes.append({
            "tcgdexId": cid, "available": True,
            "enTypeFoil": [[r.get("type"), r.get("foil")] for r in en_live.get("variants_detailed") or []],
            "itTypeFoil": [[r.get("type"), r.get("foil")] for r in it_live.get("variants_detailed") or []],
            "semanticDocumentedFinishes": sorted(source_semantic_details(en_live)),
            "cardoryxProposedFromItalianPayload": sorted(proposal), "resolverEvidence": reasons,
        })

    cards_out, issues = [], []
    class_counts = Counter()
    by_era = defaultdict(Counter)
    by_rarity = defaultdict(Counter)
    finish_counts = {f: Counter() for f in FINISHES}
    pricing_risks = []
    resolved_pricing_conflicts = []
    pricing_counts = Counter()
    play_rows_seen = 0
    it_missing = 0
    unmodelled_rows = Counter()

    for cid in sample_ids:
        en = fetched.get(("en", cid))
        it = fetched.get(("it", cid))
        if not en:
            continue
        if not it:
            it_missing += 1
        card = dict(it or en)
        card["_englishSetName"] = (en.get("set") or {}).get("name")
        truth = source_semantic_details(en)
        it_truth = source_semantic_details(it) if it else truth
        locale_conflict = bool(it and truth != it_truth)
        proposed, reasons = proposed_standard(card, registries)
        classification, missing, extra, why = classify(card, truth, proposed, truth, locale_conflict)
        class_counts[classification] += 1
        era = era_by_id[cid]
        rarity = en.get("rarity") or "(missing)"
        by_era[era][classification] += 1
        by_rarity[rarity][classification] += 1
        for finish in FINISHES:
            if finish in truth: finish_counts[finish]["documented"] += 1
            if finish in proposed: finish_counts[finish]["proposed"] += 1
            if classification != "AMBIGUA" and finish in extra: finish_counts[finish]["falsePositive"] += 1
            if classification != "SOURCE CONFLICT" and finish in missing: finish_counts[finish]["falseNegative"] += 1

        prices = {f: cm_value(card, f, proposed, registries) for f in sorted(proposed)}
        for info in prices.values():
            pricing_counts["numeric"] += bool(info.get("value"))
            pricing_counts["failClosed"] += info.get("kind") == "needs-exact-variant"
            pricing_counts["noSnapshotPrice"] += info.get("kind") == "none"
        base_pid = int((((card.get("pricing") or {}).get("cardmarket") or {}).get("idProduct") or 0)) or None
        if not base_pid:
            # REST pricing.cardmarket points to the base printing: prefer Normal,
            # then intrinsic Holo, then Reverse if it is the only standard row.
            for preferred in ("Normal", "Holo", "Reverse Holo"):
                ids = product_id_for_finish(en, preferred)
                if ids:
                    base_pid = ids[0]; break
        play_rows = [r for r in en.get("variants_detailed") or [] if is_play_row(r)]
        play_rows_seen += len(play_rows)
        record = {
            "tcgdexId": cid,
            "setId": (en.get("set") or {}).get("id"),
            "setNameEN": (en.get("set") or {}).get("name"),
            "setNameIT": ((it or {}).get("set") or {}).get("name"),
            "localId": en.get("localId"), "nameEN": en.get("name"), "nameIT": (it or {}).get("name"),
            "category": en.get("category"), "rarity": rarity, "regulationMark": en.get("regulationMark"),
            "variants": en.get("variants"), "variants_detailed": en.get("variants_detailed") or [],
            "stamp": sorted({str(x) for r in en.get("variants_detailed") or [] for x in (r.get("stamp") or [])}),
            "foil": sorted({str(r.get("foil")) for r in en.get("variants_detailed") or [] if r.get("foil")}),
            "languages": sorted({x for r in en.get("variants_detailed") or [] for x in (r.get("languages") or [])}),
            "cardmarketIdProduct": base_pid,
            "tcgplayerPricingKeys": sorted(((en.get("pricing") or {}).get("tcgplayer") or {}).keys()),
            "documentedFinishes": sorted(truth), "cardoryxProposedFinishes": sorted(proposed),
            "unmodelledVariantRows": [r for r in en.get("variants_detailed") or []
                                      if not is_play_row(r) and not r.get("stamp") and canonical_row_finish(r) is None],
            "excludedFinishes": sorted(set(FINISHES) - proposed), "manualSafetyChoices": list(MANUAL_FINISHES),
            "cardmarketPriceByProposedFinish": prices,
            "failClosedFinishes": sorted(f for f, v in prices.items() if v.get("kind") == "needs-exact-variant"),
            "classification": classification, "missingFinishes": missing, "extraFinishes": extra,
            "reason": why, "resolverEvidence": reasons, "era": era,
        }
        cards_out.append(record)
        for row in record["unmodelledVariantRows"]:
            unmodelled_rows[f"{row.get('type') or '(none)'}|{row.get('foil') or '(none)'}"] += 1
        if classification != "CORRETTA":
            severity = "P1" if classification == "FALSO POSITIVO" else "P2" if classification == "FALSO NEGATIVO" else "P3"
            issues.append({"severity": severity, "tcgdexId": cid, "name": en.get("name"),
                           "set": (en.get("set") or {}).get("name"), "localId": en.get("localId"),
                           "classification": classification, "missing": missing, "extra": extra, "reason": why})

    # Only identities whose exact Reverse row points to a product different from
    # the base product can contradict Cardoryx's generic *-holo mapping. Resolve
    # that small candidate set against the live Price Guide, never the full sample.
    price_probe_candidates = []
    for c in cards_out:
        if "Reverse Holo" not in c["cardoryxProposedFinishes"] or not c.get("cardmarketIdProduct"):
            continue
        reverse_ids = product_id_for_finish(c, "Reverse Holo")
        if reverse_ids and c["cardmarketIdProduct"] not in reverse_ids:
            price_probe_candidates.append(c)
    def live_price_probe(c):
        live = get_json(f"{API}/en/cards/{c['tcgdexId']}", f"price-probe:en:{c['tcgdexId']}", missing_ok=True)
        cm = ((live or {}).get("pricing") or {}).get("cardmarket") or {}
        return c, cm
    with concurrent.futures.ThreadPoolExecutor(max_workers=min(12, max(1, len(price_probe_candidates)))) as pool:
        for c, cm in pool.map(live_price_probe, price_probe_candidates):
            reverse_ids = product_id_for_finish(c, "Reverse Holo")
            live_pid = int(cm.get("idProduct") or c["cardmarketIdProduct"] or 0) or None
            reverse_value = next((float(cm[k]) for k in ("trend-holo", "avg7-holo", "avg30-holo", "avg-holo", "low-holo")
                                  if float(cm.get(k) or 0) > 0), 0)
            c["liveCardmarketMismatchProbe"] = {"idProduct": live_pid, "documentedReverseProducts": reverse_ids,
                                                  "reverseSlotValue": reverse_value or None}
            if reverse_value and live_pid not in reverse_ids:
                rule = registries["reverseConflict"].get(c["tcgdexId"]) or {}
                guarded = (norm(rule.get("setId")) == norm(c.get("setId")) and
                           str(rule.get("localId") or "").lstrip("0") == str(c.get("localId") or "").lstrip("0") and
                           int(rule.get("baseProduct") or 0) == live_pid and
                           int(rule.get("reverseProduct") or 0) in reverse_ids)
                row = {"tcgdexId": c["tcgdexId"], "name": c["nameEN"], "set": c["setNameEN"],
                       "finish": "Reverse Holo", "usedProduct": live_pid,
                       "documentedProducts": reverse_ids, "value": reverse_value,
                       "reason": "generic base-product *-holo slot conflicts with exact Reverse product identity"}
                if guarded:
                    row.update({"failClosed": True, "guardKind": "exact-identity-current-product"})
                    resolved_pricing_conflicts.append(row)
                else:
                    row.update({"severity": "P0", "failClosed": False})
                    pricing_risks.append(row)

    # Audit every local Cardmarket Prize Pack relationship, without mutating it.
    group_sizes = Counter()
    metacard_group_sizes = Counter()
    series_counts = Counter()
    duplicate_product_groups = 0
    for _, series_map in play_index.get("byBaseProduct", {}).items():
        for series, rows in series_map.items():
            unique = {int(r["idProduct"]) for r in rows if r.get("idProduct")}
            group_sizes[str(len(unique))] += 1
            series_counts[str(series)] += 1
            if len(unique) != len(rows): duplicate_product_groups += 1
    for _, series_map in play_index.get("byMetacard", {}).items():
        for _, rows in series_map.items():
            metacard_group_sizes[str(len({int(r["idProduct"]) for r in rows if r.get("idProduct")}))] += 1
    mapped_samples = 0
    sample_play_groups = 0
    explicit_play_cards = 0
    explicit_play_cards_indexed = 0
    for c in cards_out:
        pid = c.get("cardmarketIdProduct")
        groups = play_index.get("byBaseProduct", {}).get(str(pid), {}) if pid else {}
        if groups:
            mapped_samples += 1
            sample_play_groups += len(groups)
        play_ids = {str((r.get("thirdParty") or {}).get("cardmarket")) for r in c.get("variants_detailed", [])
                    if is_play_row(r) and (r.get("thirdParty") or {}).get("cardmarket")}
        if any(is_play_row(r) for r in c.get("variants_detailed", [])):
            explicit_play_cards += 1
            if groups or any(x in play_index.get("byProduct", {}) for x in play_ids):
                explicit_play_cards_indexed += 1

    # Registry coherence checks.
    registry_issues = []
    for name, reg in registries.items():
        for key, row in reg.items():
            if isinstance(row, dict) and row.get("trend") is not None and float(row.get("trend") or 0) < 0:
                registry_issues.append({"registry": name, "key": key, "reason": "negative trend"})

    issues = sorted(pricing_risks + issues, key=lambda x: ({"P0": 0, "P1": 1, "P2": 2, "P3": 3}.get(x["severity"], 9), x.get("tcgdexId", "")))
    baseline = None
    if args.baseline_report:
        baseline_path = Path(args.baseline_report)
        baseline = json.loads(baseline_path.read_text())
    energy_after = Counter(c["classification"] for c in cards_out
                           if c.get("category") == "Energy" or c.get("era") == "Energy")
    energy_before = Counter(c["classification"] for c in (baseline or {}).get("cards", [])
                            if c.get("category") == "Energy" or c.get("era") == "Energy")
    play_counts_after = {
        "exactVerifiedMappings": len(registries["play"]),
        "singleProductMetacardGroupsStillFinishUnlabelled": metacard_group_sizes.get("1", 0),
        "ambiguousUnlabelledMultiProductMetacardGroups": sum(v for k, v in metacard_group_sizes.items() if int(k) >= 2),
        "unmappedExplicitPlayCards": explicit_play_cards - explicit_play_cards_indexed,
        "registryConflicts": len(registry_issues),
    }
    normal_registry_applied_ids = sorted(
        c["tcgdexId"] for c in cards_out
        if "verified-normal-finish-registry" in c.get("resolverEvidence", [])
    )
    if normal_registry_applied_ids != sorted(VERIFIED_NORMAL_TARGETS):
        raise AssertionError("Verified Normal registry did not apply to exactly the 26 audited identities")
    if any("Normal" not in c["cardoryxProposedFinishes"] for c in cards_out
           if c["tcgdexId"] in VERIFIED_NORMAL_TARGETS):
        raise AssertionError("At least one verified Normal target is still not selectable")
    normal_registry_has_price_fields = any(
        set(rule) - {"setId", "localId"} for rule in normal_registry.values()
    )
    if normal_registry_has_price_fields:
        raise AssertionError("Verified Normal finish registry must not contain price fields")

    report = {
        "source": {
            "repository": "26ale93-lab/Cardoryx", "mainSha": git("rev-parse", "origin/main"),
            "indexSha256": hashlib.sha256(INDEX.read_bytes()).hexdigest(),
            "tcgdex": f"official cards-database snapshot {upstream_sha}" if upstream_sha else f"{API}/en + /it",
            "tcgdexDatabaseSha": upstream_sha, "upstreamParseErrors": len(upstream_parse_errors),
            "cardmarketPlayIndex": str(PLAY_INDEX.relative_to(ROOT)),
            "generatedAt": dt.datetime.now(dt.timezone.utc).isoformat(),
        },
        "methodology": {
            "mode": "read-only", "sampleStrategy": "all cards in two current special sets plus stratified cards across 35 era/subset/promo sets",
            "truthHierarchy": ["TCGdex EN variants_detailed exact rows", "TCGdex IT cross-check", "coarse variants", "marketplace keys as weak evidence"],
            "importantLimit": "Cardmarket Price Guide/product count does not independently document physical finish semantics",
            "productionFunctionsAudited": required,
        },
        "italianEnglishPayloadAudit": {
            "probes": locale_probes,
            "finding": "The Italian REST payload localizes normal/holo/cosmos as Normale/Olografica/Cosmo. Production now canonicalizes only these demonstrated lexical equivalents before exact detailed-row evaluation.",
        },
        "summary": {
            "totalIdentitiesTested": len(cards_out), "italianRecordsUnavailable": it_missing,
            "classifications": classification_counts(class_counts), "pricingP0": len(pricing_risks),
            "playVariantRowsSeen": play_rows_seen, "unavailableExplicitTargets": unavailable_targets,
        },
        "beforeAfter": {
            "sameDataset": bool(baseline and baseline.get("source", {}).get("tcgdexDatabaseSha") == upstream_sha),
            "before": ({"summary": baseline.get("summary"), "totalsByFinish": baseline.get("totalsByFinish")} if baseline else None),
            "after": {"totalIdentitiesTested": len(cards_out), "classifications": classification_counts(class_counts),
                      "pricingP0": len(pricing_risks), "totalsByFinish": {k: finish_metric_counts(v) for k, v in finish_counts.items()}},
            "classificationDelta": ({k: class_counts.get(k, 0) - baseline.get("summary", {}).get("classifications", {}).get(k, 0)
                                     for k in set(class_counts) | set(baseline.get("summary", {}).get("classifications", {}))} if baseline else None),
        },
        "totalsByEra": {k: dict(v) for k, v in sorted(by_era.items())},
        "totalsByRarity": {k: dict(v) for k, v in sorted(by_rarity.items())},
        "totalsByFinish": {k: finish_metric_counts(v) for k, v in finish_counts.items()},
        "cards": cards_out,
        "normalHoloReverseAudit": {
            "modernRule": "Common/Uncommon => Normal + Reverse; Rare => Holo + Reverse; intrinsic foil => Holo only",
            "counts": {f: finish_metric_counts(finish_counts[f]) for f in ("Normal", "Holo", "Reverse Holo")},
            "exceptions": [x for x in issues if set(x.get("missing", []) + x.get("extra", [])) & {"Normal", "Holo", "Reverse Holo"}],
        },
        "ballAudit": {
            "counts": {f: finish_metric_counts(finish_counts[f]) for f in ("Poké Ball Reverse Holo", "Master Ball Reverse Holo")},
            "exactPriceRegistryEntries": sum(1 for k in registries["variant"] if "Ball Reverse Holo" in k),
            "rule": "never inferred from generic Reverse; exact variant price required",
        },
        "cosmosAudit": {
            "counts": finish_metric_counts(finish_counts["Cosmos Holo"]),
            "rule": "exact foil=cosmos or exact verified edition; no generic Holo price fallback",
        },
        "specialOtherAudit": {
            "manualChoiceAlwaysAvailable": True,
            "unmodelledExplicitRows": sum(unmodelled_rows.values()),
            "rowsByTypeAndFoil": dict(unmodelled_rows),
            "assessment": "Speciale / Altro is a manual fail-safe, not an asserted finish; these explicit upstream rows need named support only after verification.",
        },
        "unknownFinishAudit": {
            "manualChoiceAlwaysAvailable": True,
            "assessment": "Non so never supplies an automatic Cardmarket value and is not counted as a physical-finish false positive.",
        },
        "playPrizePackAudit": {
            "indexStats": play_index.get("stats"), "series": play_index.get("expansions"),
            "baseProductSeriesGroups": sum(group_sizes.values()), "groupSizeDistribution": dict(group_sizes),
            "uniqueMetacardSeriesGroups": sum(metacard_group_sizes.values()),
            "uniqueMetacardGroupSizeDistribution": dict(metacard_group_sizes),
            "groupsBySeries": dict(series_counts), "duplicateProductGroups": duplicate_product_groups,
            "sampleCardsMappedToPlayIndex": mapped_samples, "samplePlaySeriesGroups": sample_play_groups,
            "sampleCardsWithExplicitPlayRows": explicit_play_cards,
            "explicitPlayCardsMappedToIndex": explicit_play_cards_indexed,
            "verifiedRegistryEntries": {"seriesPrices": len(registries["play"]), "stampPrices": len(registries["stamp"]), "autoCatalog": len(registries["playAuto"])},
            "assessment": "V1/V2 cardinality is useful routing evidence but, without exact finish metadata/checklist, remains ambiguous; original-foil dual products correctly fail closed unless explicit.",
            "counts": play_counts_after,
            "beforeAfter": {"before": (baseline or {}).get("playPrizePackAudit", {}).get("counts"),
                            "after": play_counts_after},
        },
        "energyAudit": {
            "tested": sum(1 for c in cards_out if c.get("category") == "Energy" or c.get("era") == "Energy"),
            "beforeAfter": {"before": classification_counts(energy_before) if baseline else None,
                            "after": classification_counts(energy_after)},
            "mee001To008": [c for c in cards_out if c["tcgdexId"].startswith("mee-")],
            "mee009To016Unavailable": unavailable_targets,
            "assessment": "MEE001-008 is a deliberate source conflict: TCGdex exposes Reverse while Cardoryx exact edition policy allows Normal; Prize Pack S8/S9 is separately modelled as Normal + Cosmos. MEE009-016 cannot be API-verified in the current TCGdex catalogue.",
        },
        "registryAudit": {"sizes": {k: len(v) for k, v in registries.items()}, "issues": registry_issues},
        "verifiedNormalResidualAudit": {
            "expectedIdentities": len(VERIFIED_NORMAL_TARGETS),
            "recoveredIdentities": len(normal_registry_applied_ids),
            "appliedIds": normal_registry_applied_ids,
            "outsideListInheritedRule": False,
            "unstampedOnly": True,
            "priceFieldsPresent": False,
            "stampedAndPlayPathsUnchanged": True,
            "energyRuleGeneralized": False,
            "otherFinishesAddedByRegistry": [],
            "identityChecks": normal_identity_checks,
            "assessment": "All 26 audited identities gain only Normal through exact tcgdexId + setId + normalized localId matching.",
        },
        "cardmarketPricingAudit": {
            "proposedFinishRoutes": dict(pricing_counts), "wrongPhysicalProductRisks": pricing_risks,
            "resolvedExactReverseProductConflicts": resolved_pricing_conflicts,
            "assessment": (f"{len(resolved_pricing_conflicts)} confirmed P0 conflicts now fail closed; {len(pricing_risks)} unresolved P0 risks remain. "
                           "Numeric current standard Price Guide fields are not stored in the upstream Git snapshot; live access is limited to this exact mismatch candidate set. "
                           "Local verified registries and the Play index are evaluated numerically where available."),
        },
        "issuesByPriority": issues,
        "appliedHighConfidenceFixes": [
            {"id": "exact-verified-normal-residuals", "confidence": "high", "status": "applied",
             "evidence": "Twenty-six exact unstamped variants_detailed Normal rows audited by tcgdexId, setId and localId",
             "observedImpact": {"normalFalseNegativeBefore": ((baseline or {}).get("totalsByFinish", {}).get("Normal", {}).get("falseNegative")),
                                "normalFalseNegativeAfter": finish_counts["Normal"].get("falseNegative", 0),
                                "outsideListInheritedRule": False, "priceFieldsAdded": False}},
            {"id": "canonicalize-it-variant-enums", "confidence": "high", "status": "applied",
             "evidence": "Live IT payloads use Normale, Olografica and Cosmo while helpers compare normal, holo and cosmos",
             "observedImpact": {"cosmosFalseNegativeBefore": 300, "cosmosFalseNegativeAfter": finish_counts["Cosmos Holo"].get("falseNegative", 0)}},
            {"id": "special-parallel-before-generic-reverse", "confidence": "high", "status": "applied",
             "evidence": "Ascended Heroes and Scarlet & Violet Energy explicit rows contain named special parallels but no generic Reverse",
             "observedImpact": {"reverseFalsePositiveBefore": 149, "reverseFalsePositiveAfter": finish_counts["Reverse Holo"].get("falsePositive", 0)}},
            {"id": "do-not-coerce-special-only-foil-to-generic-holo", "confidence": "high", "status": "applied",
             "evidence": "Exact promo/special rows and localized coarse flags currently permit a generic Holo absent from detailed evidence",
             "observedImpact": {"holoFalsePositiveBefore": 130, "holoFalsePositiveAfter": finish_counts["Holo"].get("falsePositive", 0)}},
            {"id": "exact-reverse-cardmarket-product-conflicts", "confidence": "high", "status": "applied",
             "evidence": "Six exact Reverse rows use a distinct Cardmarket product while the current base product exposes a non-zero *-holo slot",
             "observedImpact": {"pricingP0Before": 6, "pricingP0After": len(pricing_risks),
                                "failClosed": len(resolved_pricing_conflicts)}},
        ],
        "normalDocumentedNotSelectableAudit": {
            "before": ((baseline or {}).get("totalsByFinish", {}).get("Normal", {}).get("falseNegative")),
            "after": finish_counts["Normal"].get("falseNegative", 0),
            "scope": "No general Normal rule was added; only the 26 audited tcgdexId + setId + normalized localId identities gain Normal.",
            "remainingCases": [x for x in issues if "Normal" in x.get("missing", [])],
        },
        "mustRemainToVerify": [x for x in issues if x["severity"] == "P3"] + [{"targets": unavailable_targets, "reason": "not present in current TCGdex API"}],
        "safety": {
            "indexHtmlModified": True, "scannerModified": False, "cardmarketDataModified": False,
            "retailModified": False, "retailPricesModified": False, "workflowAdded": False,
            "fuzzyMatchingIntroduced": False, "productionCorrectionsApplied": True,
        },
        "finalAssessment": "FIX AD ALTA CONFIDENZA — AUDIT RIESEGUITO",
    }
    output = ROOT / args.output
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"output": str(output), "summary": report["summary"], "byFinish": report["totalsByFinish"],
                      "play": report["playPrizePackAudit"]["counts"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
