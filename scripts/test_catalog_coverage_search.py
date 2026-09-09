#!/usr/bin/env python3
"""Deterministic guards for the catalog/search audit changes."""

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
REPORT = ROOT / "artifacts" / "catalog_coverage_search_audit_report.json"


def function_body(source, name):
    start = source.index(f"function {name}")
    brace = source.index("{", start)
    depth = 0
    for index in range(brace, len(source)):
        if source[index] == "{":
            depth += 1
        elif source[index] == "}":
            depth -= 1
            if depth == 0:
                return source[start:index + 1]
    raise AssertionError(f"Unclosed function: {name}")


def canonical_manual_key(value):
    raw = re.sub(r"[^A-Z0-9]", "", str(value or "").upper())
    match = re.fullmatch(r"([A-Z]{0,5})(\d{1,3})([A-Z]{0,2})", raw)
    if not match:
        return raw
    return f"{match.group(1)}{int(match.group(2))}{match.group(3)}"


def main():
    source = INDEX.read_text(encoding="utf-8")
    report = json.loads(REPORT.read_text(encoding="utf-8"))
    manual = source[source.index("function normalizeManualExactName"):source.index("async function searchCards")]
    resolver = source[source.index("async function fetchCardFromExactSet"):source.index("function observedSpecialTotal")]

    assert "PRINTED_CODE_HINTS" not in source
    assert "fetchHintedPrintedCard" not in source
    assert "replace(/\\D/g,'')" not in function_body(source, "runManualCollectorSearch").split("const total=", 1)[0]
    assert "canonicalPrintedLocalId(numberInput.value||'')" in function_body(source, "runManualCollectorSearch")
    assert "queryManualCardsByNumberAndName(num,requestedName)" in source
    assert "queryManualCardsByExactLocalId(number,nameIds)" in source
    assert "manualExactNameMatches(cards,name)" in source
    assert "Il solo numero è troppo ambiguo" in source
    assert "startManualCandidatePagination" in manual and "pageSize:6" in source
    assert "similarity(" not in manual
    assert "candidateContainedInOCR" not in manual
    assert "levenshtein" not in manual.lower()
    assert "fetchHintedPrintedCard" not in resolver

    assert canonical_manual_key("029") == "29"
    assert canonical_manual_key("075") == "75"
    assert canonical_manual_key("TG01") == "TG1"
    assert canonical_manual_key("GG01") == "GG1"
    assert canonical_manual_key("SVP001") == "SVP1"
    assert canonical_manual_key("SWSH001") == "SWSH1"
    assert canonical_manual_key("88a") == "88A"
    assert canonical_manual_key("TG01") != canonical_manual_key("01")
    assert canonical_manual_key("GG01") != canonical_manual_key("01")
    assert canonical_manual_key("SVP001") != canonical_manual_key("001")
    assert canonical_manual_key("88a") != canonical_manual_key("88")

    controlled = list(range(14))
    shown = 0
    pages = []
    while shown < len(controlled):
        shown = min(len(controlled), shown + 6)
        pages.append(controlled[:shown])
    assert [len(page) for page in pages] == [6, 12, 14]
    assert len(pages[-1]) == len(set(pages[-1])) == 14
    assert pages[-1] == controlled

    exact_group = [
        {"id": "a", "name": "Genesect"},
        {"id": "b", "name": "Genesect-ex"},
        {"id": "c", "name": "Genesect-ex"},
    ]
    assert [card["id"] for card in exact_group if card["name"].lower() == "genesect"] == ["a"]
    assert len([card for card in exact_group if card["name"].lower() == "genesect-ex"]) == 2
    assert not [card for card in exact_group if card["name"].lower() == "genesect v"]

    assert report["baseline"] == {
        "physicalEligible": 21536,
        "recognizedUnique": 9468,
        "recognizedAmbiguous": 11249,
        "notRecognized": 819,
        "coveragePercent": 96.2,
        "regressions": 0,
    }
    assert report["proposedAfter"]["notRecognized"] == 817
    assert report["proposedAfter"]["ambiguousRecovered"] == 2
    assert report["proposedAfter"]["regressions"] == 0
    assert report["proposedAfter"]["falsePositives"] == 0
    assert report["implementedAfter"]["active"] is True
    assert report["implementedAfter"]["notRecognized"] == 817
    assert report["ambiguousAudit"]["resolvableWithExactNormalizedName"] == 11152
    assert report["ambiguousAudit"]["stillAmbiguousWithExactName"] == 97
    assert report["manualSearchAudit"]["numberOnly"]["implemented"] is False
    assert report["variantAudit"]["changes"] == 0
    assert report["setAliasAudit"]["newAliasesAdded"] == 0

    print(json.dumps({
        "status": "ok",
        "tests": 38,
        "baseline": report["baseline"],
        "after": report["implementedAfter"],
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
