#!/usr/bin/env python3
"""Read-only validation of Cardoryx OCR-name ambiguity resolution."""

import json, os, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
import ambiguity_name_resolution_audit as amb
import full_catalog_coverage_postmerge_audit as full

OUT=Path("artifacts/ocr_name_ambiguity_report.json")
CACHE=Path("/tmp/cardoryx_tcg_catalog_snapshot.json")
MAIN="86c39e1b74a93bed468ab0bcbbbaac2ad2109d2f"
EXPECTED={"ambiguous":11249,"safe":10225,"manual":1024,"reduction":90.9,"coverage":91.44,"falsePositives":0,"energies":936}

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")

def load_catalog():
    if CACHE.exists():
        s=json.loads(CACHE.read_text(encoding="utf-8"))
        return s["lists"],s["details"],s["network"],True
    n=full.Network()
    lists={k:full.rows(n.get(f"{v}/sets"),"sets","data") for k,v in full.BASES.items()}
    details={"it":{},"en":{}}; errors={"it":{},"en":{}}; jobs={}
    with ThreadPoolExecutor(max_workers=12) as pool:
        for locale in full.BASES:
            for row in lists[locale]:
                sid=str(row.get("id") or "")
                if sid: jobs[pool.submit(full.fetch_detail,n,locale,sid)]=(locale,sid)
        for job in as_completed(jobs):
            locale,sid=jobs[job]
            try: details[locale][sid]=job.result()
            except Exception as exc: errors[locale][sid]=str(exc)
    network={"requests":n.requests,"errors":n.errors,"setDetailErrors":errors}
    CACHE.write_text(json.dumps({"lists":lists,"details":details,"network":network},ensure_ascii=False),encoding="utf-8")
    return lists,details,network,False

def inspect_ocr(source):
    start=source.index("async function runSmartOCR()")
    end=source.index("async function fetchFullCandidate",start)
    body=source[start:end]
    markers=[
      "async function readNameOnlyWhenNeeded(img)",
      "const r1=await Tesseract.recognize(crop1,'ita+eng'",
      "const r2=await Tesseract.recognize(crop2,'ita+eng'",
      "lastOCR={\n        name:'',",
      "await renderFastCandidates(cards.slice(0,6),route)",
      "async function readCollectorCodeFocused(img)",
      "async function readBasicEnergyIdentity(img)",
    ]
    missing=[x for x in markers if x not in source]
    return {
      "verified":not missing,"missingMarkers":missing,
      "engine":"Tesseract.js v5; ita+eng for name/energy and eng for collector code",
      "currentOCR":{"energyRecognitions":4,"energyExecution":"parallel","collectorCodeRecognitions":12,"collectorExecution":"sequential"},
      "nameHelperExists":"async function readNameOnlyWhenNeeded(img)" in source,
      "nameHelperInvokedByCurrentScanner":"readNameOnlyWhenNeeded(" in body,
      "fullCardOCRTextAvailable":False,
      "collectorOCRTextsRetained":"ocrTexts:x.texts" in source,
      "collectorOCRTextSuitableForName":False,
      "dedicatedNameCropAlreadyImplementedButInactive":True,
      "additionalNameOCRNeeded":True,
      "additionalRecognitionsForAmbiguousNonEnergy":2,
      "twoReadsPossible":True,
      "twoReadsCurrentlyRequiredToAgree":False,
      "currentNameHelperBehavior":"returns the highest-quality reading rather than requiring concordance",
      "fuzzyHelpersPresentButNotUsedByRunSmartOCR":all(x in source for x in ("function similarity(","function bestOfficialCandidateFromOCR(")),
    }

def photo_inventory():
    paths=sorted(str(p) for p in Path(".").rglob("*") if p.is_file() and p.suffix.lower() in {".jpg",".jpeg",".png",".webp",".heic"})
    excluded=[p for p in paths if p.startswith("assets/energies/") or Path(p).name in {"apple-touch-icon.png","cardoryx-logo.png","icon-192.png","icon-512.png"}]
    return {"allImages":paths,"excludedAssets":excluded,"realScannerPhotos":[p for p in paths if p not in excluded]}

