#!/usr/bin/env python3
"""Read-only PokemonPriceTracker identity audit for Cardoryx.

Uses exact TCGPlayer IDs with limit=1 semantics to minimize free-tier credits.
No Cardmarket or retail files are written.
"""

from __future__ import annotations
import json, os, urllib.error, urllib.parse, urllib.request

BASE="https://www.pokemonpricetracker.com/api/v2"

PROBES=[
    ("Noibat Normal","675968"),
    ("Noibat Energy","677114"),
    ("Noibat Friend Ball","676974"),
    ("Normal sample","675813"),
    ("Holo sample","675815"),
    ("Reverse sample","675992"),
    ("Cosmos sample","679253"),
    ("Energy sample","676992"),
    ("Friend Ball sample","676858"),
    ("Love Ball sample","676860"),
    ("Quick Ball sample","676866"),
    ("Dusk Ball sample","676888"),
    ("Poke Ball sample","676852"),
    ("Team Rocket sample","676867"),
]

def fail(message, details=None):
    out={"result":"FAIL_CLOSED","message":message}
    if details is not None:
        out["details"]=details
    print(json.dumps(out,ensure_ascii=False,indent=2,sort_keys=True))
    raise SystemExit(1)

def get_card(key, tcg_id):
    params=urllib.parse.urlencode({
        "tcgPlayerId":tcg_id,
        "language":"english",
        "limit":1,
    })
    url=f"{BASE}/cards?{params}"
    req=urllib.request.Request(url,headers={
        "Authorization":f"Bearer {key}",
        "Accept":"application/json",
        "User-Agent":"Cardoryx-PokemonPriceTracker-Audit/1.0",
    })
    try:
        with urllib.request.urlopen(req,timeout=30) as r:
            body=json.loads(r.read().decode("utf-8"))
            headers={
                "consumed":r.headers.get("X-API-Calls-Consumed"),
                "dailyRemaining":r.headers.get("X-RateLimit-Daily-Remaining"),
                "minuteRemaining":r.headers.get("X-RateLimit-Minute-Remaining"),
            }
            return body, headers
    except urllib.error.HTTPError as exc:
        raw=exc.read().decode("utf-8",errors="replace")
        try:
            body=json.loads(raw)
        except Exception:
            body={"raw":raw[:1200]}
        fail("PokemonPriceTracker HTTP error",{"tcgPlayerId":tcg_id,"status":exc.code,"response":body})

def slim(card):
    prices=card.get("prices") or {}
    variants=card.get("variants") or {}
    return {
        "id":card.get("id"),
        "tcgPlayerId":str(card.get("tcgPlayerId") or ""),
        "name":card.get("name"),
        "setId":card.get("setId"),
        "setName":card.get("setName"),
        "cardNumber":card.get("cardNumber"),
        "rarity":card.get("rarity"),
        "externalCatalogId":card.get("externalCatalogId"),
        "printingsAvailable":card.get("printingsAvailable"),
        "prices":{
            "market":prices.get("market"),
            "low":prices.get("low"),
            "primaryPrinting":prices.get("primaryPrinting"),
            "lastUpdated":prices.get("lastUpdated"),
        },
        "variants":variants,
    }

def main():
    key=os.environ.get("POKEMONPRICETRACKER_API_KEY","").strip()
    if not key:
        fail("Missing POKEMONPRICETRACKER_API_KEY")

    rows=[]
    total_consumed=0
    last_remaining=None

    for label, tcg_id in PROBES:
        body,hdr=get_card(key,tcg_id)
        data=body.get("data")
        if isinstance(data,list):
            if len(data)!=1:
                fail("Exact TCGPlayer lookup did not return exactly one card",{"label":label,"tcgPlayerId":tcg_id,"count":len(data)})
            card=data[0]
        elif isinstance(data,dict):
            card=data
        else:
            fail("Exact TCGPlayer lookup returned no card",{"label":label,"tcgPlayerId":tcg_id,"data":data})

        if str(card.get("tcgPlayerId") or "") != tcg_id:
            fail("TCGPlayer identity mismatch",{"label":label,"expected":tcg_id,"actual":card.get("tcgPlayerId")})

        consumed=hdr.get("consumed")
        if consumed is not None:
            try: total_consumed += int(consumed)
            except Exception: pass
        if hdr.get("dailyRemaining") is not None:
            last_remaining=hdr.get("dailyRemaining")

        rows.append({
            "label":label,
            "card":slim(card),
            "usage":hdr,
            "metadata":body.get("metadata"),
        })

    noibat=[x for x in rows if x["label"].startswith("Noibat")]
    noibat_names=sorted(x["card"].get("name") or "" for x in noibat)
    if len(noibat)!=3:
        fail("Noibat anchor did not return three exact identities")

    report={
        "result":"PASS_READ_ONLY",
        "writesPerformed":False,
        "sourceClassification":"TCGPlayer market estimate / active-market pricing reference",
        "probeCount":len(rows),
        "creditsObserved":total_consumed,
        "dailyRemainingAfterAudit":last_remaining,
        "noibat156":{
            "count":len(noibat),
            "names":noibat_names,
            "rows":noibat,
        },
        "finishSamples":rows[3:],
        "diagnostics":{
            "allSetNames":sorted({str(x["card"].get("setName") or "") for x in rows}),
            "allCardNumbers":sorted({str(x["card"].get("cardNumber") or "") for x in rows}),
            "missingExternalCatalogId":[x["label"] for x in rows if not x["card"].get("externalCatalogId")],
            "missingPrintingsAvailable":[x["label"] for x in rows if not x["card"].get("printingsAvailable")],
        },
        "integrationDecision":{
            "automaticProductionIntegration":False,
            "reason":"Read-only identity/coverage audit only. No Cardmarket or retail integration performed."
        }
    }
    print(json.dumps(report,ensure_ascii=False,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
