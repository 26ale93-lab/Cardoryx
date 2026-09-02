#!/usr/bin/env python3

"""Read-only coverage audit for Cardoryx's current TCGdex identification logic."""

from __future__ import annotations

import json
import os
import re
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path


BASES = {
    "it": "https://api.tcgdex.net/v2/it",
    "en": "https://api.tcgdex.net/v2/en",
}
OUTPUT = Path("artifacts/catalog_coverage_audit_report.json")
SOURCE_COMMIT = os.environ.get("GITHUB_SHA", "unknown")
MAX_DETAIL_REQUESTS = 460
MAX_RUNTIME_SECONDS = 14 * 60
HTTP_TIMEOUT = 25
WORKERS = 12
EXAMPLE_LIMIT = 20

HINTS = {
    "146/159": {"setId": "sv09", "localId": "146"},
    "98/159": {"setId": "sv09", "localId": "098"},
}

PROMO_RE = re.compile(
    r"promo|promozional|black star|prize pack|play[! ]+pokemon",
    re.I,
)
SUBSET_RE = re.compile(
    r"trainer gallery|galarian gallery|radiant collection|"
    r"shiny vault|classic collection|subset|gallery",
    re.I,
)
ENERGY_RE = re.compile(r"\b(energy|energia)\b", re.I)
BASIC_ENERGY_RE = re.compile(
    r"basic\s+(?:grass|fire|water|lightning|psychic|fighting|"
    r"darkness|metal|fairy)\s+energy|"
    r"energia\s+base|energia\s+(?:erba|fuoco|acqua|lampo|psico|"
    r"lotta|oscurita|metallo|folletto)",
    re.I,
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def norm(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        text.encode("ascii", "ignore").decode("ascii").lower(),
    ).strip()


def get_json(url: str, attempts: int = 3):
    last_error = None
    for attempt in range(1, attempts + 1):
        try:
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "Cardoryx-Catalog-Coverage-Audit/1.0",
                    "Accept": "application/json",
                },
            )
            with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as response:
                return json.load(response)
        except (
            urllib.error.HTTPError,
            urllib.error.URLError,
            TimeoutError,
            OSError,
            json.JSONDecodeError,
        ) as exc:
            last_error = exc
            if isinstance(exc, urllib.error.HTTPError) and exc.code in {
                400, 401, 403, 404,
            }:
                break
            if attempt < attempts:
                time.sleep(attempt * 1.2)
    raise RuntimeError(f"GET failed: {url}: {last_error}")


def as_list(payload, *keys):
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        for key in keys:
            if isinstance(payload.get(key), list):
                return payload[key]
    return []


def release_year(item: dict) -> int | None:
    raw = str(
        item.get("releaseDate")
        or item.get("release")
        or item.get("date")
        or ""
    )
    match = re.search(r"(?:19|20)\d{2}", raw)
    return int(match.group()) if match else None


def set_text(item: dict) -> str:
    serie = item.get("serie") or item.get("series") or {}
    if isinstance(serie, dict):
        serie = serie.get("name") or serie.get("id") or ""
    return " ".join(
        str(x or "")
        for x in (item.get("id"), item.get("name"), serie)
    )


def select_representative(summaries: list[dict], limit: int):
    """Keep special sets and stratify the remainder by date/name."""
    if len(summaries) <= limit:
        return summaries, False

    special = [
        item for item in summaries
        if PROMO_RE.search(set_text(item)) or SUBSET_RE.search(set_text(item))
    ]
    chosen = {str(item.get("id")): item for item in special if item.get("id")}
    ordered = sorted(
        (item for item in summaries if item.get("id")),
        key=lambda item: (
            release_year(item) or 0,
            str(item.get("id")),
        ),
    )
    slots = max(0, limit - len(chosen))
    if slots and ordered:
        for index in range(slots):
            pos = round(index * (len(ordered) - 1) / max(1, slots - 1))
            item = ordered[pos]
            chosen[str(item["id"])] = item
    return list(chosen.values())[:limit], True


def fetch_detail(locale: str, set_id: str):
    url = f"{BASES[locale]}/sets/{urllib.parse.quote(set_id)}"
    data = get_json(url)
    if not isinstance(data, dict) or not data.get("id"):
        raise RuntimeError("set detail not recognized")
    return data


def official_count(set_detail: dict) -> int:
    card_count = set_detail.get("cardCount") or {}
    if not isinstance(card_count, dict):
        return 0
    try:
        return max(0, int(card_count.get("official") or 0))
    except (TypeError, ValueError):
        return 0


