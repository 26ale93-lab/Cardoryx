#!/usr/bin/env python3
"""Read-only Cardmarket stale-price audit.

This audit is intentionally separate from Cardmarket product/version mapping
audits. A record can have the correct physical product identity while its
stored price snapshot is old or only partially refreshed.

It NEVER writes:
- data/cardmarket_play_index.json
- data/retail_prices.json
- production application data

The confirmed Aromatisse case is the first regression fixture.
"""

from __future__ import annotations

import argparse
import json
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CARDMARKET_INDEX = ROOT / "data" / "cardmarket_play_index.json"
RETAIL = ROOT / "data" / "retail_prices.json"
OUT = ROOT / "artifacts" / "cardmarket_stale_price_audit_report.json"
CM_BASE = "https://downloads.s3.cardmarket.com/productCatalog"

CONFIRMED_STALE_CASES = {
    "aromatisse-prismatic-evolutions-039-master-ball": {
        "name": "Aromatisse",
        "set": "Prismatic Evolutions",
        "number": "039/131",
        "finish": "Master Ball Reverse Holo",
        "condition": "NM",
        "cardoryxProductId": 806459,
        "cardoryxSnapshot": {
            "low": 3.59,
            "trend": 13.99,
            "avg7": 8.30,
            "reportedLastUpdate": "2026-09-18",
        },
        "manualCardmarketCheck": {
            "checkedAt": "2026-10-10",
            "low": 3.59,
            "trend": 5.24,
            "avg30": 6.28,
            "avg7": 5.90,
            "avg1": 4.50,
        },
        "preliminaryClassification": "POSSIBLE_STALE_PRICE_SNAPSHOT",
        "mustRemainSeparateFromMappingBugs": True,
    }
}


def sha256(path: Path) -> str:
    import hashlib
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def rows(root, keys):
    if isinstance(root, list):
        return root
    if isinstance(root, dict):
        for key in keys:
            value = root.get(key)
            if isinstance(value, list):
                return value
    return []


def download(filename: str) -> Path:
    destination = Path(tempfile.gettempdir()) / filename
    section = "productList" if filename.startswith("products_") else "priceGuide"
    req = urllib.request.Request(
        f"{CM_BASE}/{section}/{filename}",
        headers={"User-Agent": "Cardoryx-Cardmarket-Stale-Audit/1.0"},
    )
    with urllib.request.urlopen(req, timeout=300) as response, destination.open("wb") as out:
        while chunk := response.read(1024 * 1024):
            out.write(chunk)
    return destination


def compact_price(row):
    if not row:
        return None
    return {
        key: row.get(key)
        for key in ("idProduct", "low", "trend", "avg", "avg1", "avg7", "avg30")
        if key in row
    }


def product_identity(row):
    if not row:
        return None
    wanted = (
        "idProduct", "name", "idCategory", "categoryName", "idExpansion",
        "expansionName", "number", "rarity", "countArticles", "dateAdded",
    )
    return {key: row.get(key) for key in wanted if key in row}


def delta(a, b):
    if not isinstance(a, (int, float)) or not isinstance(b, (int, float)):
        return None
    return round(a - b, 4)


