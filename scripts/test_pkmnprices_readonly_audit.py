#!/usr/bin/env python3
"""Read-only PkmnPrices diagnostic for Cardoryx.

Scope:
- resolve Ascended Heroes exact English set;
- inspect Noibat 156/217 identities;
- fetch exact card details/prices;
- never write Cardmarket or retail data.
"""

from __future__ import annotations
import json, os, urllib.parse, urllib.request, urllib.error

BASE="https://api.pkmnprices.com/v1"
SET_NAME="Ascended Heroes"

def fail(message, details=None):
    out={"result":"FAIL_CLOSED","message":message}
    if details is not None: out["details"]=details
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))
    raise SystemExit(1)

def get(path,key,params=None):
    qs=urllib.parse.urlencode(params or {},doseq=True)
    url=BASE+path+("?" + qs if qs else "")
    req=urllib.request.Request(url,headers={
        "X-API-Key":key,
        "Accept":"application/json",
        "User-Agent":"Cardoryx-PkmnPrices-ReadOnly-Audit/1.0",
    })
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            body=json.loads(r.read().decode("utf-8"))
            return body
    except urllib.error.HTTPError as exc:
        raw=exc.read().decode("utf-8",errors="replace")
        try: body=json.loads(raw)
        except Exception: body={"raw":raw[:1500]}
        fail("PkmnPrices HTTP error",{"status":exc.code,"path":path,"response":body})

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

def main():
    key=os.environ.get("PKMNPRICES_API_KEY","").strip()
    if not key:
        fail("Missing PKMNPRICES_API_KEY")

    sets=get("/sets",key,{"name":SET_NAME,"language":"English","per_page":20})
    rows=sets.get("data") or []
    allowed_names={SET_NAME.lower(), ("ME: " + SET_NAME).lower()}
    exact=[x for x in rows
           if str(x.get("language") or "").strip().lower()=="english"
           and str(x.get("name") or "").strip().lower() in allowed_names]
    if len(exact)!=1:
        fail("Ascended Heroes English set did not resolve uniquely",{"matches":exact,"returned":rows})
    target=exact[0]
    set_id=target.get("id")
    if set_id is None:
        fail("Resolved set has no id",target)

    cards=get("/cards",key,{
        "set_id":str(set_id),
        "number":"156",
        "total_set_number":"217",
        "language":"English",
        "per_page":100,
    })
    candidates=cards.get("data") or []
    pagination=cards.get("pagination") or {}
    if not candidates:
        fail("No card candidates for 156/217",{"set":target,"pagination":pagination})

    details=[]
    for c in candidates:
        cid=c.get("id")
        if cid is None: fail("Candidate missing id",c)
        details.append(slim_detail(get(f"/cards/{cid}",key,{"currency":"usd"})))

    variants=[]
    for d in details:
        for p in d["prices"]:
            variants.append({
                "card_id":d["id"],
                "card_name":d["name"],
                "tcg_player_id":d["tcg_player_id"],
                "cardmarket_product_id":d["cardmarket_product_id"],
                "condition":p["condition"],
                "variant":p["variant"],
                "currency":p["currency"],
                "price":p["market_price"],
            })

    nm=[v for v in variants if str(v["condition"]).lower()=="near mint"]
    result={
        "result":"PASS_READ_ONLY",
        "writesPerformed":False,
        "sourceClassification":"market estimate / pricing API",
        "targetSet":target,
        "candidateCount":len(candidates),
        "candidates":[slim_card(x) for x in candidates],
        "details":details,
        "nearMintRows":nm,
        "diagnostics":{
            "distinctNames":sorted({str(x.get("name") or "") for x in candidates}),
            "distinctTcgPlayerIds":sorted({x.get("tcg_player_id") for x in candidates if x.get("tcg_player_id") is not None}),
            "distinctCardmarketProductIds":sorted({x.get("cardmarket_product_id") for x in details if x.get("cardmarket_product_id") is not None}),
            "distinctVariants":sorted({str(v.get("variant") or "") for v in variants}),
            "currencies":sorted({str(v.get("currency") or "") for v in variants}),
        },
        "integrationDecision":{
            "automaticProductionIntegration":False,
            "reason":"Diagnostic only. Physical identity and finish semantics must be proven before integration."
        }
    }
    print(json.dumps(result,ensure_ascii=False,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
