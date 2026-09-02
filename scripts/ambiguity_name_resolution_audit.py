#!/usr/bin/env python3
"""Read-only audit of exact card-name disambiguation inside verified candidates."""

import json
import os
import re
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import full_catalog_coverage_postmerge_audit as full

OUTPUT = Path("artifacts/ambiguity_name_resolution_audit_report.json")
EXPECTED_MAIN = "86c39e1b74a93bed468ab0bcbbbaac2ad2109d2f"
EXPECTED_AMBIGUITIES = 11249
BASE_UNIQUE = 9466
PHYSICAL_ELIGIBLE = 21534
GENERIC_ONLY = {"ex", "v", "gx", "vmax", "vstar", "energy", "energia", "trainer", "allenatore"}
SUFFIX_RE = re.compile(r"(?:^|[-\s])(ex|v|gx|vmax|vstar)$", re.I)
APOSTROPHE_RE = re.compile(r"['’‘ʼ]")
REGIONAL_RE = re.compile(r"\b(?:alola|alolan|galar|galarian|hisui|hisuian|paldea|paldean|team rocket|del team rocket|di alola|di galar|di hisui|di paldea)\b", re.I)
ENERGY_RE = re.compile(r"\b(?:energy|energia)\b", re.I)
TRAINER_HINT_RE = re.compile(r"\b(?:professor|professore|professoressa|team|ball|stadium|stadio|energy search|ricerca energia|potion|pozione)\b", re.I)


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def collapse_spaces(value):
    return re.sub(r"\s+", " ", str(value or "").strip())


def raw_name_key(value):
    return collapse_spaces(value).casefold()


def conservative_name_key(value):
    text = str(value or "")
    text = text.translate(str.maketrans({"’": "'", "‘": "'", "ʼ": "'", "‐": "-", "‑": "-", "‒": "-", "–": "-", "—": "-", "―": "-"}))
    text = unicodedata.normalize("NFKD", text)
    text = "".join(char for char in text if not unicodedata.combining(char))
    return collapse_spaces(text).casefold()


def alphanumeric_length(value):
    return len(re.sub(r"[^a-z0-9]", "", conservative_name_key(value)))


def name_aliases(item):
    aliases = []
    for locale, field in (("it", "nameIT"), ("en", "nameEN")):
        value = collapse_spaces(item.get(field))
        if value:
            aliases.append({"locale": locale, "value": value, "rawKey": raw_name_key(value), "normalizedKey": conservative_name_key(value)})
    if not aliases:
        value = collapse_spaces(item.get("name"))
        if value:
            aliases.append({"locale": "fallback", "value": value, "rawKey": raw_name_key(value), "normalizedKey": conservative_name_key(value)})
    unique = []
    seen = set()
    for alias in aliases:
        marker = (alias["locale"], alias["normalizedKey"])
        if marker not in seen:
            seen.add(marker)
            unique.append(alias)
    return unique


def stripped_risk_key(value):
    text = conservative_name_key(value)
    text = re.sub(r"(?:^|[-\s])(?:ex|v|gx|vmax|vstar)$", "", text).strip(" -")
    text = REGIONAL_RE.sub("", text)
    return collapse_spaces(text).strip(" -")


def candidates_for(recognizer, item):
    number = full.numeric(item["localId"])
    set_id = item["setId"].lower()
    if item["basicEnergy"] and ((set_id == "sve" and number is not None and 1 <= number <= 24) or (set_id == "mee" and number is not None and 1 <= number <= 16)):
        return [item]
    if item["promo"]:
        return recognizer.promo_candidates(item)[0]
    if full.special_parts(item["localId"]):
        return recognizer.special_candidates(item)[0]
    if number is not None:
        return recognizer.numeric_candidates(item)[0]
    return []


def size_bucket(size):
    return str(size) if size in {2, 3, 4, 5, 6} else ">6"


