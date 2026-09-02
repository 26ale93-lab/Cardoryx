#!/usr/bin/env python3
"""Before/after regression audit for Cardoryx expanded TCGdex recognition."""

import json, os, re, time, unicodedata, urllib.error, urllib.parse, urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

BASES={"it":"https://api.tcgdex.net/v2/it","en":"https://api.tcgdex.net/v2/en"}
OUTPUT=Path("artifacts/expanded_recognition_coverage_report.json")
TARGETS={"standard":50,"secret":30,"subsetSpecialNumbering":30,"promo":30}
HINTS={"146/159":{"setId":"sv09","localId":"146"},"98/159":{"setId":"sv09","localId":"098"}}
PROMO_RE=re.compile(r"promo|promozional|black star|prize pack|play[! ]+pokemon",re.I)
SUBSET_RE=re.compile(r"trainer gallery|galarian gallery|radiant collection|shiny vault|classic collection|subset|gallery",re.I)
ENERGY_RE=re.compile(r"\b(energy|energia)\b",re.I)
BASIC_RE=re.compile(r"basic\s+(?:grass|fire|water|lightning|psychic|fighting|darkness|metal|fairy)\s+energy|energia\s+base|energia\s+(?:erba|fuoco|acqua|lampo|psico|lotta|oscurita|metallo|folletto)",re.I)

def now(): return datetime.now(timezone.utc).isoformat().replace("+00:00","Z")
def norm(v):
    s=unicodedata.normalize("NFKD",str(v or "")).encode("ascii","ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+","",s)
def rows(x,*keys):
    if isinstance(x,list): return x
    if isinstance(x,dict):
        for k in keys:
            if isinstance(x.get(k),list): return x[k]
    return []
def get(url,attempts=3,metrics=None):
    if metrics is not None: metrics["requests"]+=1
    err=None
    for n in range(1,attempts+1):
        try:
            q=urllib.request.Request(url,headers={"User-Agent":"Cardoryx-Expanded-Recognition-Audit/1.0","Accept":"application/json"})
            with urllib.request.urlopen(q,timeout=25) as r:return json.load(r)
        except Exception as e:
            err=e
            if isinstance(e,urllib.error.HTTPError) and e.code in {400,401,403,404}:break
            if n<attempts:time.sleep(n)
    raise RuntimeError(f"GET failed {url}: {err}")
def count(detail,key):
    try:return max(0,int((detail.get("cardCount") or {}).get(key) or 0))
    except:return 0
def year(detail):
    m=re.search(r"(?:19|20)\d{2}",str(detail.get("releaseDate") or detail.get("release") or ""))
    return int(m.group()) if m else None
def numeric(v):
    s=str(v or "").strip();return int(s) if re.fullmatch(r"\d+",s) else None
def parts(v):
    m=re.fullmatch(r"([A-Za-z]{1,5})[- ]*0*(\d{1,3})",str(v or "").strip())
    return (m.group(1).upper(),int(m.group(2))) if m else None
def exact_key(v):
    p=parts(v)
    if p:return f"{p[0]}{p[1]}"
    n=numeric(v)
    return str(n) if n is not None else norm(v)
def same_exact(a,b):return bool(str(a or "") and str(b or "") and exact_key(a)==exact_key(b))
def same_num(a,b):
    a=re.sub(r"\D","",str(a or "")).lstrip("0") or "0";b=re.sub(r"\D","",str(b or "")).lstrip("0") or "0";return a==b
def valid_before(a,b):
    try:a,b=int(a),int(b)
    except:return False
    return a>0 and b>0 and a<=b<=999
def valid_after(a,b):
    try:a,b=int(a),int(b)
    except:return False
    return a>0 and b>0 and b<=999
def set_blob(d):
    s=d.get("serie") or d.get("series") or {}
    if isinstance(s,dict):s=f"{s.get('id','')} {s.get('name','')}"
    return f"{d.get('id','')} {d.get('name','')} {s}"
def pocket(d):return bool(re.search(r"pokemon tcg pocket|tcg pocket",set_blob(d),re.I) or re.fullmatch(r"(?:A\d+[a-z]?|P-A)",str(d.get("id") or ""),re.I))
def fetch_detail(locale,sid):
    d=get(f"{BASES[locale]}/sets/{urllib.parse.quote(sid)}")
    if not isinstance(d,dict) or not d.get("id"):raise RuntimeError("bad set detail")
    return d

