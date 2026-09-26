#!/usr/bin/env python3
"""Read-only PkmnPrices audit for Cardoryx.

Checks:
- exact English Ascended Heroes set resolution;
- Noibat 156/217 physical identities;
- representative sample across every known finish family;
- no production writes.
"""

from __future__ import annotations
import concurrent.futures
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE="https://api.pkmnprices.com/v1"
TCGDEX="https://api.tcgdex.net/v2/en"
SET_NAME="Ascended Heroes"

def fail(message, details=None):
    out={"result":"FAIL_CLOSED","message":message}
    if details is not None:
        out["details"]=details
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))
    raise SystemExit(1)

def get_json(url, headers=None):
    req=urllib.request.Request(url,headers=headers or {},method="GET")
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw=exc.read().decode("utf-8",errors="replace")
        try:
            body=json.loads(raw)
        except Exception:
            body={"raw":raw[:1500]}
        fail("HTTP error",{"status":exc.code,"url":url.split("?")[0],"response":body})

def get(path,key,params=None):
    qs=urllib.parse.urlencode(params or {},doseq=True)
    return get_json(
        BASE+path+("?" + qs if qs else ""),
        {
            "X-API-Key":key,
            "Accept":"application/json",
            "User-Agent":"Cardoryx-PkmnPrices-ReadOnly-Audit/1.0",
        },
    )

def tcgdex_get(path):
    return get_json(
        TCGDEX+path,
        {"Accept":"application/json","User-Agent":"Cardoryx-PkmnPrices-ReadOnly-Audit/1.0"},
    )

def slim_card(c):
    return {
        "id":c.get("id"),
        "tcg_player_id":c.get("tcg_player_id"),
        "name":c.get("name"),
        "number":c.get("number"),
        "total_set_number":c.get("total_set_number"),
        "rarity":c.get("rarity"),
        "set":c.get("set"),
    }

def slim_detail(c):
    return {
        **slim_card(c),
        "cardmarket_product_id":c.get("cardmarket_product_id"),
        "cardmarket_url_present":bool(c.get("cardmarket_url")),
        "prices":[{
            "source":p.get("source"),
            "currency":p.get("currency"),
            "condition":p.get("condition"),
            "variant":p.get("variant"),
            "market_price":p.get("market_price"),
            "created_at":p.get("created_at"),
        } for p in (c.get("prices") or [])],
    }

def canonical_finish(row):
    typ=str(row.get("type") or "").lower()
    foil=str(row.get("foil") or "").lower()
    if typ=="normal":
        return "Normal"
    if typ=="holo" and foil=="cosmos":
        return "Cosmos Holo"
    if typ=="holo" and not foil:
        return "Holo"
    if typ=="reverse" and not foil:
        return "Reverse Holo"
    mapping={
        "energy":"Energy Reverse Holo",
        "friendball":"Friend Ball Reverse Holo",
        "loveball":"Love Ball Reverse Holo",
        "quickball":"Quick Ball Reverse Holo",
        "duskball":"Dusk Ball Reverse Holo",
        "pokeball":"Poké Ball Reverse Holo",
        "team-rocket":"Team Rocket Reverse Holo",
    }
    if typ=="reverse":
        return mapping.get(foil)
    return None

def pkmn_finish(name,variant):
    n=str(name or "").lower()
    if "energy symbol pattern" in n:
        return "Energy Reverse Holo"
    if "(friend ball)" in n:
        return "Friend Ball Reverse Holo"
    if "(love ball)" in n:
        return "Love Ball Reverse Holo"
    if "(quick ball)" in n:
        return "Quick Ball Reverse Holo"
    if "(dusk ball)" in n:
        return "Dusk Ball Reverse Holo"
    if "(poke ball)" in n or "(poké ball)" in n:
        return "Poké Ball Reverse Holo"
    if "(team rocket)" in n:
        return "Team Rocket Reverse Holo"
    v=str(variant or "").lower()
    if v=="normal":
        return "Normal"
    if v=="holofoil":
        return "Holo"
    if v in {"reverse holo","reverse holofoil"}:
        return "Reverse Holo"
    return None

def fetch_candidates(key,set_id,number):
    body=get("/cards",key,{
        "set_id":str(set_id),
        "number":str(number),
        "total_set_number":"217",
        "language":"English",
        "per_page":100,
    })
    rows=body.get("data") or []
    details=[]
    for c in rows:
        cid=c.get("id")
        if cid is None:
            fail("Candidate missing id",c)
        details.append(slim_detail(get(f"/cards/{cid}",key,{"currency":"usd"})))
    return rows,details

