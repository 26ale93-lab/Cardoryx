#!/usr/bin/env python3
import json, urllib.parse, urllib.request

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Cardoryx-readonly-audit/1.0"})
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.load(r)

def search(lang):
    q=urllib.parse.urlencode({"name":"Noibat"})
    rows=get(f"https://api.tcgdex.net/v2/{lang}/cards?{q}")
    if isinstance(rows,dict):
        rows=rows.get("cards") or rows.get("data") or []
    return rows

out={}
for lang in ("en","it"):
    rows=search(lang)
    matches=[]
    for row in rows:
        if str(row.get("localId","")).lstrip("0")=="156":
            cid=row.get("id")
            try:
                detail=get(f"https://api.tcgdex.net/v2/{lang}/cards/{cid}")
            except Exception as e:
                detail={"id":cid,"error":repr(e)}
            matches.append(detail)
    out[lang]=matches
print(json.dumps(out,ensure_ascii=False,indent=2))
