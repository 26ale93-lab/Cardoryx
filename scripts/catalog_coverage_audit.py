#!/usr/bin/env python3
"""Targeted read-only test of Cardoryx's current TCGdex recognition paths."""

import json, os, re, time, unicodedata, urllib.error, urllib.parse, urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

BASES={"it":"https://api.tcgdex.net/v2/it","en":"https://api.tcgdex.net/v2/en"}
OUTPUT=Path("artifacts/catalog_coverage_audit_report.json")
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
def get(url,attempts=3):
    err=None
    for n in range(1,attempts+1):
        try:
            q=urllib.request.Request(url,headers={"User-Agent":"Cardoryx-Targeted-Audit/1.0","Accept":"application/json"})
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
def prefix(v):
    m=re.fullmatch(r"([A-Za-z]+)[- ]*0*(\d+)",str(v or "").strip())
    return (m.group(1).upper(),int(m.group(2))) if m else None
def num_variants(v):
    raw=re.sub(r"\D","",str(v or "").strip())
    if not raw:return []
    n=str(int(raw));out=[]
    for x in (raw,n,n.zfill(2),n.zfill(3)):
        if x not in out:out.append(x)
    return out
def same_num(a,b):
    a=re.sub(r"\D","",str(a or "")).lstrip("0") or "0"
    b=re.sub(r"\D","",str(b or "")).lstrip("0") or "0"
    return a==b
def valid_code(a,b):
    try:a,b=int(a),int(b)
    except:return False
    return a>0 and b>0 and a<=b<=999
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
        it,en=cards["it"].get(cid),cards["en"].get(cid);c=it or en or {}
        sid=sets["it"].get(cid) or sets["en"].get(cid) or "";d=details["it"].get(sid) or details["en"].get(sid) or {}
        names=f"{it.get('name','') if it else ''} {en.get('name','') if en else ''}"
        out.append({"id":cid,"nameIT":it.get("name") if it else None,"nameEN":en.get("name") if en else None,"name":c.get("name"),"setId":sid,"setName":d.get("name"),"localId":c.get("localId"),"official":count(d,"official"),"total":count(d,"total"),"year":year(d),"pocket":pocket(d),"promo":bool(PROMO_RE.search(set_blob(d))),"subset":bool(SUBSET_RE.search(set_blob(d)) or prefix(c.get("localId"))),"basicEnergy":bool(ENERGY_RE.search(names) and BASIC_RE.search(names))})
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
    def __init__(self,ids,details):self.ids=ids;self.by={x["id"]:x for x in ids};self.details=details;self.cache={};self.errors=[]
    def set(self,sid):return self.details["it"].get(sid) or self.details["en"].get(sid) or {}
    def query(self,params):
        key=tuple(sorted(params.items()))
        if key in self.cache:return self.cache[key]
        query=urllib.parse.urlencode(params);merged={};order=[]
        for loc,base in BASES.items():
            try:result=rows(get(f"{base}/cards?{query}"),"cards","data")
            except Exception as e:self.errors.append({"locale":loc,"query":query,"error":str(e)});result=[]
            for c in result:
                cid=str(c.get("id") or "")
                if not cid:continue
                if cid not in merged:order.append(cid)
                merged[cid]=c
        self.cache[key]=[merged[cid] for cid in order];return self.cache[key]
    def any_local(self,n):
        merged={};order=[];tried=[]
        for v in num_variants(n):
            tried.append(v)
            for c in self.query({"localId":v}):
                cid=str(c.get("id") or "")
                if cid and cid not in merged:order.append(cid)
                if cid:merged[cid]=c
            if len(merged)>=20:break
        return [merged[cid] for cid in order],tried
    def full(self,c):
        x=self.by.get(str(c.get("id") or ""));
        if not x:return c
        return {**c,"id":x["id"],"localId":x["localId"],"name":x["nameIT"] or x["nameEN"],"set":{"id":x["setId"],"name":x["setName"]}}
    def hinted(self,n,t):
        h=HINTS.get(f"{int(n)}/{int(t)}")
        if not h:return None
        wanted=int(re.sub(r"\D","",h["localId"]))
        return next((x for x in self.ids if x["setId"].lower()==h["setId"] and numeric(x["localId"])==wanted),None)
    def printed(self,n,t):
        trace={"hintUsed":False,"variantsTried":[],"briefCandidates":0,"briefCandidatesChecked":0,"matchingCandidates":0,"fallbackUsed":False}
        if not str(n) or not str(t):return [],trace
        h=self.hinted(n,t)
        if h:trace.update(hintUsed=True,matchingCandidates=1);return [h],trace
        briefs,tried=self.any_local(n);trace.update(variantsTried=tried,briefCandidates=len(briefs))
        found={};order=[]
        for b in briefs[:60]:
            trace["briefCandidatesChecked"]+=1;f=self.full(b)
            if not f.get("id") or not same_num(f.get("localId"),n):continue
            sid=(f.get("set") or {}).get("id") or (b.get("set") or {}).get("id")
            if not sid or count(self.set(str(sid)),"official")!=int(t):continue
            cid=str(f["id"])
            if cid not in found:order.append(cid)
            found[cid]=self.by.get(cid,f)
        if found:
            out=[found[c] for c in order];trace["matchingCandidates"]=len(out);return out,trace
        trace["fallbackUsed"]=True
        for b in briefs[:60]:
            f=self.full(b);sid=(f.get("set") or {}).get("id") or (b.get("set") or {}).get("id")
            if sid and count(self.set(str(sid)),"official")==int(t):
                x=self.by.get(str(f.get("id") or ""))
                if x and same_num(x["localId"],n):trace["matchingCandidates"]=1;return [x],trace
        return [],trace
    def manual_name(self,target,n,t=""):
        name=target["nameIT"] or target["nameEN"] or "";raw=self.query({"name":name}) if name else [];full=[self.full(x) for x in raw[:40]]
        exact=[x for x in full if norm(x.get("name"))==norm(name)];result=exact or full
        if result and t:
            same=[x for x in result if count(self.set(str((x.get("set") or {}).get("id") or "")),"official")==int(t)]
            if same:result=same
        if result and n:
            same=[x for x in result if same_num(x.get("localId"),n)]
            if same:result=same
        shown=[str(x.get("id") or "") for x in result[:8]]
        return {"available":target["id"] in shown,"nameCandidates":len(raw),"candidatesChecked":min(40,len(raw)),"displayedCandidates":min(8,len(result)),"targetDisplayed":target["id"] in shown}

