#!/usr/bin/env python3
"""Cardmarket identity regression audit for Cardoryx.

The script only writes its JSON diagnostic report. It verifies the exact
production overrides already present in index.html, then joins the pinned
TCGdex database snapshot, the live TCGdex pricing view, and Cardmarket's
official Product Catalogue and Price Guide.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import re
import subprocess
import sys
import tempfile
import time
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
VARIANT_REPORT = ROOT / "artifacts" / "variant_finish_audit_report.json"
PLAY_INDEX = ROOT / "data" / "cardmarket_play_index.json"
OUT = ROOT / "artifacts" / "card_identity_cardmarket_audit_report.json"
API = "https://api.tcgdex.net/v2/en/cards"
CM_BASE = "https://downloads.s3.cardmarket.com/productCatalog"

# Exact Cardmarket catalogue identities and current Price Guide values prove
# the base/conflicting product pairs. The Surging Sparks cases are V1/V2
# Horizons inversions; Piplup is CEC54 base versus CEC239 Character Rare.
CONFIRMED_BASE_PRODUCT_CONFLICTS = {
    "sv08-029": {"base": 794286, "alternate": 794946, "stamp": "horizons", "cardmarketCode": "SSP029"},
    "sv08-050": {"base": 794316, "alternate": 794947, "stamp": "horizons", "cardmarketCode": "SSP050"},
    "sv08-161": {"base": 794534, "alternate": 794948, "stamp": "horizons", "cardmarketCode": "SSP161"},
    "sm12-54": {"base": 407919, "alternate": 398504, "stamp": "character-rare", "cardmarketCode": "CEC54"},
    "ecard1-66": {"base": 274941, "alternate": 274904, "stamp": "wrong-holo-number", "cardmarketCode": "EX66"},
    "pl3-7": {"base": 278698, "alternate": 278689, "stamp": "wrong-card-identity", "cardmarketCode": "SV7"},
    "pl3-70": {"base": 278761, "alternate": 882910, "stamp": "special-v2-source-conflict", "cardmarketCode": "SV70"},
    "ex4-6": {"base": 275983, "alternate": 275783, "stamp": "wrong-card-identity", "cardmarketCode": "MA6"},
    "ex4-7": {"base": 275984, "alternate": 275784, "stamp": "wrong-card-identity", "cardmarketCode": "MA7"},
    "ex4-89": {"base": 276066, "alternate": 275866, "stamp": "wrong-card-identity", "cardmarketCode": "MA89"},
    "ex4-94": {"base": 276071, "alternate": 275871, "stamp": "wrong-card-identity", "cardmarketCode": "MA94"},
    "ex4-95": {"base": 276072, "alternate": 275872, "stamp": "wrong-card-identity", "cardmarketCode": "MA95"},
    "ex4-19": {"base": 275996, "alternate": 275796, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-19"},
    "ex4-23": {"base": 276000, "alternate": 275800, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-23"},
    "ex4-64": {"base": 276041, "alternate": 275841, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-64"},
    "ex4-73": {"base": 276050, "alternate": 275850, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-73"},
    "ex4-78": {"base": 276055, "alternate": 275855, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-78"},
    "ex4-80": {"base": 276057, "alternate": 275857, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-80"},
    "ex4-82": {"base": 276059, "alternate": 275859, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-82"},
    "ex4-85": {"base": 276062, "alternate": 275862, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-85"},
    "ex4-87": {"base": 276064, "alternate": 275864, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-87"},
    "ex4-1": {"base": 275978, "alternate": 275778, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-1"},
    "ex4-3": {"base": 275980, "alternate": 275780, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-3"},
    "ex4-9": {"base": 275986, "alternate": 275786, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-9"},
    "ex4-12": {"base": 275989, "alternate": 275789, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-12"},
    "ex4-13": {"base": 275990, "alternate": 275790, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-13"},
    "ex4-17": {"base": 275994, "alternate": 275794, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-17"},
    "ex4-28": {"base": 276005, "alternate": 275805, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-28"},
    "ex4-39": {"base": 276016, "alternate": 275816, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-39"},
    "ex4-40": {"base": 276017, "alternate": 275817, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-40"},
    "ex4-41": {"base": 276018, "alternate": 275818, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-41"},
    "ex4-42": {"base": 276019, "alternate": 275819, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-42"},
    "ex4-43": {"base": 276020, "alternate": 275820, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-43"},
    "ex4-44": {"base": 276021, "alternate": 275821, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-44"},
    "ex4-45": {"base": 276022, "alternate": 275822, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-45"},
    "ex4-46": {"base": 276023, "alternate": 275823, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-46"},
    "ex4-49": {"base": 276026, "alternate": 275826, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-49"},
    "ex4-69": {"base": 276046, "alternate": 275846, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-69"},
    "ex4-70": {"base": 276047, "alternate": 275847, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-70"},
    "ex4-71": {"base": 276048, "alternate": 275848, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-71"},
    "ex4-72": {"base": 276049, "alternate": 275849, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-72"},
    "ex4-74": {"base": 276051, "alternate": 275851, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-74"},
    "ex4-75": {"base": 276052, "alternate": 275852, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-75"},
    "ex4-76": {"base": 276053, "alternate": 275853, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-76"},
    "ex4-77": {"base": 276054, "alternate": 275854, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-77"},
    "ex4-79": {"base": 276056, "alternate": 275856, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-79"},
    "ex4-81": {"base": 276058, "alternate": 275858, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-81"},
    "ex4-83": {"base": 276060, "alternate": 275860, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-83"},
    "ex4-84": {"base": 276061, "alternate": 275861, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-84"},
    "ex4-86": {"base": 276063, "alternate": 275863, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-86"},
    "ex4-88": {"base": 276065, "alternate": 275865, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-88"}
}
PROTECTED_REVERSE = {"pl2-102", "pl3-26", "pl3-5", "pl3-59", "pl3-83", "sv10.5b-013"}
EXPECTED_BASE_OVERRIDES = {
    "sv08-029": {"setId": "sv08", "localId": "029", "conflictingProduct": 794946, "baseProduct": 794286},
    "sv08-050": {"setId": "sv08", "localId": "050", "conflictingProduct": 794947, "baseProduct": 794316},
    "sv08-161": {"setId": "sv08", "localId": "161", "conflictingProduct": 794948, "baseProduct": 794534},
    "sm12-54": {"setId": "sm12", "localId": "054", "conflictingProduct": 398504, "baseProduct": 407919},
    "ecard1-66": {"setId": "ecard1", "localId": "066", "conflictingProduct": 274904, "baseProduct": 274941},
    "pl3-7": {"setId": "pl3", "localId": "007", "conflictingProduct": 278689, "baseProduct": 278698},
    "pl3-70": {"setId": "pl3", "localId": "070", "conflictingProduct": 882910, "baseProduct": 278761},
    "ex5-29": {"setId": "ex5", "localId": "029", "conflictingProduct": 280585, "baseProduct": 276103},
    "ex4-6": {"setId": "ex4", "localId": "006", "conflictingProduct": 275783, "baseProduct": 275983},
    "ex4-7": {"setId": "ex4", "localId": "007", "conflictingProduct": 275784, "baseProduct": 275984},
    "ex4-89": {"setId": "ex4", "localId": "089", "conflictingProduct": 275866, "baseProduct": 276066},
    "ex4-94": {"setId": "ex4", "localId": "094", "conflictingProduct": 275871, "baseProduct": 276071},
    "ex4-95": {"setId": "ex4", "localId": "095", "conflictingProduct": 275872, "baseProduct": 276072},
    "ex4-19": {"setId": "ex4", "localId": "019", "conflictingProduct": 275796, "baseProduct": 275996},
    "ex4-23": {"setId": "ex4", "localId": "023", "conflictingProduct": 275800, "baseProduct": 276000},
    "ex4-64": {"setId": "ex4", "localId": "064", "conflictingProduct": 275841, "baseProduct": 276041},
    "ex4-73": {"setId": "ex4", "localId": "073", "conflictingProduct": 275850, "baseProduct": 276050},
    "ex4-78": {"setId": "ex4", "localId": "078", "conflictingProduct": 275855, "baseProduct": 276055},
    "ex4-80": {"setId": "ex4", "localId": "080", "conflictingProduct": 275857, "baseProduct": 276057},
    "ex4-82": {"setId": "ex4", "localId": "082", "conflictingProduct": 275859, "baseProduct": 276059},
    "ex4-85": {"setId": "ex4", "localId": "085", "conflictingProduct": 275862, "baseProduct": 276062},
    "ex4-87": {"setId": "ex4", "localId": "087", "conflictingProduct": 275864, "baseProduct": 276064},
    "ex4-1": {"setId": "ex4", "localId": "001", "conflictingProduct": 275778, "baseProduct": 275978},
    "ex4-3": {"setId": "ex4", "localId": "003", "conflictingProduct": 275780, "baseProduct": 275980},
    "ex4-9": {"setId": "ex4", "localId": "009", "conflictingProduct": 275786, "baseProduct": 275986},
    "ex4-12": {"setId": "ex4", "localId": "012", "conflictingProduct": 275789, "baseProduct": 275989},
    "ex4-13": {"setId": "ex4", "localId": "013", "conflictingProduct": 275790, "baseProduct": 275990},
    "ex4-17": {"setId": "ex4", "localId": "017", "conflictingProduct": 275794, "baseProduct": 275994},
    "ex4-28": {"setId": "ex4", "localId": "028", "conflictingProduct": 275805, "baseProduct": 276005},
    "ex4-39": {"setId": "ex4", "localId": "039", "conflictingProduct": 275816, "baseProduct": 276016},
    "ex4-40": {"setId": "ex4", "localId": "040", "conflictingProduct": 275817, "baseProduct": 276017},
    "ex4-41": {"setId": "ex4", "localId": "041", "conflictingProduct": 275818, "baseProduct": 276018},
    "ex4-42": {"setId": "ex4", "localId": "042", "conflictingProduct": 275819, "baseProduct": 276019},
    "ex4-43": {"setId": "ex4", "localId": "043", "conflictingProduct": 275820, "baseProduct": 276020},
    "ex4-44": {"setId": "ex4", "localId": "044", "conflictingProduct": 275821, "baseProduct": 276021},
    "ex4-45": {"setId": "ex4", "localId": "045", "conflictingProduct": 275822, "baseProduct": 276022},
    "ex4-46": {"setId": "ex4", "localId": "046", "conflictingProduct": 275823, "baseProduct": 276023},
    "ex4-49": {"setId": "ex4", "localId": "049", "conflictingProduct": 275826, "baseProduct": 276026},
    "ex4-69": {"setId": "ex4", "localId": "069", "conflictingProduct": 275846, "baseProduct": 276046},
    "ex4-70": {"setId": "ex4", "localId": "070", "conflictingProduct": 275847, "baseProduct": 276047},
    "ex4-71": {"setId": "ex4", "localId": "071", "conflictingProduct": 275848, "baseProduct": 276048},
    "ex4-72": {"setId": "ex4", "localId": "072", "conflictingProduct": 275849, "baseProduct": 276049},
    "ex4-74": {"setId": "ex4", "localId": "074", "conflictingProduct": 275851, "baseProduct": 276051},
    "ex4-75": {"setId": "ex4", "localId": "075", "conflictingProduct": 275852, "baseProduct": 276052},
    "ex4-76": {"setId": "ex4", "localId": "076", "conflictingProduct": 275853, "baseProduct": 276053},
    "ex4-77": {"setId": "ex4", "localId": "077", "conflictingProduct": 275854, "baseProduct": 276054},
    "ex4-79": {"setId": "ex4", "localId": "079", "conflictingProduct": 275856, "baseProduct": 276056},
    "ex4-81": {"setId": "ex4", "localId": "081", "conflictingProduct": 275858, "baseProduct": 276058},
    "ex4-83": {"setId": "ex4", "localId": "083", "conflictingProduct": 275860, "baseProduct": 276060},
    "ex4-84": {"setId": "ex4", "localId": "084", "conflictingProduct": 275861, "baseProduct": 276061},
    "ex4-86": {"setId": "ex4", "localId": "086", "conflictingProduct": 275863, "baseProduct": 276063},
    "ex4-88": {"setId": "ex4", "localId": "088", "conflictingProduct": 275865, "baseProduct": 276065}
}


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime-only", action="store_true")
    parser.add_argument("--tcgdex-db", type=Path, default=ROOT.parent / "tcgdex-cards-database")
    parser.add_argument("--products", type=Path)
    parser.add_argument("--prices", type=Path)
    parser.add_argument("--cache", type=Path, default=Path(tempfile.gettempdir()) / "cardoryx-cm-identity-live-cache")
    parser.add_argument("--workers", type=int, default=24)
    return parser.parse_args()


def norm_local(value):
    text = str(value or "").strip().lower()
    return str(int(text)) if text.isdigit() else re.sub(r"[^a-z0-9]+", "", text)


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def git(*args, cwd=ROOT):
    return subprocess.check_output(["git", *args], cwd=cwd, text=True).strip()


def get_json(url, timeout=90):
    request = urllib.request.Request(url, headers={"User-Agent": "Cardoryx-Cardmarket-Identity-Audit/2.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.load(response)


def download_if_needed(path, filename):
    if path:
        return path
    destination = Path(tempfile.gettempdir()) / filename
    if not destination.exists():
        section = "productList" if filename.startswith("products_") else "priceGuide"
        request = urllib.request.Request(f"{CM_BASE}/{section}/{filename}", headers={"User-Agent": "Cardoryx-Cardmarket-Identity-Audit/2.0"})
        with urllib.request.urlopen(request, timeout=300) as response, destination.open("wb") as handle:
            while chunk := response.read(1024 * 1024):
                handle.write(chunk)
    return destination


def load_snapshot(db_root):
    sys.dont_write_bytecode = True
    path = ROOT / "scripts" / "test_variant_finish_audit.py"
    spec = importlib.util.spec_from_file_location("variant_audit", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_official_database(db_root)


def rows(root, keys):
    if isinstance(root, list):
        return root
    for key in keys:
        value = root.get(key) if isinstance(root, dict) else None
        if isinstance(value, list):
            return value
    return []


def cm_id(row):
    try:
        return int(((row.get("thirdParty") or {}).get("cardmarket")))
    except (TypeError, ValueError):
        return None


def physical_variant(row):
    stamps, foils = row.get("stamp") or [], row.get("foil") or []
    if isinstance(stamps, str):
        stamps = [stamps]
    if isinstance(foils, str):
        foils = [foils]
    return {
        "finish": row.get("type"), "foil": sorted(map(str, foils)), "stamp": sorted(map(str, stamps)),
        "language": row.get("language") or row.get("languages"), "variantId": row.get("variantId"),
        "firstEdition": row.get("firstEdition"),
    }


def is_base_row(row):
    return not (row.get("stamp") or row.get("foil") or row.get("firstEdition"))


def card_identity(card):
    set_info, names = card.get("set") or {}, card.get("name") or {}
    set_names = set_info.get("name") or {}
    return {
        "tcgdexId": card.get("id"), "setId": set_info.get("id"),
        "setNameEN": set_names.get("en") if isinstance(set_names, dict) else set_names,
        "setNameIT": set_names.get("it") if isinstance(set_names, dict) else None,
        "localId": card.get("localId"), "normalizedLocalId": norm_local(card.get("localId")),
        "name": names.get("en") if isinstance(names, dict) else names,
        "nameIT": names.get("it") if isinstance(names, dict) else None,
        "rarity": card.get("rarity"), "regulationMark": card.get("regulationMark"),
    }


def product_ids(card):
    return sorted({pid for row in (card.get("variants_detailed") or []) if (pid := cm_id(row))})


def live_card(card_id, cache, retries=3):
    cache.mkdir(parents=True, exist_ok=True)
    destination = cache / f"{card_id}.json"
    error_destination = cache / f"{card_id}.error.json"
    if destination.exists():
        try:
            return json.loads(destination.read_text(encoding="utf-8")), None
        except Exception:
            pass
    if error_destination.exists():
        try:
            cached_error = json.loads(error_destination.read_text(encoding="utf-8"))
            return None, cached_error.get("error")
        except Exception:
            pass
    error = None
    for attempt in range(retries):
        try:
            value = get_json(f"{API}/{urllib.parse.quote(card_id)}", timeout=60)
            destination.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")
            return value, None
        except Exception as exc:
            error = str(exc)
            if "404" in error:
                error_destination.write_text(json.dumps({"error": error}), encoding="utf-8")
                break
            time.sleep(0.4 * (attempt + 1))
    return None, error


def price_compact(row):
    return ({key: row.get(key) for key in ("idProduct", "trend", "avg7", "avg30", "low", "avg") if key in row}
            if row else None)


def descriptor_map(card):
    mapped = defaultdict(list)
    for row in card.get("variants_detailed") or []:
        if (pid := cm_id(row)):
            variant = physical_variant(row)
            if variant not in mapped[pid]:
                mapped[pid].append(variant)
    return dict(mapped)


def extract_js_object(source, name):
    marker = re.search(rf"\bconst\s+{re.escape(name)}\s*=\s*", source)
    if not marker:
        raise AssertionError(f"Missing registry {name}")
    start = source.find("{", marker.end())
    end = source.find("\n};", start)
    if start < 0 or end < 0:
        raise AssertionError(f"Unclosed registry {name}")
    literal = source[start:end + 2]
    js = f"const value=({literal}); process.stdout.write(JSON.stringify(value));"
    return json.loads(subprocess.check_output(["node", "-e", js], text=True))


def override_matches(rule, card_id, set_id, local_id, current_product):
    return bool(rule and card_id in EXPECTED_BASE_OVERRIDES and
                str(rule.get("setId") or "").lower() == str(set_id or "").lower() and
                norm_local(rule.get("localId")) == norm_local(local_id) and
                int(rule.get("conflictingProduct") or 0) == int(current_product or 0))


def runtime_cardmarket_regression():
    """Execute the production JavaScript resolvers against focused runtime fixtures."""
    fixtures = {
        "piplup": {
            "id": "sm12-54", "tcgdexId": "sm12-54", "name": "Piplup", "localId": "54",
            "set": {"id": "sm12", "name": "Eclissi Cosmica"}, "rarity": "Comune",
            "variants": {"normal": True, "holo": False, "reverse": False},
            "variants_detailed": [{"type": "normal", "size": "Standard", "variantId": "generated"}],
            "pricing": {"cardmarket": {"idProduct": 398504, "trend": 54.51, "trend-holo": 11.29}},
        },
        "surging": [
            {"id": "sv08-029", "tcgdexId": "sv08-029", "localId": "29", "set": {"id": "sv08"},
             "pricing": {"cardmarket": {"idProduct": 794946}}, "variants_detailed": [
                 {"type": "normal", "thirdParty": {"cardmarket": 794286},
                  "pricing": {"cardmarket": {"idProduct": 794286, "trend": 0.11}}}]},
            {"id": "sv08-050", "tcgdexId": "sv08-050", "localId": "50", "set": {"id": "sv08"},
             "pricing": {"cardmarket": {"idProduct": 794947}}, "variants_detailed": [
                 {"type": "normal", "thirdParty": {"cardmarket": 794316},
                  "pricing": {"cardmarket": {"idProduct": 794316, "trend": 0.12}}}]},
            {"id": "sv08-161", "tcgdexId": "sv08-161", "localId": "161", "set": {"id": "sv08"},
             "pricing": {"cardmarket": {"idProduct": 794948}}, "variants_detailed": [
                 {"type": "normal", "thirdParty": {"cardmarket": 794534},
                  "pricing": {"cardmarket": {"idProduct": 794534, "trend": 0.13}}}]},
        ],
        "frillish": {"id": "sv10.5w-044", "tcgdexId": "sv10.5w-044", "name": "Frillish",
                     "localId": "044", "set": {"id": "sv10.5w", "name": "Fuoco Bianco"}},
        "pikachu": {"id": "sv05-051", "tcgdexId": "sv05-051", "name": "Pikachu",
                    "localId": "051", "set": {"id": "sv05", "name": "Cronoforze"}},
    }
    fixtures["tyranitar"] = {
        "id": "ecard1-66", "tcgdexId": "ecard1-66", "name": "Tyranitar", "localId": "66",
        "set": {"id": "ecard1", "name": "Expedition Base Set"}, "rarity": "Rare",
        "variants": {"normal": True, "holo": False, "reverse": True},
        "variants_detailed": [
            {"type": "normal", "thirdParty": {"cardmarket": 274904}, "pricing": {"cardmarket": {"idProduct": 274904, "trend": 311.31}}},
            {"type": "reverse", "thirdParty": {"cardmarket": 362890}, "pricing": {"cardmarket": {"idProduct": 362890, "trend": 36.28}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 274904, "trend": 311.31, "trend-holo": 136.66}},
    }
    fixtures["milotic70"] = {
        "id": "pl3-70", "tcgdexId": "pl3-70", "name": "Milotic", "localId": "70",
        "set": {"id": "pl3", "name": "Supreme Victors"}, "rarity": "Uncommon",
        "variants": {"normal": True, "holo": False, "reverse": True},
        "variants_detailed": [
            {"type": "normal", "thirdParty": {"cardmarket": 882910}, "pricing": {"cardmarket": {"idProduct": 882910, "trend": 34.74}}},
            {"type": "reverse", "thirdParty": {"cardmarket": 278689}, "pricing": {"cardmarket": {"idProduct": 278689, "trend": 40.68}}},
            {"type": "normal", "stamp": ["pre-release"], "thirdParty": {"cardmarket": 882910}, "pricing": {"cardmarket": {"idProduct": 882910, "trend": 34.74}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 882910, "trend": 34.74}},
    }
    fixtures["metagross"] = {
        "id": "pl3-7", "tcgdexId": "pl3-7", "name": "Metagross", "localId": "7",
        "set": {"id": "pl3", "name": "Supreme Victors"}, "rarity": "Rare Holo",
        "variants": {"normal": False, "holo": True, "reverse": True},
        "variants_detailed": [
            {"type": "holo", "thirdParty": {"cardmarket": 278689}, "pricing": {"cardmarket": {"idProduct": 278689, "trend": 40.68, "trend-holo": 62.71}}},
            {"type": "reverse", "thirdParty": {"cardmarket": 278698}, "pricing": {"cardmarket": {"idProduct": 278698, "trend": 3.05, "trend-holo": 3.24}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 278689, "trend": 40.68, "trend-holo": 62.71}},
    }
    fixtures["ex4_high_impact"] = [
        {"id":"ex4-6","tcgdexId":"ex4-6","name":"Team Aqua's Walrein","localId":"6","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Holo Rare","wrong":275783,"correct":275983,"expected":4.40},
        {"id":"ex4-7","tcgdexId":"ex4-7","name":"Team Magma's Aggron","localId":"7","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Holo Rare","wrong":275784,"correct":275984,"expected":5.80},
        {"id":"ex4-89","tcgdexId":"ex4-89","name":"Blaziken ex","localId":"89","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Rare","wrong":275866,"correct":276066,"expected":136.64},
        {"id":"ex4-94","tcgdexId":"ex4-94","name":"Suicune ex","localId":"94","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Rare","wrong":275871,"correct":276071,"expected":714.52},
        {"id":"ex4-95","tcgdexId":"ex4-95","name":"Swampert ex","localId":"95","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Rare","wrong":275872,"correct":276072,"expected":93.11},
    ]
    for card in fixtures["ex4_high_impact"]:
        card["variants"] = {"normal": False, "holo": True, "reverse": False}
        card["variants_detailed"] = [{"type":"holo","thirdParty":{"cardmarket":card["wrong"]},"pricing":{"cardmarket":{"idProduct":card["wrong"],"trend":1}}}]
        card["pricing"] = {"cardmarket":{"idProduct":card["wrong"],"trend":1}}
    fixtures["ex4_verified_batch"] = [
        {"id":"ex4-19","tcgdexId":"ex4-19","name":"Team Magma's Camerupt","localId":"19","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275796,"correct":275996},
        {"id":"ex4-23","tcgdexId":"ex4-23","name":"Team Magma's Zangoose","localId":"23","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275800,"correct":276000},
        {"id":"ex4-64","tcgdexId":"ex4-64","name":"Team Magma's Numel","localId":"64","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275841,"correct":276041},
        {"id":"ex4-73","tcgdexId":"ex4-73","name":"Maxie","localId":"73","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275850,"correct":276050},
        {"id":"ex4-78","tcgdexId":"ex4-78","name":"Team Aqua Hideout","localId":"78","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275855,"correct":276055},
        {"id":"ex4-80","tcgdexId":"ex4-80","name":"Team Magma Ball","localId":"80","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275857,"correct":276057},
        {"id":"ex4-82","tcgdexId":"ex4-82","name":"Team Magma Conspirator","localId":"82","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275859,"correct":276059},
        {"id":"ex4-85","tcgdexId":"ex4-85","name":"Warp Point","localId":"85","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275862,"correct":276062},
        {"id":"ex4-87","tcgdexId":"ex4-87","name":"Magma Energy","localId":"87","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275864,"correct":276064},
        {"id":"ex4-1","tcgdexId":"ex4-1","name":"Team Aqua's Cacturne","localId":"1","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275778,"correct":275978},
        {"id":"ex4-3","tcgdexId":"ex4-3","name":"Team Aqua's Kyogre","localId":"3","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275780,"correct":275980},
        {"id":"ex4-9","tcgdexId":"ex4-9","name":"Team Magma's Groudon","localId":"9","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275786,"correct":275986},
        {"id":"ex4-12","tcgdexId":"ex4-12","name":"Team Magma's Torkoal","localId":"12","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275789,"correct":275989},
        {"id":"ex4-13","tcgdexId":"ex4-13","name":"Raichu","localId":"13","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275790,"correct":275990},
        {"id":"ex4-17","tcgdexId":"ex4-17","name":"Team Aqua's Seviper","localId":"17","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275794,"correct":275994},
        {"id":"ex4-28","tcgdexId":"ex4-28","name":"Team Aqua's Lanturn","localId":"28","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275805,"correct":276005},
        {"id":"ex4-39","tcgdexId":"ex4-39","name":"Bulbasaur","localId":"39","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275816,"correct":276016},
        {"id":"ex4-40","tcgdexId":"ex4-40","name":"Cubone","localId":"40","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275817,"correct":276017},
        {"id":"ex4-41","tcgdexId":"ex4-41","name":"Jigglypuff","localId":"41","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275818,"correct":276018},
        {"id":"ex4-42","tcgdexId":"ex4-42","name":"Meowth","localId":"42","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275819,"correct":276019},
        {"id":"ex4-43","tcgdexId":"ex4-43","name":"Pikachu","localId":"43","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275820,"correct":276020},
        {"id":"ex4-44","tcgdexId":"ex4-44","name":"Psyduck","localId":"44","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275821,"correct":276021},
        {"id":"ex4-45","tcgdexId":"ex4-45","name":"Slowpoke","localId":"45","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275822,"correct":276022},
        {"id":"ex4-46","tcgdexId":"ex4-46","name":"Squirtle","localId":"46","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275823,"correct":276023},
        {"id":"ex4-49","tcgdexId":"ex4-49","name":"Team Aqua's Chinchou","localId":"49","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275826,"correct":276026},
        {"id":"ex4-69","tcgdexId":"ex4-69","name":"Team Aqua Schemer","localId":"69","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275846,"correct":276046},
        {"id":"ex4-70","tcgdexId":"ex4-70","name":"Team Magma Schemer","localId":"70","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275847,"correct":276047},
        {"id":"ex4-71","tcgdexId":"ex4-71","name":"Archie","localId":"71","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275848,"correct":276048},
        {"id":"ex4-72","tcgdexId":"ex4-72","name":"Dual Ball","localId":"72","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275849,"correct":276049},
        {"id":"ex4-74","tcgdexId":"ex4-74","name":"Strength Charm","localId":"74","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275851,"correct":276051},
        {"id":"ex4-75","tcgdexId":"ex4-75","name":"Team Aqua Ball","localId":"75","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275852,"correct":276052},
        {"id":"ex4-76","tcgdexId":"ex4-76","name":"Team Aqua Belt","localId":"76","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275853,"correct":276053},
        {"id":"ex4-77","tcgdexId":"ex4-77","name":"Team Aqua Conspirator","localId":"77","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275854,"correct":276054},
        {"id":"ex4-79","tcgdexId":"ex4-79","name":"Team Aqua Technical Machine 01","localId":"79","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275856,"correct":276056},
        {"id":"ex4-81","tcgdexId":"ex4-81","name":"Team Magma Belt","localId":"81","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275858,"correct":276058},
        {"id":"ex4-83","tcgdexId":"ex4-83","name":"Team Magma Hideout","localId":"83","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275860,"correct":276060},
        {"id":"ex4-84","tcgdexId":"ex4-84","name":"Team Magma Technical Machine 01","localId":"84","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275861,"correct":276061},
        {"id":"ex4-86","tcgdexId":"ex4-86","name":"Aqua Energy","localId":"86","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275863,"correct":276063},
        {"id":"ex4-88","tcgdexId":"ex4-88","name":"Double Rainbow Energy","localId":"88","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275865,"correct":276065},
    ]
    for card in fixtures["ex4_verified_batch"]:
        card["variants"] = {"normal": False, "holo": True, "reverse": True}
        card["variants_detailed"] = [{"type":"holo","thirdParty":{"cardmarket":card["wrong"]},"pricing":{"cardmarket":{"idProduct":card["wrong"],"trend":1}}}]
        card["pricing"] = {"cardmarket":{"idProduct":card["wrong"],"trend":1}}
    harness = r"""