def total_count(set_detail: dict) -> int:
    card_count = set_detail.get("cardCount") or {}
    if not isinstance(card_count, dict):
        return 0
    try:
        return max(0, int(card_count.get("total") or 0))
    except (TypeError, ValueError):
        return 0


def digits_only(value: object) -> str:
    raw = re.sub(r"\D", "", str(value or ""))
    return (raw.lstrip("0") or "0") if raw else ""


def numeric_local(value: object) -> int | None:
    raw = str(value or "").strip()
    if not re.fullmatch(r"\d+", raw):
        return None
    return int(raw)


def card_example(identity: dict) -> dict:
    return {
        "id": identity["id"],
        "nameIT": identity.get("nameIT"),
        "nameEN": identity.get("nameEN"),
        "setId": identity.get("setId"),
        "setNameIT": identity.get("setNameIT"),
        "setNameEN": identity.get("setNameEN"),
        "localIdIT": identity.get("localIdIT"),
        "localIdEN": identity.get("localIdEN"),
        "cardCountOfficialIT": identity.get("officialIT"),
        "cardCountOfficialEN": identity.get("officialEN"),
        "cardCountTotalIT": identity.get("totalIT"),
        "cardCountTotalEN": identity.get("totalEN"),
        "releaseYear": identity.get("releaseYear"),
    }


def add_example(container: dict[str, list], key: str, example: dict):
    bucket = container.setdefault(key, [])
    if len(bucket) < EXAMPLE_LIMIT:
        bucket.append(example)


def metric_bucket():
    return {"analyzed": 0, "identifiable": 0, "potentialFalseNegatives": 0}


def finish_metric(metric: dict):
    analyzed = metric["analyzed"]
    metric["coveragePercent"] = round(
        100 * metric["identifiable"] / analyzed, 2
    ) if analyzed else None
    return metric