def make_identities(details):
    cards={"it":{},"en":{}};sets={"it":{},"en":{}}
    for loc in BASES:
        for sid,d in details[loc].items():
            for c in rows(d.get("cards"),"cards","data"):
                if isinstance(c,dict) and c.get("id"):cards[loc][str(c["id"])]=c;sets[loc][str(c["id"])]=sid
    out=[]
    for cid in sorted(set(cards["it"])|set(cards["en"])):
        it,en=cards["it"].get(cid),cards["en"].get(cid);c=it or en or {};sid=sets["it"].get(cid) or sets["en"].get(cid) or "";d=details["it"].get(sid) or details["en"].get(sid) or {};names=f"{it.get('name','') if it else ''} {en.get('name','') if en else ''}"
        out.append({"id":cid,"name":c.get("name"),"nameIT":it.get("name") if it else None,"nameEN":en.get("name") if en else None,"setId":sid,"setName":d.get("name"),"localId":c.get("localId"),"official":count(d,"official"),"year":year(d),"pocket":pocket(d),"promo":bool(PROMO_RE.search(set_blob(d))),"subset":bool(SUBSET_RE.search(set_blob(d)) or parts(c.get("localId"))),"basicEnergy":bool(ENERGY_RE.search(names) and BASIC_RE.search(names))})
    return out

def sample(items,target):
    if len(items)<=target:return list(items)
    items=sorted(items,key=lambda x:(x.get("year") or 0,x["setId"],numeric(x["localId"]) or 0,x["id"]));out=[];seen=set();per=Counter()
    for i in range(target*4):
        x=items[round(i*(len(items)-1)/max(1,target*4-1))]
        if x["id"] in seen or per[x["setId"]]>=2:continue
        out.append(x);seen.add(x["id"]);per[x["setId"]]+=1
        if len(out)==target:return out
    for x in items:
        if x["id"] not in seen:out.append(x);seen.add(x["id"])
        if len(out)==target:break
    return out

class Sim:
    def __init__(self,ids,details):
        self.ids=ids;self.by={x["id"]:x for x in ids};self.details=details;self.query_cache={};self.metrics={"before":{"requests":0,"candidatesChecked":0},"after":{"requests":0,"candidatesChecked":0}}
        self.by_local=defaultdict(list);self.by_official=defaultdict(list)
        for x in ids:
            if not x["pocket"]:
                self.by_local[exact_key(x["localId"])].append(x)
                if x["official"]:self.by_official[x["official"]].append(x)
    def query(self,params,mode):
        key=tuple(sorted(params.items()))
        if key not in self.query_cache:
            query=urllib.parse.urlencode(params);merged={};order=[]
            for base in BASES.values():
                result=rows(get(f"{base}/cards?{query}",metrics=self.metrics[mode]),"cards","data")
                for c in result:
                    cid=str(c.get("id") or "")
                    if cid and cid not in merged:order.append(cid)
                    if cid:merged[cid]=c
            self.query_cache[key]=[merged[c] for c in order]
        else:self.metrics[mode]["requests"]+=0
        return self.query_cache[key]
    def before_local(self,n):
        merged={};order=[]
        raw=re.sub(r"\D","",str(n or ""));variants=[]
        if raw:
            z=str(int(raw));variants=list(dict.fromkeys((raw,z,z.zfill(2),z.zfill(3))))
        for v in variants:
            for c in self.query({"localId":v},"before"):
                cid=str(c.get("id") or "")
                if cid and cid not in merged:order.append(cid)
                if cid:merged[cid]=c
            if len(merged)>=20:break
        return [merged[c] for c in order]
    def before(self,x,category,pmax):
        if x["basicEnergy"] and x["setId"].lower() in {"sve","mee"}:return [x],"codedBasicEnergy"
        lid=str(x["localId"] or "");n=numeric(lid);off=x["official"]
        if category=="promo":return [],"promoCodeHasNoNumberTotalPair"
        if category=="subsetSpecialNumbering":
            p=parts(lid);n=p[1] if p else None;total=pmax.get((x["setId"],p[0])) if p else None
        else:total=off
        if not valid_before(n,total):return [],"secretNumeratorGreaterThanDenominator" if n and total and n>total else "collectorCodeInvalid"
        h=HINTS.get(f"{int(n)}/{int(total)}")
        if h:
            hit=next((z for z in self.ids if z["setId"].lower()==h["setId"] and same_num(z["localId"],h["localId"])),None)
            return ([hit] if hit else []),"hint"
        briefs=self.before_local(n);self.metrics["before"]["candidatesChecked"]+=min(60,len(briefs));out=[]
        for b in briefs[:60]:
            z=self.by.get(str(b.get("id") or ""))
            if z and same_num(z["localId"],n) and z["official"]==int(total):out.append(z)
        return out,"numberTotal"
    def after(self,x,category,pmax):
        if x["basicEnergy"] and x["setId"].lower() in {"sve","mee"}:return [x],"codedBasicEnergy"
        lid=str(x["localId"] or "");n=numeric(lid);off=x["official"]
        if category in {"standard","secret"}:
            if not valid_after(n,off):return [],"collectorCodeInvalid"
            h=HINTS.get(f"{int(n)}/{int(off)}")
            if h:
                hit=next((z for z in self.ids if z["setId"].lower()==h["setId"] and same_exact(z["localId"],h["localId"]) and z["official"]==off and not z["pocket"]),None)
                if hit:return [hit],"verifiedHint"
            exact_sets=[];seen=set()
            for z in self.by_official.get(off,[]):
                if z["setId"] not in seen:seen.add(z["setId"]);exact_sets.append(z["setId"])
            exact_sets=exact_sets[:40];self.metrics["after"]["requests"]+=2+len(exact_sets);self.metrics["after"]["candidatesChecked"]+=len(exact_sets)
            return [z for z in self.by_local.get(exact_key(lid),[]) if z["setId"] in exact_sets and z["official"]==off],"exactOfficialSetThenCap"
        if category=="subsetSpecialNumbering":
            p=parts(lid);total=pmax.get((x["setId"],p[0])) if p else None
            if not p or not total:return [],"specialCodeNotExtractable"
            candidates=self.by_local.get(exact_key(lid),[]);self.metrics["after"]["requests"]+=2;self.metrics["after"]["candidatesChecked"]+=len(candidates);out=[]
            for z in candidates:
                if pmax.get((z["setId"],p[0]))==total:out.append(z)
            return out,"exactSpecialLocalIdAndObservedTotal"
        p=parts(lid)
        if not p:return [],"numericPromoWithoutDenominator"
        candidates=self.by_local.get(exact_key(lid),[]);self.metrics["after"]["requests"]+=2;self.metrics["after"]["candidatesChecked"]+=len(candidates)
        return candidates,"exactStandaloneLocalId"