const assert=require('assert');
const fs=require('fs');
const vm=require('vm');
const source=fs.readFileSync(process.argv[1],'utf8');
const fixtures=JSON.parse(process.argv[2]);
function section(start,end){
  const a=source.indexOf(start),b=source.indexOf(end,a+start.length);
  assert(a>=0&&b>a,`Missing production section ${start}`);
  return source.slice(a,b);
}
const production=[
  section("function normText(","function similarity("),
  section("function canonicalPrintedLocalId(","function extractCollectorCode("),
  section("function normalizedPlaySeries(","function playSeriesLabel("),
  section("function canonicalStamp(","function scanUnit("),
  section("async function renderScanValue(","async function chooseCard("),
  section("function cardPriceInfo(","function cardUnitPrice(")
].join('\n');
const elements={};
function element(id){
  if(!elements[id])elements[id]={
    textContent:'',innerHTML:'',value:id==='variant'?'Reverse Holo':id==='stamp'?'None':'',
    classList:{add(){},remove(){},toggle(){}},style:{},options:[],selectedOptions:[]
  };
  return elements[id];
}
const context={console,document:{getElementById:element}};
vm.createContext(context);
vm.runInContext(`
${production}
let scanPriceCard=null;
let selectedCard=null;
function scanEuro(v){const n=Number(v||0);return n>0?n.toLocaleString('it-IT',{style:'currency',currency:'EUR'}):'—'}
function scanCM(c){return resolvedCardmarketPricingForCard(c)}
function verifiedStandardEnergyPrice(){return null}
async function fetchScanPricing(card){return card}
async function enrichCardoryxEnglishIdentity(){}
async function refreshOfficialPlayAvailability(){}
function refreshScanProtectionRecommendation(){}
syncStampAvailability=()=>[];
syncVariantAvailability=()=>[];
globalThis.runtime={
  verifiedBaseCardmarketProductOverride,resolvedCardmarketPricingForCard,
  pricingWithResolvedCardmarket,knownCardmarketIdentityConflict,
  cardmarketValueForCardVariant,cardmarketStatsForCardVariant,
  verifiedVariantPrice,verifiedStampPrice,renderScanValue,cardPriceInfo,
  setSelected:c=>{selectedCard=c;scanPriceCard=null}
};`,context);
const r=context.runtime;
const p=fixtures.piplup;
const override=r.verifiedBaseCardmarketProductOverride(p);
assert.strictEqual(override?.pricing?.idProduct,407919);
assert.strictEqual(r.resolvedCardmarketPricingForCard(p)?.idProduct,407919);
assert.strictEqual(r.knownCardmarketIdentityConflict(p,398504)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...p,localId:'SM54'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...p,tcgdexId:'sm12-55',id:'sm12-55'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...p,set:{...p.set,id:'sm11'}}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...p,name:'Prinplup'}),null);
const tyr=fixtures.tyranitar;
const tyrOverride=r.verifiedBaseCardmarketProductOverride(tyr);
assert.strictEqual(tyrOverride?.pricing?.idProduct,274941);
assert.strictEqual(r.resolvedCardmarketPricingForCard(tyr)?.idProduct,274941);
assert.strictEqual(r.knownCardmarketIdentityConflict(tyr,274904)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...tyr,id:'ecard1-29',tcgdexId:'ecard1-29',localId:'29'},274941)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...tyr,localId:'29'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...tyr,name:'Tyranitar ex'}),null);
const tyrNormal=r.cardmarketValueForCardVariant(tyr,'Normal');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:tyrNormal.value,productId:tyrNormal.productId})),{value:10.33,productId:274941});
const met=fixtures.metagross;
const metOverride=r.verifiedBaseCardmarketProductOverride(met);
assert.strictEqual(metOverride?.pricing?.idProduct,278698);
assert.strictEqual(r.resolvedCardmarketPricingForCard(met)?.idProduct,278698);
assert.strictEqual(r.knownCardmarketIdentityConflict(met,278689)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...met,id:'pl3-8',tcgdexId:'pl3-8',localId:'8'},278698)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...met,localId:'8'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...met,name:'Milotic'}),null);
const metHolo=r.cardmarketValueForCardVariant(met,'Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:metHolo.value,productId:metHolo.productId})),{value:3.05,productId:278698});
const mil=fixtures.milotic70;
const milOverride=r.verifiedBaseCardmarketProductOverride(mil);
assert.strictEqual(milOverride?.pricing?.idProduct,278761);
assert.strictEqual(r.resolvedCardmarketPricingForCard(mil)?.idProduct,278761);
assert.strictEqual(r.knownCardmarketIdentityConflict(mil,278689)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...mil,id:'pl3-SH7',tcgdexId:'pl3-SH7',localId:'SH7'},278761)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...mil,localId:'71'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...mil,name:'Milotic Lv.52'}),null);
const milNormal=r.cardmarketValueForCardVariant(mil,'Normal');
const milReverse=r.cardmarketValueForCardVariant(mil,'Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:milNormal.value,productId:milNormal.productId})),{value:0.97,productId:278761});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:milReverse.value,productId:milReverse.productId})),{value:14.54,productId:278761});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(mil,'Normal'))),{low:0.13,trend:0.97,avg7:1.27,avg30:0.87});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(mil,'Reverse Holo'))),{low:0.49,trend:14.54,avg7:13.73,avg30:8.01});
for(const card of fixtures.ex4_high_impact){
  const o=r.verifiedBaseCardmarketProductOverride(card);
  assert.strictEqual(o?.pricing?.idProduct,card.correct);
  assert.strictEqual(r.resolvedCardmarketPricingForCard(card)?.idProduct,card.correct);
  assert.strictEqual(r.knownCardmarketIdentityConflict(card,card.wrong)?.kind,'identity-mismatch');
  assert.strictEqual(r.knownCardmarketIdentityConflict({...card,id:card.id+'x',tcgdexId:card.tcgdexId+'x',localId:'999'},card.correct)?.kind,'identity-mismatch');
  assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...card,name:card.name+' wrong'}),null);
  const value=r.cardmarketValueForCardVariant(card,'Holo');
  assert.deepStrictEqual(JSON.parse(JSON.stringify({value:value.value,productId:value.productId})),{value:card.expected,productId:card.correct});
}
for(const card of fixtures.ex4_verified_batch){
  const o=r.verifiedBaseCardmarketProductOverride(card);
  assert.strictEqual(o?.pricing?.idProduct,card.correct);
  assert.strictEqual(r.resolvedCardmarketPricingForCard(card)?.idProduct,card.correct);
  assert.strictEqual(r.knownCardmarketIdentityConflict(card,card.wrong)?.kind,'identity-mismatch');
  assert.strictEqual(r.knownCardmarketIdentityConflict({...card,id:card.id+'-wrong',tcgdexId:card.tcgdexId+'-wrong',localId:'999'},card.correct)?.kind,'identity-mismatch');
  assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...card,name:card.name+' wrong'}),null);
}
const normal=r.cardmarketValueForCardVariant(p,'Normal');
const reverse=r.cardmarketValueForCardVariant(p,'Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:normal.value,productId:normal.productId})),{value:0.17,productId:407919});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:reverse.value,productId:reverse.productId})),{value:0.76,productId:407919});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(p,'Normal'))),
  {low:0.02,trend:0.17,avg7:0.18,avg30:0.12});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(p,'Reverse Holo'))),
  {low:0.14,trend:0.76,avg7:0.94,avg30:0.76});