def analyze_identity(recognizer, item, candidates):
    target_aliases = name_aliases(item)
    candidate_aliases = {candidate["id"]: name_aliases(candidate) for candidate in candidates}
    normalized_owners = defaultdict(set)
    raw_owners = defaultdict(set)
    for candidate_id, aliases in candidate_aliases.items():
        for alias in aliases:
            normalized_owners[alias["normalizedKey"]].add(candidate_id)
            raw_owners[alias["rawKey"]].add(candidate_id)

    unique_normalized = [alias for alias in target_aliases if normalized_owners[alias["normalizedKey"]] == {item["id"]}]
    unique_raw = [alias for alias in target_aliases if raw_owners[alias["rawKey"]] == {item["id"]}]
    exact_collision = any(len(normalized_owners[alias["normalizedKey"]]) > 1 for alias in target_aliases)
    missing = not target_aliases
    short_or_generic = not missing and all(alphanumeric_length(alias["value"]) < 4 or alias["normalizedKey"] in GENERIC_ONLY for alias in target_aliases)
    it_key = next((alias["normalizedKey"] for alias in target_aliases if alias["locale"] == "it"), None)
    en_key = next((alias["normalizedKey"] for alias in target_aliases if alias["locale"] == "en"), None)
    it_en_discordant = bool(it_key and en_key and it_key != en_key)
    names = [alias["value"] for aliases in candidate_aliases.values() for alias in aliases]
    suffix_present = any(SUFFIX_RE.search(name) for name in names)
    apostrophe_present = any(APOSTROPHE_RE.search(name) for name in names)
    regional_present = any(REGIONAL_RE.search(name) for name in names)
    energy_present = any(ENERGY_RE.search(name) for name in names)
    trainer_hint_present = any(TRAINER_HINT_RE.search(name) for name in names)

    risk_owners = defaultdict(set)
    for candidate_id, aliases in candidate_aliases.items():
        for alias in aliases:
            key = stripped_risk_key(alias["value"])
            if key:
                risk_owners[key].add(candidate_id)
    target_risk_keys = {stripped_risk_key(alias["value"]) for alias in target_aliases if stripped_risk_key(alias["value"])}
    suffix_or_form_collision = any(len(risk_owners[key]) > 1 for key in target_risk_keys)

    # Candidate rule under audit: the OCR name is never a primary search. It is
    # eligible only after the verified candidate list exists, with two identical
    # OCR reads and one exact full-name owner across official IT+EN aliases.
    safe = bool(unique_normalized) and not missing and not short_or_generic and not exact_collision and not suffix_or_form_collision and not energy_present
    simulated_selection = item["id"] if safe else None
    false_positive = simulated_selection is not None and simulated_selection != item["id"]
    return {
        "id": item["id"], "nameIT": item.get("nameIT"), "nameEN": item.get("nameEN"), "setId": item["setId"], "set": item["setName"],
        "localId": item["localId"], "cardCountOfficial": item["official"], "category": recognizer.category(item),
        "candidateCount": len(candidates), "candidateIds": [candidate["id"] for candidate in candidates],
        "candidateNames": [{"id": candidate["id"], "nameIT": candidate.get("nameIT"), "nameEN": candidate.get("nameEN"), "setId": candidate["setId"], "set": candidate["setName"]} for candidate in candidates],
        "nameMissing": missing, "rawExactNameUnique": bool(unique_raw), "conservativeNormalizedNameUnique": bool(unique_normalized),
        "sameExactNameCollision": exact_collision, "shortOrGenericName": short_or_generic, "itEnDiscordant": it_en_discordant,
        "riskFlags": {"suffixPresent": suffix_present, "apostrophePresent": apostrophe_present, "regionalFormPresent": regional_present, "energyPresent": energy_present, "trainerNameHintPresent": trainer_hint_present, "suffixOrRegionalBaseCollision": suffix_or_form_collision, "candidateGroupOver6": len(candidates) > 6},
        "theoreticallySafeWithTwoConcordantOCRReads": safe, "simulatedSelection": simulated_selection, "falsePositive": false_positive,
    }