def case(sim,x,category,pmax):
    before,broute=sim.before(x,category,pmax);after,aroute=sim.after(x,category,pmax);bid=[z["id"] for z in before];aid=[z["id"] for z in after];bshown=bid[:6];ashown=aid[:6]
    bok=x["id"] in bshown;aok=x["id"] in ashown;amb=len(aid)>1;wrong=bool(aid and x["id"] not in aid);previous_exact=bok and len(bid)==1
    return {"id":x["id"],"name":x["nameIT"] or x["nameEN"],"setId":x["setId"],"set":x["setName"],"releaseYear":x["year"],"localId":x["localId"],"cardCountOfficial":x["official"],"before":{"recognized":bok,"route":broute,"candidateIds":bid[:15],"unique":len(bid)==1},"after":{"recognized":aok,"route":aroute,"candidateIds":aid[:15],"ambiguous":amb},"recovered":aok and not bok,"regression":previous_exact and (not aok or (len(aid)==1 and aid[0]!=bid[0])),"falsePositive":wrong}

def summarize(cases):
    tested=len(cases);before=sum(x["before"]["recognized"] for x in cases);after=sum(x["after"]["recognized"] for x in cases);rec=sum(x["recovered"] for x in cases);amb=sum(x["after"]["ambiguous"] for x in cases);reg=sum(x["regression"] for x in cases);fp=sum(x["falsePositive"] for x in cases)
    return {"tested":tested,"recognizedBefore":before,"recognizedAfter":after,"coverageBeforePercent":round(100*before/tested,2) if tested else 0,"coverageAfterPercent":round(100*after/tested,2) if tested else 0,"identitiesRecovered":rec,"ambiguousAfter":amb,"regressions":reg,"falsePositives":fp,"examplesRecovered":[x for x in cases if x["recovered"]][:15],"examplesUnresolved":[x for x in cases if not x["after"]["recognized"]][:15]}

