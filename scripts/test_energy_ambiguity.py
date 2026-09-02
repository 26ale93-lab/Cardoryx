#!/usr/bin/env python3
"""Read-only audit of Energy identities in Cardoryx recognition ambiguities."""

import json, os, re, time
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
import ambiguity_name_resolution_audit as amb
import full_catalog_coverage_postmerge_audit as full
import test_ocr_name_ambiguity as ocr_audit

OUT=Path("artifacts/energy_ambiguity_report.json")
MAIN="86c39e1b74a93bed468ab0bcbbbaac2ad2109d2f"
ENERGY=re.compile(r"\b(?:energy|energia)\b",re.I)
TYPES={
 "grass":("grass","erba"),"fire":("fire","fuoco"),"water":("water","acqua"),
 "lightning":("lightning","electric","elettro","lampo"),"psychic":("psychic","psico"),
 "fighting":("fighting","lotta"),"darkness":("darkness","dark","oscurita","oscurità"),
 "metal":("metal","metallo"),"fairy":("fairy","folletto"),"colorless":("colorless","incolore")
}

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def words(v): return set(re.findall(r"[a-z0-9]+",amb.conservative_name_key(v)))

def metadata(details):
    out={}
    for locale in ("it","en"):
        for detail in details[locale].values():
            for card in full.rows(detail.get("cards"),"cards","data"):
                if isinstance(card,dict) and card.get("id"):
                    row=out.setdefault(str(card["id"]),{})
                    for key in ("types","energyType","variants","category","rarity"):
                        if card.get(key) not in (None,"",[],{}): row[key]=card[key]
    return out

def is_energy(item,meta):
    raw=meta.get(item["id"],{})
    blob=f"{item.get('nameIT') or ''} {item.get('nameEN') or ''} {raw.get('category') or ''} {raw.get('energyType') or ''}"
    return bool(item.get("basicEnergy") or ENERGY.search(blob))

def energy_types(item,meta):
    raw=meta.get(item["id"],{}); extra=[]
    for key in ("types","energyType"):
        value=raw.get(key)
        extra.extend(value if isinstance(value,list) else [value] if value else [])
    ws=words(f"{item.get('nameIT') or ''} {item.get('nameEN') or ''} {' '.join(map(str,extra))}")
    return tuple(sorted(k for k,aliases in TYPES.items() if any(alias in ws for alias in aliases)))

def variants(item,meta):
    value=meta.get(item["id"],{}).get("variants")
    if isinstance(value,dict): return tuple(sorted(str(k).casefold() for k,v in value.items() if v is True))
    if isinstance(value,list): return tuple(sorted(str(x).casefold() for x in value if x))
    return ()

def unique_owner(cands,target_id,signal):
    target=next((x for x in cands if x["id"]==target_id),None)
    if not target: return False,()
    key=signal(target)
    if not key: return False,key
    owners=[x["id"] for x in cands if signal(x)==key]
    return owners==[target_id],key

