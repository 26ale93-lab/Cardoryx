#!/usr/bin/env python3
"""READ-ONLY audit for Frillish 044/086 Master Ball Reverse Cardmarket mapping."""
import json,urllib.request
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'
UA='Mozilla/5.0 AppleWebKit/537.36 Chrome/128 Safari/537.36'

def get_json(url,timeout=45):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json,*/*'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)

def main():
    print('INDEX_LEN',len(INDEX.read_text(encoding='utf-8')))
    products_doc=get_json('https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json')
    products=products_doc.get('products',[]) if isinstance(products_doc,dict) else []
    frillish=[p for p in products if 'frillish' in str(p.get('name','')).lower()]
    frillish=sorted(frillish,key=lambda x:int(x.get('idProduct') or 0))
    print('PRODUCT_SNAPSHOT',products_doc.get('createdAt'))
    print('FRILLISH_ROWS',json.dumps(frillish,ensure_ascii=False))
    groups=defaultdict(list)
    for p in frillish:groups[str(p.get('idMetacard'))].append(p)
    print('FRILLISH_METACARD_GROUPS',json.dumps({k:v for k,v in groups.items() if len(v)>1},ensure_ascii=False))

    pg_doc=get_json('https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json')
    pg_rows=pg_doc.get('priceGuides') or pg_doc.get('products') or pg_doc.get('priceGuide') or []
    if not isinstance(pg_rows,list):
        pg_rows=[]
        if isinstance(pg_doc,dict):
            for v in pg_doc.values():
                if isinstance(v,list) and v and isinstance(v[0],dict) and 'idProduct' in v[0]:pg_rows=v;break
    pg={int(r['idProduct']):r for r in pg_rows if isinstance(r,dict) and str(r.get('idProduct','')).isdigit()}
    compact=[]
    for p in frillish:
        pid=int(p.get('idProduct') or 0)
        r=pg.get(pid,{})
        compact.append({
          'idProduct':pid,'name':p.get('name'),'idExpansion':p.get('idExpansion'),'idMetacard':p.get('idMetacard'),'dateAdded':p.get('dateAdded'),
          'trend':r.get('trend'),'avg1':r.get('avg1'),'avg7':r.get('avg7'),'avg30':r.get('avg30'),'avg':r.get('avg'),'low':r.get('low'),
          'trend-holo':r.get('trend-holo'),'avg7-holo':r.get('avg7-holo'),'low-holo':r.get('low-holo')
        })
    print('FRILLISH_WITH_PRICES',json.dumps(compact,ensure_ascii=False))

    # Probe official expansion-list download patterns; failures are diagnostic only.
    for u in [
      'https://downloads.s3.cardmarket.com/productCatalog/expansionList/expansions_6.json',
      'https://downloads.s3.cardmarket.com/productCatalog/expansionList/expansion_6.json',
    ]:
        try:
            d=get_json(u,20)
            print('EXPANSION_URL_OK',u)
            print('EXPANSION_DOC',json.dumps(d,ensure_ascii=False)[:20000])
            break
        except Exception as e:print('EXPANSION_URL_ERR',u,repr(e))

if __name__=='__main__':main()
