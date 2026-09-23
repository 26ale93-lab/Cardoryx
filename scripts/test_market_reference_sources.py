#!/usr/bin/env python3
"""Read-only capability audit for external market-reference sources.

This script does not modify Cardoryx production data, retail_prices.json or any
Cardmarket mapping/price data. It only checks documented/public source
capabilities and whether a minimal public page is structurally accessible.
"""

from __future__ import annotations

import hashlib
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "artifacts" / "market_reference_sources_audit.json"

UA = "Mozilla/5.0 (compatible; CardoryxMarketSourceAudit/1.0; +https://github.com/26ale93-lab/Cardoryx)"
TIMEOUT = 25

SOURCES = {
    "pricechartingDocs": "https://www.pricecharting.com/api-documentation",
    "collectrPrices": "https://getcollectr.com/prices",
    "collectrApiAccess": "https://www.getcollectr.com/marketing-website/index.html",
    "collectrPublicSample": "https://app.getcollectr.com/?query=024%2F131",
    "ebayBrowseDocs": "https://developer.ebay.com/api-docs/buy/api-browse.html",
    "ebaySellerSoldDocs": "https://developer.ebay.com/DevZone/XML/docs/Reference/ebay/types/GetMyeBaySellingRequestType.html",
}


def fetch_text(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.8,*/*;q=0.5",
            "Accept-Language": "en-US,en;q=0.9,it;q=0.7",
            "Connection": "close",
        },
    )
    with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
        body = response.read().decode("utf-8", "replace")
        return {
            "ok": True,
            "status": getattr(response, "status", None),
            "finalUrl": response.geturl(),
            "bytes": len(body.encode("utf-8", "ignore")),
            "sha256": hashlib.sha256(body.encode("utf-8", "ignore")).hexdigest(),
            "text": body,
        }


def safe_fetch(url):
    try:
        return fetch_text(url)
    except Exception as exc:
        return {
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "status": getattr(exc, "code", None),
            "text": "",
        }


def has(text, phrase):
    return phrase.lower() in text.lower()


def count(text, phrase):
    return text.lower().count(phrase.lower())


def main():
    fetched = {name: safe_fetch(url) for name, url in SOURCES.items()}

    pc = fetched["pricechartingDocs"]
    pc_text = pc.get("text", "")
    collectr_prices = fetched["collectrPrices"]
    cp_text = collectr_prices.get("text", "")
    collectr_api = fetched["collectrApiAccess"]
    ca_text = collectr_api.get("text", "")
    collectr_sample = fetched["collectrPublicSample"]
    cs_text = collectr_sample.get("text", "")
    ebay_browse = fetched["ebayBrowseDocs"]
    eb_text = ebay_browse.get("text", "")
    ebay_sold = fetched["ebaySellerSoldDocs"]
    es_text = ebay_sold.get("text", "")

    report = {
        "schema": 1,
        "audit": "external-market-reference-source-capabilities",
        "readOnly": True,
        "productionModified": False,
        "retailPricesModified": False,
        "cardmarketModified": False,
        "sources": {
            "PriceCharting": {
                "docsReachable": pc.get("ok") is True,
                "requiresPaidSubscriptionToken": has(pc_text, "paid subscription"),
                "currentValuesSupported": has(pc_text, "current item values"),
                "historicPricesSupported": not has(pc_text, "Historic prices and historic sales are not supported"),
                "historicSalesSupported": not has(pc_text, "Historic prices and historic sales are not supported"),
                "ungradedCardFieldDocumented": has(pc_text, "loose-price"),
                "tcgIdDocumented": has(pc_text, "tcg-id"),
                "apiRateLimitDocumented": has(pc_text, "1 call every second"),
                "thirdPartySharingNeedsCommercialPermission": has(pc_text, "commercial license"),
                "integrationGate": "TOKEN_AND_LICENSE_REVIEW_REQUIRED",
            },
            "Collectr": {
                "priceGuideReachable": collectr_prices.get("ok") is True,
                "soldListingsAdvertised": has(cp_text, "sold listings"),
                "rawAndGradedCompsAdvertised": has(cp_text, "Raw & graded comps") or has(cp_text, "raw and graded"),
                "historyAdvertised": has(cp_text, "5+ years"),
                "apiAccessAdvertised": has(ca_text, "Collectr API Access"),
                "publicSampleReachable": collectr_sample.get("ok") is True,
                "samplePrintedNumberHits": count(cs_text, "024/131"),
                "sampleNormalVisible": has(cs_text, "Normal"),
                "sampleReverseVisible": has(cs_text, "Reverse Holofoil"),
                "sampleMasterBallVisible": has(cs_text, "Master Ball Pattern"),
                "samplePokeBallVisible": has(cs_text, "Poke Ball Pattern"),
                "languageFiltersSeen": [
                    lang for lang in ("English", "Japanese", "Chinese", "Italian")
                    if has(cs_text, lang)
                ],
                "integrationGate": "OFFICIAL_API_ACCESS_AND_LANGUAGE_SCOPE_REVIEW_REQUIRED",
            },
            "eBay": {
                "browseDocsReachable": ebay_browse.get("ok") is True,
                "browseSearchDocumented": has(eb_text, "search for items"),
                "browseSoldHistoryDocumented": has(eb_text, "sold listings") or has(eb_text, "completed listings"),
                "sellerSoldListDocsReachable": ebay_sold.get("ok") is True,
                "sellerSoldListDocumented": has(es_text, "SoldList"),
                "globalSoldComparableGate": "NO_GENERAL_SOLD_SEARCH_CONFIRMED_FROM_STANDARD_BROWSE_DOCS",
                "activeListingsGate": "APP_TOKEN_REQUIRED_FOR_BROWSE_API",
            },
        },
        "http": {
            name: {
                k: v for k, v in result.items()
                if k != "text"
            }
            for name, result in fetched.items()
        },
        "safeNextSteps": [
            "Keep Cardmarket as the only collection valuation source.",
            "Keep Italian retail stores as independent asking-price references.",
            "Do not integrate PriceCharting until an API token and usage/license scope are available.",
            "Prefer Collectr official API access over scraping if API terms expose card comps/sold listings.",
            "Do not claim eBay active asking prices are completed-sale values.",
            "Any non-Italian/global estimate must be labelled with its actual language/market scope.",
        ],
    }

    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))

    # Audit fails only if all three source families are structurally unreachable.
    reachable = [
        report["sources"]["PriceCharting"]["docsReachable"],
        report["sources"]["Collectr"]["priceGuideReachable"],
        report["sources"]["eBay"]["browseDocsReachable"],
    ]
    if not any(reachable):
        raise SystemExit("No market-reference source family was reachable")


if __name__ == "__main__":
    main()
