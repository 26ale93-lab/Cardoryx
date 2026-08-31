#!/usr/bin/env python3
import json, statistics
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1]
RETAIL=ROOT/"data"/"retail_prices.json"
REPORT=ROOT/"bsa_store_v2_report.json"
BAD={1181.0,1184.0}
def norm(x): return str(x or "").strip().casefold()
def calc(offers):
    vv=[o for o in offers if isinstance(o,dict) and isinstance(o.get("price"),(int,float))]
    pp=[float(o["price"]) for o in vv]; ss={norm(o.get("store")) for o in vv if o.get("store")}
    ok=len(pp)>=3 and len(ss)>=3
    return {"reliable":ok,"count":len(pp),"stores":len(ss),
            "min":round(min(pp),2) if ok else None,
            "max":round(max(pp),2) if ok else None,
            "median":round(statistics.median(pp),2) if ok else None}
data=json.loads(RETAIL.read_text(encoding="utf-8"))
cards=data.get("cards",{})
st=Counter(); affected=[]
for key,c in cards.items():
    offers=c.get("offers",[]) or []
    bad=[o for o in offers if norm(o.get("store"))=="bsa store" and isinstance(o.get("price"),(int,float)) and round(float(o["price"]),2) in BAD]
    if not bad: continue
    st["cardsWithAnomalousBsaOffer"]+=1
    before=c.get("stats") or calc(offers)
    clean=[o for o in offers if o not in bad]
    after=calc(clean)
    if before.get("reliable") and not after["reliable"]: st["wouldLoseReliableStatus"]+=1
    elif before.get("reliable"): st["wouldRemainReliable"]+=1
    else: st["currentlyNotReliable"]+=1
    if before.get("min")!=after["min"]: st["minWouldChange"]+=1
    if before.get("max")!=after["max"]: st["maxWouldChange"]+=1
    if before.get("median")!=after["median"]: st["medianWouldChange"]+=1
    affected.append({"key":key,"set":c.get("set"),"number":c.get("number"),"name":c.get("name"),"variant":c.get("variant"),
                     "anomalousBsaOffers":bad,"otherOffers":clean,"before":before,"afterSimulation":after})
report={"schema":2,"source":"BSA Store","mode":"read-only anomalous-cluster impact simulation",
        "rules":{"retailPricesModified":False,"cardmarketTouched":False,"anomalousCluster":sorted(BAD),
                 "noReplacementPriceInvented":True,"scope":"BSA Store only"},
        "stats":dict(st),"affectedCards":affected}
REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
print(json.dumps({"stats":dict(st),"report":str(REPORT)},ensure_ascii=False,indent=2))
