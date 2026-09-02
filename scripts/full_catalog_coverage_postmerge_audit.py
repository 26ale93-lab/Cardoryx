#!/usr/bin/env python3
"""Read-only full-catalog reachability audit for Cardoryx recognition on main."""

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

BASES = {"it": "https://api.tcgdex.net/v2/it", "en": "https://api.tcgdex.net/v2/en"}
OUTPUT = Path("artifacts/full_catalog_coverage_postmerge_report.json")
EXPECTED_MAIN = "86c39e1b74a93bed468ab0bcbbbaac2ad2109d2f"
HINTS = {"146/159": {"setId": "sv09", "localId": "146"}, "98/159": {"setId": "sv09", "localId": "098"}}
BASELINE = {"standard": 49, "secret": 30, "subsetSpecialNumbering": 30, "promo": 12}
TARGETS = {"standard": 50, "secret": 30, "subsetSpecialNumbering": 30, "promo": 30}
PROMO_RE = re.compile(r"promo|promozional|black star|prize pack|play[! ]+pokemon", re.I)
SUBSET_RE = re.compile(r"trainer gallery|galarian gallery|radiant collection|shiny vault|classic collection|subset|gallery", re.I)
ENERGY_RE = re.compile(r"\b(energy|energia)\b", re.I)
BASIC_RE = re.compile(r"basic\s+(?:grass|fire|water|lightning|psychic|fighting|darkness|metal|fairy)\s+energy|energia\s+base|energia\s+(?:erba|fuoco|acqua|lampo|psico|lotta|oscurita|metallo|folletto)", re.I)


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def norm(value):
    text = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", text)


def rows(value, *keys):
    if isinstance(value, list):
        return value
    if isinstance(value, dict):
        for key in keys:
            if isinstance(value.get(key), list):
                return value[key]
    return []


class Network:
    def __init__(self):
        self.requests = 0
        self.errors = []

    def get(self, url, attempts=3):
        self.requests += 1
        error = None
        for attempt in range(1, attempts + 1):
            try:
                request = urllib.request.Request(url, headers={"User-Agent": "Cardoryx-Full-Coverage-Audit/1.0", "Accept": "application/json"})
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.load(response)
            except Exception as exc:
                error = exc
                if isinstance(exc, urllib.error.HTTPError) and exc.code in {400, 401, 403, 404}:
                    break
                if attempt < attempts:
                    time.sleep(attempt)
        self.errors.append({"url": url, "error": str(error)})
        raise RuntimeError(f"GET failed {url}: {error}")


def count(detail, key):
    try:
        return max(0, int((detail.get("cardCount") or {}).get(key) or 0))
    except (TypeError, ValueError):
        return 0


def release_year(detail):
    match = re.search(r"(?:19|20)\d{2}", str(detail.get("releaseDate") or detail.get("release") or ""))
    return int(match.group()) if match else None


def numeric(value):
    text = str(value or "").strip()
    return int(text) if re.fullmatch(r"\d{1,3}", text) else None


def special_parts(value):
    match = re.fullmatch(r"([A-Za-z]{1,5})[- ]*0*(\d{1,3})", str(value or "").strip())
    return (match.group(1).upper(), int(match.group(2))) if match else None


def exact_local_key(value):
    special = special_parts(value)
    if special:
        return f"{special[0]}{special[1]}"
    number = numeric(value)
    if number is not None:
        return str(number)
    return norm(value)


def set_blob(detail):
    series = detail.get("serie") or detail.get("series") or {}
    if isinstance(series, dict):
        series = f"{series.get('id', '')} {series.get('name', '')}"
    return f"{detail.get('id', '')} {detail.get('name', '')} {series}"


def is_pocket(detail):
    set_id = str(detail.get("id") or "")
    return bool(re.search(r"pokemon tcg pocket|tcg pocket", set_blob(detail), re.I) or re.fullmatch(r"(?:A\d+[a-z]?|P-A)", set_id, re.I))


def fetch_detail(network, locale, set_id):
    detail = network.get(f"{BASES[locale]}/sets/{urllib.parse.quote(set_id)}")
    if not isinstance(detail, dict) or not detail.get("id"):
        raise RuntimeError("invalid set detail")
    return detail


