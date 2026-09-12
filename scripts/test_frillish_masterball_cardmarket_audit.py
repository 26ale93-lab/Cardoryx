#!/usr/bin/env python3
"""READ-ONLY audit for Frillish 044/086 Master Ball Reverse Cardmarket mapping."""
import json,re,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'
UA='Mozilla/5.0 AppleWebKit/537.36 Chrome/128 Safari/537.36'

def get_json(url,timeout=45):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'application/json,*/*'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return json.load(r)

def snippet(src,marker,before=1600,after=7000):
    p=src.find(marker)
    return '' if p<0 else src[max(0,p-before):min(len(src),p+after)]

def main():
    src=INDEX.read_text(encoding='utf-8')
    for marker in ['function verifiedVariantPrice','VERIFIED_VARIANT','verifiedVariantPrice(c,variant)','function verifiedStampPrice']:
        print('\n===',marker,'===')
        print(snippet(src,marker).replace('\n','\\n'))

    products_doc=get_json('https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json')
    products=products_doc.get('products',[])
    rows=[p for p in products if p.get('idMetacard')==450184 and int(p.get('idProduct') or 0)>=829000]
    print('\nFRILLISH_CURRENT_PRODUCTS',json.dumps(rows,ensure_ascii=False))

    pg_doc=get_json('https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json')
    pg_rows=[]
    for v in pg_doc.values() if isinstance(pg_doc,dict) else []:
        if isinstance(v,list) and v and isinstance(v[0],dict) and 'idProduct' in v[0]:pg_rows=v;break
    pg={int(r['idProduct']):r for r in pg_rows if str(r.get('idProduct','')).isdigit()}
    for pid in [836573,836574]:
        print('PRICE',pid,json.dumps(pg.get(pid),ensure_ascii=False))

if __name__=='__main__':main()
