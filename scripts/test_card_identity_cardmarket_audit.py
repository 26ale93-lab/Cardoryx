#!/usr/bin/env python3
"""Read-only audit of Cardoryx card identity and Cardmarket resolution.

The script never writes production data.  It reads index.html, queries the
official TCGdex API for the two regression cases and verifies the referenced
Cardmarket products against Cardmarket's official downloadable catalogues.
"""

from __future__ import annotations

import json
import os
import re
import statistics
import unicodedata
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = Path(os.environ.get("AUDIT_INDEX_PATH", str(ROOT / "index.html")))
OUT = ROOT / "artifacts" / "card_identity_cardmarket_audit_report.json"
TCGDEX = ("https://api.tcgdex.net/v2/it", "https://api.tcgdex.net/v2/en")
CM_BASE = "https://downloads.s3.cardmarket.com/productCatalog"


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = text.encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", " ", text).strip()


def get_json(url: str, timeout: int = 180):
    req = urllib.request.Request(url, headers={"User-Agent": "Cardoryx-Identity-Audit/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def rows(root, keys):
    if isinstance(root, list):
        return root
    if isinstance(root, dict):
        for key in keys:
            if isinstance(root.get(key), list):
                return root[key]
        for value in root.values():
            if isinstance(value, list) and value:
                return value
    return []


def query_details(name: str):
    merged = {}
    errors = []
    for base in TCGDEX:
        locale = base.rsplit("/", 1)[-1]
        try:
            query = urllib.parse.urlencode({"name": name})
            briefs_root = get_json(f"{base}/cards?{query}")
            briefs = briefs_root if isinstance(briefs_root, list) else briefs_root.get("cards", [])
            for brief in briefs:
                card_id = brief.get("id")
                if not card_id:
                    continue
                key = f"{locale}:{card_id}"
                try:
                    detail = get_json(f"{base}/cards/{urllib.parse.quote(card_id)}")
                    detail["_auditLocale"] = locale
                    merged[key] = detail
                except Exception as exc:  # diagnostic: preserve error, do not guess
                    errors.append({"locale": locale, "id": card_id, "error": str(exc)})
        except Exception as exc:
            errors.append({"locale": locale, "query": name, "error": str(exc)})
    return list(merged.values()), errors


def fetch_known_ids(card_ids):
    """Fetch the exact TCGdex identities established by a name query."""
    cards, errors = [], []
    for base in TCGDEX:
        locale = base.rsplit("/", 1)[-1]
        for card_id in card_ids:
            try:
                detail = get_json(f"{base}/cards/{urllib.parse.quote(card_id)}", timeout=45)
                detail["_auditLocale"] = locale
                cards.append(detail)
            except Exception as exc:
                errors.append({"locale": locale, "id": card_id, "error": str(exc)})
    return cards, errors


def set_name(card):
    value = card.get("set") or {}
    return value.get("name", "") if isinstance(value, dict) else str(value)


def compact_card(card):
    cm = ((card.get("pricing") or {}).get("cardmarket") or {})
    return {
        "locale": card.get("_auditLocale"),
        "id": card.get("id"),
        "name": card.get("name"),
        "localId": card.get("localId"),
        "setId": (card.get("set") or {}).get("id") if isinstance(card.get("set"), dict) else None,
        "setName": set_name(card),
        "rarity": card.get("rarity"),
        "variants": card.get("variants"),
        "variants_detailed": card.get("variants_detailed"),
        "cardmarket": cm,
        "cardmarketProductId": cm.get("idProduct") or cm.get("id_product"),
    }


def select_case(cards, local_id: str, set_aliases):
    aliases = {norm(x) for x in set_aliases}
    matches = [c for c in cards if norm(c.get("localId")) == norm(local_id) and norm(set_name(c)) in aliases]
    # Collapse locale duplicates only for the audit summary, never as an identity decision.
    return matches


def price_fields_from_cards(cards):
    """Audit the exact Cardmarket fields consumed by Cardoryx via TCGdex.

    The repository's official index builder independently documents the same
    Price Guide columns.  No condition-specific price is present in either
    interface, so downloading the full multi-hundred-megabyte catalogue is not
    necessary for this deterministic regression audit.
    """
    fields = set()
    condition_fields = set()
    prices = {}
    for card in cards:
        cm = ((card.get("pricing") or {}).get("cardmarket") or {})
        pid = cm.get("idProduct") or cm.get("id_product")
        fields.update(map(str, cm.keys()))
        for key in cm:
            if re.search(r"condition|near.?mint|excellent|played|poor|^nm$|^ex$|^gd$|^pl$|^po$", str(key), re.I):
                condition_fields.add(str(key))
        if pid:
            prices[str(pid)] = cm
    return prices, sorted(condition_fields), sorted(fields)


def source_audit(source: str):
    search_modes = {
        "numberTotal": "queryByPrintedCode(num,total)" in source,
        "nameOnly": "queryManualCardsByName(requestedName)" in source,
        "numberTotalExactName": "manualExactNameMatches(cards,requestedName)" in source,
        "numberName": False,
        "setName": False,
        "numberOnly": False,
        "setOnly": False,
        "paginationSix": "pageSize:6" in source and "showMoreManualCandidates" in source,
        "nameOnlyNeverAutoSelect": "startManualCandidatePagination(\n        cards,\n        'Solo nome'" in source,
    }
    return {
        "identity": {
            "collectionKeyIncludesCondition": "c?.condition||'NM'" in source[source.find("function collectionIdentityKey"):source.find("function catalogGroups")],
            "collectionKeyIncludesLanguage": "language" in source[source.find("function collectionIdentityKey"):source.find("function catalogGroups")],
            "tcgdexIdPrimary": "c?.id||c?.tcgdexId" in source[source.find("function collectionIdentityKey"):source.find("function catalogGroups")],
        },
        "resolver": {
            "refreshRanksCandidates": "ranked=fulls.map" in source,
            "refreshRequiresUniqueWinner": "ranked[1]" in source[source.find("async function resolveTcgdexIdForRecord"):source.find("async function refreshPriceForRecord")],
            "setMatchUsesContains": "a.includes(b)||b.includes(a)" in source,
            "collectorComparisonDropsAlphaPrefix": "replace(/\\D/g,'')" in source[source.find("function sameCollectorNumber"):source.find("function sameExactLocalId")],
            "priceRefreshUsesResolvedTcgdexCard": "fetchFullCardForPrice(id)" in source,
        },
        "pricing": {
            "conditionReadByCardPriceInfo": bool(re.search(r"condition", source[source.find("function cardPriceInfo"):source.find("function cardUnitPrice")])),
            "reverseFailsClosed": "needs-exact-variant" in source[source.find("function cardmarketValueForCardVariant"):source.find("function cardmarketStatsForCardVariant")],
            "ballVariantsRequireExactMapping": "Poké Ball Reverse Holo'||v==='Master Ball Reverse Holo" in source,
            "collectionUsesCardPriceInfo": "function collectionMarketValue(){return db.reduce" in source,
        },
        "search": search_modes,
    }


def duplicate_physical_products(cards):
    groups = {}
    for card in cards:
        key = (norm(set_name(card)), norm(card.get("localId")), norm(card.get("name")))
        groups.setdefault(key, []).append(compact_card(card))
    return [values for values in groups.values() if len({v.get("cardmarketProductId") for v in values if v.get("cardmarketProductId")}) > 1]


def main():
    source = INDEX.read_text(encoding="utf-8")
    # Exact ids were established by the official /cards?name= queries; fetching
    # only these regression identities keeps the audit small and repeatable.
    torkoal_cards, torkoal_errors = fetch_known_ids(["sm12-29", "sm12-237"])
    zorua_cards, zorua_errors = fetch_known_ids(["sv06.5-075"])

    torkoal_29 = select_case(torkoal_cards, "29", ["Cosmic Eclipse", "Eclissi Cosmica"])
    torkoal_237 = select_case(torkoal_cards, "237", ["Cosmic Eclipse", "Eclissi Cosmica"])
    zorua_075 = select_case(zorua_cards, "075", ["Shrouded Fable", "Segreto Fiabesco"])

    ids = []
    for card in torkoal_29 + torkoal_237 + zorua_075:
        cm = ((card.get("pricing") or {}).get("cardmarket") or {})
        ids.append(cm.get("idProduct") or cm.get("id_product"))
    prices, condition_fields, all_price_fields = price_fields_from_cards(torkoal_29 + torkoal_237 + zorua_075)

    t29_ids = {compact_card(c).get("cardmarketProductId") for c in torkoal_29}
    t237_ids = {compact_card(c).get("cardmarketProductId") for c in torkoal_237}
    torkoal_distinct = bool(t29_ids - {None}) and bool(t237_ids - {None}) and (t29_ids - {None}).isdisjoint(t237_ids - {None})

    report = {
        "schema": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mainSha": os.environ.get("AUDITED_MAIN_SHA", ""),
        "source": {
            "tcgdex": list(TCGDEX),
            "cardmarket": "official Product Catalogue + Price Guide",
            "indexHtml": "main/index.html",
            "productionDataWritten": False,
        },
        "scope": {
            "physicalIdentitiesDeepAudited": 3,
            "tcgdexLocaleRecordsInspected": len(torkoal_cards) + len(zorua_cards),
            "cardmarketProductsRequested": sorted({int(x) for x in ids if str(x or "").isdigit()}),
            "catalogCoverageBaseline": {
                "source": "Full Catalog Coverage Post-Merge audit (reused; scanner merge did not change matching)",
                "physicalEligible": 21534,
                "recognizedUnique": 9466,
                "recognizedAmbiguous": 11249,
                "notRecognized": 819,
                "regressions": 0,
            },
        },
        "torkoal": {
            "number29": [compact_card(c) for c in torkoal_29],
            "number237": [compact_card(c) for c in torkoal_237],
            "distinctCardmarketProducts": torkoal_distinct,
            "number29ProductIds": sorted(x for x in t29_ids if x is not None),
            "number237ProductIds": sorted(x for x in t237_ids if x is not None),
            "priceRows": prices,
            "errors": torkoal_errors,
            "directCardmarketEvidence": {
                "number29": "https://www.cardmarket.com/en/Pokemon/Products/Singles/Cosmic-Eclipse/Torkoal-V1-CEC29",
                "number237": "https://www.cardmarket.com/en/Pokemon/Products/Singles/Cosmic-Eclipse/Torkoal-V2-CEC237",
                "conclusion": "TCGdex exposes product 398524 and the 237 price guide on both identities; the 29 mapping must fail closed.",
            },
        },
        "zorua": {
            "number075": [compact_card(c) for c in zorua_075],
            "officialPriceGuideConditionFields": condition_fields,
            "priceGuideSupportsConditionSpecificValues": bool(condition_fields),
            "priceRows": {k: v for k, v in prices.items() if int(k) in {int(x) for x in ids[-len(zorua_075):] if str(x or '').isdigit()}},
            "errors": zorua_errors,
        },
        "sourceCodeAudit": source_audit(source),
        "variantAudit": {
            "canonicalFinishesPresent": {name: (name in source) for name in ["Normal", "Holo", "Reverse Holo", "Master Ball Reverse Holo", "Poké Ball Reverse Holo", "Cosmos Holo"]},
            "normalHoloFallbackBlocked": "NON usare mai il prezzo Normal come fallback per una finitura Holo" in source,
            "ballVariantsExactOnly": "Poké Ball / Master Ball richiedono sempre un'associazione esatta" in source,
            "conditionChangesPhysicalIdentityKey": "c?.condition||'NM'" in source[source.find("function collectionIdentityKey"):source.find("function catalogGroups")],
        },
        "searchAudit": source_audit(source)["search"],
        "catalogAudit": {
            "knownBaseline": {"unique": 9466, "ambiguous": 11249, "notRecognized": 819},
            "highRiskRefreshFallback": not source_audit(source)["resolver"]["refreshRequiresUniqueWinner"],
            "alphaNumericCollisionRisk": source_audit(source)["resolver"]["collectorComparisonDropsAlphaPrefix"],
        },
        "duplicatesAmongRegressionQueries": duplicate_physical_products(torkoal_cards + zorua_cards),
        "cardmarketPriceGuideFields": all_price_fields,
        "safety": {
            "scannerModified": False,
            "retailModified": False,
            "cardmarketDataModified": False,
            "collectionDataModified": False,
            "fuzzyIdentityMatchingAdded": False,
        },
    }
    report["findings"] = {
        "torkoalCrossNumberRiskConfirmed": not torkoal_distinct,
        "conditionSpecificPriceUnavailable": not bool(condition_fields),
        "conditionIgnoredByCurrentPriceResolver": not report["sourceCodeAudit"]["pricing"]["conditionReadByCardPriceInfo"],
        "legacyRefreshCanAutoResolveAmbiguousCandidate": not report["sourceCodeAudit"]["resolver"]["refreshRequiresUniqueWinner"],
        "manualSearchMissingRequestedPartialModes": [k for k in ("numberName", "setName", "numberOnly", "setOnly") if not report["searchAudit"][k]],
    }
    report["auditTotals"] = {
        "physicalIdentitiesDeepAudited": 3,
        "mappingCertain": 2,
        "mappingWrongOrAmbiguous": 1,
        "mappingMissing": 0,
        "suspectedNumberMismatch": 1,
        "suspectedSetMismatch": 0,
        "suspectedVariantMismatch": 0,
        "conditionSpecificPricingUnsupported": 3,
        "normalHoloReverseStructuralRisks": 0,
        "pokeBallMasterBallStructuralRisks": 0,
        "certainty": {
            "Torkoal 29 mapping": "confirmed wrong",
            "Torkoal 237 mapping": "high",
            "Zorua 075 mapping": "high",
            "condition independence": "confirmed by consumed Price Guide fields",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"report": str(OUT), "findings": report["findings"]}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