def build_catalog(lists, details):
    cards = {"it": {}, "en": {}}
    card_sets = {"it": {}, "en": {}}
    order = []
    seen = set()
    for locale in ("it", "en"):
        for summary in lists[locale]:
            set_id = str(summary.get("id") or "")
            detail = details[locale].get(set_id) or {}
            for card in rows(detail.get("cards"), "cards", "data"):
                card_id = str(card.get("id") or "") if isinstance(card, dict) else ""
                if not card_id:
                    continue
                cards[locale][card_id] = card
                card_sets[locale][card_id] = set_id
                if card_id not in seen:
                    seen.add(card_id)
                    order.append(card_id)
    identities = []
    for card_id in order:
        it_card = cards["it"].get(card_id)
        en_card = cards["en"].get(card_id)
        card = it_card or en_card or {}
        set_id = card_sets["it"].get(card_id) or card_sets["en"].get(card_id) or ""
        detail = details["it"].get(set_id) or details["en"].get(set_id) or {}
        names = f"{it_card.get('name', '') if it_card else ''} {en_card.get('name', '') if en_card else ''}"
        identities.append({
            "id": card_id,
            "nameIT": it_card.get("name") if it_card else None,
            "nameEN": en_card.get("name") if en_card else None,
            "name": card.get("name"),
            "setId": set_id,
            "setName": detail.get("name"),
            "localId": card.get("localId"),
            "official": count(detail, "official"),
            "year": release_year(detail),
            "pocket": is_pocket(detail),
            "promo": bool(PROMO_RE.search(set_blob(detail))),
            "subset": bool(SUBSET_RE.search(set_blob(detail)) or special_parts(card.get("localId"))),
            "basicEnergy": bool(ENERGY_RE.search(names) and BASIC_RE.search(names)),
            "itAvailable": it_card is not None,
            "enAvailable": en_card is not None,
        })
    return identities


def stable_sample(items, target):
    if len(items) <= target:
        return list(items)
    items = sorted(items, key=lambda x: (x.get("year") or 0, x["setId"], numeric(x["localId"]) or 0, x["id"]))
    out, seen, per_set = [], set(), Counter()
    for index in range(target * 4):
        item = items[round(index * (len(items) - 1) / max(1, target * 4 - 1))]
        if item["id"] in seen or per_set[item["setId"]] >= 2:
            continue
        out.append(item); seen.add(item["id"]); per_set[item["setId"]] += 1
        if len(out) == target:
            return out
    for item in items:
        if item["id"] not in seen:
            out.append(item); seen.add(item["id"])
        if len(out) == target:
            break
    return out