def main():
    started=time.monotonic()
    source=Path("index.html").read_text(encoding="utf-8")
    ocr=inspect_ocr(source); photos=photo_inventory()
    lists,details,network,reused=load_catalog()
    identities=full.build_catalog(lists,details)
    rec=full.Recognizer(lists,details,identities)
    classified={x["id"]:rec.classify(x) for x in identities}
    items=[x for x in identities if classified[x["id"]]["outcome"]=="recognizedAmbiguous"]
    analyses=[amb.analyze_identity(rec,x,amb.candidates_for(rec,x)) for x in items]
    safe=[x for x in analyses if x["theoreticallySafeWithTwoConcordantOCRReads"]]
    manual=[x for x in analyses if not x["theoreticallySafeWithTwoConcordantOCRReads"]]
    false=sum(x["falsePositive"] for x in analyses)
    energies=sum(x["riskFlags"]["energyPresent"] for x in analyses)
    exact_nonenergy=sum(x["conservativeNormalizedNameUnique"] and not x["riskFlags"]["energyPresent"] for x in analyses)
    recomputed={"ambiguous":len(analyses),"safe":len(safe),"manual":len(manual),
      "reduction":round(100*len(safe)/len(analyses),2),
      "coverage":round(100*(9466+len(safe))/21534,2),
      "falsePositives":false,"energies":energies}
    discrepancy={k:{"expected":v,"observed":recomputed.get(k)} for k,v in EXPECTED.items() if recomputed.get(k)!=v}
    genesect=amb.genesect_control(rec,identities)
    genesect.update({"realOCRReadsAvailable":False,"autoSelectionAllowedInThisAudit":False,
      "conclusion":"Exact normalized name is structurally unique; selection still requires two concordant real OCR reads."})
    regress=full.regression_check(rec)
    report={
      "schema":1,"testType":"ocr-name-ambiguity-validation","generatedAt":now(),"sourceMain":MAIN,
      "diagnosticCommit":os.environ.get("GITHUB_SHA","unknown"),
      "previousAudit":{"runId":33616802992,"diagnosticSha":"9140248130b4d597606616f9a7b662a038771d55",
        "expected":EXPECTED,"recomputed":recomputed,"discrepancies":discrepancy,"verified":not discrepancy},
      "ocrExisting":ocr,
      "photoEvidence":{**photos,"realPhotoCount":len(photos["realScannerPhotos"]),"realOCRAccuracyMeasured":False,
        "realOCRValidatedCases":0,"declaration":"OCR REALE NON VALIDATO",
        "reason":"The repository has no real scanner photographs with ground truth."},
      "failSafeSimulation":{"structurallyResolvable":len(safe),"remainingManual":len(manual),"simulatedFalsePositives":false,
        "rule":["verified number/localId and set candidate group first","exclude Energy and unsafe categories",
          "two independent name-crop reads only for an ambiguous group","both conservative normalized reads must agree",
          "full exact name must have exactly one owner inside that group","otherwise manual"],
        "forbidden":["name-first lookup","fuzzy matching","similarity","contains","Levenshtein","partial name","suffix-only selection"]},
      "manualSearch":{"notImplemented":True,"exactUniqueNonEnergyMaximum":exact_nonenergy,
        "ambiguitiesEliminableWithStrictExactName":len(safe),
        "excluded":["Energy","same-name collisions","short/generic names","suffix/regional base collisions","partial names","IT/EN alias collisions"]},
      "genesectControl":genesect,
      "performance":{"measuredOnRealPhotos":False,"currentMaximumOCRRecognitions":16,
        "additionalRecognitionsOnlyForAmbiguousNonEnergy":2,"nominalMaximumCallIncreasePercent":12.5,
        "latency":"Not measured; the existing name helper executes two serial PSM-7 recognitions.",
        "duplicateOCRAvoided":True},
      "minimumRealPhotoValidation":{"identities":30,"capturesPerIdentity":2,"minimumPhotos":60,"groundTruthRequired":True,
        "mustInclude":["Genesect-ex 067/086","groups of 2, 3, 4 and >6 candidates","old and recent cards",
          "short and multiword names","apostrophes and diacritics","ex/EX/V/GX/VMAX/VSTAR suffixes",
          "regional forms and Trainer cards","lighting, focus, angle and sleeve glare variation"]},
      "regressions":regress["regressionCount"],"regressionChecks":{k:v for k,v in regress.items() if k!="cases"},
      "network":{**network,"cacheReused":reused},
      "safety":{"readOnly":True,"indexHtmlModified":False,"retailModified":False,"cardmarketModified":False,
        "collectionDataModified":False,"scannerBehaviorModified":False},
      "runtimeSeconds":round(time.monotonic()-started,2),
      "finalAssessment":"PRONTO PER TEST SU FOTO REALI" if not discrepancy and ocr["verified"] and not false and not regress["regressionCount"] else "NON PRONTO"
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"previousAudit":report["previousAudit"],"ocrExisting":ocr,"photoEvidence":report["photoEvidence"],
      "simulation":report["failSafeSimulation"],"manualSearch":report["manualSearch"],"genesect":genesect,
      "performance":report["performance"],"regressions":report["regressions"],"networkErrors":len(network.get("errors",[])),
      "finalAssessment":report["finalAssessment"],"report":str(OUT)},ensure_ascii=False,indent=2))
    if discrepancy or not ocr["verified"] or false or regress["regressionCount"] or network.get("errors"):
        raise SystemExit("OCR name audit requires verification")

if __name__=="__main__": main()
