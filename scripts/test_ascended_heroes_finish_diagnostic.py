#!/usr/bin/env python3
import collections, json, urllib.request, time

BASE="https://api.tcgdex.net/v2/en"
def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Cardoryx-readonly-audit/1.0"})
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.load(r)

s=get(f"{BASE}/sets/me02.5")
cards=s.get("cards") or []
foils=collections.Counter()
types=collections.Counter()
examples={}
errors=[]
for i,row in enumerate(cards):
    cid=row.get("id")
    if not cid: continue
    try:
        d=get(f"{BASE}/cards/{cid}")
    except Exception as e:
        errors.append([cid,repr(e)])
        continue
    for v in d.get("variants_detailed") or []:
        t=str(v.get("type") or "").lower()
        foil=str(v.get("foil") or "").lower()
        types[t]+=1
        if foil:
            foils[foil]+=1
            examples.setdefault(foil,[]).append({"id":cid,"name":d.get("name"),"type":t})
    if i and i%60==0: time.sleep(0.2)
print(json.dumps({
  "set": {"id":s.get("id"),"name":s.get("name"),"cards":len(cards)},
  "foilCounts":dict(sorted(foils.items())),
  "typeCounts":dict(sorted(types.items())),
  "examples":{k:v[:4] for k,v in sorted(examples.items())},
  "errors":errors[:20],"errorCount":len(errors)
},indent=2))
