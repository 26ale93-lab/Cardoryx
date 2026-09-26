#!/usr/bin/env python3
"""Read-only JustTCG ↔ Cardoryx identity mapping audit for Ascended Heroes.

Scope:
- exact set only;
- exact card number;
- exact physical finish;
- Near Mint price availability measured, never integrated;
- no writes to Cardmarket or retail data.

Required env:
  JUSTTCG_API_KEY
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict

JUST_BASE = "https://api.justtcg.com/v1"
JUST_SET_ID = "me-ascended-heroes-pokemon"
JUST_SET_QUERY = "Ascended Heroes"
TCG_BASE = "https://api.tcgdex.net/v2/en"
TCG_SET_ID = "me02.5"
LIMIT = 20
MAX_PAGES = 40
SLEEP_SECONDS = 6.2

PATTERN_FOILS = {
    "energy": "Energy Reverse Holo",
    "friendball": "Friend Ball Reverse Holo",
    "loveball": "Love Ball Reverse Holo",
    "quickball": "Quick Ball Reverse Holo",
    "duskball": "Dusk Ball Reverse Holo",
    "pokeball": "Poké Ball Reverse Holo",
    "team-rocket": "Team Rocket Reverse Holo",
}

JUST_SUFFIXES = {
    "energy symbol pattern": "Energy Reverse Holo",
    "friend ball": "Friend Ball Reverse Holo",
    "love ball": "Love Ball Reverse Holo",
    "quick ball": "Quick Ball Reverse Holo",
    "dusk ball": "Dusk Ball Reverse Holo",
    "poke ball": "Poké Ball Reverse Holo",
    "poké ball": "Poké Ball Reverse Holo",
    "team rocket": "Team Rocket Reverse Holo",
}


def fail(message, details=None):
    payload = {"result": "FAIL_CLOSED", "message": message}
    if details is not None:
        payload["details"] = details
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
    raise SystemExit(1)


def request_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {}, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        fail("HTTP error", {"url": url.split("?")[0], "status": exc.code, "body": body[:1000]})


def just_get(path, api_key, params=None):
    qs = urllib.parse.urlencode(params or {}, doseq=True)
    url = JUST_BASE + path + ("?" + qs if qs else "")
    return request_json(
        url,
        {
            "x-api-key": api_key,
            "accept": "application/json",
            "user-agent": "Cardoryx-JustTCG-Mapping-Audit/1.0",
        },
    )


def tcg_get(path):
    return request_json(
        TCG_BASE + path,
        {"accept": "application/json", "user-agent": "Cardoryx-JustTCG-Mapping-Audit/1.0"},
    )


def canonical_number(value):
    s = str(value or "").strip()
    if "/" in s:
        left, right = s.split("/", 1)
        try:
            left = str(int(left))
        except Exception:
            left = left.lstrip("0") or "0"
        try:
            right = str(int(right))
        except Exception:
            right = right.lstrip("0") or "0"
        return f"{left}/{right}"
    return s.lstrip("0") or "0"


def tcgdex_finish(row):
    typ = str(row.get("type") or "").strip().lower()
    foil = str(row.get("foil") or "").strip().lower()
    if typ == "normal":
        return "Normal"
    if typ == "holo":
        if foil == "cosmos":
            return "Cosmos Holo"
        if not foil:
            return "Holo"
        return f"UNKNOWN_HOLO_FOIL:{foil}"
    if typ == "reverse":
        if foil in PATTERN_FOILS:
            return PATTERN_FOILS[foil]
        if not foil:
            return "Reverse Holo"
        return f"UNKNOWN_REVERSE_FOIL:{foil}"
    return f"UNKNOWN_TYPE:{typ or 'empty'}"


def suffix_text(name):
    m = re.search(r"\(([^()]*)\)\s*$", str(name or ""))
    return m.group(1).strip() if m else ""


def specialized_just_finish(name):
    suffix = suffix_text(name).lower()
    if not suffix:
        return None
    for token, finish in JUST_SUFFIXES.items():
        if token in suffix:
            return finish
    return None


def just_printing_finish(printing):
    p = str(printing or "").strip().lower()
    if p == "normal":
        return "Normal"
    if p == "holofoil":
        return "Holo"
    if p == "reverse holofoil":
        return "Reverse Holo"
    return f"UNKNOWN_PRINTING:{p or 'empty'}"


def main():
    key = os.environ.get("JUSTTCG_API_KEY", "").strip()
    if not key:
        fail("Missing JUSTTCG_API_KEY")

    # Resolve set identity exactly enough to prevent cross-set contamination.
    sets = just_get("/sets", key, {"game": "pokemon", "q": JUST_SET_QUERY})
    set_rows = sets.get("data") or []
    exact_sets = [x for x in set_rows if str(x.get("id") or "") == JUST_SET_ID]
    if len(exact_sets) != 1:
        fail("JustTCG set identity did not resolve uniquely", {"matches": exact_sets, "returned": set_rows[:10]})
    just_set = exact_sets[0]

    # Fetch every JustTCG card record for the exact set.
    cards = []
    page_meta = []
    expected_total = None
    offset = 0
    for page in range(MAX_PAGES):
        time.sleep(SLEEP_SECONDS)
        body = just_get(
            "/cards",
            key,
            {
                "game": "pokemon",
                "set": JUST_SET_ID,
                "limit": LIMIT,
                "offset": offset,
                "include_null_prices": "true",
            },
        )
        rows = body.get("data") or []
        meta = body.get("meta") or {}
        usage = body.get("_metadata") or {}
        total = meta.get("total")
        if not isinstance(total, int) or total < 1:
            fail("Invalid JustTCG pagination total", meta)
        if expected_total is None:
            expected_total = total
            if expected_total > MAX_PAGES * LIMIT:
                fail("JustTCG set exceeds audit safety cap", {"total": expected_total})
        elif total != expected_total:
            fail("JustTCG pagination total changed", {"expected": expected_total, "actual": total})
        bad_set = [x.get("id") for x in rows if str(x.get("set") or "") != JUST_SET_ID]
        if bad_set:
            fail("JustTCG returned cross-set records", {"sample": bad_set[:10]})
        cards.extend(rows)
        page_meta.append({
            "page": page + 1,
            "count": len(rows),
            "offset": meta.get("offset"),
            "total": total,
            "remainingDaily": usage.get("apiDailyRequestsRemaining"),
            "remainingMonthly": usage.get("apiRequestsRemaining"),
        })
        if not meta.get("hasMore"):
            break
        if not rows:
            fail("JustTCG pagination returned empty page with hasMore=true", meta)
        offset += LIMIT
    else:
        fail("JustTCG pagination exceeded page cap")

    if len(cards) != expected_total:
        fail("JustTCG page count mismatch", {"expected": expected_total, "actual": len(cards)})

    # Separate sealed products: all exposed variants have condition Sealed.
    card_records = []
    sealed_records = []
    for card in cards:
        variants = card.get("variants") or []
        if variants and all(str(v.get("condition") or "").lower() == "sealed" for v in variants):
            sealed_records.append(card)
        else:
            card_records.append(card)

    # Build JustTCG physical identity candidates.
    just_by_key = defaultdict(list)
    unknown_suffixes = Counter()
    unknown_printings = Counter()
    just_identity_records = 0
    just_nm_priced = 0

    for card in card_records:
        number = canonical_number(card.get("number"))
        name = str(card.get("name") or "")
        special = specialized_just_finish(name)
        suffix = suffix_text(name)
        variants = card.get("variants") or []
        printings = sorted({str(v.get("printing") or "") for v in variants})
        if suffix and not special:
            unknown_suffixes[suffix] += 1

        finishes = []
        if special:
            finishes = [special]
        else:
            for printing in printings:
                finish = just_printing_finish(printing)
                if finish.startswith("UNKNOWN_PRINTING:"):
                    unknown_printings[printing] += 1
                finishes.append(finish)

        for finish in sorted(set(finishes)):
            key_id = (number, finish)
            nm_rows = [
                v for v in variants
                if str(v.get("condition") or "") == "Near Mint"
                and (special or just_printing_finish(v.get("printing")) == finish)
            ]
            nm_prices = [
                float(v["price"]) for v in nm_rows
                if isinstance(v.get("price"), (int, float)) and float(v["price"]) >= 0
            ]
            rec = {
                "id": card.get("id"),
                "name": name,
                "number": card.get("number"),
                "finish": finish,
                "tcgplayerId": card.get("tcgplayerId"),
                "nmPriceAvailable": bool(nm_prices),
                "nmPrices": nm_prices,
            }
            just_by_key[key_id].append(rec)
            just_identity_records += 1
            if nm_prices:
                just_nm_priced += 1

    # Fetch TCGdex set and all exact card details.
    tcg_set = tcg_get(f"/sets/{TCG_SET_ID}")
    tcg_rows = tcg_set.get("cards") or []
    ids = [x.get("id") for x in tcg_rows if x.get("id")]
    errors = []

    def load(cid):
        try:
            return cid, tcg_get(f"/cards/{cid}"), None
        except Exception as exc:
            return cid, None, repr(exc)

    detailed = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        for cid, data, err in pool.map(load, ids):
            if err or not data:
                errors.append({"id": cid, "error": err or "empty"})
            else:
                detailed[cid] = data
    if errors:
        fail("TCGdex detailed fetch errors", {"count": len(errors), "sample": errors[:5]})

    expected_by_key = defaultdict(list)
    unknown_tcgdex = Counter()
    expected_rows = 0
    for cid, card in detailed.items():
        local_id = str(card.get("localId") or "").strip()
        number = canonical_number(f"{local_id}/217")
        for row in card.get("variants_detailed") or []:
            finish = tcgdex_finish(row)
            if finish.startswith("UNKNOWN_"):
                unknown_tcgdex[finish] += 1
            expected_by_key[(number, finish)].append({
                "tcgdexId": cid,
                "name": card.get("name"),
                "localId": card.get("localId"),
                "finish": finish,
                "type": row.get("type"),
                "foil": row.get("foil"),
                "cardmarketProduct": (row.get("thirdParty") or {}).get("cardmarket"),
            })
            expected_rows += 1

    if unknown_tcgdex:
        fail("Unhandled TCGdex finish taxonomy", dict(unknown_tcgdex))

    all_expected = set(expected_by_key)
    all_just = set(just_by_key)
    exact_keys = sorted(all_expected & all_just)
    missing_keys = sorted(all_expected - all_just)
    extra_keys = sorted(all_just - all_expected)
    ambiguous_keys = sorted(k for k in exact_keys if len(expected_by_key[k]) != 1 or len(just_by_key[k]) != 1)
    one_to_one_keys = sorted(k for k in exact_keys if len(expected_by_key[k]) == 1 and len(just_by_key[k]) == 1)

    one_to_one_nm = [
        k for k in one_to_one_keys
        if just_by_key[k][0]["nmPriceAvailable"]
    ]

    finish_expected = Counter(k[1] for k in all_expected)
    finish_exact = Counter(k[1] for k in one_to_one_keys)
    finish_missing = Counter(k[1] for k in missing_keys)
    finish_extra = Counter(k[1] for k in extra_keys)

    # Noibat anchor must map exactly to the three known physical identities.
    noibat_keys = [("156/217", x) for x in ("Normal", "Energy Reverse Holo", "Friend Ball Reverse Holo")]
    noibat = {}
    for k in noibat_keys:
        noibat[k[1]] = {
            "expected": expected_by_key.get(k, []),
            "justtcg": just_by_key.get(k, []),
        }

    report = {
        "result": "PASS_READ_ONLY",
        "writesPerformed": False,
        "scope": {
            "tcgdexSet": {"id": TCG_SET_ID, "name": tcg_set.get("name"), "cards": len(tcg_rows)},
            "justtcgSet": just_set,
            "justtcgReturnedRecords": len(cards),
            "justtcgCardRecords": len(card_records),
            "justtcgSealedRecordsExcluded": len(sealed_records),
        },
        "identityModel": "exact set + canonical card number + exact physical finish",
        "coverage": {
            "tcgdexPhysicalRows": expected_rows,
            "tcgdexUniqueIdentityKeys": len(all_expected),
            "justtcgPhysicalIdentityCandidates": just_identity_records,
            "justtcgUniqueIdentityKeys": len(all_just),
            "exactKeyIntersection": len(exact_keys),
            "oneToOneExact": len(one_to_one_keys),
            "ambiguousExactKeys": len(ambiguous_keys),
            "missingFromJustTCG": len(missing_keys),
            "extraInJustTCG": len(extra_keys),
            "oneToOneExactWithNMPrice": len(one_to_one_nm),
            "oneToOneExactWithNMPricePct": round(100 * len(one_to_one_nm) / len(one_to_one_keys), 2) if one_to_one_keys else 0,
        },
        "byFinish": {
            finish: {
                "expected": finish_expected.get(finish, 0),
                "oneToOneExact": finish_exact.get(finish, 0),
                "missing": finish_missing.get(finish, 0),
                "extra": finish_extra.get(finish, 0),
            }
            for finish in sorted(set(finish_expected) | set(finish_exact) | set(finish_missing) | set(finish_extra))
        },
        "taxonomyDiagnostics": {
            "unknownJustTCGSuffixes": dict(unknown_suffixes.most_common()),
            "unknownJustTCGPrintings": dict(unknown_printings.most_common()),
            "unknownTCGdex": dict(unknown_tcgdex),
        },
        "samples": {
            "missing": [
                {"number": k[0], "finish": k[1], "expected": expected_by_key[k][:2]}
                for k in missing_keys[:30]
            ],
            "extra": [
                {"number": k[0], "finish": k[1], "justtcg": just_by_key[k][:2]}
                for k in extra_keys[:30]
            ],
            "ambiguous": [
                {"number": k[0], "finish": k[1], "expected": expected_by_key[k], "justtcg": just_by_key[k]}
                for k in ambiguous_keys[:20]
            ],
        },
        "noibat156": noibat,
        "requests": {
            "justtcgCardPages": len(page_meta),
            "lastPage": page_meta[-1] if page_meta else None,
        },
        "decision": {
            "productionIntegration": False,
            "reason": "Read-only mapping audit only; exact coverage and ambiguity must be reviewed before any adapter is considered.",
        },
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
