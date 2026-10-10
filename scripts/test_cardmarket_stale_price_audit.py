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

    # Deliberately fail closed on collection-wide counting: repo data does not
    # represent the user's live IndexedDB collection. A real export is required.
    if args.collection_export:
        collection_scan = {
            "available": False,
            "reason": "COLLECTION_EXPORT_SCHEMA_NOT_YET_VERIFIED",
            "recordsScanned": 0,
            "staleCandidates": None,
            "providedFile": str(args.collection_export),
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
