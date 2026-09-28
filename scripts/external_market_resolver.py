#!/usr/bin/env python3
"""Cardoryx external market estimate resolver.

Pure policy module. It does not call providers and does not write Cardmarket or
retail data. Provider adapters must normalize their live responses before
passing candidates here.

External market estimates are informational only:
- never affect Cardmarket collection value;
- never count as independent retail shops;
- never get averaged across providers.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable, Mapping, Sequence

SOURCE_TYPE = "external_market_estimate"
DEFAULT_PROVIDER_PRIORITY = (
    "pokemonpricetracker",
    "pkmnprices",
    "justtcg",
)

RETRYABLE_PROVIDER_STATUSES = {
    "MISSING",
    "NO_NM_PRICE",
    "QUOTA_BLOCKED",
    "RATE_LIMITED",
    "UNAVAILABLE",
    "SET_UNRESOLVED",
}

REJECTED_PROVIDER_STATUSES = {
    "AMBIGUOUS",
    "IDENTITY_MISMATCH",
    "PRINTING_MISMATCH",
    "NUMBER_MISMATCH",
    "SET_MISMATCH",
    "LANGUAGE_MISMATCH",
    "UNSUPPORTED_SCHEMA",
}


@dataclass(frozen=True)
class ExpectedIdentity:
    tcgplayer_id: str
    set_key: str
    card_number: str
    printing: str
    market_language: str = "English"
    condition: str = "Near Mint"
    currency: str = "USD"


@dataclass(frozen=True)
class ProviderCandidate:
    provider: str
    status: str
    tcgplayer_id: str | None = None
    set_key: str | None = None
    card_number: str | None = None
    printing: str | None = None
    market_language: str | None = None
    condition: str | None = None
    currency: str | None = None
    market_price: object | None = None
    observed_name: str | None = None
    observed_at: str | None = None


def _canon(value: object | None) -> str:
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def _canon_number(value: object | None) -> str:
    text=str(value or "").strip()
    if "/" in text:
        text=text.split("/",1)[0]
    return text.lstrip("0") or "0"


def _decimal_price(value: object | None) -> Decimal | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        price=Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not price.is_finite() or price < 0:
        return None
    return price


def validate_candidate(expected: ExpectedIdentity, candidate: ProviderCandidate) -> dict:
    """Validate one provider-normalized candidate against exact identity gates."""
    if candidate.status != "EXACT_ONE":
        return {
            "accepted": False,
            "provider": candidate.provider,
            "status": candidate.status,
            "reason": candidate.status,
        }

    checks = (
        ("IDENTITY_MISMATCH", str(candidate.tcgplayer_id or "") == str(expected.tcgplayer_id)),
        ("SET_MISMATCH", _canon(candidate.set_key) == _canon(expected.set_key)),
        ("NUMBER_MISMATCH", _canon_number(candidate.card_number) == _canon_number(expected.card_number)),
        ("PRINTING_MISMATCH", _canon(candidate.printing) == _canon(expected.printing)),
        ("LANGUAGE_MISMATCH", _canon(candidate.market_language) == _canon(expected.market_language)),
        ("CONDITION_MISMATCH", _canon(candidate.condition) == _canon(expected.condition)),
        ("CURRENCY_MISMATCH", _canon(candidate.currency) == _canon(expected.currency)),
    )
    for reason, ok in checks:
        if not ok:
            return {
                "accepted": False,
                "provider": candidate.provider,
                "status": reason,
                "reason": reason,
            }

    price=_decimal_price(candidate.market_price)
    if price is None:
        return {
            "accepted": False,
            "provider": candidate.provider,
            "status": "NO_NM_PRICE",
            "reason": "NO_NM_PRICE",
        }

    return {
        "accepted": True,
        "provider": candidate.provider,
        "status": "EXACT_MARKET_ESTIMATE",
        "price": str(price),
        "currency": expected.currency,
        "condition": expected.condition,
        "marketLanguage": expected.market_language,
        "printing": expected.printing,
        "tcgPlayerId": expected.tcgplayer_id,
        "observedName": candidate.observed_name,
        "observedAt": candidate.observed_at,
    }


def resolve_external_market_estimate(
    expected: ExpectedIdentity,
    candidates: Iterable[ProviderCandidate],
    provider_priority: Sequence[str] = DEFAULT_PROVIDER_PRIORITY,
) -> dict:
    """Select one exact external estimate without averaging provider prices."""
    by_provider: dict[str, ProviderCandidate] = {}
    duplicates: set[str] = set()
    for candidate in candidates:
        provider=str(candidate.provider or "").strip().lower()
        if not provider:
            continue
        if provider in by_provider:
            duplicates.add(provider)
            continue
        by_provider[provider]=candidate

    audit=[]
    anomalies=[]
    if duplicates:
        anomalies.extend(f"DUPLICATE_PROVIDER:{x}" for x in sorted(duplicates))

    for provider in provider_priority:
        key=str(provider).strip().lower()
        candidate=by_provider.get(key)
        if candidate is None:
            audit.append({"provider": key, "status": "UNAVAILABLE", "accepted": False})
            continue

        checked=validate_candidate(expected,candidate)
        audit.append(checked)
        if checked.get("accepted"):
            return {
                "available": True,
                "sourceType": SOURCE_TYPE,
                "provider": key,
                "price": checked["price"],
                "currency": checked["currency"],
                "condition": checked["condition"],
                "marketLanguage": checked["marketLanguage"],
                "printing": checked["printing"],
                "tcgPlayerId": checked["tcgPlayerId"],
                "observedName": checked.get("observedName"),
                "observedAt": checked.get("observedAt"),
                "affectsCollectionValue": False,
                "countsAsRetailShop": False,
                "pricesAveraged": False,
                "providerPriority": list(provider_priority),
                "audit": audit,
                "anomalies": anomalies,
            }

        status=str(checked.get("status") or "")
        if status in REJECTED_PROVIDER_STATUSES or status.endswith("_MISMATCH"):
            anomalies.append(f"{key}:{status}")
        # Rejected or unavailable provider never contributes a price. Continue
        # only to seek a fully exact independent provider response.

    return {
        "available": False,
        "sourceType": SOURCE_TYPE,
        "display": "Riferimento mercato esterno non disponibile",
        "affectsCollectionValue": False,
        "countsAsRetailShop": False,
        "pricesAveraged": False,
        "providerPriority": list(provider_priority),
        "audit": audit,
        "anomalies": anomalies,
    }


def candidate_from_mapping(provider: str, row: Mapping[str, object]) -> ProviderCandidate:
    """Small adapter helper for already-normalized provider rows."""
    return ProviderCandidate(
        provider=provider,
        status=str(row.get("status") or ""),
        tcgplayer_id=None if row.get("tcgPlayerId") is None else str(row.get("tcgPlayerId")),
        set_key=None if row.get("setKey") is None else str(row.get("setKey")),
        card_number=None if row.get("cardNumber") is None else str(row.get("cardNumber")),
        printing=None if row.get("printing") is None else str(row.get("printing")),
        market_language=None if row.get("marketLanguage") is None else str(row.get("marketLanguage")),
        condition=None if row.get("condition") is None else str(row.get("condition")),
        currency=None if row.get("currency") is None else str(row.get("currency")),
        market_price=row.get("marketPrice"),
        observed_name=None if row.get("observedName") is None else str(row.get("observedName")),
        observed_at=None if row.get("observedAt") is None else str(row.get("observedAt")),
    )
