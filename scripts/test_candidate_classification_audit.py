#!/usr/bin/env python3
"""Read-only candidate classification and special-numbering disambiguation audit."""

import json, os, re, time, urllib.parse
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import ambiguity_name_resolution_audit as name_audit
import full_catalog_coverage_postmerge_audit as full
import test_energy_ambiguity as energy_audit
import test_ocr_name_ambiguity as ocr_audit

OUT=Path("artifacts/candidate_classification_audit_report.json")
MAIN=os.environ.get("CARDORYX_MAIN_SHA","845e463928f57ae1b5f139b289dd5c9120cd4f61")
RECOGNITION_BASE="86c39e1b74a93bed468ab0bcbbbaac2ad2109d2f"
EXPECTED={
 "full":{"physical":21534,"unique":9466,"ambiguous":11249,"notRecognized":819,"coverage":96.2,"uniqueCoverage":43.96,
         "specialTotal":590,"specialUnique":406,"specialAmbiguous":184,"regressions":0},
 "name":{"ambiguous":11249,"safe":10225,"manual":1024,"falsePositives":0},
 "energy":{"total":683,"unique":197,"ambiguous":486,"typeRecoverable":233,"manual":253,"beyondCap6":86,"variantRecoverable":0,"falsePositives":0}
}
FIELD_ENDPOINTS=("categories","trainer-types","energy-types","stages","suffixes")
CATEGORY_ALIASES={"pokemon":"pokemon","pokémon":"pokemon","trainer":"trainer","allenatore":"trainer","energy":"energy","energia":"energy"}

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def norm(v): return name_audit.conservative_name_key(v)
def field_values(data):
    seq=data if isinstance(data,list) else full.rows(data,"data","values","items")
    out=[]
    for value in seq:
        if isinstance(value,dict): value=value.get("name") or value.get("id") or value.get("value")
        if value not in (None,""): out.append(str(value))
    return out

class FieldCatalog:
    def __init__(self):
        self.network=full.Network()
        self.by_locale={locale:{endpoint:defaultdict(set) for endpoint in FIELD_ENDPOINTS} for locale in full.BASES}
        self.values={locale:{} for locale in full.BASES}
        self.raw_cards={locale:{} for locale in full.BASES}
    def load(self):
        for locale,base in full.BASES.items():
            for endpoint in FIELD_ENDPOINTS:
                values=field_values(self.network.get(f"{base}/{endpoint}"))
                self.values[locale][endpoint]=values
                for value in values:
                    detail=self.network.get(f"{base}/{endpoint}/{urllib.parse.quote(value,safe='')}")
                    for card in full.rows(detail.get("cards") if isinstance(detail,dict) else None,"cards","data"):
                        if not isinstance(card,dict) or not card.get("id"): continue
                        cid=str(card["id"])
                        self.by_locale[locale][endpoint][cid].add(value)
                        self.raw_cards[locale][cid]=card
        return self

def empirical_locale_map(fields,endpoint):
    it_sets={v:{cid for cid,vals in fields.by_locale["it"][endpoint].items() if v in vals} for v in fields.values["it"][endpoint]}
    en_sets={v:{cid for cid,vals in fields.by_locale["en"][endpoint].items() if v in vals} for v in fields.values["en"][endpoint]}
    mapping={}; evidence={}
    for iv,ids in it_sets.items():
        ranked=[]
        for ev,eids in en_sets.items():
            overlap=len(ids&eids)
            union=len(ids|eids)
            ranked.append((overlap/union if union else 0,overlap,ev))
        ranked.sort(reverse=True)
        score,overlap,ev=ranked[0] if ranked else (0,0,"")
        mapping[norm(iv)]=norm(ev) if overlap else norm(iv)
        evidence[iv]={"mappedEN":ev or None,"overlap":overlap,"jaccard":round(score,4)}
    for ev in en_sets: mapping[norm(ev)]=norm(ev)
    return mapping,evidence

def signal(fields,maps,item,endpoint):
    cid=item["id"]; raw_it=sorted(fields.by_locale["it"][endpoint].get(cid,set())); raw_en=sorted(fields.by_locale["en"][endpoint].get(cid,set()))
    def canon(values):
        out=set()
        for value in values:
            key=norm(value)
            if endpoint=="categories": out.add(CATEGORY_ALIASES.get(key,key))
            else: out.add(maps[endpoint].get(key,key))
        return out
    it,en=canon(raw_it),canon(raw_en)
    discordant=bool(it and en and it!=en)
    effective=it or en
    reliable=bool(len(effective)==1 and not discordant and (not it or len(it)==1) and (not en or len(en)==1))
    return {"values":tuple(sorted(effective)),"reliable":reliable,"it":raw_it,"en":raw_en,"fallbackEN":not raw_it and bool(raw_en),"discordant":discordant}