def main():
    started = time.monotonic()
    lists = {}
    list_errors = {}

    for locale, base in BASES.items():
        try:
            lists[locale] = as_list(get_json(f"{base}/sets"), "sets", "data")
        except Exception as exc:
            lists[locale] = []
            list_errors[locale] = str(exc)

    if not lists["it"] and not lists["en"]:
        raise SystemExit(f"TCGdex set lists unavailable: {list_errors}")

    total_requests = len(lists["it"]) + len(lists["en"])
    sampled = total_requests > MAX_DETAIL_REQUESTS
    selected = {}
    if sampled:
        it_limit = round(MAX_DETAIL_REQUESTS * len(lists["it"]) / total_requests)
        en_limit = MAX_DETAIL_REQUESTS - it_limit
        selected["it"], _ = select_representative(lists["it"], it_limit)
        selected["en"], _ = select_representative(lists["en"], en_limit)
    else:
        selected = lists

    details = {"it": {}, "en": {}}
    detail_errors = {"it": {}, "en": {}}
    timed_out = False
    futures = {}

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        for locale in BASES:
            for item in selected[locale]:
                set_id = str(item.get("id") or "")
                if set_id:
                    futures[pool.submit(fetch_detail, locale, set_id)] = (
                        locale, set_id
                    )

        for future in as_completed(futures):
            locale, set_id = futures[future]
            if time.monotonic() - started > MAX_RUNTIME_SECONDS:
                timed_out = True
                for pending in futures:
                    pending.cancel()
                break
            try:
                details[locale][set_id] = future.result()
            except Exception as exc:
                detail_errors[locale][set_id] = str(exc)

    cards = {"it": {}, "en": {}}
    card_to_set = {"it": {}, "en": {}}
    for locale in BASES:
        for set_id, detail in details[locale].items():
            for card in as_list(detail.get("cards"), "cards", "data"):
                if not isinstance(card, dict) or not card.get("id"):
                    continue
                card_id = str(card["id"])
                cards[locale][card_id] = card
                card_to_set[locale][card_id] = set_id

    all_ids = sorted(set(cards["it"]) | set(cards["en"]))
    identities = []

    for card_id in all_ids:
        it_card = cards["it"].get(card_id)
        en_card = cards["en"].get(card_id)
        preferred = it_card or en_card or {}
        set_id = (
            card_to_set["it"].get(card_id)
            or card_to_set["en"].get(card_id)
            or ""
        )
        it_set = details["it"].get(set_id, {})
        en_set = details["en"].get(set_id, {})
        year = release_year(it_set) or release_year(en_set)

        identities.append({
            "id": card_id,
            "setId": set_id,
            "nameIT": it_card.get("name") if it_card else None,
            "nameEN": en_card.get("name") if en_card else None,
            "localIdIT": it_card.get("localId") if it_card else None,
            "localIdEN": en_card.get("localId") if en_card else None,
            "localId": preferred.get("localId"),
            "setNameIT": it_set.get("name"),
            "setNameEN": en_set.get("name"),
            "officialIT": official_count(it_set),
            "officialEN": official_count(en_set),
            "totalIT": total_count(it_set),
            "totalEN": total_count(en_set),
            "official": official_count(it_set) or official_count(en_set),
            "total": total_count(it_set) or total_count(en_set),
            "releaseYear": year,
            "inIT": it_card is not None,
            "inEN": en_card is not None,
        })

    pair_groups = defaultdict(list)
    local_query_groups = defaultdict(list)
    for identity in identities:
        local = numeric_local(identity.get("localId"))
        official = identity.get("official") or 0
        if local is not None and official:
            pair_groups[f"{local}/{official}"].append(identity["id"])
        digit_key = digits_only(identity.get("localId"))
        if digit_key:
            local_query_groups[digit_key].append(identity["id"])

    false_reason_counts = Counter()
    examples_by_reason = {}
    category_metrics = defaultdict(metric_bucket)
    segment_examples = {}
    identifiable = 0
    false_negatives = 0
    selectable_ambiguities = 0
    numbering_counts = Counter()
    numbering_examples = {}
    official_counts = Counter()
    official_examples = {}
    special_rule_counts = Counter()
    special_rule_examples = {}

    for identity in identities:
        example = card_example(identity)
        local_raw = str(identity.get("localId") or "")
        local_num = numeric_local(local_raw)
        official = identity.get("official") or 0
        total = identity.get("total") or 0
        set_blob = " ".join(
            str(x or "") for x in (
                identity.get("setId"),
                identity.get("setNameIT"),
                identity.get("setNameEN"),
            )
        )
        name_blob = " ".join(
            str(x or "") for x in (
                identity.get("nameIT"), identity.get("nameEN")
            )
        )
        promo = bool(PROMO_RE.search(set_blob))
        energy = bool(ENERGY_RE.search(name_blob))
        basic_energy = energy and bool(BASIC_ENERGY_RE.search(name_blob))
        special_energy = energy and not basic_energy
        alphanumeric = bool(local_raw) and local_num is None
        subset = bool(SUBSET_RE.search(set_blob)) or (
            alphanumeric and not promo
        )
        secret = local_num is not None and official > 0 and local_num > official
        standard = not (promo or subset or energy or secret)
        old = identity.get("releaseYear") is not None and identity["releaseYear"] <= 2010
        recent = identity.get("releaseYear") is not None and identity["releaseYear"] >= 2023

        segments = []
        if standard:
            segments.append("standardSets")
        if secret:
            segments.append("secretBeyondOfficial")
        if promo:
            segments.append("promo")
        if subset:
            segments.append("subsetAndSpecialNumbering")
        if basic_energy:
            segments.append("basicEnergy")
        if special_energy:
            segments.append("specialEnergy")
        if old:
            segments.append("oldExpansionsThrough2010")
        if recent:
            segments.append("recentExpansionsFrom2023")
        if identity["inIT"] and not identity["inEN"]:
            segments.append("itOnly")
        if identity["inEN"] and not identity["inIT"]:
            segments.append("enOnly")

        reasons = []
        current_special_rule = False

        set_id_lower = str(identity.get("setId") or "").lower()
        if basic_energy and local_num is not None:
            if (set_id_lower == "sve" and 1 <= local_num <= 24) or (
                set_id_lower == "mee" and 1 <= local_num <= 16
            ):
                current_special_rule = True
                special_rule_counts["existingCodedBasicEnergySVE_MEE"] += 1
                add_example(
                    special_rule_examples,
                    "existingCodedBasicEnergySVE_MEE",
                    example,
                )

        if not current_special_rule:
            if not local_raw:
                reasons.append("missingLocalId")
            elif promo:
                reasons.append("promoPrintedCodeNotNumberTotal")
            elif subset and alphanumeric:
                reasons.append("subsetAlphanumericLocalId")
            elif alphanumeric:
                reasons.append("alphanumericLocalId")
            elif not official:
                reasons.append("missingCardCountOfficial")
            elif secret:
                # Current collectorCodeValid requires numerator <= denominator.
                reasons.append("secretNumeratorBeyondOfficialRejectedByOCR")

            if local_num is not None and official:
                pair = f"{local_num}/{official}"
                hint = HINTS.get(pair)
                if hint and set_id_lower != hint["setId"]:
                    reasons.append("hardcodedHintShadowsOtherSet")
                pair_size = len(pair_groups.get(pair, []))
                if pair_size > 8:
                    reasons.append("candidateDisplayLimitEight")
                elif pair_size > 1:
                    selectable_ambiguities += 1
                local_size = len(local_query_groups.get(str(local_num), []))
                if local_size > 60:
                    reasons.append("localIdQuerySliceLimitSixty")

        if identity["officialIT"] and identity["officialEN"]:
            if identity["officialIT"] != identity["officialEN"]:
                official_counts["itEnOfficialMismatch"] += 1
                add_example(official_examples, "itEnOfficialMismatch", example)
                reasons.append("itEnCardCountOfficialMismatch")
        if not identity["officialIT"] and identity["inIT"]:
            official_counts["missingOfficialIT"] += 1
            add_example(official_examples, "missingOfficialIT", example)
        if not identity["officialEN"] and identity["inEN"]:
            official_counts["missingOfficialEN"] += 1
            add_example(official_examples, "missingOfficialEN", example)
        if official and total and official > total:
            official_counts["officialGreaterThanTotal"] += 1
            add_example(official_examples, "officialGreaterThanTotal", example)
        if secret:
            numbering_counts["numericLocalIdBeyondOfficial"] += 1
            add_example(numbering_examples, "numericLocalIdBeyondOfficial", example)
            special_rule_counts["allowSecretNumeratorBeyondDenominator"] += 1
            add_example(
                special_rule_examples,
                "allowSecretNumeratorBeyondDenominator",
                example,
            )
        if alphanumeric:
            numbering_counts["alphanumericLocalId"] += 1
            add_example(numbering_examples, "alphanumericLocalId", example)
        if promo:
            special_rule_counts["promoPrintedCodeResolver"] += 1
            add_example(special_rule_examples, "promoPrintedCodeResolver", example)
        if subset:
            special_rule_counts["subsetSpecificDenominatorAndPrefix"] += 1
            add_example(
                special_rule_examples,
                "subsetSpecificDenominatorAndPrefix",
                example,
            )

        unique_reasons = list(dict.fromkeys(reasons))
        is_identifiable = not unique_reasons
        if is_identifiable:
            identifiable += 1
        else:
            false_negatives += 1
            for reason in unique_reasons:
                false_reason_counts[reason] += 1
                add_example(examples_by_reason, reason, example)

        for segment in segments:
            metric = category_metrics[segment]
            metric["analyzed"] += 1
            if is_identifiable:
                metric["identifiable"] += 1
            else:
                metric["potentialFalseNegatives"] += 1
                add_example(segment_examples, segment, example)

    locale_diff_counts = Counter()
    locale_diff_examples = {}
    for identity in identities:
        example = card_example(identity)
        if identity["inIT"] and not identity["inEN"]:
            locale_diff_counts["cardsOnlyIT"] += 1
            add_example(locale_diff_examples, "cardsOnlyIT", example)
        if identity["inEN"] and not identity["inIT"]:
            locale_diff_counts["cardsOnlyEN"] += 1
            add_example(locale_diff_examples, "cardsOnlyEN", example)
        if identity["inIT"] and identity["inEN"]:
            if str(identity.get("localIdIT")) != str(identity.get("localIdEN")):
                locale_diff_counts["localIdMismatch"] += 1
                add_example(locale_diff_examples, "localIdMismatch", example)
            if norm(identity.get("nameIT")) == norm(identity.get("nameEN")):
                locale_diff_counts["sameNormalizedName"] += 1

    it_set_ids = set(details["it"])
    en_set_ids = set(details["en"])
    set_locale_examples = {
        "setsOnlyIT": sorted(it_set_ids - en_set_ids)[:EXAMPLE_LIMIT],
        "setsOnlyEN": sorted(en_set_ids - it_set_ids)[:EXAMPLE_LIMIT],
    }

    report = {
        "schema": 1,
        "generatedAt": utc_now(),
        "source": "TCGdex v2 IT + EN",
        "sourceCommit": SOURCE_COMMIT,
        "rules": {
            "readOnly": True,
            "indexHtmlModified": False,
            "retailPricesModified": False,
            "cardmarketTouched": False,
            "collectionDataModified": False,
            "newIdentitiesCreated": False,
            "productionWorkflowModified": False,
            "retailSystemModified": False,
            "automaticCorrectionsApplied": False,
            "currentLogicReused": [
                "IT+EN card query union",
                "numeric localId variants",
                "sameCollectorNumber digit normalization",
                "set cardCount.official equality",
                "collectorCodeValid numerator<=denominator",
                "candidate display limit 8",
                "candidate verification slice 60",
                "PRINTED_CODE_HINTS",
                "coded SVE/MEE basic energy resolver",
            ],
        },
        "scope": {
            "completeCatalogRequested": True,
            "representativeSamplingUsed": sampled or timed_out,
            "samplingReason": (
                "set-detail request budget exceeded"
                if sampled else
                "runtime budget reached; completed details retained"
                if timed_out else None
            ),
            "samplingMethod": (
                "all promo/special sets plus evenly stratified release-date sample"
                if sampled else
                "all successfully completed set details"
                if timed_out else
                "complete IT and EN set lists"
            ),
            "maxRuntimeSeconds": MAX_RUNTIME_SECONDS,
            "runtimeSeconds": round(time.monotonic() - started, 2),
            "setsITListed": len(lists["it"]),
            "setsENListed": len(lists["en"]),
            "setsITSelected": len(selected["it"]),
            "setsENSelected": len(selected["en"]),
            "setsITAnalyzed": len(details["it"]),
            "setsENAnalyzed": len(details["en"]),
            "setDetailErrorsIT": len(detail_errors["it"]),
            "setDetailErrorsEN": len(detail_errors["en"]),
            "identitiesAnalyzed": len(identities),
            "cardsITAnalyzed": len(cards["it"]),
            "cardsENAnalyzed": len(cards["en"]),
        },
        "summary": {
            "identitiesAnalyzed": len(identities),
            "identifiableWithCurrentMethod": identifiable,
            "potentialFalseNegatives": false_negatives,
            "estimatedCoveragePercent": round(
                100 * identifiable / len(identities), 2
            ) if identities else 0,
            "ambiguousButSelectableCandidates": selectable_ambiguities,
            "method": (
                "Metadata simulation of the current scanner's Numero/Totale route; "
                "coverage is diagnostic, not an OCR accuracy benchmark."
            ),
        },
        "analysisSegments": {
            key: {
                **finish_metric(value),
                "falseNegativeExamples": segment_examples.get(key, []),
            }
            for key, value in sorted(category_metrics.items())
        },
        "falseNegativesByReason": dict(false_reason_counts.most_common()),
        "falseNegativeExamplesByReason": examples_by_reason,
        "numberingProblems": {
            "counts": dict(numbering_counts),
            "examples": numbering_examples,
        },
        "cardCountOfficialProblems": {
            "counts": dict(official_counts),
            "examples": official_examples,
        },
        "promoAndSubsetProblems": {
            "promoIdentities": category_metrics["promo"]["analyzed"],
            "promoPotentialFalseNegatives": category_metrics["promo"]["potentialFalseNegatives"],
            "subsetIdentities": category_metrics["subsetAndSpecialNumbering"]["analyzed"],
            "subsetPotentialFalseNegatives": category_metrics["subsetAndSpecialNumbering"]["potentialFalseNegatives"],
            "examples": {
                "promo": segment_examples.get("promo", []),
                "subset": segment_examples.get("subsetAndSpecialNumbering", []),
            },
        },
        "localeDifferences": {
            "setsOnlyIT": len(it_set_ids - en_set_ids),
            "setsOnlyEN": len(en_set_ids - it_set_ids),
            "counts": dict(locale_diff_counts),
            "cardExamples": locale_diff_examples,
            "setExamples": set_locale_examples,
        },
        "specialRulesPotentiallyRequired": [
            {
                "rule": key,
                "affectedIdentities": count,
                "examples": special_rule_examples.get(key, []),
            }
            for key, count in special_rule_counts.most_common()
        ],
        "setDetailErrors": detail_errors,
    }

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps({
        "scope": report["scope"],
        "summary": report["summary"],
        "falseNegativesByReason": report["falseNegativesByReason"],
        "report": str(OUTPUT),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
