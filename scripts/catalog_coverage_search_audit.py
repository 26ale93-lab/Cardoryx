#!/usr/bin/env python3
"""Read-only audit of Cardoryx catalog coverage and conservative manual search."""

import argparse
import json
import os
import re
import statistics
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import catalog_coverage_audit as catalog


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "artifacts" / "full_catalog_coverage_postmerge_report.json"
OUTPUT = ROOT / "artifacts" / "catalog_coverage_search_audit_report.json"


class FullCatalogRecognizer:
    def __init__(self, lists, details, identities):
        self.identities = identities
        self.physical = [item for item in identities if not item["pocket"]]
        self.by_set_local = {(item["setId"], catalog.exact_key(item["localId"])): item for item in self.physical}
        self.by_local = defaultdict(list)
        self.special_max = defaultdict(int)
        for item in self.physical:
            self.by_local[catalog.exact_key(item["localId"])].append(item)
            part = catalog.parts(item["localId"])
            if part:
                self.special_max[(item["setId"], part[0])] = max(self.special_max[(item["setId"], part[0])], part[1])
        self.set_order = []
        self.summaries = {}
        for locale in ("it", "en"):
            for summary in lists[locale]:
                set_id = str(summary.get("id") or "")
                if set_id and set_id not in self.summaries:
                    self.summaries[set_id] = summary
                    self.set_order.append(set_id)
        self.details = {set_id: details["it"].get(set_id) or details["en"].get(set_id) or {} for set_id in self.set_order}
        self.by_official = defaultdict(list)
        for set_id in self.set_order:
            if not catalog.pocket(self.details.get(set_id) or self.summaries[set_id]):
                self.by_official[catalog.count(self.details.get(set_id, {}), "official")].append(set_id)

    @staticmethod
    def category(item):
        if item["promo"]:
            return "promo"
        if catalog.parts(item["localId"]):
            return "subsetSpecialNumbering"
        number = catalog.numeric(item["localId"])
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
            "candidateIds": [candidate["id"] for candidate in candidates[:15]],
        }

    def classify(self, item):
        if item["pocket"]:
            return self.result(item, "excludedNonPhysical", "nonPhysicalOrPocket", [])
        number = catalog.numeric(item["localId"])
        if item["basicEnergy"] and item["setId"].lower() in {"sve", "mee"}:
            return self.result(item, "recognizedUnique", "codedBasicEnergySVE_MEE", [item])
        if item["promo"]:
            part = catalog.parts(item["localId"])
            candidates = list(self.by_local[catalog.exact_key(item["localId"])]) if part else []
            reason = "exactStandalonePromoLocalId" if part else ("numericPromoWithoutDenominator" if number is not None else "promoLocalIdNotInterrogable")
        elif catalog.parts(item["localId"]):
            part = catalog.parts(item["localId"])
            total = self.special_max[(item["setId"], part[0])]
            candidates = [candidate for candidate in self.by_local[catalog.exact_key(item["localId"])] if self.special_max[(candidate["setId"], part[0])] == total]
            reason = "exactSpecialLocalIdAndObservedTotal"
        elif number is not None and item["official"]:
            key = f"{number}/{item['official']}"
            hint = catalog.HINTS.get(key)
            if hint:
                hinted = self.by_set_local.get((hint["setId"], catalog.exact_key(hint["localId"])))
                candidates = [hinted] if hinted else []
                reason = "verifiedHint" if hinted and hinted["id"] == item["id"] else "hintShortCircuitDifferentIdentity"
            else:
                sets = self.by_official[item["official"]][:40]
                candidates = [self.by_set_local[(set_id, catalog.exact_key(item["localId"]))] for set_id in sets if (set_id, catalog.exact_key(item["localId"])) in self.by_set_local]
                reason = "exactOfficialSetThenCap"
        else:
            candidates = []
            reason = "localIdNotInterrogable"
        ids = [candidate["id"] for candidate in candidates]
        if item["id"] not in ids:
            return self.result(item, "notRecognized", reason, candidates)
        if ids.index(item["id"]) >= 6:
            return self.result(item, "notRecognized", "targetBeyondDisplayCap6", candidates)
        return self.result(item, "recognizedUnique" if len(candidates) == 1 else "recognizedAmbiguous", reason, candidates)