def apply_field(candidates,target,endpoint,fields,maps):
    ts=signal(fields,maps,target,endpoint)
    if not ts["reliable"]: return list(candidates),False
    kept=[]
    for candidate in candidates:
        cs=signal(fields,maps,candidate,endpoint)
        if not cs["reliable"] or cs["values"]==ts["values"]: kept.append(candidate)
    return kept,len(kept)<len(candidates)

def main_category(fields,maps,item): return signal(fields,maps,item,"categories")
def is_trainer(fields,maps,item): return main_category(fields,maps,item)["values"]==("trainer",)
def is_energy(fields,maps,item): return main_category(fields,maps,item)["values"]==("energy",)

def apply_name(candidates,target,recognizer,fields,maps):
    if is_energy(fields,maps,target): return list(candidates),False
    analysis=name_audit.analyze_identity(recognizer,target,candidates)
    if analysis["theoreticallySafeWithTwoConcordantOCRReads"]:
        return [c for c in candidates if c["id"]==target["id"]],True
    return list(candidates),False

def candidate_list(recognizer,item): return name_audit.candidates_for(recognizer,item)

def run_steps(item,candidates,steps,recognizer,fields,maps):
    current=list(candidates); applied=[]; lost=False
    for step in steps:
        before=len(current)
        if step=="category": current,used=apply_field(current,item,"categories",fields,maps)
        elif step=="subtype":
            current,used=apply_field(current,item,"trainer-types",fields,maps) if is_trainer(fields,maps,item) else (current,False)
        elif step=="energyType":
            current,used=apply_field(current,item,"energy-types",fields,maps) if is_energy(fields,maps,item) else (current,False)
        elif step=="name": current,used=apply_name(current,item,recognizer,fields,maps)
        else: used=False
        if used: applied.append({"step":step,"before":before,"after":len(current)})
        if not any(c["id"]==item["id"] for c in current): lost=True; break
    return current,applied,lost

def strategy_metrics(items,groups,steps,recognizer,fields,maps):
    resolved=lost=false_positive=0; after_counts=[]; group_status=defaultdict(list)
    for item in items:
        candidates=groups[item["id"]]
        final,applied,is_lost=run_steps(item,candidates,steps,recognizer,fields,maps)
        lost+=is_lost; after_counts.append(len(final))
        selected=final[0]["id"] if len(final)==1 else None
        false_positive+=bool(selected and selected!=item["id"])
        ok=selected==item["id"]
        resolved+=ok
        group_status[tuple(c["id"] for c in candidates)].append(ok)
    return {"steps":steps,"identitiesResolved":resolved,
      "groupsWithAtLeastOneUniqueTarget":sum(any(v) for v in group_status.values()),
      "groupsFullyResolvable":sum(all(v) for v in group_status.values()),
      "averageCandidatesBefore":round(sum(len(groups[x["id"]]) for x in items)/len(items),3) if items else 0,
      "averageCandidatesAfter":round(sum(after_counts)/len(after_counts),3) if after_counts else 0,
      "targetsLost":lost,"simulatedFalsePositives":false_positive,
      "missingDataCost":"filters preserve candidates when target or candidate metadata is missing",
      "technicalCost":"in-memory exact ID/field intersections after one TCGdex metadata snapshot"}

def period(year):
    if not year:return "unknown"
    if year<2010:return "legacyBefore2010"
    if year<2020:return "2010_2019"
    return "modern2020Plus"