const savedPricing=r.pricingWithResolvedCardmarket(p);
assert.strictEqual(savedPricing.cardmarket.idProduct,407919);
assert.notStrictEqual(savedPricing.cardmarket.idProduct,398504);
const saved={...p,pricing:savedPricing,variant:'Reverse Holo',stamp:'None',_cardoryxSetId:'sm12'};
assert.strictEqual(r.cardPriceInfo(saved).value,0.76);
r.setSelected(p);
element('variant').value='Reverse Holo';
element('stamp').value='None';
(async()=>{
  await r.renderScanValue(p);
  assert(!element('scanMarketValue').textContent.includes('Valore da verificare'));
  assert(element('scanMarketValue').textContent.includes('0,76'));
  const expectedSurging={"sv08-029":794286,"sv08-050":794316,"sv08-161":794534};
  for(const card of fixtures.surging){
    assert.strictEqual(r.verifiedBaseCardmarketProductOverride(card)?.pricing?.idProduct,expectedSurging[card.id]);
    assert.strictEqual(r.resolvedCardmarketPricingForCard(card)?.idProduct,expectedSurging[card.id]);
  }
  const frillish=r.verifiedVariantPrice(fixtures.frillish,'Master Ball Reverse Holo');
  assert.strictEqual(frillish?.productId,836574);
  assert.strictEqual(frillish?.trend,3);
  assert.strictEqual(r.verifiedVariantPrice(fixtures.frillish,'Normal'),null);
  assert.strictEqual(r.verifiedVariantPrice(fixtures.frillish,'Poké Ball Reverse Holo'),null);
  const pikachu=r.verifiedStampPrice(fixtures.pikachu,'Holo','Pokémon Day');
  assert.strictEqual(pikachu?.productId,870424);
  assert.strictEqual(pikachu?.trend,3.88);
  assert.strictEqual(r.verifiedStampPrice(fixtures.pikachu,'Normal','Pokémon Day'),null);
  assert.strictEqual(r.verifiedStampPrice(fixtures.pikachu,'Holo','None'),null);
  process.stdout.write(JSON.stringify({
    piplup:{normal,reverse,scanner:element('scanMarketValue').textContent,savedProductId:savedPricing.cardmarket.idProduct},
    surging:Object.fromEntries(fixtures.surging.map(c=>[c.id,r.resolvedCardmarketPricingForCard(c).idProduct])),
    frillish:{productId:frillish.productId,value:frillish.trend},
    pikachu:{productId:pikachu.productId,value:pikachu.trend}
  }));
})().catch(error=>{console.error(error);process.exit(1)});
"""
    output = subprocess.check_output(
        ["node", "-e", harness, str(INDEX), json.dumps(fixtures, ensure_ascii=False)],
        text=True,
    )
    return json.loads(output)


def runtime_svp_set_logo_staff_regression():
    # Verify exact live SVP Set Stamp/Staff product separation in production JS.
    source = INDEX.read_text(encoding="utf-8")

    def extract_fn(name):
        marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
        if not marker:
            raise AssertionError(f"Missing production function {name}")
        brace = source.find("{", marker.start())
        depth = 0
        quote = None
        escape = False
        for i in range(brace, len(source)):
            ch = source[i]
            if quote:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == quote:
                    quote = None
                continue
            if ch in "'\"`":
                quote = ch
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return source[marker.start():i + 1]
        raise AssertionError(f"Unclosed production function {name}")

    cache = Path(tempfile.gettempdir()) / "cardoryx_svp_stamp_regression_cache_v1"
    fixtures, errors = {}, {}
    for card_id in ("svp-005", "svp-006", "svp-007", "svp-045", "svp-067", "svp-101", "svp-150"):
        value, error = live_card(card_id, cache)
        if value:
            fixtures[card_id] = value
        if error:
            errors[card_id] = error
    if errors or len(fixtures) != 7:
        raise AssertionError(f"SVP live regression unavailable: {errors}")

    names = (
        "normText", "canonicalVariant", "canonicalStamp", "canonicalFinishTypeLabel",
        "canonicalFinishFoilLabel", "tcgdexVariantDetails", "stampEvidenceFromTCGdex",
        "tcgdexStampedRowFinish", "tcgdexExactSvpStampPrice",
    )
    js = "\n".join(extract_fn(name) for name in names)
    harness = r'''
const fixtures=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
function stamps(r){return (Array.isArray(r?.stamp)?r.stamp:[]).map(normText)}
const checked={};
for(const id of ['svp-005','svp-006','svp-007']){
  const c=fixtures[id], rows=tcgdexVariantDetails(c);
  const setRow=rows.find(r=>stamps(r).includes('setlogo')&&!stamps(r).includes('staff'));
  const staffRow=rows.find(r=>stamps(r).includes('setlogo')&&stamps(r).includes('staff'));
  if(!setRow||!staffRow)fail(id+' missing exact source pair');
  const setFinish=tcgdexStampedRowFinish(setRow), staffFinish=tcgdexStampedRowFinish(staffRow);
  if(!setFinish||!staffFinish)fail(id+' unsupported physical finish');
  const setPrice=tcgdexExactSvpStampPrice(c,setFinish,'Set Stamp');
  const staffPrice=tcgdexExactSvpStampPrice(c,staffFinish,'Staff');
  const setPid=Number(setRow?.thirdParty?.cardmarket||0), staffPid=Number(staffRow?.thirdParty?.cardmarket||0);
  if(!setPrice||Number(setPrice.idProduct)!==setPid)fail(id+' Set Stamp product mismatch');
  if(!staffPrice||Number(staffPrice.idProduct)!==staffPid)fail(id+' Staff product mismatch');
  if(setPid===staffPid)fail(id+' products are not distinct');
  if(!stampEvidenceFromTCGdex(c,'Set Stamp')||!stampEvidenceFromTCGdex(c,'Staff'))fail(id+' stamp evidence missing');
  const staffOnly={...c,variants_detailed:[staffRow]};
  if(stampEvidenceFromTCGdex(staffOnly,'Set Stamp'))fail(id+' Staff leaked into Set Stamp');
  checked[id]={setFinish,staffFinish,setPid,staffPid};
}
for(const id of ['svp-045','svp-067','svp-101','svp-150']){
  const c=fixtures[id];
  for(const finish of ['Normal','Holo','Reverse Holo','Cosmos Holo']){
    if(tcgdexExactSvpStampPrice(c,finish,'Set Stamp')!==null)fail(id+' unexpected Set Stamp auto-price');
    if(tcgdexExactSvpStampPrice(c,finish,'Staff')!==null)fail(id+' unexpected Staff auto-price');
  }
}
const foreign={...fixtures['svp-005'],set:{...(fixtures['svp-005'].set||{}),id:'sv01'}};
if(tcgdexExactSvpStampPrice(foreign,'Holo','Set Stamp')!==null)fail('resolver leaked outside svp');
process.stdout.write(JSON.stringify({checked,failClosed:['svp-045','svp-067','svp-101','svp-150'],setScopeRejected:true}));
'''
    result = json.loads(subprocess.check_output(
        ["node", "-e", js + "\n" + harness, json.dumps(fixtures, ensure_ascii=False)], text=True
    ))
    verified = extract_fn("verifiedStampPrice")
    if "tcgdexExactSvpStampPrice(card,variant,stamp)" not in verified:
        raise AssertionError("verifiedStampPrice does not consume exact SVP stamp evidence")
    if verified.find("verifiedExactSpecialStampPrice") > verified.find("tcgdexExactSvpStampPrice"):
        raise AssertionError("dynamic SVP resolver precedes existing exact static registry")
    return result


def runtime_mep_set_logo_staff_regression():
    # Verify all currently audited MEP Set Stamp/Staff product pairs in production JS.
    source = INDEX.read_text(encoding="utf-8")

    def extract_fn(name):
        marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
        if not marker:
            raise AssertionError(f"Missing production function {name}")
        brace = source.find("{", marker.end())
        depth = 0
        quote = None
        esc = False
        for i in range(brace, len(source)):
            ch = source[i]
            if quote:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == quote:
                    quote = None
                continue
            if ch in ("'", '"', "`"):
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return source[marker.start():i + 1]
        raise AssertionError(f"Unclosed production function {name}")

    names = (
        "normText", "canonicalStamp", "canonicalVariant", "canonicalFinishTypeLabel",
        "canonicalFinishFoilLabel", "tcgdexVariantDetails", "tcgdexStampedRowFinish",
        "tcgdexExactSvpStampPrice",
    )
    js = "\n".join(extract_fn(name) for name in names)
    ids = (
        "mep-001", "mep-002", "mep-003", "mep-004",
        "mep-014", "mep-015", "mep-016", "mep-017",
        "mep-064", "mep-065", "mep-066", "mep-067",
        "mep-074", "mep-075", "mep-076", "mep-077",
    )
    cache = Path(tempfile.gettempdir()) / "cardoryx_mep_stamp_regression_cache_v1"
    fixtures, errors = {}, {}
    for card_id in ids:
        value, error = live_card(card_id, cache)
        if value:
            fixtures[card_id] = value
        if error:
            errors[card_id] = error
    if errors or set(fixtures) != set(ids):
        raise AssertionError(f"MEP live fixture errors: {errors}; fetched={sorted(fixtures)}")

    harness = r'''
const fixtures=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
function stamps(r){return (Array.isArray(r?.stamp)?r.stamp:[]).map(normText)}
function pid(r){return Number(r?.thirdParty?.cardmarket||0)}
function ppid(r){return Number(r?.pricing?.cardmarket?.idProduct||r?.pricing?.cardmarket?.id_product||0)}
const checked={};
for(const [id,c] of Object.entries(fixtures)){
  const rows=tcgdexVariantDetails(c);
  const setRows=rows.filter(r=>stamps(r).includes('setlogo')&&!stamps(r).includes('staff'));
  const staffRows=rows.filter(r=>stamps(r).includes('setlogo')&&stamps(r).includes('staff'));
  if(setRows.length!==1||staffRows.length!==1)fail(id+' source pair not unique');
  const setRow=setRows[0], staffRow=staffRows[0];
  const setFinish=tcgdexStampedRowFinish(setRow), staffFinish=tcgdexStampedRowFinish(staffRow);
  if(!setFinish||!staffFinish)fail(id+' unsupported physical finish');
  if(!(pid(setRow)>0)||pid(setRow)!==ppid(setRow))fail(id+' invalid Set Stamp product');
  if(!(pid(staffRow)>0)||pid(staffRow)!==ppid(staffRow))fail(id+' invalid Staff product');
  if(pid(setRow)===pid(staffRow))fail(id+' Set Stamp/Staff product collision');
  const setPrice=tcgdexExactSvpStampPrice(c,setFinish,'Set Stamp');
  const staffPrice=tcgdexExactSvpStampPrice(c,staffFinish,'Staff');
  if(!setPrice||Number(setPrice.idProduct)!==pid(setRow))fail(id+' Set Stamp resolver mismatch');
  if(!staffPrice||Number(staffPrice.idProduct)!==pid(staffRow))fail(id+' Staff resolver mismatch');
  checked[id]={setFinish,staffFinish,setPid:pid(setRow),staffPid:pid(staffRow)};
}
const foreign={...fixtures['mep-001'],set:{...(fixtures['mep-001'].set||{}),id:'me01'}};
if(tcgdexExactSvpStampPrice(foreign,'Holo','Set Stamp')!==null)fail('resolver leaked outside verified promo sets');
process.stdout.write(JSON.stringify({checked,count:Object.keys(checked).length,setScopeRejected:true}));
'''
    result = json.loads(subprocess.check_output(
        ["node", "-e", js + "\n" + harness, json.dumps(fixtures)],
        text=True,
    ))
    if result.get("count") != 16 or not result.get("setScopeRejected"):
        raise AssertionError(f"Unexpected MEP runtime result: {result}")
    return result


def runtime_ex5_beldum_gym_challenge_regression():
    source = INDEX.read_text(encoding="utf-8")
    def extract_fn(name):
        marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
        if not marker: raise AssertionError(f"Missing production function {name}")
        brace=source.find("{", marker.end()); depth=0; quote=None; esc=False
        for i in range(brace,len(source)):
            ch=source[i]
            if quote:
                if esc: esc=False
                elif ch=="\\": esc=True
                elif ch==quote: quote=None
                continue
            if ch in ("'", '"', "`"): quote=ch
            elif ch=="{": depth+=1
            elif ch=="}":
                depth-=1
                if depth==0:return source[marker.start():i+1]
        raise AssertionError(f"Unclosed production function {name}")
    card,error=live_card("ex5-29", Path(tempfile.gettempdir())/"cardoryx_ex5_beldum_gym_v1")
    if error or not card: raise AssertionError(f"Beldum ex5-29 live fixture unavailable: {error}")
    rows=card.get("variants_detailed") or []
    base=[r for r in rows if not (r.get("stamp") or []) and cm_id(r)==276103 and int(((r.get("pricing") or {}).get("cardmarket") or {}).get("idProduct") or 0)==276103]
    gym=[r for r in rows if [str(x).lower() for x in (r.get("stamp") or [])]==["gym-challenge"] and cm_id(r)==280585 and int(((r.get("pricing") or {}).get("cardmarket") or {}).get("idProduct") or 0)==280585]
    if len(base)!=1 or len(gym)!=1: raise AssertionError(f"Unexpected Beldum product rows base={len(base)} gym={len(gym)}")
    base_cm=(base[0].get("pricing") or {}).get("cardmarket") or {}
    if not any(isinstance(base_cm.get(k),(int,float)) and base_cm.get(k)>0 for k in ("trend","avg7","avg30","avg","low")):
        raise AssertionError("Beldum base V1 has no real Cardmarket price")
    names=("normText","canonicalStamp","canonicalVariant","canonicalFinishTypeLabel","canonicalFinishFoilLabel",
           "cardSetId","canonicalPrintedLocalId","printedLocalIdParts","exactLocalIdKey","tcgdexVariantDetails",
           "tcgdexExactEx5BeldumGymChallengePrice")
    js="\n".join(extract_fn(n) for n in names)
    harness=r'''
const c=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
if(canonicalStamp('gym-challenge')!=='Gym Challenge')fail('taxonomy not canonicalized');
const ok=tcgdexExactEx5BeldumGymChallengePrice(c,'Normal','Gym Challenge');
if(!ok||Number(ok.idProduct)!==280585)fail('exact Gym Challenge product not resolved');
for(const [v,s] of [['Reverse Holo','Gym Challenge'],['Normal','None'],['Normal','GameStop']]){
  if(tcgdexExactEx5BeldumGymChallengePrice(c,v,s)!==null)fail('wrong finish/stamp accepted '+v+' '+s);
}
for(const mutated of [
  {...c,id:'ex5-30',tcgdexId:'ex5-30'},
  {...c,localId:'030'},
  {...c,name:'Beldum wrong'},
  {...c,set:{...(c.set||{}),id:'ex5-other'}},
]) if(tcgdexExactEx5BeldumGymChallengePrice(mutated,'Normal','Gym Challenge')!==null)fail('wrong identity accepted');
const wrongPid={...c,variants_detailed:(c.variants_detailed||[]).map(r=>(r.stamp||[]).includes('gym-challenge')?{...r,thirdParty:{...(r.thirdParty||{}),cardmarket:280586}}:r)};
if(tcgdexExactEx5BeldumGymChallengePrice(wrongPid,'Normal','Gym Challenge')!==null)fail('wrong product accepted');
process.stdout.write(JSON.stringify({baseProductId:276103,gymProductId:ok.idProduct,baseTrend:Number(process.argv[2]),gymTrend:Number(ok.trend||0),exact:true}));
'''
    return json.loads(subprocess.check_output(["node","-e",js+"\n"+harness,json.dumps(card),str(base_cm.get("trend") or 0)],text=True))


def runtime_swsh028_gamestop_regression():
    source = INDEX.read_text(encoding="utf-8")
    def extract_fn(name):
        marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
        if not marker: raise AssertionError(f"Missing production function {name}")
        brace=source.find("{", marker.end()); depth=0; quote=None; esc=False
        for i in range(brace,len(source)):
            ch=source[i]
            if quote:
                if esc: esc=False
                elif ch=="\\": esc=True
                elif ch==quote: quote=None
                continue
            if ch in ("'", '"', "`"): quote=ch
            elif ch=="{": depth+=1
            elif ch=="}":
                depth-=1
                if depth==0:return source[marker.start():i+1]
        raise AssertionError(f"Unclosed production function {name}")
    card,error=live_card("swshp-SWSH028", Path(tempfile.gettempdir())/"cardoryx_swsh028_gamestop_v1")
    if error or not card: raise AssertionError(f"SWSH028 live fixture unavailable: {error}")
    names=("normText","canonicalStamp","canonicalVariant","canonicalFinishTypeLabel","canonicalFinishFoilLabel",
           "cardSetId","canonicalPrintedLocalId","printedLocalIdParts","exactLocalIdKey","tcgdexVariantDetails","tcgdexExactSwsh028GameStopPrice")
    js="\n".join(extract_fn(n) for n in names)
    harness=r'''
const c=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
const ok=tcgdexExactSwsh028GameStopPrice(c,'Holo','GameStop');
if(!ok||Number(ok.idProduct)!==742039)fail('exact GameStop product not resolved');
if(!Number(ok.low)>0 && !Number(ok.trend)>0)fail('no real price');
for(const [v,s] of [['Normal','GameStop'],['Holo','EB Games'],['Holo','None']]){
  if(tcgdexExactSwsh028GameStopPrice(c,v,s)!==null)fail('wrong finish/stamp accepted '+v+' '+s);
}
for(const mutated of [
  {...c,id:'swshp-SWSH029',tcgdexId:'swshp-SWSH029'},
  {...c,localId:'SWSH029'},
  {...c,name:'Duraludon wrong'},
  {...c,set:{...(c.set||{}),id:'swshp-other'}},
]) if(tcgdexExactSwsh028GameStopPrice(mutated,'Holo','GameStop')!==null)fail('wrong identity accepted');
const wrongPid={...c,variants_detailed:(c.variants_detailed||[]).map(r=>(r.stamp||[]).includes('gamestop')?{...r,thirdParty:{...(r.thirdParty||{}),cardmarket:742040}}:r)};
if(tcgdexExactSwsh028GameStopPrice(wrongPid,'Holo','GameStop')!==null)fail('wrong product accepted');
process.stdout.write(JSON.stringify({productId:ok.idProduct,trend:ok.trend,low:ok.low,exact:true}));
'''
    return json.loads(subprocess.check_output(["node","-e",js+"\n"+harness,json.dumps(card)],text=True))


def main():
    args = cli()
    runtime_regression = runtime_cardmarket_regression()
    runtime_regression["svpSetLogoStaff"] = runtime_svp_set_logo_staff_regression()
    runtime_regression["mepSetLogoStaff"] = runtime_mep_set_logo_staff_regression()
    runtime_regression["ex5BeldumGymChallenge"] = runtime_ex5_beldum_gym_challenge_regression()
    runtime_regression["swsh028GameStop"] = runtime_swsh028_gamestop_regression()
    if args.runtime_only:
        print(json.dumps(runtime_regression, ensure_ascii=False, indent=2))
        return
    dirty = []
    for line in git("status", "--porcelain").splitlines():
        path = line.lstrip(" ?MADRCU").strip()
        if path not in {"index.html", "scripts/test_card_identity_cardmarket_audit.py", "artifacts/card_identity_cardmarket_audit_report.json",
                        "scripts/test_variant_finish_audit.py", "artifacts/variant_finish_audit_report.json"}:
            dirty.append(path)
    if dirty:
        raise SystemExit(f"Unrelated worktree changes present: {dirty}")
    products_path = download_if_needed(args.products, "products_singles_6.json")
    prices_path = download_if_needed(args.prices, "price_guide_6.json")
    cards, parse_errors, snapshot_sha = load_snapshot(args.tcgdex_db)
    by_id = {card["id"]: card for card in cards}

    variant_report = json.loads(VARIANT_REPORT.read_text(encoding="utf-8"))
    expected_historical = int((variant_report.get("summary") or {}).get("identitiesAnalyzed") or 4252)
    historical_ids = {row.get("tcgdexId") for row in (variant_report.get("cards") or []) if row.get("tcgdexId")}
    if len(historical_ids) != expected_historical:
        historical_ids = {card["id"] for card in cards[:expected_historical]}
        historical_note = "Il report Variant & Finish non persiste tutti gli ID: la metrica separata 4.252 usa una slice deterministica di pari dimensione; le conclusioni usano il catalogo completo."
    else:
        historical_note = "ID esatti recuperati dal report Variant & Finish."

    historical_current = {row["tcgdexId"]: row.get("cardmarketIdProduct") for row in (variant_report.get("cards") or [])}
    product_root = json.loads(products_path.read_text(encoding="utf-8"))
    price_root = json.loads(prices_path.read_text(encoding="utf-8"))
    products = {int(row["idProduct"]): row for row in rows(product_root, ("products",)) if row.get("idProduct")}
    prices = {int(row["idProduct"]): row for row in rows(price_root, ("priceGuides", "priceGuide")) if row.get("idProduct")}

    pid_to_cards, multi_ids = defaultdict(set), set()
    for card in cards:
        ids = product_ids(card)
        if len(ids) > 1:
            multi_ids.add(card["id"])
        for pid in ids:
            pid_to_cards[pid].add(card["id"])
    shared_pids = {pid: ids for pid, ids in pid_to_cards.items() if len(ids) > 1}
    shared_identity_ids = set().union(*shared_pids.values()) if shared_pids else set()
    candidate_ids = multi_ids | shared_identity_ids | {"sm12-29", "sm12-54", "sm12-237"} | PROTECTED_REVERSE

    # The historical report already persists the exact top-level product read
    # from TCGdex for all 4,252 identities. Only multi-product identities outside
    # that sample require live detail calls; a single-product shared identity has
    # an unambiguous top-level candidate by construction.
    # Shared-product ambiguity is only actionable when current live TCGdex can
    # prove the top-level Cardmarket product against an exact physical base row.
    # Fetch shared identities as evidence; failed/missing live evidence remains
    # fail-closed and cannot downgrade a P1.
    # Exact set-logo/staff evidence requires live rows even when the identity
    # belongs to the historical sample and is not a shared product. Scope this
    # extra fetch strictly to the two promo sets whose taxonomy is verified.
    verified_set_logo_ids = {
        card["id"] for card in cards
        if card["id"].startswith(("svp-", "mep-")) and any(
            "set-logo" in {str(v or "").strip().lower() for v in (row.get("stamp") or [])}
            for row in (card.get("variants_detailed") or [])
        )
    }
    live_targets = ((multi_ids - historical_ids) | shared_identity_ids | verified_set_logo_ids | {"swshp-SWSH028", "ex5-29"} |
                    set(CONFIRMED_BASE_PRODUCT_CONFLICTS) |
                    {"sm12-29", "sm12-54", "sm12-237"} | PROTECTED_REVERSE)
    live, live_errors = {}, {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        futures = {pool.submit(live_card, card_id, args.cache): card_id for card_id in sorted(live_targets)}
        for future in concurrent.futures.as_completed(futures):
            card_id = futures[future]
            value, error = future.result()
            if value:
                live[card_id] = value
            if error:
                live_errors[card_id] = error

    source = INDEX.read_text(encoding="utf-8")
    base_overrides = extract_js_object(source, "VERIFIED_BASE_CARDMARKET_PRODUCT_OVERRIDES")
    if base_overrides != EXPECTED_BASE_OVERRIDES:
        raise AssertionError("Base Cardmarket override registry differs from the 20 audited P0 identities")
    play_index = json.loads(PLAY_INDEX.read_text(encoding="utf-8"))
    torkoal_guard = "knownCardmarketIdentityConflict" in source and "sm12-29" in source and "398524" in source
    protected_reverse = {card_id: card_id in source for card_id in sorted(PROTECTED_REVERSE)}
    cases = []
    for card_id in sorted(candidate_ids):
        card = by_id.get(card_id)
        if not card:
            continue
        details, ids = descriptor_map(card), product_ids(card)
        current_cm = (((live.get(card_id) or {}).get("pricing") or {}).get("cardmarket") or {})
        try:
            current_pid = int(current_cm.get("idProduct") or current_cm.get("id_product"))
        except (TypeError, ValueError):
            try:
                current_pid = int(historical_current.get(card_id))
            except (TypeError, ValueError):
                current_pid = ids[0] if len(ids) == 1 else None
        # TCGdex currently points Piplup CEC54 at the Character Rare CEC239
        # product. Cardmarket's official catalogue proves that product 407919
        # is the same-expansion/same-metacard CEC54 base product. Keep both IDs
        # in the audit even when the snapshot omits one of the physical rows.
        if card_id == "sm12-54":
            ids = sorted(set(ids) | {398504, 407919})
            details = dict(details)
            details[398504] = [{"identity": "CEC239 Character Rare", "source": "Cardmarket official catalogue"}]
            details[407919] = [{"identity": "CEC54 base Normal/Reverse", "source": "Cardmarket official catalogue"}]
        base_ids = sorted({cm_id(row) for row in (card.get("variants_detailed") or []) if cm_id(row) and is_base_row(row)})
        alt_ids = sorted(set(ids) - ({current_pid} if current_pid else set()))
        shared = sorted({other for pid in ids for other in pid_to_cards[pid] if other != card_id})

        # Preserve already-proven alternate Play! products before considering
        # live evidence. The live rule is allowed to clear only P1 ambiguity;
        # it must never flatten an EXACT_ALTERNATE_PRODUCT into generic SAFE.
        snapshot_play_rows = (play_index.get("byBaseProduct") or {}).get(str(current_pid), {}) if current_pid else {}
        snapshot_mapped_play_products = {
            int(row["idProduct"])
            for series in snapshot_play_rows.values()
            for row in series
            if row.get("idProduct")
        }
        snapshot_exact_alternate_product = bool(
            current_pid and len(ids) > 1 and
            (set(ids) - set(base_ids)) and
            snapshot_mapped_play_products.intersection(set(ids) - set(base_ids))
        )

        # Strict live evidence can clear stale snapshot ambiguity only when all
        # identity signals agree on the same physical base product. Special
        # stamp/foil/1st Edition rows never qualify and a reused product stays P1.
        live_card_detail = live.get(card_id) or {}
        live_cm = ((live_card_detail.get("pricing") or {}).get("cardmarket") or {})
        try:
            live_pid = int(live_cm.get("idProduct") or live_cm.get("id_product"))
        except (TypeError, ValueError):
            live_pid = None
        live_base_rows = []
        live_explicit_rows = []
        for live_row in live_card_detail.get("variants_detailed") or []:
            pid = cm_id(live_row)
            pricing_cm = ((live_row.get("pricing") or {}).get("cardmarket") or {})
            try:
                pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))
            except (TypeError, ValueError):
                pricing_pid = None
            if is_base_row(live_row):
                if pid == live_pid and pricing_pid == live_pid:
                    live_base_rows.append(live_row)
            elif pid == live_pid:
                live_explicit_rows.append(live_row)
        live_usable_price = any(
            isinstance(live_cm.get(key), (int, float)) and live_cm.get(key) > 0
            for key in ("trend", "avg7", "avg30", "avg", "low")
        )
        live_exact_base_evidence = bool(
            live_pid and current_pid == live_pid and live_base_rows and
            live_usable_price and not live_explicit_rows
        )

        # Cardoryx production supports an exact dynamic resolver only for the
        # verified SVP/MEP `set-logo` taxonomy. A plain Set Stamp row must
        # exclude `staff`; Staff must contain both tokens. Each row must carry
        # its own matching Cardmarket product + live Price Guide.
        live_svp_set_logo_pair = False
        live_svp_stamp_products = {}
        if card_id.startswith(("svp-", "mep-")):
            def exact_svp_stamp_rows(require_staff):
                exact = []
                for row in live_card_detail.get("variants_detailed") or []:
                    stamp_tokens = {str(v or "").strip().lower() for v in (row.get("stamp") or [])}
                    if "set-logo" not in stamp_tokens:
                        continue
                    if ("staff" in stamp_tokens) != require_staff:
                        continue
                    languages = row.get("languages")
                    if isinstance(languages, list) and languages and "it" not in languages:
                        continue
                    row_type = str(row.get("type") or "").strip().lower()
                    row_foil = str(row.get("foil") or "").strip().lower()
                    supported_finish = (
                        (row_type in {"normal", "holo", "reverse"} and not row_foil) or
                        (row_type == "holo" and row_foil == "cosmos") or
                        (row_type == "reverse" and row_foil in {"pokeball", "masterball"})
                    )
                    if not supported_finish:
                        continue
                    row_pid = cm_id(row)
                    pricing_cm = ((row.get("pricing") or {}).get("cardmarket") or {})
                    try:
                        pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))
                    except (TypeError, ValueError):
                        pricing_pid = None
                    usable = any(
                        isinstance(pricing_cm.get(key), (int, float)) and pricing_cm.get(key) > 0
                        for key in ("trend", "avg7", "avg30", "avg", "low")
                    )
                    if row_pid and pricing_pid == row_pid and usable:
                        exact.append((row, row_pid))
                return exact

            svp_set_rows = exact_svp_stamp_rows(False)
            svp_staff_rows = exact_svp_stamp_rows(True)
            if (len(svp_set_rows) == 1 and len(svp_staff_rows) == 1 and
                    svp_set_rows[0][1] != svp_staff_rows[0][1]):
                live_svp_set_logo_pair = True
                live_svp_stamp_products = {
                    "setStamp": svp_set_rows[0][1],
                    "staff": svp_staff_rows[0][1],
                }

        live_ex5_beldum_gym_pair = False
        live_ex5_beldum_products = None
        if card_id == "ex5-29":
            base_rows = []
            gym_rows = []
            for row in live_card_detail.get("variants_detailed") or []:
                stamp_tokens = [str(v or "").strip().lower() for v in (row.get("stamp") or [])]
                row_pid = cm_id(row)
                pricing_cm = ((row.get("pricing") or {}).get("cardmarket") or {})
                try:
                    pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))
                except (TypeError, ValueError):
                    pricing_pid = None
                usable = any(isinstance(pricing_cm.get(k), (int, float)) and pricing_cm.get(k) > 0
                             for k in ("trend", "avg7", "avg30", "avg", "low"))
                if not stamp_tokens and row_pid == 276103 and pricing_pid == 276103 and usable:
                    base_rows.append(row)
                if (stamp_tokens == ["gym-challenge"] and str(row.get("type") or "").lower() == "normal" and
                        not row.get("foil") and row_pid == 280585 and pricing_pid == 280585 and usable):
                    gym_rows.append(row)
            if len(base_rows) == 1 and len(gym_rows) == 1:
                live_ex5_beldum_gym_pair = True
                live_ex5_beldum_products = {"base": 276103, "gymChallenge": 280585}

        live_swsh028_gamestop = False
        live_swsh028_gamestop_pid = None
        if card_id == "swshp-SWSH028":
            exact_rows = []
            for row in live_card_detail.get("variants_detailed") or []:
                stamp_tokens = [str(v or "").strip().lower() for v in (row.get("stamp") or [])]
                row_pid = cm_id(row)
                pricing_cm = ((row.get("pricing") or {}).get("cardmarket") or {})
                try:
                    pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))
                except (TypeError, ValueError):
                    pricing_pid = None
                usable = any(isinstance(pricing_cm.get(k), (int, float)) and pricing_cm.get(k) > 0
                             for k in ("trend", "avg7", "avg30", "avg", "low"))
                if (stamp_tokens == ["gamestop"] and str(row.get("type") or "").lower() == "holo" and
                        not row.get("foil") and row_pid == 742039 and pricing_pid == 742039 and usable):
                    exact_rows.append(row)
            if len(exact_rows) == 1:
                live_swsh028_gamestop = True
                live_swsh028_gamestop_pid = 742039

        classification, priority, confidence = "SAFE", None, "HIGH"
        reason = "Il prodotto corrente è associato a una riga base e le alternative restano identità fisiche esplicite."
        action = "Nessuna modifica."
        inversion = CONFIRMED_BASE_PRODUCT_CONFLICTS.get(card_id)
        applied_override = False
        resolved_pid = current_pid
        resolved_value = current_value = (prices.get(current_pid) or {}).get("trend") if current_pid else current_cm.get("trend")
        override_tests = None
        if inversion and current_pid == inversion["alternate"]:
            rule = base_overrides.get(card_id)
            applied_override = override_matches(rule, card_id, (card.get("set") or {}).get("id"), card.get("localId"), current_pid)
            exact_live_rows = [row for row in (live.get(card_id) or {}).get("variants_detailed") or []
                               if int((row.get("thirdParty") or {}).get("cardmarket") or 0) == inversion["base"] and
                               int((((row.get("pricing") or {}).get("cardmarket") or {}).get("idProduct") or 0)) == inversion["base"]]
            exact_cm = (((exact_live_rows[0].get("pricing") or {}).get("cardmarket") or {}) if exact_live_rows else {})
            override_tests = {
                "exactIdentityAccepted": applied_override,
                "wrongTcgdexIdRejected": not override_matches(rule, card_id + "-other", (card.get("set") or {}).get("id"), card.get("localId"), current_pid),
                "wrongSetIdRejected": not override_matches(rule, card_id, f"{(card.get('set') or {}).get('id')}-other", card.get("localId"), current_pid),
                "wrongLocalIdRejected": not override_matches(rule, card_id, (card.get("set") or {}).get("id"), str(card.get("localId")) + "9", current_pid),
                "correctedFutureProductRejected": not override_matches(rule, card_id, (card.get("set") or {}).get("id"), card.get("localId"), inversion["base"]),
                "exactLivePriceRowPresent": bool(exact_cm),
            }
            if applied_override:
                resolved_pid = inversion["base"]
                resolved_value = next((exact_cm.get(key) for key in ("trend", "avg7", "avg30", "avg", "low")
                                       if isinstance(exact_cm.get(key), (int, float)) and exact_cm.get(key) > 0), None)
                classification, priority = "SAFE", None
                if exact_cm:
                    reason = "Il resolver applica il prodotto base verificato solo alla quadrupla identità esatta e legge la Price Guide dalla riga live esatta."
                else:
                    reason = "La quadrupla identità esatta blocca il prodotto conflittuale; la Price Guide del prodotto base non è presente nella riga live e il resolver resta fail-closed."
                action = "Mantenere la guardia esatta e il fail-closed; nessun prezzo statico."
            else:
                classification, priority = "P0_WRONG_PRODUCT", "P0"
                reason = "Il conflitto di prodotto è dimostrato ma la guardia esatta non è disponibile."
                action = "Fail-closed; non usare il prodotto conflittuale."
        elif card_id == "sm12-29" and current_pid == 398524:
            classification, priority = "SOURCE_CONFLICT", "P0_PROTECTED"
            reason, action = "TCGdex assegna il prodotto 398524 a un'altra identità fisica; Cardoryx lo blocca già con guardia esatta.", "Mantenere il fail-closed esistente."
        elif card_id in PROTECTED_REVERSE:
            classification, priority = "SOURCE_CONFLICT", "P0_PROTECTED"
            reason, action = "Conflitto Reverse Cardmarket noto e già protetto con identità/prodotto esatti.", "Mantenere il fail-closed esistente."
        elif live_ex5_beldum_gym_pair:
            classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"
            reason = ("Beldum EX Hidden Legends 29/101 ha V1 base Cardmarket 276103 e una stampa Gym Challenge "
                      "fisicamente distinta 280585, entrambe verificate sulla stessa identità live. Il runtime "
                      "separa base Normal/Reverse dallo stamp Gym Challenge senza fallback.")
            action = "Mantenere override base ex5-29 e resolver esatto Gym Challenge; nessuna regola generale per altri set."
        elif live_swsh028_gamestop:
            classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"
            reason = ("TCGdex live espone la stampa GameStop esatta di Duraludon SWSH028 con productId "
                      "Cardmarket 742039 e Price Guide sulla stessa riga fisica. Il runtime la risolve "
                      "solo per identità, finitura e stamp esatti.")
            action = "Mantenere il resolver esatto SWSH028 GameStop; EB Games e gli altri promo restano fail-closed."
        elif live_svp_set_logo_pair:
            classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"
            reason = ("TCGdex live espone una coppia fisica promo esatta e distinta: `set-logo` e "
                      "`set-logo + staff`, ciascuna con il proprio productId e Price Guide Cardmarket. "
                      "Il runtime Cardoryx le risolve separatamente senza fallback tra stamp.")
            action = "Mantenere il resolver set-logo esatto; nessun mapping statico e nessun riuso prezzo fra Set Stamp e Staff."
        elif live_exact_base_evidence and not snapshot_exact_alternate_product:
            classification, priority, confidence = "SAFE", None, "HIGH"
            resolved_pid = live_pid
            resolved_value = next(
                (live_cm.get(key) for key in ("trend", "avg7", "avg30", "avg", "low")
                 if isinstance(live_cm.get(key), (int, float)) and live_cm.get(key) > 0),
                None,
            )
            reason = ("TCGdex live conferma lo stesso productId Cardmarket sia a livello top-level sia "
                      "in una riga fisica base unstamped/unfoiled, con prezzo reale disponibile e senza "
                      "riuso dello stesso prodotto da parte di varianti speciali.")
            action = "Nessuna modifica di produzione: identità base live esatta, falso positivo dello snapshot statico."
        elif not current_pid and len(ids) > 1:
            classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
            reason = "La sorgente espone più prodotti ma non un product ID top-level corrente verificabile."
            action = "Restare fail-closed finché il prodotto principale non è dimostrato."
        elif shared and current_pid and current_pid in shared_pids:
            classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "MEDIUM"
            reason = "Lo stesso prodotto corrente è associato da TCGdex a più tcgdexId fisicamente distinti e non esiste una protezione esatta nota."
            action = "Verificare il prodotto sul catalogo Cardmarket; nel frattempo preferire fail-closed."
        elif current_pid and current_pid not in base_ids:
            classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "MEDIUM"
            reason, action = "Il prodotto top-level corrente non compare tra le righe fisiche base unstamped/unfoiled.", "Verifica esatta V1/V2/V3 prima di qualsiasi mapping."
        elif len(ids) > 1:
            if set(ids) - set(base_ids):
                play_rows = (play_index.get("byBaseProduct") or {}).get(str(current_pid), {}) if current_pid else {}
                mapped_play_products = {int(row["idProduct"]) for series in play_rows.values() for row in series if row.get("idProduct")}
                if mapped_play_products.intersection(set(ids) - set(base_ids)):
                    classification, priority = "EXACT_ALTERNATE_PRODUCT", "P2"
                    reason = "Una variante Play! fisicamente distinta possiede un prodotto esatto e Cardoryx la distingue tramite l'indice locale dedicato."
                    action = "Mantenere il mapping esatto esistente."
                else:
                    classification, priority = "SAFE", None
                    reason = "Le alternative appartengono a stamp/foil espliciti; Cardoryx usa il prodotto base corretto e non trasferisce automaticamente quel prezzo alle alternative."
                    action = "Nessuna modifica: mantenere la separazione/fail-closed corrente."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "MEDIUM"
                reason, action = "Più prodotti Cardmarket sono associati a finiture base senza metadati sufficienti a scegliere automaticamente.", "Verifica esatta V1/V2/V3; non generalizzare."

        case = {
            **card_identity(card), "inHistorical4252": card_id in historical_ids,
            "currentProductId": current_pid, "alternateProductIds": alt_ids, "allProductIds": ids,
            "baseRowProductIdsAccordingToTcgdex": base_ids,
            "physicalVariantsByProductId": {str(pid): details[pid] for pid in ids},
            "cardmarketProductCatalog": {str(pid): products.get(pid) for pid in ids},
            "sharedProductWithTcgdexIds": shared, "currentCardoryxValue": current_value,
            "baseOverrideApplied": applied_override, "resolvedProductId": resolved_pid,
            "resolvedCardoryxValue": resolved_value, "baseOverrideGuardTests": override_tests,
            "liveExactBaseEvidence": live_exact_base_evidence,
            "liveExactBaseProductId": live_pid if live_exact_base_evidence else None,
            "liveExactBasePriceAvailable": live_usable_price,
            "liveExplicitVariantUsesSameProduct": bool(live_explicit_rows),
            "liveExactSvpSetLogoStaffPair": live_svp_set_logo_pair,
            "liveExactSvpStampProducts": live_svp_stamp_products,
            "liveExactEx5BeldumGymChallenge": live_ex5_beldum_gym_pair,
            "liveExactEx5BeldumProducts": live_ex5_beldum_products,
            "liveExactSwsh028GameStop": live_swsh028_gamestop,
            "liveExactSwsh028GameStopProductId": live_swsh028_gamestop_pid,
            "snapshotExactAlternateProductProtected": snapshot_exact_alternate_product,
            "realPriceGuideValues": {str(pid): price_compact(prices.get(pid)) for pid in ids if prices.get(pid)},
            "trendDeltaVersusCurrent": {str(pid): round(row["trend"] - current_value, 2) for pid, row in prices.items()
                                         if pid in ids and pid != current_pid and isinstance(current_value, (int, float)) and isinstance(row.get("trend"), (int, float))},
            "classification": classification, "priority": priority, "confidence": confidence,
            "reason": reason, "recommendedAction": action,
        }
        if inversion and card_id.startswith("sv08-"):
            case["confirmedCardmarketVersionEvidence"] = {
                "V1ProductId": inversion["base"], "V2ProductId": inversion["alternate"],
                "V1Url": f"https://www.cardmarket.com/en/Pokemon/Products/Singles/Surging-Sparks/{case['name']}-V1-{inversion['cardmarketCode']}",
                "V2Url": f"https://www.cardmarket.com/en/Pokemon/Products/Singles/Surging-Sparks/{case['name']}-V2-{inversion['cardmarketCode']}",
                "physicalVariantAccordingToCardmarket": {
                    str(inversion["base"]): "V1 — stampa base standard; prodotto con slot Normal/Reverse",
                    str(inversion["alternate"]): "V2 — stampa Pokémon Horizons stamped",
                },
                "tcgdexAssociationIsInverted": True,
            }
        if card_id == "sm12-54":
            case["verifiedBaseProductId"] = 407919
            case["currentProductPhysicalIdentity"] = "Piplup CEC239 Character Rare"
            case["verifiedBasePhysicalIdentity"] = "Piplup CEC54 base Normal/Reverse"
            case["verifiedBaseProductConflictEvidence"] = {
                "conflictingProductId": 398504, "baseProductId": 407919,
                "exactIdentity": "Cosmic Eclipse / Eclissi Cosmica 054/236",
                "guard": "tcgdexId + setId + normalized localId + current product",
                "priceSourcePolicy": "required live exact variants_detailed product row; otherwise fail-closed",
                "exactLivePriceRowPresent": bool(exact_cm),
            }
        cases.append(case)

    counts = Counter(case["classification"] for case in cases)
    history_cards = [by_id[x] for x in historical_ids if x in by_id]
    p0 = [case for case in cases if case["classification"] == "P0_WRONG_PRODUCT"]
    p1 = [case for case in cases if case["classification"] == "P1_AMBIGUOUS_PRODUCT"]
    over, under = [], []
    for case in p0 + p1:
        current = case.get("currentCardoryxValue")
        alternatives = [row.get("trend") for key, row in case["realPriceGuideValues"].items()
                        if int(key) != case.get("currentProductId") and row and isinstance(row.get("trend"), (int, float))]
        if isinstance(current, (int, float)) and alternatives:
            if current > min(alternatives): over.append((round(current - min(alternatives), 2), case["tcgdexId"], current, min(alternatives)))
            if current < max(alternatives): under.append((round(max(alternatives) - current, 2), case["tcgdexId"], current, max(alternatives)))

    fuecoco = next(case for case in cases if case["tcgdexId"] == "sv08-029")
    fuecoco_snapshot = by_id["sv08-029"]
    fuecoco_live = live.get("sv08-029") or {}
    fuecoco.update({
        "phase1Classification": "SOURCE_CONFLICT",
        "operationalFinding": "WRONG_BASE_PRODUCT",
        "resolutionClass": "NEEDS_EXACT_MAPPING",
        "tcgdexVariants": fuecoco_snapshot.get("variants"),
        "tcgdexVariantsDetailed": fuecoco_snapshot.get("variants_detailed"),
        "liveTcgdexPricingCardmarket": ((fuecoco_live.get("pricing") or {}).get("cardmarket") or {}),
        "liveTcgdexVariantsDetailed": fuecoco_live.get("variants_detailed"),
        "exactNormalUnstampedProductExists": True,
        "productForDisplayedNormalCard": 794286,
        "correctionPolicy": "Applicabile solo con mapping esatto tcgdexId/setId/localId e guardia sul prodotto conflittuale corrente 794946; altrimenti fail-closed.",
        "generalRuleRisk": "HIGH: V1/V2/V3 non codificano universalmente la stessa relazione fisica e includono 1st Edition, shadowless, promo, stamped e reprint.",
    })
    multi_classifications = Counter(c["classification"] for c in cases if len(c["allProductIds"]) > 1)
    historical_classifications = Counter(c["classification"] for c in cases if c["inHistorical4252"])
    confirmed_over = []
    for case in p0:
        current = case.get("currentCardoryxValue")
        alternatives = [row.get("trend") for key, row in case["realPriceGuideValues"].items()
                        if int(key) != case.get("currentProductId") and row and isinstance(row.get("trend"), (int, float))]
        if isinstance(current, (int, float)) and alternatives and current > min(alternatives):
            confirmed_over.append((round(current - min(alternatives), 2), case["tcgdexId"], current, min(alternatives)))
    known_phase_a_p0 = [case for case in p0 if case["tcgdexId"] in EXPECTED_BASE_OVERRIDES]
    piplup = next(case for case in cases if case["tcgdexId"] == "sm12-54")
    report = {
        "schema": 3, "generatedAt": datetime.now(timezone.utc).isoformat(),
        "auditMode": "PRODUCTION_REGRESSION_PLUS_READ_ONLY_PHASE_B_DIAGNOSTIC",
        "mainSha": git("rev-parse", "HEAD"),
        "snapshot": {"tcgdexGitSha": snapshot_sha, "databasePath": str(args.tcgdex_db), "parseErrors": parse_errors,
                     "sameSnapshotAsVariantAudit": snapshot_sha in json.dumps(variant_report)},
        "sources": {"indexHtmlSha256": sha256(INDEX), "variantReportSha256": sha256(VARIANT_REPORT),
                    "cardmarketPlayIndexSha256": sha256(PLAY_INDEX),
                    "cardmarketProducts": {"path": str(products_path), "sha256": sha256(products_path)},
                    "cardmarketPriceGuide": {"path": str(prices_path), "sha256": sha256(prices_path)}, "liveTcgdexApi": API},
        "coverage": {
            "historical4252": {"expectedIdentities": expected_historical, "recoveredIdentities": len(history_cards), "note": historical_note,
                               "identitiesWithCardmarketProduct": sum(bool(product_ids(c)) for c in history_cards),
                               "identitiesWithOneProduct": sum(len(product_ids(c)) == 1 for c in history_cards),
                               "identitiesWithMultipleProducts": sum(len(product_ids(c)) > 1 for c in history_cards)},
            "fullCatalog": {"identitiesAnalyzed": len(cards), "identitiesWithCardmarketProduct": sum(bool(product_ids(c)) for c in cards),
                            "identitiesWithOneProduct": sum(len(product_ids(c)) == 1 for c in cards),
                            "identitiesWithMultipleProducts": len(multi_ids), "distinctProductsSharedAcrossTcgdexIds": len(shared_pids),
                            "candidateIdentitiesDeepAudited": len(cases), "liveDetailRequests": len(live_targets),
                            "liveApiErrors": live_errors}},
        "classificationTotals": {name: counts.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
        "liveExactBaseEvidence": {
            "count": sum(bool(case.get("liveExactBaseEvidence")) for case in cases),
            "ids": [case["tcgdexId"] for case in cases if case.get("liveExactBaseEvidence")],
            "protectedExactAlternateCount": sum(bool(case.get("snapshotExactAlternateProductProtected")) for case in cases),
            "policy": "live top-level product == live physical base-row product == live row pricing product; usable real price; no explicit special row reuses product; existing exact alternate Play products remain protected",
        },
        "p0Regression": {"before": 20, "after": len(known_phase_a_p0),
                         "exactOverridesApplied": sum(bool(c.get("baseOverrideApplied")) for c in cases),
                         "registry": base_overrides,
                         "noP1AutoMapped": not any(c.get("baseOverrideApplied") for c in cases if c["tcgdexId"] not in EXPECTED_BASE_OVERRIDES),
                         "priorThree": {"before": 3, "after": sum(c["classification"] == "P0_WRONG_PRODUCT" for c in cases if c["tcgdexId"].startswith("sv08-") and c["tcgdexId"] in EXPECTED_BASE_OVERRIDES)},
                         "piplup": {"before": 1, "after": int(piplup["classification"] == "P0_WRONG_PRODUCT")}},
        "multiProductClassificationTotals": {name: multi_classifications.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
        "historical4252CandidateClassificationTotals": {name: historical_classifications.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
        "fuecoco": fuecoco, "piplup": piplup, "p0WrongProduct": p0,
        "p1AmbiguousProductIds": [c["tcgdexId"] for c in p1],
        "sourceConflicts": [c for c in cases if c["classification"] == "SOURCE_CONFLICT"],
        "unmappedExactProduct": [c for c in cases if c["classification"] == "UNMAPPED_EXACT_PRODUCT"],
        "caseIndex": [{"tcgdexId": c["tcgdexId"], "classification": c["classification"],
                       "priority": c.get("priority"), "inHistorical4252": c["inHistorical4252"]}
                      for c in cases],
        "alreadyProtected": {"torkoalSm12_29Product398524": torkoal_guard, "reverseConflicts": protected_reverse,
                             "allRequestedProtectionsPresent": torkoal_guard and all(protected_reverse.values())},
        "riskExtremes": {"maximumObservedOvervaluation": max(over, default=None), "maximumObservedUndervaluation": max(under, default=None),
                         "maximumConfirmedP0Overvaluation": max(confirmed_over, default=None),
                         "maximumConfirmedP0Undervaluation": None,
                         "method": "Differenze fra soli campi trend reali Cardmarket; nessuna stima o interpolazione."},
        "safety": {"productionFilesModified": True, "indexHtmlModified": True,
                   "productionChangeScope": "20 exact Cardmarket base-product identity overrides; latest batch adds 9 metacard-verified EX Team Magma vs Team Aqua identities",
                   "cardmarketDataModified": False,
                   "retailModified": False, "retailPricesModified": False, "scannerOcrSearchModified": False,
                   "finishesModified": True, "workflowAdded": False, "mergePerformed": False},
    }
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(OUT), "mainSha": report["mainSha"], "snapshot": snapshot_sha,
                      "coverage": report["coverage"], "classifications": report["classificationTotals"],
                      "fuecoco": {k: fuecoco.get(k) for k in ("currentProductId", "alternateProductIds", "currentCardoryxValue", "classification")},
                      "riskExtremes": report["riskExtremes"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
