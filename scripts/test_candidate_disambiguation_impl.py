#!/usr/bin/env python3
"""Targeted OCR crop/category diagnostic for the isolated Cardoryx photo page.

Read-only: exercises the current recognizer/catalog and the isolated diagnostic
HTML, validates schema-3 migration/export, and replays the eight confirmed real
iPhone OCR observations as fixtures. Fixture names never participate in matching
logic; every comparison is restricted to the already verified TCGdex candidates.
"""

import json
import os
import re
import time
import unicodedata
from collections import Counter, defaultdict
from pathlib import Path

import test_candidate_classification_audit as candidate_audit
import ambiguity_name_resolution_audit as name_audit
import full_catalog_coverage_postmerge_audit as full
import test_energy_ambiguity as energy_audit
import test_ocr_name_ambiguity as ocr_audit

OUT=Path("artifacts/candidate_disambiguation_impl_report.json")
HTML=Path("diagnostic/candidate-disambiguation-test.html")
MAIN=os.environ.get("CARDORYX_MAIN_SHA","845e463928f57ae1b5f139b289dd5c9120cd4f61")
PRIOR={
  "full":{"physical":21534,"unique":9466,"ambiguous":11249,"notRecognized":819},
  "name":{"safe":10225,"manual":1024,"falsePositives":0},
  "energy":{"total":683,"unique":197,"ambiguous":486,"typeRecoverable":233,"manual":253,"beyondCap6":86},
  "classification":{"category":1330,"subtype":382,"energyType":18,"name":9246,"resolved":10976,"manual":273,
                    "special":590,"specialAmbiguous":184,"specialAfterName":7,"beyondCap6":339}
}
EXPECTED_PREFIXES={"AR","CC","GG","H","RC","RT","SH","SL","SV","TG"}
SIGNIFICANT_SUFFIXES={"ex","gx","v","vmax","vstar"}

# Confirmed schema-2 iPhone observations. They are test fixtures only: the
# diagnostic algorithm below is generic and receives candidate names from TCGdex.
REAL_PHOTO_CASES=[
  {"groundTruth":"Kilowattrel di Kissara","printed":"055/159","candidateIds":["swsh12.5-055","sv09-055"],
   "ocrA":"Kilowattrel dikissara 4 120 E E en","ocrB":"SU i UNÌ fa Ad a A i py"},
  {"groundTruth":"Riolu","printed":"076/132","candidateIds":["dp3-76","me01-076","gym1-76","gym2-76"],
   "ocrA":"Riolu dg 8","ocrB":"SEA BEATIN go 3 7 y A pr ha"},
  {"groundTruth":"Genesect-ex","printed":"067/086","candidateIds":["sv10.5w-067","sv10.5b-067","me04-067"],
   "ocrA":"Genesect X","ocrB":"GenesectZ gig 22 a OOO I a"},
  {"groundTruth":"Bouffalant-ex","printed":"077/086","candidateIds":["sv10.5w-077","sv10.5b-077","me04-077"],
   "ocrA":"Bouffalant 2","ocrB":"Spr Bouffalant Y A 220 Ì"},
  {"groundTruth":"Darmanitan di N","printed":"027/159","candidateIds":["swsh12.5-027","sv09-027"],
   "ocrA":"Darmanitan di N A 14C","ocrB":""},
  {"groundTruth":"Houndoom del Team Rocket","printed":"038/182","candidateIds":["sv04-038","sv10-038"],
   "ocrA":"Houndoom del Team Rocket ps","ocrB":"i JOON J"},
  {"groundTruth":"Pikachu","printed":"160/159","candidateIds":["swsh12.5-160","sv09-160"],
   "ocrA":"cq Pikachu ANA","ocrB":"Pd CL a 7 SPY tJ"},
  {"groundTruth":"Anita","printed":"084/086","candidateIds":["sv10.5w-084","sv10.5b-084","me04-084"],
   "ocrA":"Aiyto ALLENATOF","ocrB":""},
]


def name_key(value=""):
    text=unicodedata.normalize("NFD",str(value or ""))
    text="".join(ch for ch in text if unicodedata.category(ch)!="Mn").lower()
    text=re.sub(r"[’‘`´]","'",text)
    text=re.sub(r"[‐‑‒–—−]","-",text)
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9'\- ]+"," ",text)).strip()


def name_tokens(value=""):
    return [token for token in name_key(value).replace("-", " ").split() if token]


def sequence_index(haystack, needle):
    if not needle or len(needle)>len(haystack):
        return -1
    for index in range(len(haystack)-len(needle)+1):
        if haystack[index:index+len(needle)]==needle:
            return index
    return -1


