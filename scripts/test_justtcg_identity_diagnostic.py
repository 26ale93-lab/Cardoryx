#!/usr/bin/env python3
"""Targeted read-only JustTCG identity diagnostic for Ascended Heroes 156/217."""

import json
import os
import time
import urllib.parse
import urllib.request

BASE="https://api.justtcg.com/v1/cards"
SET_ID="me-ascended-heroes-pokemon"

def get(params, key):
    url=BASE+"?"+urllib.parse.urlencode(params)
    req=urllib.request.Request(url,headers={"x-api-key":key,"accept":"application/json","user-agent":"Cardoryx-JustTCG-Identity-Diagnostic/1.0"})
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))

def slim(body):
    return {
      "meta": body.get("meta"),
      "usage": body.get("_metadata"),
      "data": [{
        "id": c.get("id"),
        "uuid": c.get("uuid"),
        "name": c.get("name"),
        "number": c.get("number"),
        "rarity": c.get("rarity"),
        "set": c.get("set"),
        "set_name": c.get("set_name"),
        "tcgplayerId": c.get("tcgplayerId"),
        "variants": [{
          "id": v.get("id"),
          "condition": v.get("condition"),
          "printing": v.get("printing"),
          "language": v.get("language"),
          "price": v.get("price")
        } for v in (c.get("variants") or [])]
      } for c in (body.get("data") or [])]
    }

def main():
    key=os.environ.get("JUSTTCG_API_KEY","").strip()
    if not key:
        raise SystemExit("missing JUSTTCG_API_KEY")
    by_number=get({"game":"pokemon","set":SET_ID,"number":"156/217","limit":20,"include_null_prices":"true"},key)
    time.sleep(6.2)
    by_name=get({"game":"pokemon","set":SET_ID,"q":"Noibat","limit":20,"include_null_prices":"true"},key)
    print(json.dumps({"result":"PASS_READ_ONLY","byNumber":slim(by_number),"byName":slim(by_name)},ensure_ascii=False,indent=2,sort_keys=True))

if __name__=="__main__":
    main()
