#!/usr/bin/env python3
"""Read-only Cardmarket catalogue/price audit for Eevee 116/128 Cosmos Holo.
No changes to retail prices, the collection, or Cardmarket source data.
"""
import json, re, sys, urllib.request

CATALOG="https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json"
GUIDE="https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json"
HEADERS={"User-Agent":"Cardoryx-ReadOnly-Cardmarket-Audit/1.0"}

def get(url):
    req=urllib.request.Request(url,headers=HEADERS)
    with urllib.request.urlopen(req,timeout=120) as response:
        return json.load(response)

def records(doc):
    if isinstance(doc,list): return doc
    if not isinstance(doc,dict): return []
    for k in ("products","product","priceGuides","priceGuide","items"):
        if isinstance(doc.get(k),list): return doc[k]
    return []

def key(row,*names):
    for n in names:
        if row.get(n) is not None:return row[n]
    return None

def main():
    products=records(get(CATALOG))
    if len(products)<10000:raise RuntimeError("Incomplete Cardmarket product catalogue; fail closed")
    candidates=[]
    for p in products:
        if not isinstance(p,dict):continue
        name=str(key(p,"name","Name") or "")
        if not re.search(r"\\beevee\\b",name,re.I):continue
        if not re.search(r"(?:x?30c|30th|celebration)",name,re.I):continue
        candidates.append({"productId":key(p,"idProduct","id_product","productId"),
                           "name":name,
                           "expansionId":key(p,"idExpansion","id_expansion","expansionId"),
                           "metacardId":key(p,"idMetacard","id_metacard","metacardId"),
                           "original":p})
    ids={str(x["productId"]) for x in candidates if x["productId"] is not None}
    guide=records(get(GUIDE))
    if len(guide)<10000:raise RuntimeError("Incomplete Cardmarket price guide; fail closed")
    prices={}
    for p in guide:
        if not isinstance(p,dict):continue
        pid=str(key(p,"idProduct","id_product","productId"))
        if pid in ids:prices[pid]=p
    output={"catalogue_rows":len(products),"price_rows":len(guide),
      "candidates":[{**{k:v for k,v in c.items() if k!="original"},
                     "catalog":c["original"],"priceGuide":prices.get(str(c["productId"]))} for c in candidates]}
    with open("eevee_116_cardmarket_audit.json","w",encoding="utf-8") as f:
        json.dump(output,f,indent=2,ensure_ascii=False)
    print("CATALOGUE",len(products),"PRICE_GUIDE",len(guide))
    for c in output["candidates"]:
        print("CANDIDATE",json.dumps({"id":c["productId"],"name":c["name"],
           "expansion":c["expansionId"],"metacard":c["metacardId"],
           "price":c["priceGuide"]},ensure_ascii=False))
    if not candidates:raise RuntimeError("No matching Eevee 30C products; fail closed")
if __name__=="__main__":
    try:main()
    except Exception as e:
        print("AUDIT FAILED",repr(e),file=sys.stderr);sys.exit(1)