def subset_code(x,pmax):
    p=prefix(x["localId"])
    if not p:return str(x["localId"] or "")
    total=pmax.get((x["setId"],p[0]));return f"{p[0]}{p[1]}/{p[0]}{total}" if total else f"{p[0]}{p[1]}"

def run_case(sim,x,category,pmax,pairs):
    lid=str(x["localId"] or "");n=numeric(lid);off=int(x["official"] or 0);code="";inp="";total="";failure=None;point=None;found=[]
    trace={"hintUsed":False,"variantsTried":[],"briefCandidates":0,"briefCandidatesChecked":0,"matchingCandidates":0,"fallbackUsed":False};energy=False
    sid=x["setId"].lower()
    if x["basicEnergy"] and n is not None and ((sid=="sve" and 1<=n<=24) or (sid=="mee" and 1<=n<=16)):
        energy=True;code=f"{sid.upper()} IT {n:03d}";found=[x]
    elif category in {"standard","secret"}:
        inp,total=str(n or ""),str(off or "");code=f"{inp}/{total}" if inp and total else ""
        if not valid_code(inp,total):failure="secretNumeratorGreaterThanDenominator" if n and off and n>off else "collectorCodeInvalid";point="index.html: collectorCodeValid() / runSmartOCR()"
        else:found,trace=sim.printed(inp,total)
    elif category=="subsetSpecialNumbering":
        code=subset_code(x,pmax);p=prefix(lid);inp=str(p[1]) if p else "";total=str(pmax.get((x["setId"],p[0]),"")) if p else ""
        if not inp or not total:failure="alphanumericPrintedCodeNotExtractable";point="index.html: extractCollectorCode() numeric-only pattern"
        elif not valid_code(inp,total):failure="alphanumericPrintedCodeRejected";point="index.html: collectorCodeValid()"
        else:found,trace=sim.printed(inp,total)
    else:code=f"{x['setId']} {lid}".strip();failure="promoCodeHasNoNumberTotalPair";point="index.html: readCollectorCodeFocused() / extractCollectorCode()"
    ids=[z.get("id") for z in found];shown=ids[:6];success=x["id"] in shown
    if not success and failure is None:
        if trace["hintUsed"]:failure="hardcodedHintReturnedDifferentCard";point="index.html: PRINTED_CODE_HINTS / fetchHintedPrintedCard()"
        elif x["id"] in ids:failure="targetBeyondPhotoDisplaySlice6";point="index.html: runSmartOCR() cards.slice(0,6)"
        else:
            briefs,_=sim.any_local(inp);bids=[str(z.get("id") or "") for z in briefs]
            if x["id"] not in bids:failure="targetMissingFromLocalIdQuery";point="index.html: queryByAnyLocalId()"
            elif x["id"] not in bids[:60]:failure="targetBeyondSlice60";point="index.html: queryByPrintedCode() briefs.slice(0,60)"
            else:failure="setOfficialOrLocalIdVerificationFailed";point="index.html: queryByPrintedCode() verification"
    pair=f"{n}/{off}" if n is not None and off else "";previous=(category!="standard" or trace["briefCandidates"]>60 or pairs.get(pair,0)>8 or pair in HINTS)
    manual=sim.manual_name(x,inp or re.sub(r"\D","",lid),total if category not in {"promo","subsetSpecialNumbering"} else "") if not success else {"available":None,"notRunBecauseAutomaticSucceeded":True}
    return {"id":x["id"],"name":x["nameIT"] or x["nameEN"],"setId":x["setId"],"set":x["setName"],"releaseYear":x["year"],"localId":lid,"cardCountOfficial":off,"printedCodeSimulated":code,"currentPath":"codedBasicEnergy" if energy else "photoNumberTotal","outcome":"recognized" if success else "notRecognized","trueFalseNegative":not success,"apparentPreviousAuditFalseNegative":bool(success and previous),"failureReason":failure,"exactCodePoint":point,"manualNameRouteRecovery":manual,"trace":{**trace,"returnedCandidateIds":ids[:15],"photoDisplayedCandidateIds":shown,"previousAuditPairSize":pairs.get(pair,0)}}

