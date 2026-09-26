#!/usr/bin/env python3
"""Read-only comparison: JustTCG vs PkmnPrices vs PokemonPriceTracker.

Uses the same exact TCGPlayer identities across all three sources.
No production data writes.
"""

from __future__ import annotations
import json, os, time, urllib.error, urllib.parse, urllib.request
from collections import defaultdict

JUST="https://api.justtcg.com/v1"
PKMN="https://api.pkmnprices.com/v1"
PPT="https://www.pokemonpricetracker.com/api/v2"
JUST_SET="me-ascended-heroes-pokemon"
PKMN_SET_ID=632

PROBES=[
    {"finish":"Normal","number":"001","tcg":"675813"},
    {"finish":"Holo","number":"003","tcg":"675815"},
    {"finish":"Reverse Holo","number":"180","tcg":"675992"},
    {"finish":"Cosmos Holo","number":"007","tcg":"679253"},
    {"finish":"Energy Reverse Holo","number":"001","tcg":"676992"},
    {"finish":"Friend Ball Reverse Holo","number":"008","tcg":"676858"},
    {"finish":"Love Ball Reverse Holo","number":"011","tcg":"676860"},
    {"finish":"Quick Ball Reverse Holo","number":"017","tcg":"676866"},
    {"finish":"Dusk Ball Reverse Holo","number":"044","tcg":"676888"},
    {"finish":"Poké Ball Reverse Holo","number":"001","tcg":"676852"},
    {"finish":"Team Rocket Reverse Holo","number":"018","tcg":"676867"},
]

def fail(msg, details=None):
    out={"result":"FAIL_CLOSED","message":msg}
    if details is not None: out["details"]=details
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))
    raise SystemExit(1)

def req_json(url,headers):
    req=urllib.request.Request(url,headers=headers,method="GET")
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            return json.loads(r.read().decode("utf-8")), dict(r.headers)
    except urllib.error.HTTPError as exc:
        raw=exc.read().decode("utf-8",errors="replace")
        try: body=json.loads(raw)
        except Exception: body={"raw":raw[:1000]}
        fail("HTTP error",{"url":url.split("?")[0],"status":exc.code,"response":body})

def get(base,path,params,headers):
    return req_json(base+path+"?"+urllib.parse.urlencode(params,doseq=True),headers)

def norm_tcg(v):
    return str(v or "").strip()

def just_fetch(key, probe):
    body,hdr=get(JUST,"/cards",{
        "game":"pokemon","set":JUST_SET,"number":probe["number"],"limit":20,"include_null_prices":"true"
    },{"x-api-key":key,"accept":"application/json","user-agent":"Cardoryx-Source-Compare/1.0"})
    rows=body.get("data") or []
    hits=[r for r in rows if norm_tcg(r.get("tcgplayerId"))==probe["tcg"]]
    if len(hits)>1:
        return {"status":"AMBIGUOUS","count":len(hits),"rows":hits[:3],"usage":body.get("_metadata")}
    if not hits:
        return {"status":"MISSING","count":0,"usage":body.get("_metadata")}
    r=hits[0]
    vars=r.get("variants") or []
    nm=[v for v in vars if str(v.get("condition") or "").lower()=="near mint" and isinstance(v.get("price"),(int,float))]
    return {
        "status":"EXACT_ONE","name":r.get("name"),"number":r.get("number"),"tcgPlayerId":r.get("tcgplayerId"),
        "nmPriceAvailable":bool(nm),"nmPrices":[v.get("price") for v in nm],"printings":sorted({str(v.get("printing") or "") for v in vars}),
        "usage":body.get("_metadata")
    }

def pkmn_fetch(key, probe):
    body,_=get(PKMN,"/cards",{
        "set_id":str(PKMN_SET_ID),"number":probe["number"],"total_set_number":"217","language":"English","per_page":100
    },{"X-API-Key":key,"Accept":"application/json","User-Agent":"Cardoryx-Source-Compare/1.0"})
    rows=body.get("data") or []
    hits=[r for r in rows if norm_tcg(r.get("tcg_player_id"))==probe["tcg"]]
    if len(hits)>1:
        return {"status":"AMBIGUOUS","count":len(hits)}
    if not hits:
        return {"status":"MISSING","count":0}
    r=hits[0]
    cid=r.get("id")
    if cid is None:
        return {"status":"MISSING_DETAIL_ID","count":1}
    detail,_=get(PKMN,f"/cards/{cid}",{"currency":"usd"},{"X-API-Key":key,"Accept":"application/json","User-Agent":"Cardoryx-Source-Compare/1.0"})
    prices=detail.get("prices") or []
    nm=[p for p in prices if str(p.get("condition") or "").lower()=="near mint" and isinstance(p.get("market_price"),(int,float))]
    return {
        "status":"EXACT_ONE","name":detail.get("name"),"number":detail.get("number"),"tcgPlayerId":detail.get("tcg_player_id"),
        "nmPriceAvailable":bool(nm),"nmPrices":[p.get("market_price") for p in nm],"variants":sorted({str(p.get("variant") or "") for p in prices}),
        "cardmarketProductId":detail.get("cardmarket_product_id")
    }