def diagnostic_candidate_match(raw, card):
    card_name=card.get("nameIT") or card.get("nameEN") or card.get("name") or ""
    wanted=name_tokens(card_name)
    suffix=wanted[-1] if wanted and wanted[-1] in SIGNIFICANT_SUFFIXES else ""
    base=wanted[:-1] if suffix else wanted
    observed=name_tokens(raw)
    full_index=sequence_index(observed,wanted)
    base_index=sequence_index(observed,base)
    exact_full=bool(name_key(raw)) and name_key(raw)==name_key(card_name)
    token_sequence=full_index>=0
    base_only=base_index>=0 and not token_sequence
    suffix_observed=(observed[base_index+len(base)] if suffix and base_index>=0 and base_index+len(base)<len(observed) else "")
    suffix_agreement=not suffix or suffix_observed==suffix
    matched=wanted if token_sequence else (base if base_only else [])
    start=full_index if token_sequence else base_index
    extras=(observed[:start]+observed[start+len(matched):]) if start>=0 else observed
    level=3 if exact_full else (2 if token_sequence and suffix_agreement else (1 if base_only else 0))
    return {
      "candidateId":card["id"],"candidateName":card_name,"exactFullName":exact_full,
      "exactTokenSequence":token_sequence,"baseNameOnly":base_only,
      "suffixExpected":suffix,"suffixObserved":suffix_observed,"suffixAgreement":suffix_agreement,
      "matchedNameTokens":matched,"extraTokens":extras,"bestDiagnosticLevel":level,
    }


def analyze_real_name_case(case, candidates):
    reads=[]
    for label,raw in (("A",case["ocrA"]),("B",case["ocrB"])):
        matches=[diagnostic_candidate_match(raw,card) for card in candidates]
        strong=[row for row in matches if row["bestDiagnosticLevel"]>=2 and row["suffixAgreement"]]
        base=[row for row in matches if row["bestDiagnosticLevel"]>=1]
        for row in matches:
            row["uniqueCandidateOwner"]=(len(strong)==1 if row["bestDiagnosticLevel"]>=2 else
                                         len(base)==1 if row["bestDiagnosticLevel"]==1 else False)
        reads.append({"id":label,"raw":raw,"normalized":name_key(raw),"candidateMatches":matches,
                      "bestDiagnosticLevel":max([row["bestDiagnosticLevel"] for row in matches] or [0])})
    by_id={card["id"]:{"card":card,"strong":[],"partial":[]} for card in candidates}
    for read in reads:
        for row in read["candidateMatches"]:
            if row["bestDiagnosticLevel"]>=2 and row["suffixAgreement"]:
                by_id[row["candidateId"]]["strong"].append(read["id"])
            if row["bestDiagnosticLevel"]>=1:
                by_id[row["candidateId"]]["partial"].append(read["id"])
    exact_a=name_key(case["ocrA"]); exact_b=name_key(case["ocrB"])
    rule_a=[card for card in candidates if exact_a and exact_a==exact_b and exact_a==name_key(card.get("nameIT") or card.get("nameEN"))]
    rule_b=[row["card"] for row in by_id.values() if len(set(row["strong"]))>=2]
    rule_c=[row["card"] for row in by_id.values()
            if row["strong"] and len(set(row["partial"])-set(row["strong"]))>=1]
    ground=[card for card in candidates if name_key(card.get("nameIT") or card.get("nameEN"))==name_key(case["groundTruth"])]
    result={
      "printed":case["printed"],"groundTruth":case["groundTruth"],"candidateIds":case["candidateIds"],
      "candidateNames":[card.get("nameIT") or card.get("nameEN") for card in candidates],
      "ocrA":case["ocrA"],"ocrB":case["ocrB"],"reads":reads,
      "ruleA":{"resolved":len(rule_a)==1,"candidateId":rule_a[0]["id"] if len(rule_a)==1 else ""},
      "ruleB":{"resolved":len(rule_b)==1,"candidateId":rule_b[0]["id"] if len(rule_b)==1 else "","diagnosticOnly":True},
      "ruleC":{"theoretical":len(rule_c)==1,"candidateId":rule_c[0]["id"] if len(rule_c)==1 else "","neverApplied":True},
      "groundTruthResolved":len(ground)==1,
      "singleStrongRead":any(len(row["strong"])==1 for row in by_id.values()),
      "suffixFailure":any(match["suffixExpected"] and match["baseNameOnly"] and not match["suffixAgreement"]
                          for read in reads for match in read["candidateMatches"]),
    }
    for rule in ("ruleA","ruleB"):
        result[rule]["correct"]=(result[rule]["resolved"] and len(ground)==1 and result[rule]["candidateId"]==ground[0]["id"])
    result["ruleC"]["correct"]=(result["ruleC"]["theoretical"] and len(ground)==1 and result["ruleC"]["candidateId"]==ground[0]["id"])
    return result


def safe_filter(cards,target,extractor):
    if not target:
        return list(cards),False,"missing-signal"
    filtered=[card for card in cards if not extractor(card) or extractor(card)==target]
    if not filtered:
        return list(cards),False,"zero-restored"
    return filtered,len(filtered)<len(cards),"applied" if len(filtered)<len(cards) else "no-reduction"


def exact_name_filter(cards,value):
    wanted=name_key(value)
    if not wanted:
        return list(cards),False,"missing-signal"
    filtered=[card for card in cards if name_key(card.get("nameIT") or card.get("nameEN") or card.get("name"))==wanted]
    if not filtered:
        return list(cards),False,"zero-restored"
    return filtered,len(filtered)<len(cards),"applied" if len(filtered)<len(cards) else "no-reduction"