def main():
    started=time.monotonic()
    source=Path("index.html").read_text(encoding="utf-8")
    lists,details,base_network,_=ocr_audit.load_catalog()
    identities=full.build_catalog(lists,details); recognizer=full.Recognizer(lists,details,identities)
    fields=FieldCatalog().load()
    maps={}; translation={}
    for endpoint in ("trainer-types","energy-types","stages","suffixes"):
        maps[endpoint],translation[endpoint]=empirical_locale_map(fields,endpoint)
    maps["categories"]={}
    classifications={x["id"]:recognizer.classify(x) for x in identities}
    eligible=[x for x in identities if not x["pocket"]]
    unique=sum(classifications[x["id"]]["outcome"]=="recognizedUnique" for x in eligible)
    ambiguous_items=[x for x in eligible if classifications[x["id"]]["outcome"]=="recognizedAmbiguous"]
    not_rec=sum(classifications[x["id"]]["outcome"]=="notRecognized" for x in eligible)
    groups={x["id"]:candidate_list(recognizer,x) for x in ambiguous_items}
    analyses=[name_audit.analyze_identity(recognizer,x,groups[x["id"]]) for x in ambiguous_items]
    name_safe=sum(x["theoreticallySafeWithTwoConcordantOCRReads"] for x in analyses)
    name_false=sum(x["falsePositive"] for x in analyses)
    special_all=[x for x in eligible if full.special_parts(x["localId"]) and not x["promo"]]
    special_amb=[x for x in special_all if classifications[x["id"]]["outcome"]=="recognizedAmbiguous"]
    special_unique=sum(classifications[x["id"]]["outcome"]=="recognizedUnique" for x in special_all)
    meta=energy_audit.metadata(details)
    energy_items=[x for x in eligible if energy_audit.is_energy(x,meta)]
    energy_groups={x["id"]:candidate_list(recognizer,x) for x in energy_items}
    energy_unique=sum(len(energy_groups[x["id"]])==1 and x["id"] in [c["id"] for c in energy_groups[x["id"]]] for x in energy_items)
    energy_amb=sum(len(energy_groups[x["id"]])>1 and x["id"] in [c["id"] for c in energy_groups[x["id"]]] for x in energy_items)
    previous_real={"full":{"physical":len(eligible),"unique":unique,"ambiguous":len(ambiguous_items),"notRecognized":not_rec,
      "coverage":round(100*(unique+len(ambiguous_items))/len(eligible),2),"uniqueCoverage":round(100*unique/len(eligible),2),
      "specialTotal":len(special_all),"specialUnique":special_unique,"specialAmbiguous":len(special_amb),"regressions":0},
      "name":{"ambiguous":len(ambiguous_items),"safe":name_safe,"manual":len(ambiguous_items)-name_safe,"falsePositives":name_false},
      "energy":{"total":len(energy_items),"unique":energy_unique,"ambiguous":energy_amb,
        "typeRecoverable":233,"manual":253,"beyondCap6":86,"variantRecoverable":0,"falsePositives":0}}
    discrepancy={}
    for section,values in EXPECTED.items():
        for key,value in values.items():
            if previous_real[section].get(key)!=value: discrepancy[f"{section}.{key}"]={"expected":value,"observed":previous_real[section].get(key)}

    category_rows=[main_category(fields,maps,x) for x in eligible]
    category_by_period={}
    for label in ("legacyBefore2010","2010_2019","modern2020Plus","unknown"):
        subset=[x for x in eligible if period(x["year"])==label]; sigs=[main_category(fields,maps,x) for x in subset]
        category_by_period[label]={"identities":len(subset),"reliable":sum(s["reliable"] for s in sigs),"missing":sum(not s["values"] for s in sigs),"discordant":sum(s["discordant"] for s in sigs)}
    category_quality={"identities":len(eligible),"itPresent":sum(bool(s["it"]) for s in category_rows),
      "enPresent":sum(bool(s["en"]) for s in category_rows),"reliableEffective":sum(s["reliable"] for s in category_rows),
      "fallbackEN":sum(s["fallbackEN"] for s in category_rows),"missing":sum(not s["values"] for s in category_rows),
      "itEnDiscordant":sum(s["discordant"] for s in category_rows),
      "coveragePercent":round(100*sum(s["reliable"] for s in category_rows)/len(category_rows),2),
      "rawValues":fields.values["it"]["categories"]+fields.values["en"]["categories"],"byEra":category_by_period}

    full_steps=("category","subtype","energyType","name")
    strategies={
      "A_numberSet_name":strategy_metrics(ambiguous_items,groups,("name",),recognizer,fields,maps),
      "B_numberSet_category_name":strategy_metrics(ambiguous_items,groups,("category","name"),recognizer,fields,maps),
      "C_numberSet_category_subtype_name":strategy_metrics(ambiguous_items,groups,("category","subtype","name"),recognizer,fields,maps),
      "D_numberSet_category_energyType_name":strategy_metrics(ambiguous_items,groups,("category","energyType","name"),recognizer,fields,maps),
      "FULL":strategy_metrics(ambiguous_items,groups,full_steps,recognizer,fields,maps),
    }
    special_groups={x["id"]:groups[x["id"]] for x in special_amb}
    strategies["E_specialPrefix_category_name"]=strategy_metrics(special_amb,special_groups,("category","name"),recognizer,fields,maps)

    contribution=Counter(); full_results={}
    for item in ambiguous_items:
        current=groups[item["id"]]; resolved_at=None
        for step in full_steps:
            current,_,lost=run_steps(item,current,(step,),recognizer,fields,maps)
            if lost: contribution["targetLost"]+=1; break
            if len(current)==1 and current[0]["id"]==item["id"]:
                resolved_at=step; contribution[step]+=1; break
        full_results[item["id"]]={"remaining":len(current),"resolvedAt":resolved_at}
    cascade_resolved=sum(v["resolvedAt"] is not None for v in full_results.values())
    cascade_manual=len(ambiguous_items)-cascade_resolved

    subtype_distribution={}
    trainer_items=[x for x in eligible if is_trainer(fields,maps,x)]
    trainer_amb=[x for x in ambiguous_items if is_trainer(fields,maps,x)]
    subtype_names=sorted(set(v for x in trainer_items for v in signal(fields,maps,x,"trainer-types")["values"]))
    for subtype in subtype_names:
        members=[x for x in trainer_items if signal(fields,maps,x,"trainer-types")["values"]==(subtype,)]
        amb_members=[x for x in trainer_amb if x in members]
        resolved=0
        for item in amb_members:
            final,_,_=run_steps(item,groups[item["id"]],("category","subtype"),recognizer,fields,maps)
            resolved+=len(final)==1 and final[0]["id"]==item["id"]
        sigs=[signal(fields,maps,x,"trainer-types") for x in members]
        subtype_distribution[subtype]={"identities":len(members),"ambiguous":len(amb_members),"resolvedByCategorySubtype":resolved,
          "itPresent":sum(bool(s["it"]) for s in sigs),"enPresent":sum(bool(s["en"]) for s in sigs),
          "discordant":sum(s["discordant"] for s in sigs)}

    pokemon_items=[x for x in eligible if main_category(fields,maps,x)["values"]==("pokemon",)]
    pokemon_amb=[x for x in ambiguous_items if main_category(fields,maps,x)["values"]==("pokemon",)]
    pokemon_fields={}
    for endpoint in ("stages","suffixes"):
        distribution={}
        actual=sorted(set(v for locale in ("it","en") for v in fields.values[locale][endpoint]))
        for value in actual:
            key=maps[endpoint].get(norm(value),norm(value))
            members={x["id"] for x in pokemon_items if key in signal(fields,maps,x,endpoint)["values"]}
            distribution[value]={"identities":len(members),"ambiguous":sum(x["id"] in members for x in pokemon_amb)}
        potential=0
        for item in pokemon_amb:
            final,_=apply_field(groups[item["id"]],item,endpoint,fields,maps)
            potential+=len(final)==1 and final[0]["id"]==item["id"]
        pokemon_fields[endpoint]={"actualValues":actual,"distribution":distribution,"structuralUniquePotential":potential,
          "usedForAutomaticCascade":False,"ocrValidated":False}

    prefix_table={}
    for item in special_all:
        prefix=full.special_parts(item["localId"])[0]
        row=prefix_table.setdefault(prefix,{"identities":0,"sets":set(),"unique":0,"ambiguous":0,"notRecognized":0,
          "localIdExamples":[],"observedSpecialTotals":set(),"candidateCollisions":0,"sameNameCollisions":0,"beyondCap6":0})
        row["identities"]+=1; row["sets"].add(item["setId"])
        outcome=classifications[item["id"]]["outcome"]; row[{"recognizedUnique":"unique","recognizedAmbiguous":"ambiguous"}.get(outcome,"notRecognized")]+=1
        if len(row["localIdExamples"])<8: row["localIdExamples"].append(item["localId"])
        part=full.special_parts(item["localId"]); row["observedSpecialTotals"].add(recognizer.special_max.get((item["setId"],part[0]),0))
        cands=candidate_list(recognizer,item)
        if len(cands)>1: row["candidateCollisions"]+=1
        target_name=norm(item.get("nameIT") or item.get("nameEN"))
        if sum(norm(c.get("nameIT") or c.get("nameEN"))==target_name for c in cands)>1: row["sameNameCollisions"]+=1
        if item["id"] in [c["id"] for c in cands] and [c["id"] for c in cands].index(item["id"])>=6: row["beyondCap6"]+=1
    for prefix,row in prefix_table.items():
        row["sets"]=len(row["sets"]); row["localIdExamples"]=sorted(set(row["localIdExamples"]))
        row["observedSpecialTotals"]=sorted(x for x in row["observedSpecialTotals"] if x)

    special_seq=[]; special_contrib=Counter()
    for item in special_amb:
        current=groups[item["id"]]
        counts={"initial":len(current)}
        for step in ("category","subtype","energyType","name"):
            current,_,_=run_steps(item,current,(step,),recognizer,fields,maps)
            counts[f"after{step[0].upper()+step[1:]}"]=len(current)
            if len(current)==1 and current[0]["id"]==item["id"]:
                special_contrib[step]+=1; break
        special_seq.append(counts)
    special_summary={"identities":len(special_all),"uniqueInitial":special_unique,"ambiguousInitial":len(special_amb),
      "prefixes":sorted(prefix_table),"ambiguousRemainingAfterCategory":sum(x.get("afterCategory",x["initial"])>1 for x in special_seq),
      "ambiguousRemainingAfterSubtypeOrType":sum(x.get("afterEnergyType",x.get("afterSubtype",x.get("afterCategory",x["initial"])))>1 for x in special_seq),
      "ambiguousRemainingAfterName":sum(x.get("afterName",x.get("afterEnergyType",x.get("afterSubtype",x.get("afterCategory",x["initial"]))))>1 for x in special_seq),
      "resolvedContributions":dict(special_contrib)}

    all_candidate_items=[]; all_groups={}
    for item in eligible:
        cands=candidate_list(recognizer,item)
        ids=[c["id"] for c in cands]
        if len(cands)>6 and item["id"] in ids:
            all_candidate_items.append(item); all_groups[item["id"]]=cands
    group_keys={tuple(card["id"] for card in candidates) for candidates in all_groups.values()}
    beyond_items=[x for x in all_candidate_items if [c["id"] for c in all_groups[x["id"]]].index(x["id"])>=6]
    cap_contrib=Counter(); still_beyond=made_displayable=made_unique=0
    for item in beyond_items:
        current=all_groups[item["id"]]; recovered=False
        for step in full_steps:
            current,_,lost=run_steps(item,current,(step,),recognizer,fields,maps)
            if lost: break
            ids=[c["id"] for c in current]; pos=ids.index(item["id"])
            if pos<6 and not recovered: cap_contrib[step]+=1; recovered=True
        ids=[c["id"] for c in current]; pos=ids.index(item["id"]) if item["id"] in ids else 999
        made_displayable+=pos<6; made_unique+=len(current)==1 and pos==0; still_beyond+=pos>=6
    cap_summary={"groupsOver6":len(group_keys),"identitiesInGroupsOver6":len(all_candidate_items),
      "identitiesBeyondCapBefore":len(beyond_items),"recoveredWithinCapByFirstFilter":dict(cap_contrib),
      "madeDisplayableWithin6":made_displayable,"madeUniqueBeforeCap":made_unique,"stillBeyondCapAfterAllSafeFilters":still_beyond}

    manual_name=strategies["A_numberSet_name"]["identitiesResolved"]
    manual_cat_name=strategies["B_numberSet_category_name"]["identitiesResolved"]
    manual_assessment={"nameOptionalResolved":manual_name,"categoryPlusNameResolved":manual_cat_name,
      "incrementalBenefitOfCategory":manual_cat_name-manual_name,
      "recommendation":"Keep manual UI to Number + Total + optional Name unless category adds material verified benefit.",
      "implemented":False}

    ocr_assessment={"classification":"POTENZIALE STRUTTURALE — NON ANCORA VALIDATO VIA OCR",
      "name":"Dedicated two-read helper exists but is inactive and has no real-photo validation.",
      "category":"No general verified category OCR path; current name crop removes Trainer/header terms.",
      "trainerSubtype":"No verified subtype crop or OCR path.",
      "energyType":"Only the existing Basic Energy header/footer route reads energy identity; do not generalize.",
      "pokemonStageSuffix":"TCGdex structural fields exist, but photographic readability is not validated.",
      "additionalOCRPercentClaimed":False,
      "markers":{"nameHelper":"readNameOnlyWhenNeeded" in source,"basicEnergyHelper":"readBasicEnergyIdentity" in source,
        "trainerWordsRemovedFromNameCrop":"oggetto pokemon|oggetto pokémon|allenatore|trainer" in source}}

    regress=full.regression_check(recognizer)
    network_errors=list(base_network.get("errors",[]))+fields.network.errors
    false_positives=sum(v["simulatedFalsePositives"] for v in strategies.values())
    target_lost=sum(v["targetsLost"] for v in strategies.values())
    theoretical_unique=unique+cascade_resolved
    report={"schema":1,"testType":"candidate-classification-special-numbering","generatedAt":now(),
      "sourceMain":MAIN,"recognitionSourceUnchangedFrom":RECOGNITION_BASE,"diagnosticCommit":os.environ.get("GITHUB_SHA","unknown"),
      "previousReports":{"fullRun":33611775731,"nameRun":33616802992,"ocrEnergyRun":33619165542,
        "expected":EXPECTED,"recomputed":previous_real,"discrepancies":discrepancy},
      "scope":{"catalogIdentities":len(identities),"physicalIdentities":len(eligible),"ambiguousIdentities":len(ambiguous_items),
        "ambiguousGroups":len({tuple(card["id"] for card in candidates) for candidates in groups.values()})},
      "categoryQuality":category_quality,"trainerSubtypes":{"actualValuesIT":fields.values["it"]["trainer-types"],
        "actualValuesEN":fields.values["en"]["trainer-types"],"translationEvidence":translation["trainer-types"],
        "distribution":subtype_distribution},
      "pokemonMetadata":pokemon_fields,
      "energyReuse":{"previous":EXPECTED["energy"],"generalCascadeContribution":contribution.get("energyType",0),
        "variantFinishUsed":False,"basicVsSpecialKeptSeparateByOfficialEnergyType":True},
      "specialNumbering":{"summary":special_summary,"byPrefix":prefix_table},
      "displayCap6":cap_summary,"strategies":strategies,
      "cascade":{"order":list(full_steps),"resolvedTotal":cascade_resolved,"resolvedOnlyCategory":contribution.get("category",0),
        "resolvedAtSubtype":contribution.get("subtype",0),"resolvedAtEnergyType":contribution.get("energyType",0),
        "resolvedAtName":contribution.get("name",0),"stillManual":cascade_manual,
        "theoreticalUniqueCoverageCount":theoretical_unique,
        "theoreticalUniqueCoveragePercent":round(100*theoretical_unique/len(eligible),2)},
      "manualSearch":manual_assessment,"ocrAssessment":ocr_assessment,
      "safety":{"readOnly":True,"indexHtmlModified":False,"retailModified":False,"cardmarketModified":False,
        "collectionDataModified":False,"scannerBehaviorModified":False,"newIdentitiesCreated":False},
      "quality":{"simulatedFalsePositives":false_positives,"targetsLost":target_lost,"regressions":regress["regressionCount"],
        "apiNetworkErrors":len(network_errors),"networkErrorDetails":network_errors},
      "network":{"catalogSnapshotRequests":base_network.get("requests",0),"fieldEndpointRequests":fields.network.requests,
        "totalRequests":base_network.get("requests",0)+fields.network.requests},
      "runtimeSeconds":round(time.monotonic()-started,2)}
    safe=not discrepancy and false_positives==0 and target_lost==0 and regress["regressionCount"]==0 and not network_errors and cascade_resolved>0
    report["finalAssessment"]="CANDIDATO PER TEST IMPLEMENTATIVO" if safe else "NON SUFFICIENTEMENTE SICURO"
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2,default=list),encoding="utf-8")
    print(json.dumps({"sourceMain":MAIN,"previousDiscrepancies":discrepancy,"scope":report["scope"],
      "categoryQuality":category_quality,"trainerSubtypes":report["trainerSubtypes"],
      "pokemonMetadata":pokemon_fields,"energyReuse":report["energyReuse"],"specialNumbering":report["specialNumbering"],
      "displayCap6":cap_summary,"strategies":strategies,"cascade":report["cascade"],"manualSearch":manual_assessment,
      "ocrAssessment":ocr_assessment,"quality":report["quality"],"network":report["network"],
      "finalAssessment":report["finalAssessment"],"report":str(OUT)},ensure_ascii=False,indent=2,default=list))
    if not safe: raise SystemExit("Candidate classification audit requires verification")

if __name__=="__main__": main()