def ppt_fetch(key, probe):
    body,hdr=get(PPT,"/cards",{
        "tcgPlayerId":probe["tcg"],"language":"english","limit":1
    },{"Authorization":f"Bearer {key}","Accept":"application/json","User-Agent":"Cardoryx-Source-Compare/1.0"})
    data=body.get("data")
    if isinstance(data,list):
        if len(data)!=1: return {"status":"MISSING" if not data else "AMBIGUOUS","count":len(data)}
        r=data[0]
    elif isinstance(data,dict):
        r=data
    else:
        return {"status":"MISSING","count":0}
    if norm_tcg(r.get("tcgPlayerId"))!=probe["tcg"]:
        return {"status":"IDENTITY_MISMATCH","actual":r.get("tcgPlayerId")}
    vars=r.get("variants") or {}
    nm=[]
    for k,v in vars.items():
        if str(v.get("conditionUsed") or "").lower().startswith("near mint") and isinstance(v.get("marketPrice"),(int,float)):
            nm.append(v.get("marketPrice"))
    return {
        "status":"EXACT_ONE","name":r.get("name"),"number":r.get("cardNumber"),"tcgPlayerId":r.get("tcgPlayerId"),
        "nmPriceAvailable":bool(nm),"nmPrices":nm,"printings":r.get("printingsAvailable") or [],
        "externalCatalogId":r.get("externalCatalogId"),
        "setName":r.get("setName"),
        "usage":{"consumed":hdr.get("X-API-Calls-Consumed"),"dailyRemaining":hdr.get("X-RateLimit-Daily-Remaining")}
    }

def summarize(rows, source):
    vals=[x[source] for x in rows]
    return {
        "tested":len(vals),
        "exactOne":sum(1 for x in vals if x.get("status")=="EXACT_ONE"),
        "missing":sum(1 for x in vals if x.get("status")=="MISSING"),
        "ambiguous":sum(1 for x in vals if x.get("status")=="AMBIGUOUS"),
        "other":sum(1 for x in vals if x.get("status") not in {"EXACT_ONE","MISSING","AMBIGUOUS"}),
        "exactWithNMPrice":sum(1 for x in vals if x.get("status")=="EXACT_ONE" and x.get("nmPriceAvailable")),
    }

def main():
    jk=os.environ.get("JUSTTCG_API_KEY","").strip()
    pk=os.environ.get("PKMNPRICES_API_KEY","").strip()
    pt=os.environ.get("POKEMONPRICETRACKER_API_KEY","").strip()
    missing=[n for n,v in [("JUSTTCG_API_KEY",jk),("PKMNPRICES_API_KEY",pk),("POKEMONPRICETRACKER_API_KEY",pt)] if not v]
    if missing: fail("Missing source secrets",missing)

    rows=[]
    for i,p in enumerate(PROBES):
        j=just_fetch(jk,p)
        time.sleep(6.2)
        pkrow=pkmn_fetch(pk,p)
        ptrow=ppt_fetch(pt,p)
        rows.append({"finish":p["finish"],"number":p["number"],"tcgPlayerId":p["tcg"],"justtcg":j,"pkmnprices":pkrow,"pokemonPriceTracker":ptrow})

    report={
        "result":"PASS_READ_ONLY",
        "writesPerformed":False,
        "identityBasis":"same exact TCGPlayer ID across sources; Ascended Heroes representative finish sample",
        "summary":{
            "justtcg":summarize(rows,"justtcg"),
            "pkmnprices":summarize(rows,"pkmnprices"),
            "pokemonPriceTracker":summarize(rows,"pokemonPriceTracker"),
        },
        "rows":rows,
        "notes":{
            "pricesAreNotAveraged":True,
            "cardmarketUnchanged":True,
            "retailUnchanged":True,
            "productionIntegration":False,
        }
    }
    print(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
