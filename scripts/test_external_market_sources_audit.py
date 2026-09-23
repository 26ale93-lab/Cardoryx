#!/usr/bin/env python3
"""Cardoryx external market sources audit (READ-ONLY).

Purpose:
- classify PriceCharting, Collectr and eBay capabilities without touching production;
- verify whether required credentials are configured;
- make no scraping requests and never bypass anti-bot/captcha protections;
- keep Cardmarket and retail_prices.json untouched.

Optional environment variables:
  PRICECHARTING_TOKEN
  COLLECTR_API_KEY
  EBAY_CLIENT_ID
  EBAY_CLIENT_SECRET

The audit intentionally performs no authenticated API calls unless a future
revision adds a documented endpoint and an explicit test for that source.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPORT = ROOT / "external_market_sources_audit_report.json"


def present(name: str) -> bool:
    return bool(str(os.getenv(name, "")).strip())


def source(name, capability, access, usable_now, blockers, notes, docs):
    return {
        "source": name,
        "capability": capability,
        "access": access,
        "usableNow": usable_now,
        "blockers": blockers,
        "notes": notes,
        "officialDocs": docs,
    }


def main():
    credentials = {
        "priceChartingTokenConfigured": present("PRICECHARTING_TOKEN"),
        "collectrApiKeyConfigured": present("COLLECTR_API_KEY"),
        "ebayClientIdConfigured": present("EBAY_CLIENT_ID"),
        "ebayClientSecretConfigured": present("EBAY_CLIENT_SECRET"),
    }

    pricecharting_ready = credentials["priceChartingTokenConfigured"]
    collectr_ready = credentials["collectrApiKeyConfigured"]
    ebay_ready = (
        credentials["ebayClientIdConfigured"]
        and credentials["ebayClientSecretConfigured"]
    )

    sources = [
        source(
            "PriceCharting",
            {
                "currentMarketEstimate": True,
                "activeListings": False,
                "historicSales": False,
                "rawUngradedPrice": True,
                "gradedPrices": True,
            },
            {
                "officialApi": True,
                "paidSubscriptionRequired": True,
                "commercialPermissionRequiredForThirdPartyApp": True,
            },
            pricecharting_ready,
            [] if pricecharting_ready else ["PRICECHARTING_TOKEN_NOT_CONFIGURED"],
            [
                "Use only official Prices API/CSV.",
                "Do not scrape public product pages.",
                "Historic sales are not provided by the Prices API/CSV.",
                "Product matching must remain fail-closed on set/card/variant identity.",
            ],
            ["https://www.pricecharting.com/api-documentation"],
        ),
        source(
            "Collectr",
            {
                "currentMarketEstimate": True,
                "activeListings": True,
                "historicSales": True,
                "rawUngradedPrice": True,
                "gradedPrices": True,
            },
            {
                "officialApi": True,
                "approvalRequired": True,
                "automatedScrapingForbidden": True,
            },
            collectr_ready,
            [] if collectr_ready else ["COLLECTR_API_APPROVAL_OR_KEY_NOT_CONFIGURED"],
            [
                "Automated scraping/reverse engineering is not permitted.",
                "Integration must wait for approved API access and endpoint documentation.",
                "Do not infer API endpoints from the app or website.",
            ],
            [
                "https://getcollectr.com/api-terms-and-conditions.html",
                "https://getcollectr.com/prices",
            ],
        ),
        source(
            "eBay",
            {
                "currentMarketEstimate": False,
                "activeListings": True,
                "historicSales": False,
                "sellerOwnedCompletedSales": True,
                "rawUngradedPrice": False,
                "gradedPrices": False,
            },
            {
                "officialBrowseApi": True,
                "oauthClientCredentialsRequired": True,
                "generalMarketplaceCompletedSalesSearch": False,
            },
            ebay_ready,
            [] if ebay_ready else ["EBAY_APPLICATION_CREDENTIALS_NOT_CONFIGURED"],
            [
                "Browse API is suitable for active listings and supports EBAY_IT.",
                "Seller transaction APIs expose completed sales for the authenticated seller.",
                "Do not label active asking prices as sold prices.",
                "Do not scrape completed-listing pages to manufacture a sold-history feed.",
            ],
            [
                "https://developer.ebay.com/api-docs/buy/api-browse.html",
                "https://developer.ebay.com/devzone/xml/docs/Reference/ebay/GetSellerTransactions.html",
            ],
        ),
    ]

    recommended_model = {
        "cardmarket": {
            "role": "primaryCollectionValuation",
            "mustRemainSeparate": True,
        },
        "retailStores": {
            "role": "independentAskingPriceReferences",
            "minimumStoresToDisplay": 1,
        },
        "priceCharting": {
            "role": "externalMarketEstimate",
            "enabledOnlyWithOfficialAccess": True,
        },
        "collectr": {
            "role": "externalMarketAndSoldCompsReference",
            "enabledOnlyWithApprovedApiAccess": True,
        },
        "ebay": {
            "role": "activeAskingPrices",
            "soldComps": "unsupported-for-general-marketplace-with-current-official-path",
        },
    }

    report = {
        "audit": "Cardoryx external market sources",
        "readOnly": True,
        "productionModified": False,
        "cardmarketModified": False,
        "retailPricesModified": False,
        "antiBotBypassAttempted": False,
        "credentials": credentials,
        "sources": sources,
        "recommendedModel": recommended_model,
        "nextGate": {
            "priceCharting": (
                "RUN_MATCHING_SAMPLE"
                if pricecharting_ready
                else "OBTAIN_API_TOKEN_AND_LICENSE_CLARITY"
            ),
            "collectr": (
                "RUN_DOCUMENTED_API_SAMPLE"
                if collectr_ready
                else "REQUEST_API_ACCESS"
            ),
            "ebay": (
                "RUN_ACTIVE_LISTING_SAMPLE"
                if ebay_ready
                else "CREATE_EBAY_DEVELOPER_APP"
            ),
        },
    }

    REPORT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