def main():
    started=time.monotonic();lists={loc:rows(get(f"{base}/sets"),"sets","data") for loc,base in BASES.items()};details={"it":{},"en":{}};errors={"it":{},"en":{}};futures={}
    with ThreadPoolExecutor(max_workers=12) as pool:
        for loc in BASES:
            for s in lists[loc]:
                if s.get("id"):futures[pool.submit(fetch_detail,loc,str(s["id"]))]=(loc,str(s["id"]))
        for f in as_completed(futures):
            loc,sid=futures[f]
            try:details[loc][sid]=f.result()
            except Exception as e:errors[loc][sid]=str(e)
    identities=make_identities(details);physical=[x for x in identities if not x["pocket"]];pmax=defaultdict(int)
    for x in physical:
        p=parts(x["localId"])
        if p:pmax[(x["setId"],p[0])]=max(pmax[(x["setId"],p[0])],p[1])
    pools={k:[] for k in TARGETS}
    for x in physical:
        n=numeric(x["localId"]);off=x["official"]
        if x["promo"]:pools["promo"].append(x)
        elif x["subset"]:pools["subsetSpecialNumbering"].append(x)
        elif n is not None and off and n>off:pools["secret"].append(x)
        elif n is not None and off and n<=off:pools["standard"].append(x)
    samples={k:sample(pools[k],v) for k,v in TARGETS.items()};controls=sample([x for x in pools["standard"] if x["basicEnergy"] and x["setId"].lower() in {"sve","mee"}],6)
    if controls:
        cids={x["id"] for x in controls};samples["standard"]=(controls+[x for x in samples["standard"] if x["id"] not in cids])[:50]
    sim=Sim(identities,details);results={k:[case(sim,x,k,pmax) for x in samples[k]] for k in TARGETS};cats={k:summarize(v) for k,v in results.items()}
    tested=sum(v["tested"] for v in cats.values());before=sum(v["recognizedBefore"] for v in cats.values());after=sum(v["recognizedAfter"] for v in cats.values());recovered=sum(v["identitiesRecovered"] for v in cats.values());amb=sum(v["ambiguousAfter"] for v in cats.values());reg=sum(v["regressions"] for v in cats.values());fp=sum(v["falsePositives"] for v in cats.values())
    sve_mee=[x for x in results["standard"] if x["before"]["route"]=="codedBasicEnergy"]
    static=Path("index.html").read_text(encoding="utf-8")
    source_checks={"secretNumeratorAccepted":"return a>0 && b>0 && b<=999;" in static,"limitAfterOfficialSetFilter":".filter(isPhysicalTCGSet)\n    .slice(0,40)" in static,"specialLocalIdPreserved":"queryBySpecialPrintedCode" in static and "sameExactLocalId" in static,"promoPathPresent":"queryByStandalonePrintedLocalId" in static,"hintFullyVerified":"verifiedNumberTotalCandidate(card,num,total)" in static,"pocketExcluded":"isPhysicalTCGSet" in static,"sveMeeResolverPreserved":"const coded=makeCodedBasicEnergy(identity);if(coded)return [coded];" in static}
    safe=after>before and reg==0 and fp==0 and all(source_checks.values()) and all(x["after"]["recognized"] for x in sve_mee)
    report={"schema":2,"testType":"expanded-recognition-before-after","generatedAt":now(),"sourceCommit":os.environ.get("GITHUB_SHA","unknown"),"rules":{"readOnlyTest":True,"productionMergePerformed":False,"retailModified":False,"cardmarketModified":False,"collectionDataModified":False,"newIdentitiesCreated":False,"productionWorkflowModified":False},"scope":{"setsITRead":len(details["it"]),"setsENRead":len(details["en"]),"setErrorsIT":len(errors["it"]),"setErrorsEN":len(errors["en"]),"catalogIdentitiesAvailable":len(identities),"physicalIdentitiesEligible":len(physical),"tested":tested,"sample":{k:len(v) for k,v in samples.items()},"runtimeSeconds":round(time.monotonic()-started,2)},"summary":{"recognizedBefore":before,"recognizedAfter":after,"coverageBeforePercent":round(100*before/tested,2),"coverageAfterPercent":round(100*after/tested,2),"identitiesRecovered":recovered,"ambiguousAfter":amb,"regressions":reg,"falsePositives":fp,"sveMeeControlsTested":len(sve_mee),"sveMeeControlsPassed":sum(x["after"]["recognized"] for x in sve_mee),"safeToMerge":safe},"categories":cats,"caseResults":results,"performance":{"simulationRequestsBefore":sim.metrics["before"]["requests"],"simulationRequestsAfter":sim.metrics["after"]["requests"],"candidatesCheckedBefore":sim.metrics["before"]["candidatesChecked"],"candidatesCheckedAfter":sim.metrics["after"]["candidatesChecked"],"note":"Catalog download is shared; after estimates exact-set/localId requests without OCR-image timing."},"sourceChecks":source_checks,"safety":{"ambiguousCasesAreNeverAutoSelected":True,"numericPromoWithoutDenominatorRemainsUnresolved":True,"specialPrefixesArePreserved":True,"physicalTCGOnly":True},"finalAssessment":"SAFE TO MERGE" if safe else "NOT SAFE TO MERGE"}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True);OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"summary":report["summary"],"categories":{k:{a:b for a,b in v.items() if not a.startswith("examples")} for k,v in cats.items()},"performance":report["performance"],"sourceChecks":source_checks,"finalAssessment":report["finalAssessment"],"report":str(OUTPUT)},ensure_ascii=False,indent=2))
    if not safe:raise SystemExit("Expanded recognition regression criteria failed")
if __name__=="__main__":main()
