#!/usr/bin/env python3
"""Cardmarket identity regression audit for Cardoryx.

The script only writes its JSON diagnostic report. It verifies the three exact
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
}
PROTECTED_REVERSE = {"pl2-102", "pl3-26", "pl3-5", "pl3-59", "pl3-83", "sv10.5b-013"}
EXPECTED_BASE_OVERRIDES = {
    "sv08-029": {"setId": "sv08", "localId": "029", "conflictingProduct": 794946, "baseProduct": 794286},
    "sv08-050": {"setId": "sv08", "localId": "050", "conflictingProduct": 794947, "baseProduct": 794316},
    "sv08-161": {"setId": "sv08", "localId": "161", "conflictingProduct": 794948, "baseProduct": 794534},
    "sm12-54": {"setId": "sm12", "localId": "054", "conflictingProduct": 398504, "baseProduct": 407919},
}


def cli():
    parser = argparse.ArgumentParser()
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


def main():
    args = cli()
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
    live_targets = (multi_ids - historical_ids) | set(CONFIRMED_BASE_PRODUCT_CONFLICTS) | {"sm12-29", "sm12-54", "sm12-237"} | PROTECTED_REVERSE
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
        raise AssertionError("Base Cardmarket override registry differs from the four audited P0 identities")
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
        "p0Regression": {"before": 4, "after": len(known_phase_a_p0),
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
                   "productionChangeScope": "Four exact Cardmarket base-product identity overrides; this phase adds only Piplup",
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