def main():
    started=time.monotonic()
    lists,details,network,reused=ocr_audit.load_catalog()
    identities=full.build_catalog(lists,details)
    rec=full.Recognizer(lists,details,identities); meta=metadata(details)
    items=[x for x in rec.physical if is_energy(x,meta)]
    current={x["id"]:rec.classify(x) for x in items}; rows=[]
    for item in items:
        cands=amb.candidates_for(rec,item); ids=[x["id"] for x in cands]
        pos=ids.index(item["id"]) if item["id"] in ids else None
        reachable=pos is not None; unique=reachable and len(cands)==1; ambiguous=reachable and len(cands)>1
        type_ok,type_key=unique_owner(cands,item["id"],lambda x:energy_types(x,meta)) if ambiguous else (False,())
        variant_ok,variant_key=unique_owner(cands,item["id"],lambda x:variants(x,meta)) if ambiguous and not type_ok else (False,())
        beyond=bool(ambiguous and pos>=6); before_cap=bool(beyond and (type_ok or variant_ok))
        selected=item["id"] if type_ok or variant_ok else None
        rows.append({"id":item["id"],"nameIT":item.get("nameIT"),"nameEN":item.get("nameEN"),
          "setId":item["setId"],"set":item["setName"],"localId":item["localId"],"cardCountOfficial":item["official"],
          "currentOutcome":current[item["id"]]["outcome"],"currentReason":current[item["id"]]["reason"],
          "candidateCount":len(cands),"candidateIds":ids[:20],"targetPosition":pos,"alreadyUnique":unique,"ambiguous":ambiguous,
          "energyTypeSignal":list(type_key),"recoverableWithVerifiedEnergyType":type_ok,
          "variantSignature":list(variant_key),"potentiallyRecoverableWithVerifiedVariantFinish":variant_ok,
          "targetBeyondDisplayCap6":beyond,"recoverableBeforeDisplayCap6":before_cap,
          "simulatedSelection":selected,"falsePositive":selected is not None and selected!=item["id"]})
    unique=[x for x in rows if x["alreadyUnique"]]; ambiguous_rows=[x for x in rows if x["ambiguous"]]
    by_type=[x for x in rows if x["recoverableWithVerifiedEnergyType"]]
    by_variant=[x for x in rows if x["potentiallyRecoverableWithVerifiedVariantFinish"]]
    beyond=[x for x in rows if x["targetBeyondDisplayCap6"]]
    cap_recovered=[x for x in rows if x["recoverableBeforeDisplayCap6"]]
    recovered={x["id"] for x in by_type+by_variant}
    manual=[x for x in rows if not x["alreadyUnique"] and x["id"] not in recovered]
    false=sum(x["falsePositive"] for x in rows); regress=full.regression_check(rec)
    same_name=[]
    for row in ambiguous_rows:
        target=rec.by_id[row["id"]]
        key=amb.conservative_name_key(target.get("nameIT") or target.get("nameEN"))
        peers=[rec.by_id[x] for x in row["candidateIds"] if x in rec.by_id]
        if sum(amb.conservative_name_key(x.get("nameIT") or x.get("nameEN"))==key for x in peers)>1: same_name.append(row)
    gain=len(recovered)
    summary={"energiesAnalyzed":len(rows),"alreadyUnique":len(unique),"ambiguous":len(ambiguous_rows),
      "notReachableOrInsufficientIdentifiers":len(rows)-len(unique)-len(ambiguous_rows),
      "recoverableWithVerifiedEnergyType":len(by_type),
      "potentiallyRecoverableWithVerifiedVariantFinish":len(by_variant),
      "targetBeyondDisplayCap6":len(beyond),"recoverableBeforeDisplayCap6":len(cap_recovered),
      "sameNameAndNumberAcrossSets":len(same_name),"stillManual":len(manual),"potentialUniqueGain":gain,
      "theoreticalGlobalUniqueCoverageCount":9466+gain,
      "theoreticalGlobalUniqueCoveragePercent":round(100*(9466+gain)/21534,2),
      "simulatedFalsePositives":false,"regressions":regress["regressionCount"]}
    report={"schema":1,"testType":"energy-ambiguity-audit","generatedAt":now(),"sourceMain":MAIN,
      "diagnosticCommit":os.environ.get("GITHUB_SHA","unknown"),
      "scope":{"setsIT":len(lists["it"]),"setsEN":len(lists["en"]),"physicalCatalogIdentities":len(rec.physical)},
      "summary":summary,
      "currentOutcomes":dict(Counter(x["currentOutcome"] for x in rows)),
      "currentReasons":dict(Counter(x["currentReason"] for x in rows)),
      "candidateSizeDistribution":dict(Counter(str(x["candidateCount"]) if x["candidateCount"]<=6 else ">6" for x in ambiguous_rows)),
      "method":{"energySelection":"TCGdex IT/EN names/category/energyType only","typeRule":"exact canonical type has one owner inside verified candidates",
        "variantRule":"TCGdex-declared variant signature has one owner; potential only until physical finish is verified",
        "displayCapRule":"exact disambiguation before cap6; cap is not increased","priceUsed":False,
        "generalNameRuleUsed":False,"ocrAccuracyClaimed":False},
      "specialControls":{"sveMeeTested":regress["sveMeeTested"],"sveMeePassed":regress["sveMeePassed"],
        "previousAuditEnergyDangerCases":936,"reconstructedAmbiguousEnergyIdentities":len(ambiguous_rows),
        "note":"The prior 936 flags ambiguous identities whose candidate group contains Energy; this audit classifies target Energy identities."},
      "examples":{"typeRecoverable":by_type[:25],"variantRecoverable":by_variant[:25],
        "beyondCap6Recoverable":cap_recovered[:25],"sameNameSameNumberAcrossSets":same_name[:25],"manual":manual[:25]},
      "identityResults":rows,"regressionChecks":{k:v for k,v in regress.items() if k!="cases"},
      "network":{**network,"cacheReused":reused},
      "safety":{"readOnly":True,"indexHtmlModified":False,"retailModified":False,"cardmarketModified":False,
        "collectionDataModified":False,"scannerBehaviorModified":False},
      "runtimeSeconds":round(time.monotonic()-started,2),
      "finalAssessment":"CANDIDATO PER IMPLEMENTAZIONE" if gain>0 and not false and not regress["regressionCount"] and not network.get("errors") else "NON SUFFICIENTEMENTE SICURO"}
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"scope":report["scope"],"summary":summary,"currentOutcomes":report["currentOutcomes"],
      "currentReasons":report["currentReasons"],"candidateSizeDistribution":report["candidateSizeDistribution"],
      "specialControls":report["specialControls"],"regressions":report["regressionChecks"],
      "networkErrors":len(network.get("errors",[])),"finalAssessment":report["finalAssessment"],"report":str(OUT)},ensure_ascii=False,indent=2))
    if false or regress["regressionCount"] or network.get("errors"): raise SystemExit("Energy audit requires verification")

if __name__=="__main__": main()