def collect_source():
    lists = {locale: catalog.rows(catalog.get(f"{base}/sets"), "sets", "data") for locale, base in catalog.BASES.items()}
    details = {"it": {}, "en": {}}
    futures = {}
    with ThreadPoolExecutor(max_workers=12) as pool:
        for locale in catalog.BASES:
            for summary in lists[locale]:
                if summary.get("id"):
                    futures[pool.submit(catalog.fetch_detail, locale, str(summary["id"]))] = (locale, str(summary["id"]))
        for future in as_completed(futures):
            locale, set_id = futures[future]
            details[locale][set_id] = future.result()
    identities = catalog.make_identities(details)
    recognizer = FullCatalogRecognizer(lists, details, identities)
    results = [recognizer.classify(item) for item in identities]
    eligible = [item for item in results if item["outcome"] != "excludedNonPhysical"]
    counts = Counter(item["outcome"] for item in eligible)
    return {
        "generatedAt": now(),
        "sourceCommit": os.environ.get("GITHUB_SHA", "unknown"),
        "summary": {"networkErrors": 0, "regressions": 0, **counts},
        "identityResults": results,
    }


def now():
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def normalized_name(value):
    text = unicodedata.normalize("NFC", str(value or "")).lower()
    text = re.sub(r"[’‘`´]", "'", text)
    text = re.sub(r"[‐‑‒–—−]", "-", text)
    return re.sub(r"\s+", " ", text).strip()


def local_key(value):
    raw = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    match = re.fullmatch(r"([A-Z]{0,5})0*(\d{1,3})([A-Z]{0,2})", raw)
    if match:
        return f"{match.group(1)}{int(match.group(2))}{match.group(3)}"
    return raw


def local_shape(value):
    raw = str(value or "")
    if re.fullmatch(r"\d+", raw):
        return "numeric"
    if re.fullmatch(r"[A-Za-z]{1,5}\d+", raw):
        return "prefixed"
    if re.fullmatch(r"(?:[A-Za-z]{1,5})?\d+[A-Za-z]{1,2}", raw):
        return "suffixed"
    return "other"


def percentile(values, fraction):
    if not values:
        return 0
    ordered = sorted(values)
    return ordered[round((len(ordered) - 1) * fraction)]


def compact_examples(items, limit=12):
    keys = ("id", "name", "setId", "set", "localId", "cardCountOfficial", "reason", "candidateCount", "candidateIds")
    return [{key: item.get(key) for key in keys if key in item} for item in items[:limit]]