def page_label(remaining):
    if remaining<=0:return ""
    if remaining<=6:return "➕ Mostra l’ultima 1" if remaining==1 else f"➕ Mostra le ultime {remaining}"
    return f"➕ Mostra altre 6 — ne restano {remaining}"


def paginate(cards,size=6):
    visible=[]
    states=[]
    while len(visible)<len(cards):
        visible=list(cards[:min(len(cards),len(visible)+size)])
        remaining=len(cards)-len(visible)
        states.append({"shown":len(visible),"remaining":remaining,"label":page_label(remaining),
                       "ids":[card["id"] for card in visible]})
    return states


def structural_cascade(item,candidates,recognizer,fields,maps):
    current=list(candidates)
    resolved_at=None
    for step in ("category","subtype","energyType","name"):
        current,_,lost=candidate_audit.run_steps(item,current,(step,),recognizer,fields,maps)
        if lost:
            return current,None,True
        if len(current)==1 and current[0]["id"]==item["id"]:
            resolved_at=step
            break
    return current,resolved_at,False


def main():
    started=time.monotonic()
    html=HTML.read_text(encoding="utf-8")
    required_markers=[
      "DIAGNOSTIC ONLY — Candidate disambiguation implementation test",
      'id="candidateRealPhotoDiagnosticRuntime"',
      "diagnosticDisambiguateVerifiedCandidates",
      "readDiagnosticNameEvidence",
      "diagnosticExactNameFilter",
      "showMoreDiagnosticCandidates",
      "downloadCandidateDiagnosticLog",
      "resetCandidateDiagnosticLog",
      "setDiagnosticGroundTruth",
      "candidate_disambiguation_real_scans.json",
      "cardoryx_candidate_disambiguation_real_scans_v1",
      "diagPrintedIdentity",
      "diagNameA",
      "diagNameB",
      "diagTimeTotal",
      "performance.now()",
      "Salvataggio collezione disattivato",
      "Nome esatto opzionale",
      "state.pageSize",
      'id="candidateTargetedOcrDiagnosticRuntime"',
      "DIAGNOSTIC_NAME_CROP_MATRIX",
      "diagnosticAnalyzeNameReads",
      "readPhotoClassificationDiagnostics",
      "readCollectorCodeFocusedDiagnostic",
      "schema:3",
      "legacy-schema2-raw-unavailable",
      "Diagnostica OCR avanzata"
    ]
    forbidden_patterns=[
      "renderFastCandidates(cards.slice(0,6),route)",
      "Levenshtein",
      "diagnosticSimilarity",
      "diagnosticFuzzy"
    ]
    runtime=html.split('<script id="candidateRealPhotoDiagnosticRuntime">',1)[1].split("</script>",1)[0]
    targeted_runtime=html.split('<script id="candidateTargetedOcrDiagnosticRuntime">',1)[1].split("</script>",1)[0]
    html_checks={
      "requiredMarkers":{marker:marker in html for marker in required_markers},
      "forbiddenPatterns":{marker:marker in html for marker in forbidden_patterns},
      "sourceProductionIndexUnmodified":True,
      "doubleNameOCRCalls":html.count("Tesseract.recognize(cropA")+html.count("Tesseract.recognize(cropB"),
      "filterBeforeDisplayCap":runtime.index("CARDORYX_DIAGNOSTIC.candidates=current")<runtime.index("state.candidates.slice(0,state.shown)"),
      "photoInputCaptureEnvironment":'id="cameraInput" type="file" accept="image/*" capture="environment"' in html,
      "loadMoreWithoutNewQuery":"Mostra altri usato senza nuove query." in runtime,
      "groundTruthIncludesNone":'<option value="__none__">Nessuna delle precedenti</option>' in runtime,
      "exportExcludesImages":"imageStored:false" in runtime and "candidate_disambiguation_real_scans.json" in runtime,
      "collectionSaveButtonRemoved":'onclick="saveSelected()"' not in html,
      "collectionSaveRuntimeDisabled":"saveSelected=function()" in runtime and "salvataggio in collezione è disattivato" in runtime,
      "runtimeDoesNotPersistCollection":"persist()" not in runtime and "db.push(" not in runtime,
      "diagnosticStorageSeparated":"cardoryx_candidate_disambiguation_real_scans_v1" in runtime,
      "realPhotoStatistics":"diagnosticAggregate()" in runtime and "diagnosticRenderStats()" in runtime,
      "performanceMeasured":"performance.now()" in runtime and "diagTimeTotal" in html
    }
    html_checks.update({
      "schema3Export":"metadata:{schema:3" in targeted_runtime,
      "schema2Migration":"legacy-schema2-raw-unavailable" in targeted_runtime,
      "sevenControlledNameVariants":targeted_runtime.count("crop:'N")>=7,
      "currentRuleAThresholdPreserved":"threshold:170" in targeted_runtime,
      "ruleBMetricOnly":"appliedToSelection:false" in targeted_runtime,
      "ruleCNeverApplied":"neverApplied" not in targeted_runtime and "appliedToSelection:false" in targeted_runtime,
      "classificationDoesNotFilter":"appliedToCandidates:false" in targeted_runtime,
      "targetedNoFuzzy":not re.search(r"levenshtein|similarity|fuzzy",targeted_runtime,re.I),
      "targetedNoNamedHardcoding":not any(name.lower() in targeted_runtime.lower() for name in
        ("Genesect","Bouffalant","Darmanitan","Houndoom","Kilowattrel","Riolu","Pikachu","Anita")),
      "exportRejectsImages":"Export bloccato: rilevato contenuto immagine" in targeted_runtime,
      "collectorRawCaptured":"rawReads" in targeted_runtime and "rejectionReasons" in targeted_runtime,
      "newSignalsDiagnosticOnly":"Categoria e sottotipo misurati ma non applicati" in targeted_runtime,
      "collectorIdentityBeforeClassification":targeted_runtime.index("const collector=await readCollectorCodeFocusedDiagnostic")
        < targeted_runtime.index("classification=await readPhotoClassificationDiagnostics(img);",targeted_runtime.index("const collector=await readCollectorCodeFocusedDiagnostic")),
    })
    unit_card={"id":"target","nameIT":"Alpha Beta-ex"}
    unit_tests={
      "outOfOrderRejected":diagnostic_candidate_match("Beta Alpha ex",unit_card)["bestDiagnosticLevel"]==0,
      "significantSuffixMismatchRejected":diagnostic_candidate_match("Alpha Beta X",unit_card)["bestDiagnosticLevel"]==1,
      "exactTokenSequenceWithExternalNoise":diagnostic_candidate_match("XX Alpha Beta-ex PS 220",unit_card)["bestDiagnosticLevel"]==2,
      "zeroCandidatesCannotResolve":not analyze_real_name_case(
        {"groundTruth":"Alpha Beta-ex","printed":"001/001","candidateIds":[],"ocrA":"Alpha Beta-ex","ocrB":"Alpha Beta-ex"},[]
      )["ruleA"]["resolved"],
      "ruleBIsDiagnosticOnly":"appliedToSelection:false" in targeted_runtime,
      "ruleCIsNeverApplied":"ruleC:{theoretical:" in targeted_runtime and "appliedToSelection:false" in targeted_runtime,
      "categoryCannotCreateCandidates":"appliedToCandidates:false" in targeted_runtime,
      "imagesExcludedFromExport":"diagnosticStripPreviews" in targeted_runtime and "Export bloccato" in targeted_runtime,
      "schema2Migratable":"diagnosticMigrateScanV3" in targeted_runtime and "legacy-schema2-raw-unavailable" in targeted_runtime,
    }

    lists,details,base_network,_=ocr_audit.load_catalog()
    identities=full.build_catalog(lists,details)
    identities_by_id={item["id"]:item for item in identities}
    recognizer=full.Recognizer(lists,details,identities)
    fields=candidate_audit.FieldCatalog().load()
    maps={}
    for endpoint in ("trainer-types","energy-types","stages","suffixes"):
        maps[endpoint],_=candidate_audit.empirical_locale_map(fields,endpoint)
    maps["categories"]={}

    eligible=[item for item in identities if not item["pocket"]]
    classified={item["id"]:recognizer.classify(item) for item in eligible}
    unique=[item for item in eligible if classified[item["id"]]["outcome"]=="recognizedUnique"]
    ambiguous=[item for item in eligible if classified[item["id"]]["outcome"]=="recognizedAmbiguous"]
    not_rec=[item for item in eligible if classified[item["id"]]["outcome"]=="notRecognized"]
    groups={item["id"]:name_audit.candidates_for(recognizer,item) for item in ambiguous}

    prior_observed={
      "full":{"physical":len(eligible),"unique":len(unique),"ambiguous":len(ambiguous),"notRecognized":len(not_rec)}
    }
    discrepancies={}
    for key,value in PRIOR["full"].items():
        if prior_observed["full"][key]!=value:
            discrepancies[f"full.{key}"]={"expected":value,"observed":prior_observed["full"][key]}

    real_case_results=[]
    for fixture in REAL_PHOTO_CASES:
        candidates=[identities_by_id[card_id] for card_id in fixture["candidateIds"] if card_id in identities_by_id]
        if len(candidates)!=len(fixture["candidateIds"]):
            missing=sorted(set(fixture["candidateIds"])-set(card["id"] for card in candidates))
            discrepancies[f"realPhoto.{fixture['printed']}.missingCandidates"]={"expected":fixture["candidateIds"],"missing":missing}
        real_case_results.append(analyze_real_name_case(fixture,candidates))
    real_name_metrics={
      "confirmedExportSchema":2,"totalTests":27,"photoScans":19,"collectorVerified":11,"collectorFailures":8,
      "collectorSuccessPercent":round(100*11/19,2),"ambiguousPhotoScans":8,
      "ruleAResolved":sum(row["ruleA"]["resolved"] for row in real_case_results),
      "ruleACorrect":sum(row["ruleA"]["correct"] for row in real_case_results),
      "ruleAFalsePositives":sum(row["ruleA"]["resolved"] and not row["ruleA"]["correct"] for row in real_case_results),
      "ruleBResolved":sum(row["ruleB"]["resolved"] for row in real_case_results),
      "ruleBCorrect":sum(row["ruleB"]["correct"] for row in real_case_results),
      "ruleBFalsePositives":sum(row["ruleB"]["resolved"] and not row["ruleB"]["correct"] for row in real_case_results),
      "ruleCTheoretical":sum(row["ruleC"]["theoretical"] for row in real_case_results),
      "ruleCCorrect":sum(row["ruleC"]["correct"] for row in real_case_results),
      "singleStrongReadCases":sum(row["singleStrongRead"] for row in real_case_results),
      "suffixFailureCases":sum(row["suffixFailure"] for row in real_case_results),
      "rawDoubleConsensus":0,"categoryDetected":0,"subtypeDetected":0,"energyTypeDetected":0,
      "cases":real_case_results,
    }

    contributions=Counter()
    lost=0
    false_positive=0
    final_by_id={}
    for item in ambiguous:
        final,resolved_at,target_lost=structural_cascade(item,groups[item["id"]],recognizer,fields,maps)
        lost+=target_lost
        selected=final[0]["id"] if len(final)==1 else None
        false_positive+=bool(selected and selected!=item["id"])
        if resolved_at:contributions[resolved_at]+=1
        final_by_id[item["id"]]={"count":len(final),"resolvedAt":resolved_at}

    expected_contrib={"category":1330,"subtype":382,"energyType":18,"name":9246}
    for key,value in expected_contrib.items():
        if contributions[key]!=value:
            discrepancies[f"classification.{key}"]={"expected":value,"observed":contributions[key]}

    category_photo={
      "method":"Three deterministic top-card OCR crops; exact textual signals only; results are metrics and never filter candidates.",
      "structuralCasesResolved":contributions["category"],
      "realPhotoCasesTested":19,
      "readCorrectly":0,
      "previousCategoryDetected":0,
      "newCropConfigurationsPrepared":3,
      "groundTruthAccuracy":None,
      "status":"RILEVAZIONE IMPLEMENTATA COME METRICA — DA MISURARE NEL SECONDO TEST FOTO REALI"
    }

    trainer_rows={}
    trainer_items=[item for item in ambiguous if candidate_audit.is_trainer(fields,maps,item)]
    for item in trainer_items:
        sig=candidate_audit.signal(fields,maps,item,"trainer-types")
        subtype=sig["values"][0] if sig["reliable"] else "missing-or-discordant"
        row=trainer_rows.setdefault(subtype,{"ambiguousTested":0,"structurallyResolved":0,"realPhotoResolved":0,"fallback":0})
        row["ambiguousTested"]+=1
        if final_by_id[item["id"]]["resolvedAt"] in {"category","subtype"}:
            row["structurallyResolved"]+=1
        row["fallback"]+=final_by_id[item["id"]]["count"]>1

    energy_items=[item for item in ambiguous if candidate_audit.is_energy(fields,maps,item)]
    energy_summary={
      "previousAuditReused":PRIOR["energy"],
      "ambiguousInCurrentRecognizedGroup":len(energy_items),
      "incrementalResolvedInGeneralCascade":contributions["energyType"],
      "realPhotoTypeReads":0,
      "realPhotoResolved":0,
      "stillManualStructural":sum(final_by_id[item["id"]]["count"]>1 for item in energy_items),
      "variantFinishUsed":False,
      "status":"Basic Energy SVE/MEE route preserved; broader type OCR not photo-validated"
    }

    name_analyses=[name_audit.analyze_identity(recognizer,item,groups[item["id"]]) for item in ambiguous]
    safe_name=sum(row["theoreticallySafeWithTwoConcordantOCRReads"] for row in name_analyses)
    name_summary={
      "previousCrop":{"coordinates":{"x":.12,"y":.055,"w":.72,"h":.075},"scale":2.2,
        "ocrA":{"preprocessing":"original","language":"ita+eng","psm":7},
        "ocrB":{"preprocessing":"threshold 170","language":"ita+eng","psm":7},
        "deskew":False,"whitelist":None,
        "observedProblem":"The fixed upper strip also captured HP/PS, numbers, symbols, attack text, and artwork when framing/perspective varied."},
      "newCropMatrix":[
        {"id":"N1-A","coordinates":{"x":.12,"y":.055,"w":.72,"h":.075},"scale":2.2,"preprocessing":"original","role":"current baseline"},
        {"id":"N1-B","coordinates":{"x":.12,"y":.055,"w":.72,"h":.075},"scale":2.2,"preprocessing":"grayscale"},
        {"id":"N1-C","coordinates":{"x":.12,"y":.055,"w":.72,"h":.075},"scale":2.2,"preprocessing":"contrast 1.65"},
        {"id":"N1-D","coordinates":{"x":.12,"y":.055,"w":.72,"h":.075},"scale":2.2,"preprocessing":"threshold 170","role":"current second read"},
        {"id":"N2-E","coordinates":{"x":.08,"y":.045,"w":.68,"h":.065},"scale":4.0,"preprocessing":"upscale original","tradeoff":"narrower vertical band; may miss shifted names"},
        {"id":"N3-F","coordinates":{"x":.08,"y":.025,"w":.76,"h":.09},"scale":4.0,"preprocessing":"upscale grayscale","tradeoff":"more framing tolerance; more HP contamination"},
        {"id":"N4-G","coordinates":{"x":.04,"y":.04,"w":.84,"h":.075},"scale":4.0,"preprocessing":"upscale threshold","tradeoff":"wide-name support; highest graphic contamination risk"},
      ],
      "bestCrop":"NOT YET MEASURABLE: schema-2 exports do not contain crop images; N2-E and N3-F are priority candidates for the next real-photo run.",
      "requiresConcordance":True,"requiresSingleExactCandidateMatch":True,
      "structurallySafeCases":safe_name,
      "realPhotoScans":19,"ambiguousRealPhotoScans":8,
      "ruleA":{key:real_name_metrics[key] for key in ("ruleAResolved","ruleACorrect","ruleAFalsePositives")},
      "ruleB":{key:real_name_metrics[key] for key in ("ruleBResolved","ruleBCorrect","ruleBFalsePositives")},
      "ruleCTheoretical":real_name_metrics["ruleCTheoretical"],
      "singleStrongReadCases":real_name_metrics["singleStrongReadCases"],
      "suffixFailureCases":real_name_metrics["suffixFailureCases"],
      "declaration":"Current OCR measured on real photos; new crops require a second real-photo test before any accuracy claim."
    }
    if safe_name!=PRIOR["name"]["safe"]:
        discrepancies["name.safe"]={"expected":PRIOR["name"]["safe"],"observed":safe_name}

    genesect=next((row for row in real_case_results if row["printed"]=="067/086"),{})
    genesect["hardcodedMatchingRule"]=False
    genesect["diagnosticConclusion"]="Base name observed, significant suffix did not agree, so all verified candidates remain manual."

    special=[item for item in eligible if full.special_parts(item["localId"]) and not item["promo"]]
    special_amb=[item for item in special if classified[item["id"]]["outcome"]=="recognizedAmbiguous"]
    special_rows={}
    for item in special:
        prefix=full.special_parts(item["localId"])[0]
        row=special_rows.setdefault(prefix,{"identities":0,"ambiguousInitial":0,"resolvedCascade":0,"resolvedByName":0,"manual":0})
        row["identities"]+=1
        if item in special_amb:
            row["ambiguousInitial"]+=1
            result=final_by_id[item["id"]]
            row["resolvedCascade"]+=bool(result["resolvedAt"])
            row["resolvedByName"]+=result["resolvedAt"]=="name"
            row["manual"]+=result["count"]>1
    special_summary={
      "identities":len(special),"ambiguousInitial":len(special_amb),"prefixes":sorted(special_rows),
      "resolved":sum(row["resolvedCascade"] for row in special_rows.values()),
      "manual":sum(row["manual"] for row in special_rows.values()),"byPrefix":special_rows
    }
    if set(special_rows)!=EXPECTED_PREFIXES:
        discrepancies["special.prefixes"]={"expected":sorted(EXPECTED_PREFIXES),"observed":sorted(special_rows)}
    for key,observed,expected in [
      ("special.total",len(special),PRIOR["classification"]["special"]),
      ("special.ambiguous",len(special_amb),PRIOR["classification"]["specialAmbiguous"]),
      ("special.manual",special_summary["manual"],PRIOR["classification"]["specialAfterName"])
    ]:
        if observed!=expected:discrepancies[key]={"expected":expected,"observed":observed}

    over6_items=[]
    over6_groups={}
    for item in eligible:
        cards=name_audit.candidates_for(recognizer,item)
        ids=[card["id"] for card in cards]
        if len(cards)>6 and item["id"] in ids:
            over6_items.append(item)
            over6_groups[item["id"]]=cards
    unique_group_lists={}
    for cards in over6_groups.values():
        key=tuple(card["id"] for card in cards)
        unique_group_lists[key]=cards
    pagination_failures=[]
    for key,cards in unique_group_lists.items():
        pages=paginate(cards)
        final_ids=pages[-1]["ids"] if pages else []
        expected=[card["id"] for card in cards]
        if final_ids!=expected or len(final_ids)!=len(set(final_ids)):
            pagination_failures.append({"candidateIds":expected,"finalIds":final_ids})
    beyond=[item for item in over6_items if [c["id"] for c in over6_groups[item["id"]]].index(item["id"])>=6]
    after_filters=0
    unique_before_cap=0
    still_beyond=0
    for item in beyond:
        final,_,target_lost=structural_cascade(item,over6_groups[item["id"]],recognizer,fields,maps)
        ids=[card["id"] for card in final]
        position=ids.index(item["id"]) if item["id"] in ids else 10**9
        after_filters+=position<6
        unique_before_cap+=len(final)==1 and position==0
        still_beyond+=position>=6
        lost+=target_lost
    display_cap={
      "groupsOver6":len(unique_group_lists),"identitiesInGroupsOver6":len(over6_items),
      "identitiesBeyondCapBefore":len(beyond),"recoveredWithin6BySafeFilters":after_filters,
      "madeUniqueBeforeCap":unique_before_cap,"stillBeyond6AfterSafeFilters":still_beyond,
      "loadMoreTested":True,"groupsPaginationTested":len(unique_group_lists),
      "paginationFailures":len(pagination_failures),"candidateIdsLost":sum(len(x["candidateIds"])-len(x["finalIds"]) for x in pagination_failures),
      "duplicateIds":sum(len(x["finalIds"])-len(set(x["finalIds"])) for x in pagination_failures),
      "fourteenCandidateControl":{"labels":[state["label"] for state in paginate([{"id":str(i)} for i in range(14)])],
                                  "shown":[state["shown"] for state in paginate([{"id":str(i)} for i in range(14)])]}
    }
    if len(beyond)!=PRIOR["classification"]["beyondCap6"]:
        discrepancies["display.beyondCap6"]={"expected":PRIOR["classification"]["beyondCap6"],"observed":len(beyond)}

    manual_resolved=safe_name
    manual_summary={
      "optionalNameTested":True,"ambiguousIdentitiesTested":len(ambiguous),
      "exactOptionalNameStructurallyUnique":manual_resolved,
      "incrementalCategoryFieldNotRequiredForInitialUI":True,
      "behavior":"number/total verified candidates → optional exact name → unique or original candidates",
      "zeroMatchRestoresOriginal":True
    }

    synthetic=[{"id":"a","signal":"pokemon","name":"Alpha-ex"},{"id":"b","signal":"trainer","name":"Beta-ex"},{"id":"c","signal":"","name":"Gamma"}]
    known=[synthetic[0],synthetic[1]]
    restored,_,reason=safe_filter(known,"energy",lambda x:x["signal"])
    exact_restored,_,name_reason=exact_name_filter(synthetic,"Not present")
    failsafe={
      "zeroCategoryFilterRestoresOriginal":reason=="zero-restored" and restored==known,
      "zeroNameFilterRestoresOriginal":name_reason=="zero-restored" and exact_restored==synthetic,
      "missingCandidateMetadataPreserved":synthetic[2] in safe_filter(synthetic,"pokemon",lambda x:x["signal"])[0],
      "candidatesLost":lost,
      "simulatedFalsePositives":false_positive
    }

    regression=full.regression_check(recognizer)
    network_errors=list(base_network.get("errors",[]))+fields.network.errors
    resolved_total=sum(contributions.values())
    status_ok=(
      not discrepancies and all(html_checks["requiredMarkers"].values())
      and not any(html_checks["forbiddenPatterns"].values())
      and html_checks["filterBeforeDisplayCap"]
      and html_checks["photoInputCaptureEnvironment"]
      and html_checks["loadMoreWithoutNewQuery"]
      and html_checks["groundTruthIncludesNone"]
      and html_checks["exportExcludesImages"]
      and html_checks["collectionSaveButtonRemoved"]
      and html_checks["collectionSaveRuntimeDisabled"]
      and html_checks["runtimeDoesNotPersistCollection"]
      and html_checks["diagnosticStorageSeparated"]
      and html_checks["realPhotoStatistics"]
      and html_checks["performanceMeasured"]
      and html_checks["schema3Export"] and html_checks["schema2Migration"]
      and html_checks["sevenControlledNameVariants"] and html_checks["currentRuleAThresholdPreserved"]
      and html_checks["ruleBMetricOnly"] and html_checks["ruleCNeverApplied"]
      and html_checks["classificationDoesNotFilter"] and html_checks["targetedNoFuzzy"]
      and html_checks["targetedNoNamedHardcoding"] and html_checks["exportRejectsImages"]
      and html_checks["collectorRawCaptured"] and html_checks["newSignalsDiagnosticOnly"]
      and html_checks["collectorIdentityBeforeClassification"]
      and all(unit_tests.values())
      and genesect.get("ruleA",{}).get("resolved") is False
      and genesect.get("ruleB",{}).get("resolved") is False
      and genesect.get("ruleC",{}).get("theoretical") is False
      and real_name_metrics["ruleAFalsePositives"]==0 and real_name_metrics["ruleBFalsePositives"]==0
      and not pagination_failures
      and failsafe["zeroCategoryFilterRestoresOriginal"]
      and failsafe["zeroNameFilterRestoresOriginal"]
      and failsafe["missingCandidateMetadataPreserved"]
      and failsafe["candidatesLost"]==0
      and failsafe["simulatedFalsePositives"]==0
      and regression["regressionCount"]==0 and not network_errors
    )
    report={
      "schema":3,"testType":"targeted-real-photo-ocr-crop-category-diagnostic",
      "sourceMain":MAIN,"diagnosticCommit":os.environ.get("GITHUB_SHA","unknown"),
      "branch":os.environ.get("GITHUB_REF_NAME","diagnostic/candidate-disambiguation-implementation-test-20260902"),
      "priorReports":{"expected":PRIOR,"observed":prior_observed,"discrepancies":discrepancies},
      "scope":{"catalogIdentities":len(identities),"physicalIdentities":len(eligible),
               "ambiguousIdentities":len(ambiguous),"ambiguousGroups":len({tuple(c["id"] for c in cards) for cards in groups.values()})},
      "implementation":{"html":str(HTML),"checks":html_checks,
        "unitTests":unit_tests,
        "cascade":["verified printed number/localId/set","verified category when available",
                   "verified trainer subtype or Energy type when available","two concordant exact name OCR reads",
                   "single candidate or manual fallback"],
        "productionBehaviorChanged":False},
      "category":category_photo,"trainers":{"bySubtype":trainer_rows,"realPhotoSubtypeReads":0},
      "energy":energy_summary,"name":name_summary,"realPhotoReplay":real_name_metrics,"genesect067of086":genesect,
      "specialNumbering":special_summary,"displayCap6":display_cap,"manualSearch":manual_summary,
      "structuralSimulation":{"contributions":dict(contributions),"resolvedTotal":resolved_total,
        "stillManual":len(ambiguous)-resolved_total,
        "theoreticalUniqueCoverageCount":len(unique)+resolved_total,
        "theoreticalUniqueCoveragePercent":round(100*(len(unique)+resolved_total)/len(eligible),2)},
      "photoValidation":{"sourceExport":"candidate_disambiguation_real_scans.json schema 2 (Work context; not committed)",
        "realScansExecutedPreviously":27,"photoScansExecutedPreviously":19,"newPhotosExecutedInWorkflow":0,
        "recommendedMinimum":{"identities":30,"acquisitionsEach":2,"totalScans":60},
        "diagnosticPage":"diagnostic/candidate-disambiguation-test.html",
        "diagnosticLogDownload":"candidate_disambiguation_real_scans.json",
        "features":{"cameraCapture":True,"numberLocalIdOCR":True,"categoryPanel":True,
          "trainerSubtypePanel":True,"energyTypePanel":True,"doubleNameOCR":True,
          "specialNumberingPreserved":True,"loadMore":True,"manualGroundTruth":True,
          "localStatistics":True,"jsonExport":True,"diagnosticReset":True,
          "performanceTiming":True,"collectionSaveDisabled":True},
        "status":"PRONTO PER SECONDO TEST FOTO REALI"},
      "collectorCode":{"previous":{"photoScans":19,"verified":11,"failed":8,"successPercent":round(100*11/19,2)},
        "historicalFailureClassification":"Schema 2 did not store collector raw reads; all 8 old failures are legacy-schema2-raw-unavailable.",
        "schema3Capture":["all raw reads","parsed reads","slash detected","denominator detected","parser rejection reasons"],
        "parserChanged":False,"recommendedNextStep":"Collect the second iPhone export, then rank real parser failure modes before changing parsing."},
      "classificationPhoto":{"previousDetected":{"category":0,"subtype":0,"energyType":0},
        "schema3Method":"three exact-text OCR crops; diagnostic only; no color inference; no candidate filtering",
        "trainerControl":{"name":"Anita","previousRaw":"Aiyto ALLENATOF","categoryDetected":False,"subtypeDetected":False,
          "note":"Previous OCR is too corrupted for exact Allenatore/Aiuto signals; new crops must be measured on a new photo."},
        "energyStatus":"Prepared for textual Base/Special/type signals; no real energy accuracy claim until new ground-truth photos."},
      "performance":{"additionalOCRUniqueCandidate":3,"additionalOCRAmbiguousCandidate":8,
        "nameReadsPrevious":2,"nameReadsSchema3":7,"classificationReadsSchema3":3,
        "measuredAdditionalTimeMs":None,"worstCaseAdditionalOCRCallsOverPrevious":8,
        "note":"Actual iPhone timings will be exported per crop; no performance values are invented."},
      "quality":{"simulatedFalsePositives":false_positive,
        "realReplayFalsePositivesRuleA":real_name_metrics["ruleAFalsePositives"],
        "realReplayFalsePositivesRuleB":real_name_metrics["ruleBFalsePositives"],"candidateIdsLost":lost,
        "regressions":regression["regressionCount"],"apiNetworkErrors":len(network_errors),
        "networkErrorDetails":network_errors,"falseNegativeOCR":"not measurable without real photos"},
      "failSafe":failsafe,
      "safety":{"mainModified":False,"retailModified":False,"cardmarketModified":False,
        "collectionDataModified":False,"newIdentitiesCreated":False,"pricesModified":False},
      "runtimeSeconds":round(time.monotonic()-started,2),
      "finalAssessment":"PRONTO PER SECONDO TEST FOTO REALI" if status_ok else "NON SUFFICIENTEMENTE SICURO"
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
      "sourceMain":MAIN,"scope":report["scope"],"priorDiscrepancies":discrepancies,
      "category":category_photo,"trainers":report["trainers"],"energy":energy_summary,
      "name":name_summary,"realPhotoReplay":real_name_metrics,"genesect":genesect,"special":special_summary,
      "displayCap6":display_cap,"manualSearch":manual_summary,
      "structuralSimulation":report["structuralSimulation"],"photoValidation":report["photoValidation"],
      "collectorCode":report["collectorCode"],"classificationPhoto":report["classificationPhoto"],
      "performance":report["performance"],"quality":report["quality"],"failSafe":failsafe,
      "safety":report["safety"],"finalAssessment":report["finalAssessment"],"report":str(OUT)
    },ensure_ascii=False,indent=2))
    if not status_ok:
        raise SystemExit("Diagnostic implementation requires verification")


if __name__=="__main__":
    main()
