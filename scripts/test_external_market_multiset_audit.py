#!/usr/bin/env python3
"""Read-only multi-set comparison of external Pokémon market sources.\n\n# RERUN_MARKER_20260927

Goal:
- compare JustTCG, PkmnPrices and PokemonPriceTracker on the same TCGdex-backed
  physical finish identities across multiple eras/sets;
- require exact TCGPlayer identity and expected printing;
- never write Cardmarket or retail production data.

This is diagnostic-only and intentionally conservative.
"""

from __future__ import annotations

import concurrent.futures
import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request

TCGDEX="https://api.tcgdex.net/v2/en"
JUST="https://api.justtcg.com/v1"
PKMN="https://api.pkmnprices.com/v1"
PPT="https://www.pokemonpricetracker.com/api/v2"

# Five eras/sets, including the current stress-case set.
TARGET_SET_IDS=["me02.5","sv08","swsh11","sm12","xy1"]

# Older TCGdex records do not always expose variants_detailed. These fallback
# representatives come from Cardoryx's already-verified production checklists.
# They are deliberately narrow: exact card + exact documented finish only.
SOURCE_SET_ALIASES={
    # Confirmed exact provider naming differences from the first multi-set run.
    # Keep these exceptions scoped to the demonstrated set IDs.
    "sm12":"SM - Cosmic Eclipse",
    "xy1":"XY Base Set",
}

LEGACY_VERIFIED={
    "sm12":{
        "Normal":("sm12-113","Normal"),
        "Holo":("sm12-142","Holo"),
        "Reverse Holo":("sm12-128","Reverse Holo"),
    },
    "xy1":{
        "Normal":("xy1-107","Normal"),
        "Holo":("xy1-114","Holo"),
        "Reverse Holo":("xy1-122","Reverse Holo"),
    },
}
WANTED_FINISHES=["Normal","Holo","Reverse Holo"]
JUST_SLEEP=7.2
JUST_RETRY_WAIT=65
PKMN_SLEEP=3.2
PKMN_RETRY_WAIT=65

def fail(message, details=None):
    out={"result":"FAIL_CLOSED","message":message}
    if details is not None:
        out["details"]=details
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))
    raise SystemExit(1)