def summarize(category,cases):
    tested=len(cases);ok=sum(x["outcome"]=="recognized" for x in cases);true=sum(x["trueFalseNegative"] for x in cases);apparent=sum(x["apparentPreviousAuditFalseNegative"] for x in cases);manual=sum(x["manualNameRouteRecovery"].get("available") is True for x in cases);reasons=Counter(x["failureReason"] for x in cases if x["failureReason"]);fail=[x for x in cases if x["trueFalseNegative"]]
    return {"category":category,"tested":tested,"successes":ok,"trueFalseNegatives":true,"apparentPreviousAuditFalseNegatives":apparent,"manualNameRouteRecoveriesAmongFailures":manual,"realRecognitionPercent":round(100*ok/tested,2) if tested else None,"failureReasons":dict(reasons.most_common()),"examples":(fail or cases)[:15]}

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
    identities=make_identities(details);physical=[x for x in identities if not x["pocket"]];pmax=defaultdict(int);pairs=Counter()
    for x in physical:
        p=prefix(x["localId"])
        if p:pmax[(x["setId"],p[0])]=max(pmax[(x["setId"],p[0])],p[1])
        n=numeric(x["localId"])
        if n is not None and x["official"]:pairs[f"{n}/{x['official']}"]+=1
    pools={k:[] for k in TARGETS}
    for x in physical:
        n=numeric(x["localId"]);off=x["official"]
        if x["promo"]:pools["promo"].append(x)
        elif x["subset"]:pools["subsetSpecialNumbering"].append(x)
        elif n is not None and off and n>off:pools["secret"].append(x)
        elif n is not None and off and n<=off:pools["standard"].append(x)
    samples={k:sample(pools[k],v) for k,v in TARGETS.items()}
    controls=sample([x for x in pools["standard"] if x["basicEnergy"] and x["setId"].lower() in {"sve","mee"}],6)
    if controls:
        cids={x["id"] for x in controls};samples["standard"]=(controls+[x for x in samples["standard"] if x["id"] not in cids])[:50]
    sim=Sim(identities,details);results={k:[run_case(sim,x,k,pmax,pairs) for x in samples[k]] for k in TARGETS};cats={k:summarize(k,v) for k,v in results.items()};tested=sum(x["tested"] for x in cats.values());ok=sum(x["successes"] for x in cats.values());true=sum(x["trueFalseNegatives"] for x in cats.values());apparent=sum(x["apparentPreviousAuditFalseNegatives"] for x in cats.values());reasons=Counter()
    for x in cats.values():reasons.update(x["failureReasons"])
    report={"schema":1,"testType":"targeted-recognition-false-negative","generatedAt":now(),"source":"TCGdex v2 IT + EN","sourceCommit":os.environ.get("GITHUB_SHA","unknown"),"rules":{"readOnly":True,"indexHtmlModified":False,"retailPricesModified":False,"cardmarketTouched":False,"collectionDataModified":False,"newIdentitiesCreated":False,"productionWorkflowModified":False,"retailSystemModified":False,"automaticCorrectionsApplied":False,"currentLogicReused":["apiCardsQuery IT+EN Map merge","numVariants","queryByAnyLocalId break>=20","PRINTED_CODE_HINTS first","queryByPrintedCode slice(0,60)","cardCount.official equality","sameCollectorNumber","manual name slice(0,40)","number-only slice(0,30)","manual display slice(0,8)","photo display slice(0,6)","SVE/MEE Basic Energy resolver"]},"scope":{"setsITRead":len(details["it"]),"setsENRead":len(details["en"]),"setErrorsIT":len(errors["it"]),"setErrorsEN":len(errors["en"]),"catalogIdentitiesAvailable":len(identities),"physicalIdentitiesEligibleForSampling":len(physical),"pocketIdentitiesExcludedFromSampleOnly":len(identities)-len(physical),"identitiesAnalyzed":tested,"requestedSample":TARGETS,"actualSample":{k:len(v) for k,v in samples.items()},"runtimeSeconds":round(time.monotonic()-started,2),"networkQueryErrors":len(sim.errors)},"summary":{"tested":tested,"successes":ok,"trueFalseNegatives":true,"apparentPreviousAuditFalseNegatives":apparent,"realRecognitionPercent":round(100*ok/tested,2) if tested else 0,"identifiableWithCurrentMethod":ok,"potentialFalseNegatives":true,"estimatedCoveragePercent":round(100*ok/tested,2) if tested else 0,"failureReasons":dict(reasons.most_common()),"interpretation":"Live-query simulation of current Cardoryx paths; OCR image accuracy is outside scope."},"categories":cats,"caseResults":results,"minimumPotentialFixes":[{"finding":"secretNumeratorGreaterThanDenominator","potentialMinimumChange":"Allow numerator > denominator only after exact localId and cardCount.official verification.","applied":False},{"finding":"targetBeyondSlice60","potentialMinimumChange":"Prioritize exact official-count sets before the existing 60-item cap.","applied":False},{"finding":"hardcodedHintReturnedDifferentCard","potentialMinimumChange":"Do not short-circuit on an unverified pair hint.","applied":False}],"finalAssessment":{"safeToFix":["Verify/remove pair-hint short-circuiting.","Narrow by cardCount.official before slice(0,60).","Allow secret numerator > denominator only with downstream exact-set verification."],"requiresSpecialRule":["Subset prefixes and subset denominators (TG/GG/RC/SV/etc.).","Promo codes without number/total pairs.","Basic Energy families outside SVE/MEE."],"doNotGeneralize":["Do not strip alphanumeric prefixes globally.","Do not replace cardCount.official with total globally.","Do not accept localId without set verification.","Do not create EN-only or Pocket identities automatically.","Do not remove caps without narrowing candidates first."]},"networkQueryErrors":sim.errors,"setDetailErrors":errors}
    OUTPUT.parent.mkdir(parents=True,exist_ok=True);OUTPUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"scope":report["scope"],"summary":report["summary"],"categories":{k:{a:b for a,b in v.items() if a!="examples"} for k,v in cats.items()},"report":str(OUTPUT)},ensure_ascii=False,indent=2))
if __name__=="__main__":main()