def classify_case(case, product, live_price):
    if not product:
        return "PRODUCT_NOT_FOUND"
    if not live_price:
        return "PRICE_GUIDE_PRODUCT_NOT_FOUND"

    old = case["cardoryxSnapshot"]
    same_low = (
        isinstance(old.get("low"), (int, float))
        and isinstance(live_price.get("low"), (int, float))
        and abs(old["low"] - live_price["low"]) < 1e-9
    )
    trend_changed = (
        isinstance(old.get("trend"), (int, float))
        and isinstance(live_price.get("trend"), (int, float))
        and abs(old["trend"] - live_price["trend"]) > 1e-9
    )
    averages_changed = any(
        isinstance(old.get(k), (int, float))
        and isinstance(live_price.get(k), (int, float))
        and abs(old[k] - live_price[k]) > 1e-9
        for k in ("avg7",)
    )

    manual = case.get("manualCardmarketCheck") or {}
    manual_trend = manual.get("trend")
    live_trend = live_price.get("trend")
    manual_differs_from_download = (
        isinstance(manual_trend, (int, float))
        and isinstance(live_trend, (int, float))
        and abs(manual_trend - live_trend) > 1e-9
    )

    # If Cardoryx matches the downloadable Cardmarket Price Guide but the
    # manually verified live Cardmarket page differs, classify this as a source
    # freshness divergence. Do not blame the mapping or estimate a replacement.
    if not trend_changed and not averages_changed and manual_differs_from_download:
        return "CARDMARKET_DOWNLOAD_STALE_VS_LIVE_PAGE"
    # Correct-low / changed-trend is evidence consistent with a stale or partial
    # Cardoryx refresh. It is NOT proof of a wrong product mapping.
    if same_low and (trend_changed or averages_changed):
        return "CARDORYX_STALE_OR_PARTIAL_REFRESH_EVIDENCE"
    if trend_changed or averages_changed:
        return "CARDORYX_PRICE_SNAPSHOT_CHANGED"
    return "CURRENT_VALUES_MATCH_STORED_SNAPSHOT"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--products", type=Path)
    parser.add_argument("--prices", type=Path)
    parser.add_argument(
        "--collection-export",
        type=Path,
        help="Optional Cardoryx collection export. If absent, collection-wide stale count is unavailable.",
    )
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args()

    protected_before = {
        "cardmarket": sha256(CARDMARKET_INDEX),
        "retail": sha256(RETAIL),
    }

    products_path = args.products or download("products_singles_6.json")
    prices_path = args.prices or download("price_guide_6.json")

    product_root = json.loads(products_path.read_text(encoding="utf-8"))
    price_root = json.loads(prices_path.read_text(encoding="utf-8"))
    products = {
        int(r["idProduct"]): r
        for r in rows(product_root, ("products",))
        if r.get("idProduct") is not None
    }
    prices = {
        int(r["idProduct"]): r
        for r in rows(price_root, ("priceGuides", "priceGuide"))
        if r.get("idProduct") is not None
    }

    cases = []
    for key, case in CONFIRMED_STALE_CASES.items():
        pid = int(case["cardoryxProductId"])
        product = products.get(pid)
        live = prices.get(pid)
        classification = classify_case(case, product, live)

        stored = case["cardoryxSnapshot"]
        live_compact = compact_price(live)
        trend_delta = delta(stored.get("trend"), (live or {}).get("trend"))
        trend_percent = None
        live_trend = (live or {}).get("trend")
        if isinstance(trend_delta, (int, float)) and isinstance(live_trend, (int, float)) and live_trend:
            trend_percent = round((trend_delta / live_trend) * 100, 2)

        cases.append({
            "case": key,
            "expectedIdentity": {
                "name": case["name"],
                "set": case["set"],
                "number": case["number"],
                "finish": case["finish"],
                "condition": case["condition"],
            },
            "cardoryxProductId": pid,
            "productCatalogueIdentity": product_identity(product),
            "cardoryxSnapshot": stored,
            "manualCardmarketCheck": case["manualCardmarketCheck"],
            "officialCurrentPriceGuide": live_compact,
            "storedMinusCurrentTrend": trend_delta,
            "storedTrendOverCurrentPercent": trend_percent,
            "classification": classification,
            "sourceFreshnessDivergence": (
                classification == "CARDMARKET_DOWNLOAD_STALE_VS_LIVE_PAGE"
            ),
            "mappingErrorAutomaticallyAssumed": False,
            "separateFromKnownV1V2MappingBugs": True,
        })

    collection_scan = {
        "available": False,
        "reason": "COLLECTION_EXPORT_NOT_PROVIDED",
        "recordsScanned": 0,
        "staleCandidates": None,
    }

    if args.collection_export:
        exported = json.loads(args.collection_export.read_text(encoding="utf-8"))
        if exported.get("format") == "cardoryx-full-backup" and isinstance(exported.get("cards"), list):
            records = []
            for card in exported.get("cards") or []:
                backup = card.get("backupValue") or {}
                variant = str(card.get("variant") or "")
                exact = bool(backup.get("exactVariant"))
                product_id = None
                value_field = None

                # For exact Ball variants, resolve the physical row directly
                # from variants_detailed. This is diagnostic-only.
                if exact and ("Ball Reverse Holo" in variant):
                    target_foil = "Master Ball" if "Master Ball" in variant else "Poké Ball"
                    matches = []
                    for row in card.get("variants_detailed") or []:
                        typ = str(row.get("type") or "").lower()
                        foil = str(row.get("foil") or "")
                        cm = ((row.get("pricing") or {}).get("cardmarket") or {})
                        if "reverse" in typ and target_foil.lower().replace("é","e") in foil.lower().replace("é","e") and cm.get("idProduct"):
                            matches.append(cm)
                    if matches:
                        matches.sort(key=lambda x: str(x.get("updated") or ""))
                        product_id = matches[-1].get("idProduct")
                        value_field = "trend"
                        if matches[-1].get("trend") in (None, 0) and isinstance(matches[-1].get("low"), (int, float)):
                            value_field = "low"

                # Ordinary records use their stored Cardmarket product and the
                # production value slot implied by the selected finish.
                if product_id is None:
                    cm = ((card.get("pricing") or {}).get("cardmarket") or {})
                    product_id = cm.get("idProduct")
                    low_variant = variant.lower()
                    value_field = "trend-holo" if ("holo" in low_variant or "reverse" in low_variant) else "trend"

                records.append({
                    "id": card.get("tcgdexId") or card.get("id"),
                    "name": card.get("name"),
                    "set": card.get("set"),
                    "number": card.get("localId"),
                    "variant": variant,
                    "condition": card.get("condition"),
                    "qty": card.get("qty"),
                    "productId": product_id,
                    "valueField": value_field,
                    "storedUnitValue": backup.get("unitValue"),
                    "storedUpdated": backup.get("updated"),
                    "source": backup.get("source"),
                    "exactVariant": exact,
                })
            exported_at = exported.get("exportedAt")
            collection_summary = exported.get("collection")
        elif exported.get("schema") == "cardoryx-sanitized-price-audit-v1":
            records = exported.get("records")
            exported_at = exported.get("exportedAt")
            collection_summary = exported.get("collection")
        elif isinstance(exported.get("r"), list):
            keys = (
                "id","name","set","number","variant","condition","qty",
                "productId","valueField","storedUnitValue","storedUpdated",
                "source","exactVariant"
            )
            records = [dict(zip(keys, row)) for row in exported["r"] if isinstance(row, list)]
            exported_at = exported.get("e")
            collection_summary = exported.get("c")
        else:
            raise SystemExit("Unsupported collection audit schema")
        if not isinstance(records, list):
            raise SystemExit("Collection audit records missing")

        changed = []
        same = []
        missing_product = []
        missing_price = []
        unresolved = []
        slot_candidates = []

        for rec in records:
            pid = rec.get("productId")
            field = rec.get("valueField")
            stored = rec.get("storedUnitValue")
            if not pid or not field:
                unresolved.append(rec)
                continue
            try:
                pid = int(pid)
            except (TypeError, ValueError):
                unresolved.append(rec)
                continue

            current = prices.get(pid)
            if current is None:
                missing_product.append(rec)
                continue

            current_value = current.get(field)
            if not isinstance(current_value, (int, float)):
                missing_price.append({**rec, "currentGuide": compact_price(current)})
                continue

            row = {
                "id": rec.get("id"),
                "name": rec.get("name"),
                "set": rec.get("set"),
                "number": rec.get("number"),
                "variant": rec.get("variant"),
                "condition": rec.get("condition"),
                "qty": rec.get("qty"),
                "productId": pid,
                "valueField": field,
                "storedUnitValue": stored,
                "currentGuideValue": current_value,
                "delta": delta(stored, current_value),
                "storedUpdated": rec.get("storedUpdated"),
                "source": rec.get("source"),
                "exactVariant": bool(rec.get("exactVariant")),
            }
            if isinstance(stored, (int, float)) and abs(stored-current_value) > 1e-9:
                changed.append(row)
            else:
                same.append(row)

            # Diagnostic only: special physical finishes using the generic
            # 'trend' slot are candidates for a wrong price-slot selection when
            # the same exact product exposes a materially different holo slot.
            variant = str(rec.get("variant") or "").lower()
            special = any(token in variant for token in (
                "master ball", "poké ball", "poke ball", "reverse holo", "cosmos"
            ))
            alt_field = "trend-holo" if field == "trend" else "trend"
            alt_value = current.get(alt_field)
            if special and rec.get("exactVariant") and isinstance(alt_value, (int,float)) and alt_value > 0:
                if abs(alt_value-current_value) > 1e-9:
                    slot_candidates.append({
                        **row,
                        "alternateField": alt_field,
                        "alternateGuideValue": alt_value,
                    })

        changed.sort(key=lambda x: abs(x.get("delta") or 0), reverse=True)
        slot_candidates.sort(
            key=lambda x: abs((x.get("currentGuideValue") or 0)-(x.get("alternateGuideValue") or 0)),
            reverse=True,
        )

        collection_scan = {
            "available": True,
            "providedFile": str(args.collection_export),
            "exportedAt": exported_at,
            "collectionSummary": collection_summary,
            "recordsScanned": len(records),
            "recordsResolvedToProductAndSlot": len(changed)+len(same)+len(missing_product)+len(missing_price),
            "storedValueDiffersFromCurrentDownload": len(changed),
            "storedValueMatchesCurrentDownload": len(same),
            "productMissingFromCurrentGuide": len(missing_product),
            "priceSlotMissingFromCurrentGuide": len(missing_price),
            "unresolvedTargetProductOrSlot": len(unresolved),
            "specialExactPriceSlotCandidates": len(slot_candidates),
            "topChanged": changed[:100],
            "specialExactPriceSlotCandidateRows": slot_candidates[:100],
            "importantLimitation": (
                "This scan detects Cardoryx-vs-downloadable-Price-Guide differences. "
                "It cannot count Cardmarket-download-vs-live-page freshness divergence "
                "without a verified live-page value for each product."
            ),
        }

    protected_after = {
        "cardmarket": sha256(CARDMARKET_INDEX),
        "retail": sha256(RETAIL),
    }
    if protected_before != protected_after:
        raise SystemExit("Protected Cardmarket/retail data changed during read-only audit")

    report = {
        "result": "PASS_READ_ONLY",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "scope": "Cardmarket stale/partial-refresh diagnostics; separate from mapping/version errors",
        "cases": cases,
        "collectionWideStaleScan": collection_scan,
        "rules": {
            "doNotEstimatePrices": True,
            "doNotModifyCardmarketData": True,
            "doNotModifyRetailData": True,
            "doNotTreatMatchingLowAsProofOfCorrectRefresh": True,
            "doNotTreatChangedTrendAsProofOfWrongMapping": True,
        },
        "protectedHashes": {
            "before": protected_before,
            "after": protected_after,
            "unchanged": protected_before == protected_after,
        },
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
