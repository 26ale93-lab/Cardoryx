#!/usr/bin/env python3
"""Read-only JustTCG audit for Cardoryx.

Purpose:
- evaluate JustTCG as an external market-estimate source;
- never write Cardoryx valuation/retail data;
- fail closed when authentication, set identity, or response shape is unclear.

Required env:
  JUSTTCG_API_KEY

Output:
  stdout JSON summary only.
"""

from __future__ import annotations

import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

BASE = "https://api.justtcg.com/v1"
GAME = "pokemon"
SET_QUERY = "Ascended Heroes"
EXPECTED_SET_NAME_TOKENS = {"ascended", "heroes"}
LIMIT = 20
MAX_CARD_PAGES = 50  # 1,000 cards max; stays within the free daily quota for this isolated audit.
REQUEST_SLEEP_SECONDS = 6.2  # free tier: <=10 requests/minute.


def fail(message: str, *, details=None, code: int = 1):
    payload = {"result": "FAIL_CLOSED", "message": message}
    if details is not None:
        payload["details"] = details
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(code)


def api_get(path: str, api_key: str, params=None):
    qs = urllib.parse.urlencode(params or {}, doseq=True)
    url = f"{BASE}{path}" + (f"?{qs}" if qs else "")
    req = urllib.request.Request(
        url,
        headers={
            "x-api-key": api_key,
            "accept": "application/json",
            "user-agent": "Cardoryx-JustTCG-ReadOnly-Audit/1.0",
        },
        method="GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
            body = json.loads(raw)
            return resp.status, dict(resp.headers), body
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            body = json.loads(raw)
        except Exception:
            body = {"raw": raw[:2000]}
        fail(
            f"JustTCG HTTP {exc.code}",
            details={"url": url.split("?")[0], "response": body},
        )
    except Exception as exc:
        fail("JustTCG request failed", details={"type": type(exc).__name__, "error": str(exc)})


def norm(value):
    return "".join(ch.lower() for ch in str(value or "") if ch.isalnum())


def exact_set_candidates(rows):
    out = []
    for row in rows:
        name = str(row.get("name") or "")
        tokens = {t for t in norm(name).replace("-", " ").split() if t}
        # norm() removes separators, so also use ordinary lowercase tokenization.
        ordinary = {x.strip("—–-:()[]").lower() for x in name.replace("—", " ").replace("-", " ").split()}
        if EXPECTED_SET_NAME_TOKENS.issubset(ordinary):
            out.append(row)
    return out


def variant_language(v):
    lang = v.get("language")
    return str(lang or "English").strip() or "English"


def main():
    api_key = os.environ.get("JUSTTCG_API_KEY", "").strip()
    if not api_key:
        fail("Missing JUSTTCG_API_KEY. No network audit executed.", code=2)

    # 1) Prove API/auth works and Pokemon exists.
    _, _, games = api_get("/games", api_key)
    game_rows = games.get("data") or []
    pokemon = [g for g in game_rows if str(g.get("id") or "").lower() == GAME]
    if len(pokemon) != 1:
        fail("Pokemon game identity not uniquely available", details={"matches": pokemon})

    time.sleep(REQUEST_SLEEP_SECONDS)

    # 2) Resolve exact set by official JustTCG set search.
    _, _, sets = api_get("/sets", api_key, {"game": GAME, "q": SET_QUERY})
    set_rows = sets.get("data") or []
    candidates = exact_set_candidates(set_rows)
    if len(candidates) != 1:
        fail(
            "Ascended Heroes set did not resolve uniquely",
            details={"query": SET_QUERY, "candidates": candidates, "returned": set_rows[:20]},
        )
    target_set = candidates[0]
    set_id = target_set.get("id")
    if not set_id:
        fail("Resolved set has no stable id", details=target_set)

    cards = []
    request_metadata = []
    offset = 0

    # 3) Read-only paginated set scan.
    for page in range(MAX_CARD_PAGES):
        time.sleep(REQUEST_SLEEP_SECONDS)
        _, headers, body = api_get(
            "/cards",
            api_key,
            {
                "game": GAME,
                "set": set_id,
                "limit": LIMIT,
                "offset": offset,
                "include_null_prices": "true",
            },
        )
        data = body.get("data") or []
        meta = body.get("meta") or {}
        metadata = body.get("_metadata") or {}
        total = meta.get("total")
        if not isinstance(total, int) or total < 1:
            fail("Pagination metadata has no valid total", details={"meta": meta})
        if expected_total is None:
            expected_total = total
            if expected_total > MAX_CARD_PAGES * LIMIT:
                fail(
                    "Set exceeds audit safety budget",
                    details={"total": expected_total, "maxCards": MAX_CARD_PAGES * LIMIT, "set": set_id},
                )
        elif total != expected_total:
            fail("Pagination total changed during audit", details={"expected": expected_total, "actual": total})

        wrong_set = [
            {"id": c.get("id"), "set": c.get("set"), "set_name": c.get("set_name")}
            for c in data
            if str(c.get("set") or "") != str(set_id)
        ]
        if wrong_set:
            fail("Set filter returned cards from another set", details={"expectedSet": set_id, "cards": wrong_set[:10]})

        request_metadata.append(
            {
                "page": page + 1,
                "count": len(data),
                "total": total,
                "offset": meta.get("offset"),
                "remainingMonthly": metadata.get("apiRequestsRemaining"),
                "remainingDaily": metadata.get("apiDailyRequestsRemaining"),
                "plan": metadata.get("apiPlan"),
            }
        )
        cards.extend(data)

        has_more = bool(meta.get("hasMore"))
        if not has_more:
            break
        if not data:
            fail("Pagination claimed more data but returned an empty page", details={"meta": meta})
        offset += LIMIT
    else:
        fail("Card pagination exceeded safety cap", details={"maxPages": MAX_CARD_PAGES, "set": set_id})

    if not cards:
        fail("Resolved set returned zero cards", details=target_set)
    if expected_total is None or len(cards) != expected_total:
        fail("Pagination did not return the advertised total", details={"expected": expected_total, "actual": len(cards)})

    unique_ids = [str(c.get("id") or "") for c in cards]
    if any(not x for x in unique_ids) or len(unique_ids) != len(set(unique_ids)):
        fail("Card IDs missing or duplicated", details={"cards": len(cards), "uniqueIds": len(set(unique_ids))})

    card_names = Counter()
    numbers = Counter()
    rarities = Counter()
    printings = Counter()
    conditions = Counter()
    languages = Counter()
    variants_total = 0
    variants_priced = 0
    cards_with_any_price = 0
    cards_with_italian = 0
    cards_with_italian_price = 0
    null_price_variants = 0
    per_card = []

    for card in cards:
        card_names[str(card.get("name") or "")] += 1
        number = str(card.get("number") or "").strip()
        if number:
            numbers[number] += 1
        rarity = str(card.get("rarity") or "UNKNOWN")
        rarities[rarity] += 1

        variants = card.get("variants") or []
        if not isinstance(variants, list):
            fail("Unexpected variants shape", details={"card": card.get("id")})

        has_price = False
        has_it = False
        has_it_price = False
        observed = []

        for v in variants:
            variants_total += 1
            printing = str(v.get("printing") or "UNKNOWN")
            condition = str(v.get("condition") or "UNKNOWN")
            language = variant_language(v)
            price = v.get("price")

            printings[printing] += 1
            conditions[condition] += 1
            languages[language] += 1

            if price is None:
                null_price_variants += 1
            elif isinstance(price, (int, float)) and price >= 0:
                variants_priced += 1
                has_price = True
            else:
                fail("Unexpected price value", details={"card": card.get("id"), "variant": v})

            if language.lower() == "italian":
                has_it = True
                if isinstance(price, (int, float)) and price >= 0:
                    has_it_price = True

            observed.append(
                {
                    "condition": condition,
                    "printing": printing,
                    "language": language,
                    "priced": isinstance(price, (int, float)) and price >= 0,
                }
            )

        cards_with_any_price += int(has_price)
        cards_with_italian += int(has_it)
        cards_with_italian_price += int(has_it_price)
        per_card.append(
            {
                "id": card.get("id"),
                "name": card.get("name"),
                "number": card.get("number"),
                "tcgplayerId": card.get("tcgplayerId"),
                "variantCount": len(variants),
                "observed": observed,
            }
        )

    noibat = [
        c for c in per_card
        if str(c.get("name") or "").strip().lower() == "noibat"
        and str(c.get("number") or "").lstrip("0") == "156"
    ]

    # Noibat is a diagnostic anchor, not a hard integration assumption.
    noibat_status = "EXACT_ONE" if len(noibat) == 1 else ("MISSING" if not noibat else "AMBIGUOUS")

    summary = {
        "result": "PASS_READ_ONLY",
        "sourceClassification": "market estimate (provider states blended listings + verified in-store sales; not completed-sales-only)",
        "writesPerformed": False,
        "target": {
            "game": GAME,
            "setQuery": SET_QUERY,
            "resolvedSet": target_set,
        },
        "requests": {
            "count": 2 + len(request_metadata),  # games + sets + card pages
            "advertisedTotalCards": expected_total,
            "cardPages": request_metadata,
        },
        "coverage": {
            "cards": len(cards),
            "cardsWithAnyPrice": cards_with_any_price,
            "cardsWithAnyPricePct": round(cards_with_any_price * 100 / len(cards), 2),
            "variants": variants_total,
            "variantsPriced": variants_priced,
            "variantsPricedPct": round(variants_priced * 100 / variants_total, 2) if variants_total else 0,
            "nullPriceVariants": null_price_variants,
            "cardsWithItalianVariant": cards_with_italian,
            "cardsWithItalianPricedVariant": cards_with_italian_price,
        },
        "taxonomy": {
            "printings": dict(printings.most_common()),
            "conditions": dict(conditions.most_common()),
            "languages": dict(languages.most_common()),
            "rarities": dict(rarities.most_common()),
        },
        "identityDiagnostics": {
            "duplicateNumbers": {k: v for k, v in numbers.items() if v > 1},
            "duplicateNames": {k: v for k, v in card_names.items() if v > 1},
            "noibat156Status": noibat_status,
            "noibat156": noibat,
        },
        "integrationDecision": {
            "automaticProductionIntegration": False,
            "reason": "Audit only. Exact Cardoryx identity mapping and source semantics must be validated before any production use.",
        },
    }

    print(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