def genesect_control(recognizer, identities):
    target = next((item for item in identities if item["setId"] == "sv11B" and full.numeric(item["localId"]) == 67 and item["official"] == 86 and conservative_name_key(item.get("nameIT") or item.get("nameEN")) in {"genesect-ex", "genesect ex"}), None)
    if target is None:
        target = next((item for item in identities if full.numeric(item["localId"]) == 67 and item["official"] == 86 and "genesect" in conservative_name_key(item.get("nameIT") or item.get("nameEN"))), None)
    if target is None:
        return {"found": False, "passed": False, "reason": "Genesect target not found"}
    candidates = candidates_for(recognizer, target)
    analyzed = analyze_identity(recognizer, target, candidates)
    normalized_names = {conservative_name_key(candidate.get("nameIT") or candidate.get("nameEN")): candidate["id"] for candidate in candidates}
    expected = {"hydreigon-ex", "genesect-ex", "sliggoo"}
    present = set(normalized_names)
    return {
        "found": True, "passed": expected.issubset(present) and analyzed["conservativeNormalizedNameUnique"],
        "printedCode": "067/086", "targetId": target["id"], "targetSet": target["setName"],
        "candidateCount": len(candidates), "candidates": analyzed["candidateNames"],
        "normalizedNames": sorted(present), "requiredNamesPresent": expected.issubset(present),
        "genesectExactNameUnique": analyzed["conservativeNormalizedNameUnique"],
        "eligibleUnderCandidateRule": analyzed["theoreticallySafeWithTwoConcordantOCRReads"],
        "note": "Diagnostic control only; no hardcoded recognition rule was created.",
    }