def request_json(url, headers=None, allow_429=False):
    req=urllib.request.Request(url,headers=headers or {},method="GET")
    try:
        with urllib.request.urlopen(req,timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8")), dict(resp.headers), resp.status
    except urllib.error.HTTPError as exc:
        raw=exc.read().decode("utf-8",errors="replace")
        try:
            body=json.loads(raw)
        except Exception:
            body={"raw":raw[:1200]}
        if allow_429 and exc.code==429:
            return body,dict(exc.headers),exc.code
        fail("HTTP error",{"status":exc.code,"url":url.split("?")[0],"response":body})
    except Exception as exc:
        fail("Request failed",{"url":url.split("?")[0],"type":type(exc).__name__,"error":str(exc)})

def get(base,path,params=None,headers=None,allow_429=False):
    qs=urllib.parse.urlencode(params or {},doseq=True)
    url=base+path+(("?"+qs) if qs else "")
    return request_json(url,headers=headers,allow_429=allow_429)

def just_get(key,path,params=None):
    headers={
        "x-api-key":key,
        "accept":"application/json",
        "user-agent":"Cardoryx-External-Market-Multiset-Audit/1.0",
    }
    body,hdr,status=get(JUST,path,params,headers,allow_429=True)
    if status==429 and isinstance(body,dict) and body.get("code")=="RATE_LIMIT_EXCEEDED":
        time.sleep(JUST_RETRY_WAIT)
        body,hdr,status=get(JUST,path,params,headers,allow_429=True)
    return body,hdr,status

def pkmn_get(key,path,params=None):
    headers={
        "X-API-Key":key,
        "Accept":"application/json",
        "User-Agent":"Cardoryx-External-Market-Multiset-Audit/1.0",
    }
    body,_,status=get(PKMN,path,params,headers,allow_429=True)
    if status==429:
        code=((body.get("error") or {}).get("code") if isinstance(body,dict) else None)
        if code=="rate_limit_exceeded":
            time.sleep(PKMN_RETRY_WAIT)
            body,_,status=get(PKMN,path,params,headers,allow_429=True)
        if status==429:
            fail("PkmnPrices rate limit remained blocked after one controlled retry",body)
    time.sleep(PKMN_SLEEP)
    return body

def norm(value):
    return re.sub(r"[^a-z0-9]+","",str(value or "").lower())

def suffix_norm(value):
    s=str(value or "")
    if ":" in s:
        s=s.split(":",1)[1]
    return norm(s)

def tcgdex_get(path):
    body,_,_=get(TCGDEX,path,headers={
        "Accept":"application/json",
        "User-Agent":"Cardoryx-External-Market-Multiset-Audit/1.0",
    })
    return body

def canonical_finish(row):
    typ=str(row.get("type") or "").lower()
    foil=str(row.get("foil") or "").lower()
    if typ=="normal":
        return "Normal"
    if typ=="holo" and not foil:
        return "Holo"
    if typ=="reverse" and not foil:
        return "Reverse Holo"
    return None

def expected_printing(finish):
    return {
        "Normal":"Normal",
        "Holo":"Holofoil",
        "Reverse Holo":"Reverse Holofoil",
    }.get(finish)

def row_tcgplayer(row):
    return str((row.get("thirdParty") or {}).get("tcgplayer") or "").strip()

def resolve_tcgdex_probes():
    set_reports=[]
    probes=[]
    for sid in TARGET_SET_IDS:
        try:
            set_body=tcgdex_get(f"/sets/{sid}")
        except SystemExit:
            set_reports.append({"tcgdexSetId":sid,"status":"TCGDEX_SET_UNAVAILABLE"})
            continue
        set_name=str(set_body.get("name") or "").strip()
        cards=[x for x in (set_body.get("cards") or []) if x.get("id")]
        if not set_name or not cards:
            set_reports.append({"tcgdexSetId":sid,"status":"TCGDEX_SET_INVALID","name":set_name})
            continue

        details={}
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
            futs={pool.submit(tcgdex_get,f"/cards/{c['id']}"):c["id"] for c in cards}
            for fut,cid in [(f,c) for f,c in futs.items()]:
                try:
                    details[cid]=fut.result()
                except Exception:
                    continue

        chosen={}
        used_tcg=set()

        # Preferred path: exact variant-level identity from TCGdex.
        for finish in WANTED_FINISHES:
            for card in details.values():
                for vr in (card.get("variants_detailed") or []):
                    if canonical_finish(vr)!=finish:
                        continue
                    tcg=row_tcgplayer(vr)
                    if not tcg or tcg in used_tcg:
                        continue
                    local=str(card.get("localId") or "").strip()
                    if not local:
                        continue
                    chosen[finish]={
                        "tcgdexSetId":sid,
                        "tcgdexSetName":set_name,
                        "tcgdexCardId":card.get("id"),
                        "name":card.get("name"),
                        "number":local,
                        "finish":finish,
                        "expectedPrinting":expected_printing(finish),
                        "tcgPlayerId":tcg,
                        "rarity":card.get("rarity"),
                        "identityEvidence":"TCGDEX_VARIANT_DETAILED",
                    }
                    used_tcg.add(tcg)
                    break
                if finish in chosen:
                    break

        # Narrow fallback for older sets: use only representatives already
        # verified by Cardoryx production audit/checklists. TCGPlayer identity
        # comes from the exact TCGdex card, while physical finish comes from the
        # verified Cardoryx registry.
        for finish,(card_id,verified_finish) in LEGACY_VERIFIED.get(sid,{}).items():
            if finish in chosen:
                continue
            card=details.get(card_id) or tcgdex_get(f"/cards/{card_id}")
            tcg=str((card.get("thirdParty") or {}).get("tcgplayer") or "").strip()
            local=str(card.get("localId") or "").strip()
            if not tcg or not local or verified_finish!=finish:
                continue
            chosen[finish]={
                "tcgdexSetId":sid,
                "tcgdexSetName":set_name,
                "tcgdexCardId":card.get("id"),
                "name":card.get("name"),
                "number":local,
                "finish":finish,
                "expectedPrinting":expected_printing(finish),
                "tcgPlayerId":tcg,
                "rarity":card.get("rarity"),
                "identityEvidence":"CARDORYX_VERIFIED_CHECKLIST+TCGDEX_CARD_ID",
            }

        missing=[x for x in WANTED_FINISHES if x not in chosen]
        set_reports.append({
            "tcgdexSetId":sid,
            "name":set_name,
            "status":"READY" if len(chosen)>=2 else "INSUFFICIENT_PROBES",
            "selected":sorted(chosen),
            "missing":missing,
        })
        probes.extend(chosen[x] for x in WANTED_FINISHES if x in chosen)

    ready=sum(1 for x in set_reports if x.get("status")=="READY")
    if ready<4:
        fail("Too few TCGdex sets produced representative probes",{"readySets":ready,"sets":set_reports})
    if len(probes)<10:
        fail("Too few TCGdex probes for multi-set audit",{"probeCount":len(probes),"sets":set_reports})
    return set_reports,probes

def unique_set_candidate(rows,target_name):
    target=norm(target_name)
    target_suffix=suffix_norm(target_name)
    exact=[]
    for r in rows:
        name=str(r.get("name") or "")
        if norm(name)==target or suffix_norm(name)==target or suffix_norm(name)==target_suffix:
            exact.append(r)
    by_id={}
    for r in exact:
        rid=str(r.get("id") or "")
        if rid:
            by_id[rid]=r
    vals=list(by_id.values())
    return vals[0] if len(vals)==1 else None

def resolve_just_set(key,set_name):
    params={"game":"pokemon","q":set_name}
    headers={"x-api-key":key,"accept":"application/json","user-agent":"Cardoryx-External-Market-Multiset-Audit/1.0"}
    body,_,status=get(JUST,"/sets",params,headers,allow_429=True)
    if status==429 and isinstance(body,dict) and body.get("code")=="RATE_LIMIT_EXCEEDED":
        time.sleep(65)
        body,_,status=get(JUST,"/sets",params,headers,allow_429=True)
    if status==429:
        return {"status":"QUOTA_BLOCKED","response":body}
    rows=body.get("data") or []
    hit=unique_set_candidate(rows,set_name)
    if not hit:
        return {"status":"UNRESOLVED","returned":[{"id":x.get("id"),"name":x.get("name")} for x in rows[:20]]}
    return {"status":"EXACT_ONE","id":hit.get("id"),"name":hit.get("name")}

def resolve_pkmn_set(key,set_name):
    body=pkmn_get(key,"/sets",{"name":set_name,"language":"English","per_page":50})
    rows=body.get("data") or []
    hit=unique_set_candidate(rows,set_name)
    if not hit:
        return {"status":"UNRESOLVED","returned":[{"id":x.get("id"),"name":x.get("name")} for x in rows[:20]]}
    return {"status":"EXACT_ONE","id":hit.get("id"),"name":hit.get("name")}

def has_expected_printing_just(card, expected):
    valid=[]
    for v in (card.get("variants") or []):
        if str(v.get("printing") or "")!=expected:
            continue
        if str(v.get("condition") or "").lower()!="near mint":
            continue
        price=v.get("price")
        if isinstance(price,(int,float)) and price>=0:
            valid.append(price)
    return valid

def just_probe(key,set_resolved,probe):
    if set_resolved.get("status")!="EXACT_ONE":
        return {"status":"SET_UNRESOLVED"}
    params={
        "game":"pokemon","set":set_resolved["id"],"number":probe["number"],
        "limit":20,"include_null_prices":"true"
    }
    headers={"x-api-key":key,"accept":"application/json","user-agent":"Cardoryx-External-Market-Multiset-Audit/1.0"}
    body,_,status=get(JUST,"/cards",params,headers,allow_429=True)
    if status==429 and isinstance(body,dict) and body.get("code")=="RATE_LIMIT_EXCEEDED":
        time.sleep(65)
        body,_,status=get(JUST,"/cards",params,headers,allow_429=True)
    if status==429:
        return {"status":"QUOTA_BLOCKED","response":body}
    rows=body.get("data") or []
    hits=[r for r in rows if str(r.get("tcgplayerId") or "")==probe["tcgPlayerId"]]
    if len(hits)!=1:
        return {"status":"MISSING" if not hits else "AMBIGUOUS","count":len(hits)}
    card=hits[0]
    prices=has_expected_printing_just(card,probe["expectedPrinting"])
    return {
        "status":"EXACT_FINISH" if prices else "IDENTITY_ONLY",
        "name":card.get("name"),
        "number":card.get("number"),
        "tcgPlayerId":card.get("tcgplayerId"),
        "expectedPrinting":probe["expectedPrinting"],
        "nmPrices":prices,
    }

def pkmn_probe(key,set_resolved,probe):
    if set_resolved.get("status")!="EXACT_ONE":
        return {"status":"SET_UNRESOLVED"}
    body=pkmn_get(key,"/cards",{
        "set_id":str(set_resolved["id"]),"number":probe["number"],
        "language":"English","per_page":100
    })
    rows=body.get("data") or []
    hits=[r for r in rows if str(r.get("tcg_player_id") or "")==probe["tcgPlayerId"]]
    if len(hits)!=1:
        return {"status":"MISSING" if not hits else "AMBIGUOUS","count":len(hits)}
    cid=hits[0].get("id")
    if cid is None:
        return {"status":"IDENTITY_ONLY","reason":"missing detail id"}
    detail=pkmn_get(key,f"/cards/{cid}",{"currency":"usd"})
    prices=[]
    for p in (detail.get("prices") or []):
        if str(p.get("variant") or "")!=probe["expectedPrinting"]:
            continue
        if str(p.get("condition") or "").lower()!="near mint":
            continue
        value=p.get("market_price")
        if isinstance(value,(int,float)) and value>=0:
            prices.append(value)
    return {
        "status":"EXACT_FINISH" if prices else "IDENTITY_ONLY",
        "name":detail.get("name"),
        "number":detail.get("number"),
        "tcgPlayerId":detail.get("tcg_player_id"),
        "expectedPrinting":probe["expectedPrinting"],
        "nmPrices":prices,
        "cardmarketProductId":detail.get("cardmarket_product_id"),
    }

def ppt_probe(key,probe):
    body,_,status=get(PPT,"/cards",{
        "tcgPlayerId":probe["tcgPlayerId"],"language":"english","limit":1
    },{
        "Authorization":f"Bearer {key}","Accept":"application/json","User-Agent":"Cardoryx-External-Market-Multiset-Audit/1.0"
    },allow_429=True)
    if status==429:
        return {"status":"QUOTA_BLOCKED","response":body}
    data=body.get("data")
    if isinstance(data,list):
        if len(data)!=1:
            return {"status":"MISSING" if not data else "AMBIGUOUS","count":len(data)}
        card=data[0]
    elif isinstance(data,dict):
        card=data
    else:
        return {"status":"MISSING","count":0}
    if str(card.get("tcgPlayerId") or "")!=probe["tcgPlayerId"]:
        return {"status":"IDENTITY_MISMATCH","actual":card.get("tcgPlayerId")}
    variant=(card.get("variants") or {}).get(probe["expectedPrinting"])
    prices=[]
    if isinstance(variant,dict):
        cond=str(variant.get("conditionUsed") or "").lower()
        value=variant.get("marketPrice")
        if cond.startswith("near mint") and isinstance(value,(int,float)) and value>=0:
            prices.append(value)
    return {
        "status":"EXACT_FINISH" if prices else "IDENTITY_ONLY",
        "name":card.get("name"),
        "number":card.get("cardNumber"),
        "tcgPlayerId":card.get("tcgPlayerId"),
        "expectedPrinting":probe["expectedPrinting"],
        "nmPrices":prices,
        "setName":card.get("setName"),
        "externalCatalogId":card.get("externalCatalogId"),
    }

def summarize(rows,key):
    vals=[r[key] for r in rows]
    return {
        "tested":len(vals),
        "exactFinish":sum(1 for x in vals if x.get("status")=="EXACT_FINISH"),
        "identityOnly":sum(1 for x in vals if x.get("status")=="IDENTITY_ONLY"),
        "missing":sum(1 for x in vals if x.get("status")=="MISSING"),
        "ambiguous":sum(1 for x in vals if x.get("status")=="AMBIGUOUS"),
        "setUnresolved":sum(1 for x in vals if x.get("status")=="SET_UNRESOLVED"),
        "quotaBlocked":sum(1 for x in vals if x.get("status")=="QUOTA_BLOCKED"),
        "other":sum(1 for x in vals if x.get("status") not in {
            "EXACT_FINISH","IDENTITY_ONLY","MISSING","AMBIGUOUS","SET_UNRESOLVED","QUOTA_BLOCKED"
        }),
    }

def main():
    jk=os.environ.get("JUSTTCG_API_KEY","").strip()
    pk=os.environ.get("PKMNPRICES_API_KEY","").strip()
    pt=os.environ.get("POKEMONPRICETRACKER_API_KEY","").strip()
    missing=[name for name,val in [
        ("JUSTTCG_API_KEY",jk),("PKMNPRICES_API_KEY",pk),("POKEMONPRICETRACKER_API_KEY",pt)
    ] if not val]
    if missing:
        fail("Missing API secrets",missing)

    tcg_sets,probes=resolve_tcgdex_probes()

    unique_sets=[]
    seen=set()
    for p in probes:
        sid=p["tcgdexSetId"]
        if sid in seen:
            continue
        seen.add(sid)
        unique_sets.append((sid,p["tcgdexSetName"]))

    just_sets={}
    pkmn_sets={}
    just_quota_blocked=False
    pkmn_skip=os.environ.get("PKMNPRICES_SKIP_ON_QUOTA","").strip()=="1"
    for sid,name in unique_sets:
        provider_name=SOURCE_SET_ALIASES.get(sid,name)
        if just_quota_blocked:
            just_sets[name]={"status":"QUOTA_BLOCKED","providerQuery":provider_name}
        else:
            just_sets[name]=resolve_just_set(jk,provider_name)
            just_sets[name]["providerQuery"]=provider_name
            if just_sets[name].get("status")=="QUOTA_BLOCKED":
                just_quota_blocked=True
            else:
                time.sleep(JUST_SLEEP)
        if pkmn_skip:
            pkmn_sets[name]={"status":"QUOTA_BLOCKED","providerQuery":provider_name}
        else:
            pkmn_sets[name]=resolve_pkmn_set(pk,provider_name)
            pkmn_sets[name]["providerQuery"]=provider_name

    rows=[]
    ppt_quota_blocked=False
    ppt_skip=os.environ.get("POKEMONPRICETRACKER_SKIP_ON_QUOTA","").strip()=="1"
    for probe in probes:
        jset=just_sets.get(probe["tcgdexSetName"],{"status":"UNRESOLVED"})
        if just_quota_blocked and jset.get("status")=="QUOTA_BLOCKED":
            j={"status":"QUOTA_BLOCKED"}
        else:
            j=just_probe(jk,jset,probe)
            if j.get("status")!="QUOTA_BLOCKED":
                time.sleep(JUST_SLEEP)
            else:
                just_quota_blocked=True
        pset=pkmn_sets.get(probe["tcgdexSetName"],{"status":"UNRESOLVED"})
        pr={"status":"QUOTA_BLOCKED"} if pset.get("status")=="QUOTA_BLOCKED" else pkmn_probe(pk,pset,probe)
        if ppt_skip or ppt_quota_blocked:
            pp={"status":"QUOTA_BLOCKED"}
        else:
            pp=ppt_probe(pt,probe)
            if pp.get("status")=="QUOTA_BLOCKED":
                ppt_quota_blocked=True
        rows.append({
            "set":probe["tcgdexSetName"],
            "tcgdexSetId":probe["tcgdexSetId"],
            "name":probe["name"],
            "number":probe["number"],
            "rarity":probe["rarity"],
            "finish":probe["finish"],
            "expectedPrinting":probe["expectedPrinting"],
            "tcgPlayerId":probe["tcgPlayerId"],
            "justtcg":j,
            "pkmnprices":pr,
            "pokemonPriceTracker":pp,
        })

    report={
        "result":"PASS_READ_ONLY",
        "writesPerformed":False,
        "selection":{
            "targetSetIds":TARGET_SET_IDS,
            "wantedFinishes":WANTED_FINISHES,
            "tcgdexSets":tcg_sets,
            "probeCount":len(rows),
        },
        "sourceSetResolution":{
            "justtcg":just_sets,
            "pkmnprices":pkmn_sets,
        },
        "summary":{
            "justtcg":summarize(rows,"justtcg"),
            "pkmnprices":summarize(rows,"pkmnprices"),
            "pokemonPriceTracker":summarize(rows,"pokemonPriceTracker"),
        },
        "rows":rows,
        "safety":{
            "cardmarketWritten":False,
            "retailWritten":False,
            "pricesAveraged":False,
            "productionIntegrationPerformed":False,
        }
    }
    print(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