class Recognizer:
    def __init__(self, lists, details, identities):
        self.lists = lists
        self.details = details
        self.identities = identities
        self.by_id = {item["id"]: item for item in identities}
        self.physical = [item for item in identities if not item["pocket"]]
        self.set_order = []
        self.summaries = {}
        for locale in ("it", "en"):
            for summary in lists[locale]:
                set_id = str(summary.get("id") or "")
                if set_id and set_id not in self.summaries:
                    self.summaries[set_id] = summary
                    self.set_order.append(set_id)
        self.effective_details = {set_id: details["it"].get(set_id) or details["en"].get(set_id) or {} for set_id in self.set_order}
        self.by_local = defaultdict(list)
        self.by_set_local = {}
        self.special_max = defaultdict(int)
        for item in self.physical:
            key = exact_local_key(item["localId"])
            self.by_local[key].append(item)
            self.by_set_local[(item["setId"], key)] = item
            part = special_parts(item["localId"])
            if part:
                self.special_max[(item["setId"], part[0])] = max(self.special_max[(item["setId"], part[0])], part[1])
        self.sets_by_official = {}

    def physical_set(self, set_id):
        return bool(set_id and not is_pocket(self.effective_details.get(set_id) or self.summaries.get(set_id) or {"id": set_id}))

    def query_sets_by_official(self, total):
        if total in self.sets_by_official:
            return self.sets_by_official[total]
        direct = [set_id for set_id in self.set_order if count(self.summaries.get(set_id, {}), "official") == total]
        selected = direct if direct else [set_id for set_id in self.set_order if count(self.effective_details.get(set_id, {}), "official") == total]
        selected = [set_id for set_id in selected if self.physical_set(set_id)][:40]
        self.sets_by_official[total] = selected
        return selected

    def numeric_candidates(self, item):
        number = numeric(item["localId"])
        official = item["official"]
        if number is None:
            return [], "localIdNotNumeric"
        if not official:
            return [], "cardCountOfficialMissing"
        hint = HINTS.get(f"{number}/{official}")
        if hint:
            hinted = self.by_set_local.get((hint["setId"], exact_local_key(hint["localId"])))
            if hinted and hinted["official"] == official and self.physical_set(hinted["setId"]):
                return [hinted], "verifiedHint" if hinted["id"] == item["id"] else "hintShortCircuitDifferentIdentity"
        allowed_sets = self.query_sets_by_official(official)
        if item["setId"] not in allowed_sets:
            all_matching = [set_id for set_id in self.set_order if self.physical_set(set_id) and count(self.effective_details.get(set_id, {}), "official") == official]
            reason = "exactOfficialSetBeyondCap40" if item["setId"] in all_matching else "setMissingFromOfficialCountQuery"
            return [], reason
        candidates = []
        for set_id in allowed_sets:
            candidate = self.by_set_local.get((set_id, exact_local_key(item["localId"])))
            if candidate and numeric(candidate["localId"]) is not None and candidate["official"] == official:
                candidates.append(candidate)
        return candidates, "exactOfficialSetThenCap"

    def special_candidates(self, item):
        part = special_parts(item["localId"])
        if not part:
            return [], "specialLocalIdNotInterrogable"
        observed_total = self.special_max.get((item["setId"], part[0]), 0)
        if not observed_total:
            return [], "specialDenominatorUnavailable"
        candidates = []
        for candidate in self.by_local.get(exact_local_key(item["localId"]), []):
            if self.special_max.get((candidate["setId"], part[0]), 0) == observed_total:
                candidates.append(candidate)
        return candidates, "exactSpecialLocalIdAndObservedTotal"

    def promo_candidates(self, item):
        part = special_parts(item["localId"])
        if not part:
            return [], "numericPromoWithoutDenominator" if numeric(item["localId"]) is not None else "promoLocalIdNotInterrogable"
        return list(self.by_local.get(exact_local_key(item["localId"]), [])), "exactStandalonePromoLocalId"

    def classify(self, item):
        if item["pocket"]:
            return self.result(item, "excludedNonPhysical", "nonPhysicalOrPocket", [])
        set_id = item["setId"].lower()
        number = numeric(item["localId"])
        if item["basicEnergy"] and ((set_id == "sve" and number is not None and 1 <= number <= 24) or (set_id == "mee" and number is not None and 1 <= number <= 16)):
            return self.result(item, "recognizedUnique", "codedBasicEnergySVE_MEE", [item])
        if item["promo"]:
            candidates, route = self.promo_candidates(item)
        elif special_parts(item["localId"]):
            candidates, route = self.special_candidates(item)
        elif number is not None:
            candidates, route = self.numeric_candidates(item)
        else:
            return self.result(item, "notRecognized", "localIdNotInterrogable", [])
        candidate_ids = [candidate["id"] for candidate in candidates]
        if item["id"] not in candidate_ids:
            return self.result(item, "notRecognized", route, candidates)
        position = candidate_ids.index(item["id"])
        if position >= 6:
            return self.result(item, "notRecognized", "targetBeyondDisplayCap6", candidates)
        outcome = "recognizedUnique" if len(candidates) == 1 else "recognizedAmbiguous"
        return self.result(item, outcome, route, candidates)

    @staticmethod
    def category(item):
        if item["promo"]:
            return "promo"
        if special_parts(item["localId"]):
            return "subsetSpecialNumbering"
        number = numeric(item["localId"])
        if number is not None and item["official"] and number > item["official"]:
            return "secret"
        if number is not None:
            return "standard"
        return "other"

    def result(self, item, outcome, reason, candidates):
        return {
            "id": item["id"], "name": item["nameIT"] or item["nameEN"], "setId": item["setId"], "set": item["setName"],
            "localId": item["localId"], "cardCountOfficial": item["official"], "category": self.category(item),
            "outcome": outcome, "reason": reason, "candidateCount": len(candidates),
            "candidateIds": [candidate["id"] for candidate in candidates[:15]], "itAvailable": item["itAvailable"], "enAvailable": item["enAvailable"],
        }