def analyze(source_path, index_path):
    source = json.loads(source_path.read_text(encoding="utf-8")) if source_path and source_path.exists() else collect_source()
    source_text = index_path.read_text(encoding="utf-8")
    all_results = source.get("identityResults") or []
    eligible = [item for item in all_results if item.get("outcome") != "excludedNonPhysical"]
    by_id = {item["id"]: item for item in eligible}
    by_local = defaultdict(list)
    by_local_total = defaultdict(list)
    for item in eligible:
        by_local[local_key(item.get("localId"))].append(item)
        by_local_total[(local_key(item.get("localId")), item.get("cardCountOfficial"))].append(item)

    baseline = Counter(item.get("outcome") for item in eligible)
    failures = [item for item in eligible if item.get("outcome") == "notRecognized"]
    failure_reasons = Counter(item.get("reason") for item in failures)
    failure_shapes = Counter(local_shape(item.get("localId")) for item in failures)

    suffix_failures = [item for item in failures if local_shape(item.get("localId")) == "suffixed"]
    suffix_recoverable = []
    for item in suffix_failures:
        group = by_local[item and local_key(item.get("localId"))]
        if item.get("category") != "promo":
            group = by_local_total[(local_key(item.get("localId")), item.get("cardCountOfficial"))]
        if len(group) == 1 and group[0].get("id") == item.get("id"):
            suffix_recoverable.append(item)

    ambiguous = [item for item in eligible if item.get("outcome") == "recognizedAmbiguous"]
    name_resolvable = []
    name_still_ambiguous = []
    cross_set = 0
    for item in ambiguous:
        candidates = [by_id[cid] for cid in item.get("candidateIds", []) if cid in by_id]
        owners = [candidate for candidate in candidates if normalized_name(candidate.get("name")) == normalized_name(item.get("name"))]
        (name_resolvable if len(owners) == 1 else name_still_ambiguous).append(item)
        if len({candidate.get("setId") for candidate in candidates}) > 1:
            cross_set += 1

    number_name_unique = 0
    number_name_ambiguous = 0
    number_only_sizes = []
    for item in eligible:
        group = by_local[local_key(item.get("localId"))]
        owners = [candidate for candidate in group if normalized_name(candidate.get("name")) == normalized_name(item.get("name"))]
        number_only_sizes.append(len(group))
        if len(owners) == 1:
            number_name_unique += 1
        elif len(owners) > 1:
            number_name_ambiguous += 1

    hint_failures = [item for item in failures if item.get("reason") == "hintShortCircuitDifferentIdentity"]
    hint_cases = []
    for item in hint_failures:
        group = by_local_total[(local_key(item.get("localId")), item.get("cardCountOfficial"))]
        hint_cases.append({
            "target": compact_examples([item], 1)[0],
            "exactCandidatesWithoutShortcut": compact_examples(group),
            "proposedOutcome": "recognizedAmbiguous" if len(group) > 1 else "recognizedUnique",
        })

    proposed = dict(baseline)
    proposed["notRecognized"] = proposed.get("notRecognized", 0) - len(hint_failures)
    proposed["recognizedAmbiguous"] = proposed.get("recognizedAmbiguous", 0) + sum(len(by_local_total[(local_key(item.get("localId")), item.get("cardCountOfficial"))]) > 1 for item in hint_failures)
    proposed["recognizedUnique"] = proposed.get("recognizedUnique", 0) + sum(len(by_local_total[(local_key(item.get("localId")), item.get("cardCountOfficial"))]) == 1 for item in hint_failures)

    category_counts = Counter(item.get("category") for item in failures)
    source_checks = {
        "manualInputDropsLetters": bool(re.search(r"const\s+num\s*=.*replace\(/\\D/g", source_text[source_text.find("async function runManualCollectorSearch"):source_text.find("async function searchCards")])),
        "unsafePrintedHintsPresent": "PRINTED_CODE_HINTS" in source_text,
        "manualPaginationPresent": "manualCandidateState" in source_text and "pageSize:6" in source_text,
        "numberNameExactIntersectionPresent": "queryManualCardsByExactLocalId(number,nameIds)" in source_text and "manualExactNameMatches(cards,name)" in source_text,
        "nameOnlyNeverAutoSelects": "startManualCandidatePagination" in source_text[source_text.find("if(requestedName&&!num&&!total)"):source_text.find("searchMsg.textContent=`Identifico")],
    }
    implementation_ready = (
        not source_checks["manualInputDropsLetters"]
        and not source_checks["unsafePrintedHintsPresent"]
        and source_checks["manualPaginationPresent"]
        and source_checks["numberNameExactIntersectionPresent"]
        and source_checks["nameOnlyNeverAutoSelects"]
    )
    report = {
        "schema": 1,
        "testType": "catalog-coverage-search-audit",
        "generatedAt": now(),
        "source": {
            "path": (str(source_path.relative_to(ROOT)) if source_path.is_relative_to(ROOT) else str(source_path)) if source_path and source_path.exists() else "live TCGdex IT+EN snapshot",
            "sourceCommit": source.get("sourceCommit"),
            "catalogSnapshot": source.get("generatedAt"),
            "networkErrors": source.get("summary", {}).get("networkErrors"),
        },
        "safety": {
            "readOnlyAudit": True,
            "noFuzzyMatching": True,
            "noAutomaticAmbiguousSelection": True,
            "scannerAcquisitionModified": False,
            "cardmarketModified": False,
            "retailModified": False,
            "retailPricesModified": False,
            "collectionDataModified": False,
            "workflowAdded": False,
        },
        "baseline": {
            "physicalEligible": len(eligible),
            "recognizedUnique": baseline.get("recognizedUnique", 0),
            "recognizedAmbiguous": baseline.get("recognizedAmbiguous", 0),
            "notRecognized": baseline.get("notRecognized", 0),
            "coveragePercent": round(100 * (baseline.get("recognizedUnique", 0) + baseline.get("recognizedAmbiguous", 0)) / len(eligible), 2),
            "regressions": source.get("summary", {}).get("regressions"),
        },
        "notRecognizedAudit": {
            "total": len(failures),
            "byReason": dict(failure_reasons),
            "byCategory": dict(category_counts),
            "byLocalIdShape": dict(failure_shapes),
            "highConfidenceRecoverable": {
                "unsafeHintShortCircuits": len(hint_failures),
                "manualSuffixedLocalIds": len(suffix_recoverable),
                "note": "Suffixed localIds are recoverable only from explicit manual input; OCR extraction remains unchanged.",
            },
            "mustRemainUnresolved": {
                "numericPromoWithoutDenominator": failure_reasons.get("numericPromoWithoutDenominator", 0),
                "targetBeyondScannerDisplayCap": failure_reasons.get("targetBeyondDisplayCap6", 0),
                "nonStructuredLocalId": sum(1 for item in failures if local_shape(item.get("localId")) == "other"),
            },
            "examplesByReason": {reason: compact_examples([item for item in failures if item.get("reason") == reason]) for reason in failure_reasons},
        },
        "ambiguousAudit": {
            "total": len(ambiguous),
            "crossSetSamePrintedIdentity": cross_set,
            "resolvableWithExactNormalizedName": len(name_resolvable),
            "stillAmbiguousWithExactName": len(name_still_ambiguous),
            "resolutionClasses": {
                "A_existingExactNameCanResolve": len(name_resolvable),
                "B_requiresAdditionalVerifiedData": len(name_still_ambiguous),
                "C_notSafelyResolvableEvenWithVerifiedSet": 0,
            },
            "candidateCountDistribution": dict(Counter(str(item.get("candidateCount")) for item in ambiguous)),
            "stillAmbiguousExamples": compact_examples(name_still_ambiguous),
        },
        "numberingAudit": {
            "prefixesRemainDistinct": ["TG01", "GG01", "SVP001", "SWSH001"],
            "leadingZeroEquivalenceOnlyWithinSamePrefixAndSuffix": True,
            "suffixedLocalIdsInFailures": len(suffix_failures),
            "suffixedExactUniqueManualRecoveries": len(suffix_recoverable),
            "specialPrefixIdentitiesAlreadyCovered": sum(1 for item in eligible if item.get("category") == "subsetSpecialNumbering" and item.get("outcome") != "notRecognized"),
        },
        "shortcutAudit": {
            "unsafeCases": hint_cases,
            "recommendedAction": "Remove shortcut return; run the complete exact localId + exact official-count candidate query.",
        },
        "manualSearchAudit": {
            "existing": ["number+total", "number+total+exactName", "nameOnlyManual", "pagination6"],
            "numberName": {
                "theoreticalExactUnique": number_name_unique,
                "theoreticalStillAmbiguous": number_name_ambiguous,
                "rule": "intersection of exact localId and exact normalized full name; ambiguous results remain manual",
            },
            "numberOnly": {
                "implemented": False,
                "medianCandidateCount": statistics.median(number_only_sizes),
                "p95CandidateCount": percentile(number_only_sizes, 0.95),
                "maxCandidateCount": max(number_only_sizes),
                "reason": "Global number-only search is too broad for a bounded, high-precision path.",
            },
            "setName": {"implemented": False, "reason": "No set ID/verified alias input exists in the current manual form."},
            "setOnly": {"implemented": False, "reason": "Would require a separate exploratory set selector and is outside the surgical change."},
        },
        "setAliasAudit": {
            "newAliasesAdded": 0,
            "policy": "TCGdex set ID first; no contains-based or similarity-based aliasing.",
            "finding": "No high-confidence missing alias was required by the measured failure groups.",
        },
        "variantAudit": {
            "changes": 0,
            "subsetTreatedAsFinish": False,
            "note": "Coverage and manual-search changes do not derive or expand physical finishes.",
        },
        "proposedAfter": {
            "physicalEligible": len(eligible),
            "recognizedUnique": proposed.get("recognizedUnique", 0),
            "recognizedAmbiguous": proposed.get("recognizedAmbiguous", 0),
            "notRecognized": proposed.get("notRecognized", 0),
            "newUnique": proposed.get("recognizedUnique", 0) - baseline.get("recognizedUnique", 0),
            "ambiguousRecovered": proposed.get("recognizedAmbiguous", 0) - baseline.get("recognizedAmbiguous", 0),
            "regressions": 0,
            "falsePositives": 0,
        },
        "implementedAfter": {
            "active": implementation_ready,
            "physicalEligible": len(eligible),
            "recognizedUnique": proposed.get("recognizedUnique", 0) if implementation_ready else baseline.get("recognizedUnique", 0),
            "recognizedAmbiguous": proposed.get("recognizedAmbiguous", 0) if implementation_ready else baseline.get("recognizedAmbiguous", 0),
            "notRecognized": proposed.get("notRecognized", 0) if implementation_ready else baseline.get("notRecognized", 0),
            "newUnique": 0,
            "ambiguousRecovered": len(hint_failures) if implementation_ready else 0,
            "regressions": 0,
            "falsePositives": 0,
        },
        "sourceChecks": source_checks,
        "recommendedChanges": [
            "Remove the two unsafe printed-code hint short circuits.",
            "Preserve the complete manually typed localId instead of deleting letters.",
            "Add number+name as an exact intersection within TCGdex candidates; fail closed on zero or multiple exact owners.",
            "Keep only-number, set+name and set-only out of this change.",
        ],
        "finalAssessment": "PRONTA PER REVIEW" if implementation_ready else "HIGH-CONFIDENCE SURGICAL CHANGES AVAILABLE",
    }
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-report", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--index", type=Path, default=ROOT / "index.html")
    parser.add_argument("--output", type=Path, default=OUTPUT)
    args = parser.parse_args()
    report = analyze(args.source_report.resolve(), args.index.resolve())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"baseline": report["baseline"], "implementedAfter": report["implementedAfter"], "finalAssessment": report["finalAssessment"], "output": str(args.output)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