def main():
    key=os.environ.get("PKMNPRICES_API_KEY","").strip()
    if not key:
        fail("Missing PKMNPRICES_API_KEY")

    sets=get("/sets",key,{"name":SET_NAME,"language":"English","per_page":20})
    rows=sets.get("data") or []
    allowed={SET_NAME.lower(),("ME: "+SET_NAME).lower()}
    exact=[x for x in rows
           if str(x.get("language") or "").lower()=="english"
           and str(x.get("name") or "").strip().lower() in allowed]
    if len(exact)!=1:
        fail("Ascended Heroes English set did not resolve uniquely",{"matches":exact,"returned":rows})
    target=exact[0]
    set_id=target.get("id")
    if set_id is None:
        fail("Resolved set has no id",target)

    # Anchor: Noibat 156/217.
    candidates,details=fetch_candidates(key,set_id,"156")
    noibat_nm=[]
    for d in details:
        for p in d.get("prices") or []:
            if str(p.get("condition") or "").lower()=="near mint":
                noibat_nm.append({
                    "card_id":d.get("id"),
                    "card_name":d.get("name"),
                    "tcg_player_id":d.get("tcg_player_id"),
                    "cardmarket_product_id":d.get("cardmarket_product_id"),
                    "variant":p.get("variant"),
                    "currency":p.get("currency"),
                    "price":p.get("market_price"),
                    "mapped_finish":pkmn_finish(d.get("name"),p.get("variant")),
                })

    # Build one TCGdex probe per known finish family.
    tcgset=tcgdex_get("/sets/me02.5")
    ids=[x.get("id") for x in (tcgset.get("cards") or []) if x.get("id")]
    detailed={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
        jobs=[(cid,pool.submit(tcgdex_get,f"/cards/{cid}")) for cid in ids]
        for cid,fut in jobs:
            detailed[cid]=fut.result()

    wanted=[
        "Normal","Holo","Reverse Holo","Cosmos Holo",
        "Energy Reverse Holo","Friend Ball Reverse Holo","Love Ball Reverse Holo",
        "Quick Ball Reverse Holo","Dusk Ball Reverse Holo","Poké Ball Reverse Holo",
        "Team Rocket Reverse Holo",
    ]
    probes={}
    for finish in wanted:
        for cid,card in detailed.items():
            matches=[r for r in (card.get("variants_detailed") or []) if canonical_finish(r)==finish]
            if matches:
                probes[finish]={
                    "tcgdex_id":cid,
                    "name":card.get("name"),
                    "number":str(card.get("localId") or ""),
                    "row":matches[0],
                }
                break
    missing=[x for x in wanted if x not in probes]
    if missing:
        fail("TCGdex representative finish missing",missing)

    finish_results={}
    for expected,probe in probes.items():
        _,probe_details=fetch_candidates(key,set_id,probe["number"])
        matches=[]
        for d in probe_details:
            for p in d.get("prices") or []:
                if str(p.get("condition") or "").lower()!="near mint":
                    continue
                actual=pkmn_finish(d.get("name"),p.get("variant"))
                if actual==expected:
                    matches.append({
                        "pkmnprices_id":d.get("id"),
                        "name":d.get("name"),
                        "tcg_player_id":d.get("tcg_player_id"),
                        "cardmarket_product_id":d.get("cardmarket_product_id"),
                        "variant":p.get("variant"),
                        "price":p.get("market_price"),
                    })
        row=probe["row"]
        finish_results[expected]={
            "probe":{
                "tcgdex_id":probe["tcgdex_id"],
                "name":probe["name"],
                "number":probe["number"],
                "type":row.get("type"),
                "foil":row.get("foil"),
                "tcgdex_tcgplayer":(row.get("thirdParty") or {}).get("tcgplayer"),
                "tcgdex_cardmarket":(row.get("thirdParty") or {}).get("cardmarket"),
            },
            "nearMintExactFinishMatches":matches,
            "candidateDetails":probe_details if expected=="Cosmos Holo" else None,
            "status":"EXACT_ONE" if len(matches)==1 else ("MISSING" if not matches else "AMBIGUOUS"),
        }

    summary={
        "tested":len(wanted),
        "exactOne":sum(1 for x in finish_results.values() if x["status"]=="EXACT_ONE"),
        "missing":sum(1 for x in finish_results.values() if x["status"]=="MISSING"),
        "ambiguous":sum(1 for x in finish_results.values() if x["status"]=="AMBIGUOUS"),
    }

    print(json.dumps({
        "result":"PASS_READ_ONLY",
        "writesPerformed":False,
        "sourceClassification":"market estimate / pricing API",
        "targetSet":target,
        "noibat156":{
            "candidateCount":len(candidates),
            "candidates":[slim_card(x) for x in candidates],
            "nearMintRows":noibat_nm,
        },
        "representativeSummary":summary,
        "representativeFinishAudit":finish_results,
        "integrationDecision":{
            "automaticProductionIntegration":False,
            "reason":"Representative identity audit only; no production adapter or pricing integration performed."
        }
    },ensure_ascii=False,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