def aggregate(results):
    eligible = [result for result in results if result["outcome"] != "excludedNonPhysical"]
    unique = sum(result["outcome"] == "recognizedUnique" for result in eligible)
    ambiguous = sum(result["outcome"] == "recognizedAmbiguous" for result in eligible)
    not_recognized = len(eligible) - unique - ambiguous
    by_category = {}
    for category in sorted({result["category"] for result in eligible}):
        group = [result for result in eligible if result["category"] == category]
        u = sum(result["outcome"] == "recognizedUnique" for result in group)
        a = sum(result["outcome"] == "recognizedAmbiguous" for result in group)
        n = len(group) - u - a
        by_category[category] = {"total": len(group), "recognizedUnique": u, "recognizedAmbiguous": a, "notRecognized": n, "coveragePercent": round(100 * (u + a) / len(group), 2) if group else 0, "uniqueCoveragePercent": round(100 * u / len(group), 2) if group else 0}
    reasons = Counter(result["reason"] for result in eligible if result["outcome"] == "notRecognized")
    examples = {}
    for reason, _ in reasons.most_common(20):
        examples[reason] = [result for result in eligible if result["outcome"] == "notRecognized" and result["reason"] == reason][:15]
    return eligible, unique, ambiguous, not_recognized, by_category, reasons, examples


def regression_check(recognizer):
    pools = {key: [] for key in TARGETS}
    for item in recognizer.physical:
        category = recognizer.category(item)
        if category in pools:
            pools[category].append(item)
    samples = {key: stable_sample(pools[key], target) for key, target in TARGETS.items()}
    controls = stable_sample([item for item in pools["standard"] if item["basicEnergy"] and item["setId"].lower() in {"sve", "mee"}], 6)
    if controls:
        control_ids = {item["id"] for item in controls}
        samples["standard"] = (controls + [item for item in samples["standard"] if item["id"] not in control_ids])[:50]
    observed, cases = {}, {}
    for category, items in samples.items():
        category_cases = [recognizer.classify(item) for item in items]
        cases[category] = category_cases
        observed[category] = sum(case["outcome"] in {"recognizedUnique", "recognizedAmbiguous"} for case in category_cases)
    regressions = {category: {"expected": BASELINE[category], "observed": observed[category]} for category in BASELINE if observed[category] < BASELINE[category]}
    energy_results = [recognizer.classify(item) for item in controls]
    energy_passed = sum(result["outcome"] == "recognizedUnique" for result in energy_results)
    if energy_passed != len(energy_results):
        regressions["SVE_MEE"] = {"expected": len(energy_results), "observed": energy_passed}
    return {"sampleSize": sum(len(items) for items in samples.values()), "expectedRecognized": BASELINE, "observedRecognized": observed, "regressions": regressions, "regressionCount": len(regressions), "sveMeeTested": len(energy_results), "sveMeePassed": energy_passed, "cases": cases}


