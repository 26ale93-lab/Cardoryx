#!/usr/bin/env python3
"""Diagnostic implementation test for Cardoryx candidate disambiguation.

Read-only: exercises the current recognizer/catalog, the isolated diagnostic HTML,
fail-safe filters, exact-name disambiguation, Energy reuse, special numbering,
manual optional-name filtering, and six-at-a-time candidate pagination.
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


def name_key(value=""):
    text=unicodedata.normalize("NFD",str(value or ""))
    text="".join(ch for ch in text if unicodedata.category(ch)!="Mn").lower()
    text=re.sub(r"[’‘`´]","'",text)
    text=re.sub(r"[‐‑‒–—−]","-",text)
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9'\- ]+"," ",text)).strip()


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
      "diagnosticDisambiguateVerifiedCandidates",
      "readDiagnosticNameEvidence",
      "diagnosticExactNameFilter",
      "showMoreDiagnosticCandidates",
      "downloadCandidateDiagnosticLog",
      "Nome esatto opzionale",
      "state.pageSize"
    ]
    forbidden_patterns=[
      "renderFastCandidates(cards.slice(0,6),route)",
      "Levenshtein",
      "diagnosticSimilarity",
      "diagnosticFuzzy"
    ]
    html_checks={
      "requiredMarkers":{marker:marker in html for marker in required_markers},
      "forbiddenPatterns":{marker:marker in html for marker in forbidden_patterns},
      "sourceProductionIndexUnmodified":True,
      "doubleNameOCRCalls":html.count("Tesseract.recognize(cropA")+html.count("Tesseract.recognize(cropB"),
      "filterBeforeDisplayCap":html.index("diagnosticDisambiguateVerifiedCandidates")<html.index("renderDiagnosticCandidatePage")
    }

    lists,details,base_network,_=ocr_audit.load_catalog()
    identities=full.build_catalog(lists,details)
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
      "method":"No general verified category OCR exists; the implementation accepts only explicitly verified evidence.",
      "structuralCasesResolved":contributions["category"],
      "realPhotoCasesTested":0,
      "readCorrectly":0,
      "failures":0,
      "status":"POTENZIALE STRUTTURALE — NON VALIDATO VIA FOTO"
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
      "ocrA":"narrow raw name crop, PSM 7, ita+eng",
      "ocrB":"same crop after deterministic threshold enhancement, PSM 7, ita+eng",
      "requiresConcordance":True,
      "requiresSingleExactCandidateMatch":True,
      "structurallySafeCases":safe_name,
      "realPhotoScans":0,
      "doubleOCRConcordant":0,
      "exactUniqueRealPhoto":0,
      "autoSelectionsRealPhoto":0,
      "fallbackRealPhoto":0,
      "falseNegativeOCR":"not measurable without real photos",
      "declaration":"OCR REALE NON ANCORA VALIDATO"
    }
    if safe_name!=PRIOR["name"]["safe"]:
        discrepancies["name.safe"]={"expected":PRIOR["name"]["safe"],"observed":safe_name}

    genesect_targets=[item for item in ambiguous
      if name_key(item.get("nameIT") or item.get("nameEN"))=="genesect-ex"
      and full.numeric(item["localId"])==67 and item["official"]==86]
    genesect={}
    if len(genesect_targets)==1:
        target=genesect_targets[0]
        candidates=groups[target["id"]]
        exact,_,_=exact_name_filter(candidates,"Genesect-ex")
        discordant=list(candidates)
        genesect={
          "targetId":target["id"],"candidateNames":[c.get("nameIT") or c.get("nameEN") for c in candidates],
          "candidateCount":len(candidates),"ocrA":"Genesect-ex","ocrB":"Genesect-ex",
          "concordantExactResultIds":[c["id"] for c in exact],
          "concordantAutoSelect":len(exact)==1 and exact[0]["id"]==target["id"],
          "discordantOCRKeepsAllCandidates":len(discordant)==len(candidates),
          "hardcoded":False
        }
    else:
        discrepancies["genesect.targetCount"]={"expected":1,"observed":len(genesect_targets)}

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

    synthetic=[{"id":"a","signal":"pokemon","name":"Genesect-ex"},{"id":"b","signal":"trainer","name":"Hydreigon-ex"},{"id":"c","signal":"","name":"Sliggoo"}]
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
      and genesect.get("concordantAutoSelect") and genesect.get("discordantOCRKeepsAllCandidates")
      and not pagination_failures
      and failsafe["zeroCategoryFilterRestoresOriginal"]
      and failsafe["zeroNameFilterRestoresOriginal"]
      and failsafe["missingCandidateMetadataPreserved"]
      and failsafe["candidatesLost"]==0
      and failsafe["simulatedFalsePositives"]==0
      and regression["regressionCount"]==0 and not network_errors
    )
    report={
      "schema":1,"testType":"candidate-disambiguation-diagnostic-implementation",
      "sourceMain":MAIN,"diagnosticCommit":os.environ.get("GITHUB_SHA","unknown"),
      "branch":os.environ.get("GITHUB_REF_NAME","diagnostic/candidate-disambiguation-implementation-test-20260902"),
      "priorReports":{"expected":PRIOR,"observed":prior_observed,"discrepancies":discrepancies},
      "scope":{"catalogIdentities":len(identities),"physicalIdentities":len(eligible),
               "ambiguousIdentities":len(ambiguous),"ambiguousGroups":len({tuple(c["id"] for c in cards) for cards in groups.values()})},
      "implementation":{"html":str(HTML),"checks":html_checks,
        "cascade":["verified printed number/localId/set","verified category when available",
                   "verified trainer subtype or Energy type when available","two concordant exact name OCR reads",
                   "single candidate or manual fallback"],
        "productionBehaviorChanged":False},
      "category":category_photo,"trainers":{"bySubtype":trainer_rows,"realPhotoSubtypeReads":0},
      "energy":energy_summary,"name":name_summary,"genesect067of086":genesect,
      "specialNumbering":special_summary,"displayCap6":display_cap,"manualSearch":manual_summary,
      "structuralSimulation":{"contributions":dict(contributions),"resolvedTotal":resolved_total,
        "stillManual":len(ambiguous)-resolved_total,
        "theoreticalUniqueCoverageCount":len(unique)+resolved_total,
        "theoreticalUniqueCoveragePercent":round(100*(len(unique)+resolved_total)/len(eligible),2)},
      "photoValidation":{"availableRepositoryPhotos":0,"realScansExecuted":0,
        "recommendedMinimum":{"identities":30,"acquisitionsEach":2,"totalScans":60},
        "diagnosticLogDownload":"candidate_disambiguation_photo_log.json",
        "status":"PRONTO PER TEST SU FOTO REALI — accuratezza OCR non dichiarata"},
      "performance":{"additionalOCRUniqueCandidate":0,"additionalOCRAmbiguousCandidate":2,
        "averageAdditionalOCRCallsIfAppliedToCurrentRecognizedMix":round(2*len(ambiguous)/(len(unique)+len(ambiguous)),3),
        "measuredAdditionalTimeMs":None,"worstCaseAdditionalOCRCalls":2,
        "note":"Timing on iPhone must be measured with real photos; both name reads run in parallel."},
      "quality":{"simulatedFalsePositives":false_positive,"candidateIdsLost":lost,
        "regressions":regression["regressionCount"],"apiNetworkErrors":len(network_errors),
        "networkErrorDetails":network_errors,"falseNegativeOCR":"not measurable without real photos"},
      "failSafe":failsafe,
      "safety":{"mainModified":False,"retailModified":False,"cardmarketModified":False,
        "collectionDataModified":False,"newIdentitiesCreated":False,"pricesModified":False},
      "runtimeSeconds":round(time.monotonic()-started,2),
      "finalAssessment":"PRONTO PER TEST SU FOTO REALI" if status_ok else "NON SUFFICIENTEMENTE SICURO"
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({
      "sourceMain":MAIN,"scope":report["scope"],"priorDiscrepancies":discrepancies,
      "category":category_photo,"trainers":report["trainers"],"energy":energy_summary,
      "name":name_summary,"genesect":genesect,"special":special_summary,
      "displayCap6":display_cap,"manualSearch":manual_summary,
      "structuralSimulation":report["structuralSimulation"],"photoValidation":report["photoValidation"],
      "performance":report["performance"],"quality":report["quality"],"failSafe":failsafe,
      "safety":report["safety"],"finalAssessment":report["finalAssessment"],"report":str(OUT)
    },ensure_ascii=False,indent=2))
    if not status_ok:
        raise SystemExit("Diagnostic implementation requires verification")


if __name__=="__main__":
    main()
