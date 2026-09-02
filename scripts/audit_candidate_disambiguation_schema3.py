#!/usr/bin/env python3
"""Read-only audit of Cardoryx real-photo candidate disambiguation export schema 3.

The source export is supplied locally and is never copied into the repository.
This script only reads JSON and writes the requested diagnostic report.
"""

from __future__ import annotations

import argparse
import itertools
import json
import math
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any


READ_IDS = ("N1-A", "N1-B", "N1-C", "N1-D", "N2-E", "N3-F", "N4-G")


def n(value: Any) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def rounded(value: float | None, digits: int = 2) -> float | None:
    return None if value is None else round(value, digits)


def percentile_nearest(values: list[float], fraction: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    return ordered[max(0, math.ceil(fraction * len(ordered)) - 1)]


def read_map(scan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(read.get("id")): read
        for read in scan.get("nameDiagnostics", {}).get("reads", [])
        if read.get("id")
    }


def candidate_names(scan: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for read in scan.get("nameDiagnostics", {}).get("reads", []):
        for match in read.get("candidateMatches", []):
            cid = str(match.get("candidateId") or "")
            if cid:
                result[cid] = str(match.get("candidateName") or "")
    auto_id = str(scan.get("automaticCandidateId") or "")
    if auto_id:
        result.setdefault(auto_id, str(scan.get("automaticCandidateName") or ""))
    gt_id = str(scan.get("groundTruthCardId") or "")
    if gt_id:
        result.setdefault(gt_id, str(scan.get("groundTruthName") or ""))
    return result


def match_summary(match: dict[str, Any]) -> dict[str, Any]:
    return {
        "candidateId": match.get("candidateId"),
        "candidateName": match.get("candidateName"),
        "exactFullName": bool(match.get("exactFullName")),
        "exactTokenSequence": bool(match.get("exactTokenSequence")),
        "baseNameOnly": bool(match.get("baseNameOnly")),
        "suffixExpected": match.get("suffixExpected") or "",
        "suffixObserved": match.get("suffixObserved") or "",
        "suffixAgreement": match.get("suffixAgreement"),
        "matchedNameTokens": match.get("matchedNameTokens") or [],
        "extraTokens": match.get("extraTokens") or [],
        "numericTokens": match.get("numericTokens") or [],
        "hpPsTokens": match.get("hpPsTokens") or [],
        "symbolTokens": match.get("symbolTokens") or [],
        "bestDiagnosticLevel": n(match.get("bestDiagnosticLevel")),
        "uniqueCandidateOwner": bool(match.get("uniqueCandidateOwner")),
    }


def read_summary(read: dict[str, Any] | None) -> dict[str, Any]:
    if read is None:
        return {"available": False}
    return {
        "available": True,
        "id": read.get("id"),
        "crop": read.get("crop"),
        "coordinates": read.get("coordinates"),
        "scale": read.get("scale"),
        "preprocessing": read.get("preprocessing"),
        "threshold": read.get("threshold"),
        "raw": read.get("raw") or "",
        "normalized": read.get("normalized") or "",
        "confidence": read.get("confidence"),
        "timingMs": read.get("timingMs"),
        "error": read.get("error") or "",
        "bestDiagnosticLevel": n(read.get("bestDiagnosticLevel")),
        "candidateMatches": [
            match_summary(x)
            for x in read.get("candidateMatches", [])
            if x.get("exactFullName")
            or x.get("exactTokenSequence")
            or x.get("baseNameOnly")
            or x.get("uniqueCandidateOwner")
        ],
        "candidateMatchOmission": "zero-signal candidate rows omitted; candidate IDs remain at scan level",
    }


def strong_support(read: dict[str, Any]) -> set[str]:
    return {
        str(match.get("candidateId"))
        for match in read.get("candidateMatches", [])
        if match.get("candidateId")
        and match.get("exactTokenSequence")
        and match.get("suffixAgreement") is not False
        and match.get("uniqueCandidateOwner")
    }


def is_correct(candidate_id: str, scan: dict[str, Any]) -> bool | None:
    ground_truth = str(scan.get("groundTruthCardId") or "")
    if not ground_truth:
        return None
    return candidate_id == ground_truth


def source_counts(scans: list[dict[str, Any]]) -> dict[str, Any]:
    photos = [s for s in scans if s.get("source") == "photo"]
    schema3_photos = [
        s for s in photos if s.get("collectorDiagnostics", {}).get("legacy") is not True
    ]
    multi_crop = [s for s in photos if read_map(s)]
    return {
        "recordsTotal": len(scans),
        "photoScans": len(photos),
        "manualScans": sum(s.get("source") == "manual" for s in scans),
        "schema3PhotoRecords": len(schema3_photos),
        "legacySchema2PhotoRecords": len(photos) - len(schema3_photos),
        "schema3PhotosWithNameMultiCrop": len(multi_crop),
        "groundTruthCompleted": sum(
            bool(s.get("groundTruthCardId") or s.get("groundTruthName")) for s in scans
        ),
        "importantScopeNote": (
            "Le statistiche aggregate comprendono record schema 2 migrati. Raw OCR, crop e timing "
            "avanzati sono disponibili soltanto nei record schema 3 che li contengono."
        ),
    }


def audit_wrong(scans: list[dict[str, Any]]) -> dict[str, Any]:
    wrong = [s for s in scans if s.get("automaticCorrect") is False]
    records = []
    for scan in wrong:
        nd = scan.get("nameDiagnostics", {})
        ci = n(scan.get("candidateCountInitial"))
        auto_id = str(scan.get("automaticCandidateId") or "")
        ids = [str(x) for x in scan.get("candidateIdsInitial", [])]
        if ci == 1 and auto_id in ids:
            cause = "A. candidato già unico dopo identità stampata"
        elif scan.get("categoryApplied"):
            cause = "B. filtro categoria"
        elif scan.get("subtypeApplied"):
            cause = "C. filtro sottotipo"
        elif scan.get("energyTypeApplied"):
            cause = "D. filtro tipo Energia"
        elif scan.get("nameApplied") and nd.get("ruleA", {}).get("resolved"):
            cause = "E. Rule A nome"
        elif scan.get("nameApplied") and nd.get("ruleB", {}).get("resolved"):
            cause = "F. Rule B nome"
        else:
            cause = "G. altra causa"
        records.append(
            {
                "scanId": scan.get("id"),
                "source": scan.get("source"),
                "printedIdentity": scan.get("printedIdentity"),
                "candidateIdsInitial": scan.get("candidateIdsInitial") or [],
                "candidateCountInitial": ci,
                "candidateCountFinal": n(scan.get("candidateCountFinal")),
                "automaticCandidateId": auto_id,
                "automaticCandidateName": scan.get("automaticCandidateName") or "",
                "groundTruthCardId": scan.get("groundTruthCardId") or "",
                "groundTruthName": scan.get("groundTruthName") or "",
                "automaticCorrect": scan.get("automaticCorrect"),
                "finalClassification": scan.get("finalClassification"),
                "detectedCategory": scan.get("detectedCategory") or "",
                "detectedSubtype": scan.get("detectedSubtype") or "",
                "detectedEnergyType": scan.get("detectedEnergyType") or "",
                "categoryApplied": bool(scan.get("categoryApplied")),
                "subtypeApplied": bool(scan.get("subtypeApplied")),
                "energyTypeApplied": bool(scan.get("energyTypeApplied")),
                "nameApplied": bool(scan.get("nameApplied")),
                "ruleA": nd.get("ruleA") or {"resolved": False},
                "ruleB": nd.get("ruleB") or {"resolved": False},
                "ruleC": nd.get("ruleC") or {"theoretical": False},
                "timeline": scan.get("timeline") or [],
                "causeClassification": cause,
                "evidence": (
                    f"Il record conserva {ci} candidati iniziali e {n(scan.get('candidateCountFinal'))} finali; "
                    f"categoryApplied={bool(scan.get('categoryApplied'))}, subtypeApplied={bool(scan.get('subtypeApplied'))}, "
                    f"energyTypeApplied={bool(scan.get('energyTypeApplied'))}, nameApplied={bool(scan.get('nameApplied'))}. "
                    f"L'automaticCandidateId {auto_id or '[vuoto]'} non appartiene ai candidati iniziali={auto_id not in ids}; "
                    f"collector route={scan.get('collectorDiagnostics', {}).get('route') or '[non disponibile]'}."
                ),
            }
        )
    return {"count": len(records), "records": records}


def audit_ambiguous(scans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    result = []
    for scan in scans:
        if scan.get("source") != "photo" or n(scan.get("candidateCountInitial")) <= 1:
            continue
        reads = read_map(scan)
        names = candidate_names(scan)
        nd = scan.get("nameDiagnostics", {})
        resolved = (
            nd.get("ruleA", {}).get("candidateId")
            or nd.get("ruleB", {}).get("candidateId")
            or nd.get("ruleC", {}).get("candidateId")
            or ""
        )
        result.append(
            {
                "scanId": scan.get("id"),
                "schemaData": 2 if nd.get("legacy") else 3,
                "printedIdentity": scan.get("printedIdentity"),
                "groundTruthCardId": scan.get("groundTruthCardId") or "",
                "groundTruthName": scan.get("groundTruthName") or "",
                "candidateCount": n(scan.get("candidateCountInitial")),
                "candidateIds": scan.get("candidateIdsInitial") or [],
                "candidateNames": [
                    {"id": cid, "name": names.get(str(cid)) or None}
                    for cid in scan.get("candidateIdsInitial", [])
                ],
                "reads": {rid: read_summary(reads.get(rid)) for rid in READ_IDS},
                "ruleA": nd.get("ruleA") or {"resolved": False},
                "ruleB": nd.get("ruleB") or {"resolved": False},
                "ruleC": nd.get("ruleC") or {"theoretical": False},
                "resolvedCandidateId": resolved,
                "resolvedCorrectAgainstGroundTruth": is_correct(str(resolved), scan) if resolved else None,
                "dataAvailability": (
                    "complete-multicrop"
                    if reads
                    else "legacy-schema2-multicrop-unavailable"
                ),
            }
        )
    return result


def audit_exact_tokens(scans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for scan in scans:
        gt = str(scan.get("groundTruthCardId") or "")
        for read in scan.get("nameDiagnostics", {}).get("reads", []):
            for match in read.get("candidateMatches", []):
                if not (match.get("exactTokenSequence") and match.get("uniqueCandidateOwner")):
                    continue
                suffix_expected = str(match.get("suffixExpected") or "")
                suffix_ok = match.get("suffixAgreement") is not False
                if match.get("exactFullName") and suffix_ok:
                    classification = "1. nome completo + suffisso corretti"
                elif suffix_expected and not suffix_ok:
                    classification = "4. suffisso mancante o discordante"
                elif match.get("baseNameOnly"):
                    classification = "3. solo base name"
                elif match.get("extraTokens"):
                    classification = "2. nome completo corretto con rumore esterno"
                else:
                    classification = "5. match non sicuro"
                rows.append(
                    {
                        "scanId": scan.get("id"),
                        "groundTruthCardId": gt,
                        "groundTruthName": scan.get("groundTruthName") or "",
                        "readId": read.get("id"),
                        "crop": read.get("crop"),
                        "preprocessing": read.get("preprocessing"),
                        "raw": read.get("raw") or "",
                        "normalized": read.get("normalized") or "",
                        "candidateId": match.get("candidateId"),
                        "candidateName": match.get("candidateName"),
                        "extraTokens": match.get("extraTokens") or [],
                        "suffixExpected": suffix_expected,
                        "suffixObserved": match.get("suffixObserved") or "",
                        "suffixAgreement": match.get("suffixAgreement"),
                        "uniqueCandidateOwner": bool(match.get("uniqueCandidateOwner")),
                        "correct": (str(match.get("candidateId")) == gt) if gt else None,
                        "classification": classification,
                    }
                )
    return rows


def audit_rule_b(scans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for scan in scans:
        rule = scan.get("nameDiagnostics", {}).get("ruleB", {})
        if not rule.get("resolved"):
            continue
        cid = str(rule.get("candidateId") or "")
        supporters = []
        for read in scan.get("nameDiagnostics", {}).get("reads", []):
            for match in read.get("candidateMatches", []):
                if str(match.get("candidateId") or "") == cid and cid in strong_support(read):
                    supporters.append(
                        {
                            "readId": read.get("id"),
                            "crop": read.get("crop"),
                            "coordinates": read.get("coordinates"),
                            "preprocessing": read.get("preprocessing"),
                            "raw": read.get("raw") or "",
                            "suffixExpected": match.get("suffixExpected") or "",
                            "suffixAgreement": match.get("suffixAgreement"),
                        }
                    )
                    break
        independent_pairs = [
            [a["readId"], b["readId"]]
            for a, b in itertools.combinations(supporters, 2)
            if a.get("crop") != b.get("crop") or a.get("coordinates") != b.get("coordinates")
        ]
        correct = is_correct(cid, scan)
        if correct is False:
            classification = "ERRATO"
        elif independent_pairs:
            classification = "SAFE"
        else:
            classification = "NON SUFFICIENTEMENTE INDIPENDENTE"
        rows.append(
            {
                "scanId": scan.get("id"),
                "candidateId": cid,
                "candidateName": rule.get("candidateName") or "",
                "groundTruthCardId": scan.get("groundTruthCardId") or "",
                "groundTruthName": scan.get("groundTruthName") or "",
                "correct": correct,
                "supportingReads": supporters,
                "independentSupportingPairs": independent_pairs,
                "sameCropOnly": not bool(independent_pairs),
                "classification": classification,
            }
        )
    return rows


def audit_suffix_failures(scans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    rows = []
    for scan in scans:
        all_reads = scan.get("nameDiagnostics", {}).get("reads", [])
        for read in all_reads:
            for match in read.get("candidateMatches", []):
                if not (
                    match.get("baseNameOnly")
                    and match.get("suffixExpected")
                    and match.get("suffixAgreement") is False
                    and match.get("uniqueCandidateOwner")
                ):
                    continue
                candidate_id = str(match.get("candidateId") or "")
                base = " ".join(match.get("matchedNameTokens") or [])
                same_base = []
                for other in all_reads[0].get("candidateMatches", []) if all_reads else []:
                    if str(other.get("candidateId") or "") == candidate_id:
                        continue
                    if base and " ".join(other.get("matchedNameTokens") or []) == base:
                        same_base.append(
                            {"candidateId": other.get("candidateId"), "candidateName": other.get("candidateName")}
                        )
                rows.append(
                    {
                        "scanId": scan.get("id"),
                        "groundTruthCardId": scan.get("groundTruthCardId") or "",
                        "groundTruthName": scan.get("groundTruthName") or "",
                        "candidateId": candidate_id,
                        "candidateFullName": match.get("candidateName"),
                        "baseName": base,
                        "suffixRequired": match.get("suffixExpected"),
                        "suffixObserved": match.get("suffixObserved") or "",
                        "readId": read.get("id"),
                        "crop": read.get("crop"),
                        "raw": read.get("raw") or "",
                        "otherCandidatesWithSameDetectedBase": same_base,
                        "correctAgainstGroundTruth": is_correct(candidate_id, scan),
                        "decision": "NON SUFFICIENTE: il suffisso fisico significativo non concorda.",
                    }
                )
    return rows


def crop_performance(scans: list[dict[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for rid in READ_IDS:
        reads: list[tuple[dict[str, Any], dict[str, Any]]] = []
        for scan in scans:
            read = read_map(scan).get(rid)
            if read is not None:
                reads.append((scan, read))
        timings = [float(read.get("timingMs")) for _, read in reads if read.get("timingMs") is not None]
        exact_full_correct = exact_token_correct = base_only = suffix_success = suffix_failure = 0
        owner_correct = owner_wrong = fp = 0
        for scan, read in reads:
            gt = str(scan.get("groundTruthCardId") or "")
            for match in read.get("candidateMatches", []):
                owner = bool(match.get("uniqueCandidateOwner"))
                correct = bool(gt and str(match.get("candidateId") or "") == gt)
                if owner and match.get("exactFullName") and correct:
                    exact_full_correct += 1
                if owner and match.get("exactTokenSequence") and correct:
                    exact_token_correct += 1
                if owner and match.get("baseNameOnly"):
                    base_only += 1
                if owner and match.get("suffixExpected"):
                    if match.get("suffixAgreement") is False:
                        suffix_failure += 1
                    elif correct:
                        suffix_success += 1
                if owner:
                    if correct:
                        owner_correct += 1
                    elif gt:
                        owner_wrong += 1
                        if match.get("exactTokenSequence") and match.get("suffixAgreement") is not False:
                            fp += 1
        result[rid] = {
            "scansAttempted": len(reads),
            "nonEmptyReads": sum(bool(str(read.get("raw") or "").strip()) for _, read in reads),
            "exactFullNameCorrect": exact_full_correct,
            "exactTokenSequenceCorrect": exact_token_correct,
            "baseNameOnly": base_only,
            "suffixSuccess": suffix_success,
            "suffixFailure": suffix_failure,
            "candidateUniqueOwnerCorrect": owner_correct,
            "candidateUniqueOwnerWrong": owner_wrong,
            "potentialFalsePositives": fp,
            "meanTimingMs": rounded(statistics.fmean(timings) if timings else None),
            "medianTimingMs": rounded(statistics.median(timings) if timings else None),
            "p95TimingMs": rounded(percentile_nearest(timings, 0.95)) if len(timings) >= 20 else None,
            "p95Availability": "insufficient-sample (<20)" if len(timings) < 20 else "available",
        }
    return result


def pair_performance(scans: list[dict[str, Any]]) -> list[dict[str, Any]]:
    output = []
    for left, right in itertools.combinations(READ_IDS, 2):
        attempted = supported = correct = wrong = suffix_safe = 0
        attempt_costs: list[float] = []
        recovered_costs: list[float] = []
        examples = []
        independent = not left.startswith("N1-") or not right.startswith("N1-")
        for scan in scans:
            reads = read_map(scan)
            if left not in reads or right not in reads:
                continue
            attempted += 1
            combined_cost = float(reads[left].get("timingMs") or 0) + float(reads[right].get("timingMs") or 0)
            attempt_costs.append(combined_cost)
            common = strong_support(reads[left]) & strong_support(reads[right])
            if len(common) != 1:
                continue
            cid = next(iter(common))
            supported += 1
            check = is_correct(cid, scan)
            if check is True:
                correct += 1
            elif check is False:
                wrong += 1
            suffix_safe += 1
            recovered_costs.append(combined_cost)
            examples.append({"scanId": scan.get("id"), "candidateId": cid, "correct": check})
        output.append(
            {
                "pair": [left, right],
                "independentCrops": independent,
                "scansWithBothReads": attempted,
                "sameCandidateSupported": supported,
                "correct": correct,
                "wrong": wrong,
                "suffixSafe": suffix_safe,
                "casesRecovered": correct,
                "falsePositives": wrong,
                "meanCombinedOcrMs": rounded(statistics.fmean(attempt_costs) if attempt_costs else None),
                "medianCombinedOcrMs": rounded(statistics.median(attempt_costs) if attempt_costs else None),
                "meanRecoveredCaseOcrMs": rounded(statistics.fmean(recovered_costs) if recovered_costs else None),
                "examples": examples,
            }
        )
    return sorted(output, key=lambda x: (-x["correct"], x["wrong"], x["meanCombinedOcrMs"] or 10**9))


def n4_audit(scans: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = useful = potential_wrong = nonempty = 0
    times = []
    for scan in scans:
        reads = read_map(scan)
        if "N4-G" not in reads:
            continue
        attempts += 1
        read = reads["N4-G"]
        nonempty += bool(str(read.get("raw") or "").strip())
        if read.get("timingMs") is not None:
            times.append(float(read["timingMs"]))
        gt = str(scan.get("groundTruthCardId") or "")
        n4 = strong_support(read)
        earlier = set().union(*(strong_support(reads[x]) for x in READ_IDS[:-1] if x in reads))
        if gt and gt in n4 and gt not in earlier:
            useful += 1
        if gt and any(cid != gt for cid in n4):
            potential_wrong += 1
    return {
        "attempts": attempts,
        "nonEmpty": nonempty,
        "incrementalCorrectIdentifications": useful,
        "potentialFalsePositives": potential_wrong,
        "meanTimingMs": rounded(statistics.fmean(times) if times else None),
        "recommendation": (
            "Eliminabile dal prossimo test: nessun recupero corretto incrementale osservato."
            if useful == 0
            else "Mantenere: produce recuperi corretti non disponibili in N1/N2/N3."
        ),
    }


def category_audit(scans: list[dict[str, Any]]) -> dict[str, Any]:
    attempts = []
    for scan in scans:
        diag = scan.get("classificationDiagnostics", {})
        reads = diag.get("reads", [])
        if scan.get("source") != "photo" or diag.get("legacy") is True:
            continue
        attempts.append(
            {
                "scanId": scan.get("id"),
                "printedIdentity": scan.get("printedIdentity"),
                "groundTruthCardId": scan.get("groundTruthCardId") or "",
                "groundTruthName": scan.get("groundTruthName") or "",
                "categoryRaw": diag.get("categoryRaw") or "",
                "categoryDetected": diag.get("categoryDetected") or "",
                "categoryConfidence": diag.get("categoryConfidence"),
                "subtypeRaw": diag.get("subtypeRaw") or "",
                "subtypeDetected": diag.get("subtypeDetected") or "",
                "energyRaw": diag.get("energyRaw") or "",
                "energyDetected": diag.get("energyDetected") or "",
                "reads": [
                    {
                        "id": r.get("id"),
                        "preprocessing": r.get("preprocessing"),
                        "raw": r.get("raw") or "",
                        "category": r.get("category") or "",
                        "subtype": r.get("subtype") or "",
                        "energyType": r.get("energyType") or "",
                        "timingMs": r.get("timingMs"),
                    }
                    for r in reads
                ],
                "ocrAttempted": bool(reads),
                "notAttemptedReason": "collector identity not verified" if not reads else "",
                "effectOnCandidates": {
                    "categoryApplied": bool(scan.get("categoryApplied")),
                    "before": n(scan.get("candidateCountInitial")),
                    "afterCategory": n(scan.get("candidateCountAfterCategory")),
                    "subtypeApplied": bool(scan.get("subtypeApplied")),
                    "energyTypeApplied": bool(scan.get("energyTypeApplied")),
                    "afterSubtypeOrType": n(scan.get("candidateCountAfterSubtypeType")),
                },
                "correctness": "not-verifiable: export has no explicit category ground truth",
            }
        )
    return {
        "attempts": len(attempts),
        "ocrExecuted": sum(x["ocrAttempted"] for x in attempts),
        "skippedAfterCollectorFailure": sum(not x["ocrAttempted"] for x in attempts),
        "detected": sum(bool(x["categoryDetected"]) for x in attempts),
        "byDetectedCategory": dict(Counter(x["categoryDetected"] or "not-detected" for x in attempts)),
        "trainerSubtypeAttempts": sum(x["categoryDetected"] == "trainer" for x in attempts),
        "trainerSubtypeDetected": sum(bool(x["subtypeDetected"]) for x in attempts),
        "energyTypeAttempts": sum(x["categoryDetected"] == "energy" for x in attempts),
        "energyTypeDetected": sum(bool(x["energyDetected"]) for x in attempts),
        "validationNote": (
            "La singola rilevazione Energy 1/1 non è una validazione statistica. "
            "L'export non contiene una ground truth categoria separata, quindi precisione categoria non calcolata."
        ),
        "records": attempts,
    }


def collector_failure_mode(scan: dict[str, Any]) -> str:
    diag = scan.get("collectorDiagnostics", {})
    if diag.get("legacy"):
        return "legacy-schema2-raw-unavailable"
    reads = diag.get("rawReads", [])
    if not reads or all(not str(r.get("raw") or "").strip() for r in reads):
        return "OCR vuoto/spazzatura"
    parsed = [r.get("parsed") for r in reads if r.get("parsed")]
    slash = any(r.get("slashDetected") for r in reads)
    denominator = any(r.get("denominatorDetected") for r in reads)
    number_total = [p for p in parsed if p.get("kind") == "numberTotal"]
    standalone = [p for p in parsed if p.get("kind") == "standaloneLocalId"]
    if number_total:
        values = Counter((p.get("num"), p.get("total")) for p in number_total)
        if max(values.values()) < 2:
            return "numero plausibile discordante / nessun consenso verificabile"
        return "numero plausibile ma nessun set verificabile"
    if standalone:
        values = Counter(p.get("localId") for p in standalone)
        if max(values.values()) < 2:
            return "localId alfanumerico spurio / nessun doppio voto"
        return "localId plausibile ma nessun set verificabile"
    if slash and not denominator:
        return "slash letto, denominatore non letto"
    if not slash:
        return "slash non letto / OCR spazzatura"
    return "numeratore non ricostruibile"


def collector_audit(scans: list[dict[str, Any]]) -> dict[str, Any]:
    failures = [
        s
        for s in scans
        if s.get("source") == "photo" and n(s.get("candidateCountInitial")) == 0
    ]
    rows = []
    for scan in failures:
        diag = scan.get("collectorDiagnostics", {})
        mode = collector_failure_mode(scan)
        rows.append(
            {
                "scanId": scan.get("id"),
                "schemaData": 2 if diag.get("legacy") else 3,
                "printedIdentity": scan.get("printedIdentity"),
                "groundTruthCardId": scan.get("groundTruthCardId") or "",
                "groundTruthName": scan.get("groundTruthName") or "",
                "slashDetected": diag.get("slashDetected"),
                "denominatorDetected": diag.get("denominatorDetected"),
                "rawReads": diag.get("rawReads") or [],
                "parsedReads": diag.get("parsedReads") or [],
                "rejectionReasons": diag.get("rejectionReasons") or [],
                "failureMode": mode,
                "safelyRecoverableByNormalization": False,
                "safetyReason": (
                    "Nessuna identità coerente dispone di almeno due letture concordanti; "
                    "normalizzare ulteriormente creerebbe rischio di falso positivo."
                    if not diag.get("legacy")
                    else "Raw OCR non disponibile nel record migrato."
                ),
            }
        )
    modes = Counter(x["failureMode"] for x in rows)
    return {
        "count": len(rows),
        "legacyWithoutRaw": sum(x["schemaData"] == 2 for x in rows),
        "schema3WithRaw": sum(x["schemaData"] == 3 for x in rows),
        "failureModes": dict(modes),
        "safelyRecoverableByNormalization": 0,
        "records": rows,
    }


def verify_expected(stats: dict[str, Any], derived: dict[str, Any]) -> dict[str, Any]:
    expected = {
        "scansTotal": 51,
        "photoScans": 38,
        "groundTruthCompleted": 34,
        "collectorVerified": 24,
        "collectorFailure": 14,
        "ambiguousPhotoScans": 20,
        "exactTokenSequenceMatches": 10,
        "ruleBResolved": 2,
        "ruleAResolved": 0,
        "suffixFailures": 7,
        "baseNameOnlyCases": 7,
        "categoryAttempts": 13,
        "categoryDetected": 2,
        "energyTypeDetected": 1,
        "automaticWrong": 1,
    }
    checks = {key: {"expected": value, "actual": stats.get(key), "match": stats.get(key) == value} for key, value in expected.items()}
    checks["derivedAmbiguousRows"] = {
        "expected": stats.get("ambiguousPhotoScans"),
        "actual": len(derived["ambiguousPhotoAudit"]),
        "match": len(derived["ambiguousPhotoAudit"]) == stats.get("ambiguousPhotoScans"),
    }
    checks["derivedExactTokenRows"] = {
        "expected": stats.get("exactTokenSequenceMatches"),
        "actual": len(derived["exactTokenSequenceAudit"]),
        "match": len(derived["exactTokenSequenceAudit"]) == stats.get("exactTokenSequenceMatches"),
    }
    checks["derivedRuleBRows"] = {
        "expected": stats.get("ruleBResolved"),
        "actual": len(derived["ruleBAudit"]),
        "match": len(derived["ruleBAudit"]) == stats.get("ruleBResolved"),
    }
    checks["derivedSuffixRows"] = {
        "expected": stats.get("suffixFailures"),
        "actual": len(derived["suffixFailureAudit"]),
        "match": len(derived["suffixFailureAudit"]) == stats.get("suffixFailures"),
    }
    return {"allMatched": all(x["match"] for x in checks.values()), "checks": checks}


def build_report(
    data: dict[str, Any],
    source_path: Path,
    verified_main_sha: str = "",
    diagnostic_base_sha: str = "",
) -> dict[str, Any]:
    scans = data.get("scans", [])
    stats = data.get("statistics", {})
    derived: dict[str, Any] = {
        "ambiguousPhotoAudit": audit_ambiguous(scans),
        "exactTokenSequenceAudit": audit_exact_tokens(scans),
        "ruleBAudit": audit_rule_b(scans),
        "suffixFailureAudit": audit_suffix_failures(scans),
    }
    crops = crop_performance(scans)
    pairs = pair_performance(scans)
    safe_independent = [x for x in pairs if x["independentCrops"] and x["correct"] > 0 and x["wrong"] == 0]
    best_pair = safe_independent[0] if safe_independent else None
    n4 = n4_audit(scans)
    wrong = audit_wrong(scans)
    categories = category_audit(scans)
    collectors = collector_audit(scans)
    rule_b_safe = sum(x["classification"] == "SAFE" for x in derived["ruleBAudit"])
    rule_b_wrong = sum(x["classification"] == "ERRATO" for x in derived["ruleBAudit"])
    final_assessment = (
        "CONFIGURAZIONE OCR CANDIDATA PER TERZO TEST FOTO REALI"
        if wrong["count"] == 1
        and best_pair is not None
        and rule_b_wrong == 0
        and all(x["potentialFalsePositives"] == 0 for x in crops.values())
        else "DATI INSUFFICIENTI — SERVE ALTRO DIAGNOSTICO"
    )
    report = {
        "auditContext": {
            "verifiedMainSha": verified_main_sha or data.get("metadata", {}).get("mainSha"),
            "diagnosticBaseSha": diagnostic_base_sha or None,
            "mode": "read-only export audit",
        },
        "source": {
            "fileName": source_path.name,
            "exportMetadata": data.get("metadata", {}),
            "sourceCounts": source_counts(scans),
            "reportedStatistics": stats,
            "sourceFileCommitted": False,
        },
        "automaticWrongAudit": wrong,
        "ambiguousPhotoAudit": derived["ambiguousPhotoAudit"],
        "exactTokenSequenceAudit": {
            "count": len(derived["exactTokenSequenceAudit"]),
            "records": derived["exactTokenSequenceAudit"],
            "classificationCounts": dict(Counter(x["classification"] for x in derived["exactTokenSequenceAudit"])),
        },
        "ruleBAudit": {
            "count": len(derived["ruleBAudit"]),
            "safe": rule_b_safe,
            "notSufficientlyIndependent": sum(x["classification"] == "NON SUFFICIENTEMENTE INDIPENDENTE" for x in derived["ruleBAudit"]),
            "wrong": rule_b_wrong,
            "records": derived["ruleBAudit"],
        },
        "suffixFailureAudit": {
        "count": len(derived["suffixFailureAudit"]),
            "distinctScans": len({x["scanId"] for x in derived["suffixFailureAudit"]}),
            "records": derived["suffixFailureAudit"],
            "rule": "Il base name non è sufficiente se un suffisso fisico significativo distingue l'identità.",
        },
        "cropPerformance": crops,
        "pairPerformance": pairs,
        "n4Audit": n4,
        "categoryAudit": categories,
        "collectorFailureAudit": collectors,
        "recommendedNextConfiguration": {
            "cropsToKeep": list(best_pair["pair"]) if best_pair else [],
            "cropsPotentiallyRemove": ["N4-G"] if n4["incrementalCorrectIdentifications"] == 0 else [],
            "preprocessing": {
                rid: next((read_map(s)[rid].get("preprocessing") for s in scans if rid in read_map(s)), None)
                for rid in (best_pair["pair"] if best_pair else [])
            },
            "candidatePair": best_pair,
            "suffixRule": "Richiedere suffisso significativo esatto; base name solo non può selezionare.",
            "categoryNextTest": "Sì, solo diagnostica: 2/13 rilevazioni e nessuna ground truth categoria esplicita non bastano per filtrare.",
            "recommendedNewPhotos": 30,
            "reason": (
                "La coppia proposta usa crop distinti, recupera almeno un caso reale con ground truth e non mostra falsi positivi. "
                "Il campione multi-crop resta piccolo: serve un terzo test, non una modifica di produzione."
                if best_pair
                else "Nessuna coppia cross-crop ha recuperi reali a zero falsi positivi."
            ),
        },
        "safety": {
            "fuzzyMatchingIntroduced": False,
            "productionLogicModified": False,
            "diagnosticPageModified": False,
            "sourceExportCommitted": False,
            "retailModified": False,
            "cardmarketModified": False,
            "collectionDataModified": False,
            "mainModified": False,
            "potentialFalsePositivesInRecommendedPair": best_pair["wrong"] if best_pair else None,
            "scopeLimit": "Audit dei dati esportati; nessuna immagine disponibile o analizzata.",
        },
        "finalAssessment": final_assessment,
    }
    report["sourceVerification"] = verify_expected(stats, derived)
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, default=Path("artifacts/candidate_disambiguation_schema3_audit.json"))
    parser.add_argument("--verified-main-sha", default="")
    parser.add_argument("--diagnostic-base-sha", default="")
    args = parser.parse_args()
    data = json.loads(args.source.read_text(encoding="utf-8"))
    if data.get("metadata", {}).get("schema") != 3:
        raise SystemExit("Expected schema 3 export")
    report = build_report(data, args.source, args.verified_main_sha, args.diagnostic_base_sha)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if not report["sourceVerification"]["allMatched"]:
        raise SystemExit("Export totals do not match the requested/source statistics")
    print(json.dumps({
        "output": str(args.output),
        "mainSha": report["source"]["exportMetadata"].get("mainSha"),
        "photos": report["source"]["sourceCounts"]["photoScans"],
        "schema3MultiCrop": report["source"]["sourceCounts"]["schema3PhotosWithNameMultiCrop"],
        "automaticWrong": report["automaticWrongAudit"]["count"],
        "bestPair": report["recommendedNextConfiguration"]["cropsToKeep"],
        "finalAssessment": report["finalAssessment"],
    }, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