def main():
    started = time.monotonic()
    network = Network()
    lists = {}
    for locale, base in BASES.items():
        lists[locale] = rows(network.get(f"{base}/sets"), "sets", "data")
    details = {"it": {}, "en": {}}
    set_errors = {"it": {}, "en": {}}
    futures = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        for locale in BASES:
            for summary in lists[locale]:
                set_id = str(summary.get("id") or "")
                if set_id:
                    futures[pool.submit(fetch_detail, network, locale, set_id)] = (locale, set_id)
        for future in as_completed(futures):
            locale, set_id = futures[future]
            try:
                details[locale][set_id] = future.result()
            except Exception as exc:
                set_errors[locale][set_id] = str(exc)
    identities = build_catalog(lists, details)
    recognizer = Recognizer(lists, details, identities)
    results = [recognizer.classify(item) for item in identities]
    eligible, unique, ambiguous, not_recognized, categories, reasons, examples = aggregate(results)
    regressions = regression_check(recognizer)
    energy_overlay = [result for item, result in zip(identities, results) if item["basicEnergy"]]
    energy_distribution = Counter(result["outcome"] for result in energy_overlay)
    high_potential = []
    for reason, amount in reasons.most_common():
        if reason in {"exactOfficialSetBeyondCap40", "targetBeyondDisplayCap6", "cardCountOfficialMissing", "promoLocalIdNotInterrogable", "localIdNotInterrogable"}:
            high_potential.append({"reason": reason, "identities": amount, "requiresValidation": True})
    report = {
        "schema": 1,
        "testType": "full-catalog-coverage-postmerge",
        "generatedAt": now(),
        "sourceCommit": os.environ.get("GITHUB_SHA", "unknown"),
        "expectedMainAtStart": EXPECTED_MAIN,
        "method": {
            "description": "Full static reachability simulation of the recognition functions present in index.html, using one downloaded snapshot of every TCGdex IT/EN set and card list.",
            "ocrImageAccuracyIncluded": False,
            "candidateOrdering": "TCGdex IT set order followed by EN-only sets; scanner display cap of six retained.",
            "coverageDefinition": "Only identities actually returned within the current scanner path and display cap are counted as covered.",
            "rulesReused": ["IT+EN id merge", "cardCount.official before cap40", "exact numeric localId", "secret numerator allowed", "exact alphanumeric localId", "observed subset prefix total", "standalone alphanumeric promo", "verified hints", "physical TCG filter", "SVE/MEE deterministic resolver", "display cap6", "no automatic choice when ambiguous"],
        },
        "safety": {"readOnly": True, "indexHtmlModified": False, "retailModified": False, "cardmarketModified": False, "collectionDataModified": False, "newIdentitiesCreated": False, "scannerBehaviorModified": False, "productionWorkflowModified": False},
        "scope": {"setsIT": len(lists["it"]), "setsEN": len(lists["en"]), "setsITLoaded": len(details["it"]), "setsENLoaded": len(details["en"]), "catalogIdentities": len(identities), "physicalIdentitiesEligible": len(eligible), "excludedNonPhysicalPocket": len(identities) - len(eligible), "runtimeSeconds": round(time.monotonic() - started, 2)},
        "summary": {"recognizedUnique": unique, "recognizedAmbiguous": ambiguous, "notRecognized": not_recognized, "coveragePercent": round(100 * (unique + ambiguous) / len(eligible), 2) if eligible else 0, "uniqueCoveragePercent": round(100 * unique / len(eligible), 2) if eligible else 0, "ambiguousPercent": round(100 * ambiguous / len(eligible), 2) if eligible else 0, "networkRequests": network.requests, "networkErrors": len(network.errors), "regressions": regressions["regressionCount"]},
        "distributionByCategory": categories,
        "energySpecialFamiliesOverlay": {"total": len(energy_overlay), "outcomes": dict(energy_distribution)},
        "topFailureReasons": [{"reason": reason, "identities": amount} for reason, amount in reasons.most_common(10)],
        "failureExamples": examples,
        "highPotentialRecoveryGroups": high_potential,
        "mustRemainUnresolved": [{"reason": "numericPromoWithoutDenominator", "identities": reasons.get("numericPromoWithoutDenominator", 0), "why": "No unique physical set/localId can be proven from the current printed inputs."}, {"reason": "targetBeyondDisplayCap6", "identities": reasons.get("targetBeyondDisplayCap6", 0), "why": "More exact candidates exist than the UI can safely display; automatic selection would create false positives."}],
        "regressionChecks": regressions,
        "networkErrors": network.errors,
        "setDetailErrors": set_errors,
        "identityResults": results,
    }
    reliable = len(eligible) > 0 and regressions["regressionCount"] == 0 and len(network.errors) == 0
    report["finalAssessment"] = "AUDIT AFFIDABILE" if reliable else "DA VERIFICARE"
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"scope": report["scope"], "summary": report["summary"], "distributionByCategory": categories, "topFailureReasons": report["topFailureReasons"], "highPotentialRecoveryGroups": high_potential, "finalAssessment": report["finalAssessment"], "report": str(OUTPUT)}, ensure_ascii=False, indent=2))
    if not reliable:
        raise SystemExit("Full catalog audit requires verification")


if __name__ == "__main__":
    main()