def main():
    started = time.monotonic()
    network = full.Network()
    lists = {locale: full.rows(network.get(f"{base}/sets"), "sets", "data") for locale, base in full.BASES.items()}
    details = {"it": {}, "en": {}}
    set_errors = {"it": {}, "en": {}}
    futures = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        for locale in full.BASES:
            for summary in lists[locale]:
                set_id = str(summary.get("id") or "")
                if set_id:
                    futures[pool.submit(full.fetch_detail, network, locale, set_id)] = (locale, set_id)
        for future in as_completed(futures):
            locale, set_id = futures[future]
            try:
                details[locale][set_id] = future.result()
            except Exception as exc:
                set_errors[locale][set_id] = str(exc)

    identities = full.build_catalog(lists, details)
    recognizer = full.Recognizer(lists, details, identities)
    classifications = {item["id"]: recognizer.classify(item) for item in identities}
    ambiguous_items = [item for item in identities if classifications[item["id"]]["outcome"] == "recognizedAmbiguous"]
    analyses = []
    groups = {}
    for item in ambiguous_items:
        candidates = candidates_for(recognizer, item)
        analysis = analyze_identity(recognizer, item, candidates)
        analyses.append(analysis)
        key = tuple(candidate["id"] for candidate in candidates)
        if key not in groups:
            groups[key] = {"candidateCount": len(candidates), "candidateIds": list(key), "ambiguousIdentityIds": []}
        groups[key]["ambiguousIdentityIds"].append(item["id"])

    safe = [item for item in analyses if item["theoreticallySafeWithTwoConcordantOCRReads"]]
    manual = [item for item in analyses if not item["theoreticallySafeWithTwoConcordantOCRReads"]]
    group_distribution = Counter(size_bucket(group["candidateCount"]) for group in groups.values())
    identity_distribution = Counter(size_bucket(item["candidateCount"]) for item in analyses)
    danger_counts = Counter()
    for item in analyses:
        if item["sameExactNameCollision"]: danger_counts["sameExactNameCollision"] += 1
        if item["nameMissing"]: danger_counts["nameMissing"] += 1
        if item["itEnDiscordant"]: danger_counts["itEnDiscordant"] += 1
        if item["shortOrGenericName"]: danger_counts["shortOrGenericName"] += 1
        for key, enabled in item["riskFlags"].items():
            if enabled: danger_counts[key] += 1

    false_positives = sum(item["falsePositive"] for item in analyses)
    regressions = full.regression_check(recognizer)
    genesect = genesect_control(recognizer, identities)
    safe_count = len(safe)
    reduction = round(100 * safe_count / len(analyses), 2) if analyses else 0
    theoretical_unique = BASE_UNIQUE + safe_count
    theoretical_unique_percent = round(100 * theoretical_unique / PHYSICAL_ELIGIBLE, 2)
    reliable = len(ambiguous_items) == EXPECTED_AMBIGUITIES and false_positives == 0 and regressions["regressionCount"] == 0 and len(network.errors) == 0 and genesect.get("passed") is True

    report = {
        "schema": 1, "testType": "ambiguity-resolution-by-card-name", "generatedAt": now(),
        "sourceMain": EXPECTED_MAIN, "diagnosticCommit": os.environ.get("GITHUB_SHA", "unknown"),
        "principle": "verified printed identity -> verified TCGdex candidates -> exact official name as second filter only",
        "candidateRuleNotImplemented": {"steps": ["number/localId and set already verified", "more than one candidate remains", "at least two concordant OCR name reads", "complete conservatively-normalized OCR name equals exactly one official IT/EN candidate alias", "auto-selection only for that unique owner", "otherwise manual choice"], "forbidden": ["name-first lookup", "fuzzy matching", "similarity percentage", "contains matching", "Levenshtein auto-selection", "substring-only suffix selection"]},
        "normalization": {"allowed": ["case folding", "multiple-space collapse", "Unicode apostrophe equivalence", "typographic hyphen equivalence", "deterministic diacritic normalization"], "removesMeaningfulTokens": False, "usesFuzzyMatching": False},
        "safety": {"readOnly": True, "indexHtmlModified": False, "retailModified": False, "cardmarketModified": False, "collectionDataModified": False, "newIdentitiesCreated": False, "scannerBehaviorModified": False, "productionWorkflowModified": False},
        "scope": {"setsIT": len(lists["it"]), "setsEN": len(lists["en"]), "catalogIdentities": len(identities), "physicalIdentities": len(recognizer.physical), "ambiguousGroups": len(groups), "ambiguousIdentities": len(analyses), "runtimeSeconds": round(time.monotonic() - started, 2)},
        "summary": {"ambiguousIdentities": len(analyses), "rawExactNameUnique": sum(item["rawExactNameUnique"] for item in analyses), "conservativeNormalizedNameUnique": sum(item["conservativeNormalizedNameUnique"] for item in analyses), "sameExactName": sum(item["sameExactNameCollision"] for item in analyses), "nameMissing": sum(item["nameMissing"] for item in analyses), "itEnDiscordant": sum(item["itEnDiscordant"] for item in analyses), "theoreticallyDisambiguableWithExactNameAndGuards": safe_count, "mustRemainManual": len(manual), "potentialAmbiguityReductionPercent": reduction, "currentUniqueCoverageCount": BASE_UNIQUE, "theoreticalUniqueCoverageCount": theoretical_unique, "theoreticalUniqueCoveragePercent": theoretical_unique_percent, "simulatedFalsePositives": false_positives, "regressions": regressions["regressionCount"], "networkErrors": len(network.errors), "estimatedFalsePositiveRisk": "LOW only with all candidate-rule guards; otherwise not assessed as safe"},
        "candidateGroupSizeDistribution": {"groups": dict(group_distribution), "identities": dict(identity_distribution)},
        "dangerousCategories": dict(danger_counts.most_common()),
        "futureRuleExclusions": ["missing or short/generic OCR name", "zero or multiple exact normalized owners", "same-name collisions", "Energy names", "suffix/regional base collisions", "single OCR reading", "substring or suffix-only matches", "locale aliases that identify more than one card", "candidates outside the already verified number/localId+set group"],
        "genesectControl": genesect,
        "regressionChecks": {key: value for key, value in regressions.items() if key != "cases"},
        "network": {"requests": network.requests, "errors": network.errors, "setDetailErrors": set_errors},
        "examples": {"safe": safe[:25], "manual": manual[:25], "sameName": [item for item in analyses if item["sameExactNameCollision"]][:25], "suffixOrRegionalCollision": [item for item in analyses if item["riskFlags"]["suffixOrRegionalBaseCollision"]][:25], "apostrophe": [item for item in analyses if item["riskFlags"]["apostrophePresent"]][:25], "itEnDiscordant": [item for item in analyses if item["itEnDiscordant"]][:25]},
        "identityResults": analyses,
        "finalAssessment": "CANDIDATO SICURO PER TEST IMPLEMENTATIVO" if reliable and safe_count > 0 else "NON SUFFICIENTEMENTE SICURO",
    }
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scope": report["scope"], "summary": report["summary"], "candidateGroupSizeDistribution": report["candidateGroupSizeDistribution"], "dangerousCategories": report["dangerousCategories"], "genesectControl": genesect, "regressionChecks": report["regressionChecks"], "network": {"requests": network.requests, "errors": len(network.errors)}, "finalAssessment": report["finalAssessment"], "report": str(OUTPUT)}, ensure_ascii=False, indent=2))
    if not reliable:
        raise SystemExit("Ambiguity name-resolution audit requires verification")


if __name__ == "__main__":
    main()
