#!/usr/bin/env python3
"""READ-ONLY audit for Frillish 044/086 Master Ball Reverse Cardmarket runtime mapping."""
import json
import re
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'


def get_json(url, timeout=30):
    req=urllib.request.Request(url,headers={'User-Agent':'Cardoryx-audit/1.0'})
    with urllib.request.urlopen(req,timeout=timeout) as r:
        return json.load(r)


def walk(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values():
            yield from walk(v)
    elif isinstance(obj,list):
        for v in obj:
            yield from walk(v)


def main():
    src=INDEX.read_text(encoding='utf-8')
    print('INDEX_LEN',len(src))
    marker='VERIFIED_EXACT_CARDMARKET_PRICE_GUIDES'
    m=re.search(re.escape(marker),src,re.I)
    if m:
        print(src[max(0,m.start()-1200):min(len(src),m.end()+5000)].replace('\n','\\n'))

    for u in ['https://api.tcgdex.net/v2/it/cards/sv10.5w-044','https://api.tcgdex.net/v2/en/cards/sv10.5w-044']:
        print('\nDETAIL',u)
        try: print(json.dumps(get_json(u,12),ensure_ascii=False)[:30000])
        except Exception as e: print('ERR',repr(e))

    product_urls=[
      'https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json',
      'https://downloads.s3.cardmarket.com/productCatalog/productList/products_6.json',
      'https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json.gz',
    ]
    product_id=None
    for u in product_urls:
        print('\nCM_PRODUCTS',u)
        try:
            data=get_json(u,45)
            hits=[]
            for row in walk(data):
                text=json.dumps(row,ensure_ascii=False).lower()
                if 'frillish' in text and ('xwht044' in text or 'white flare' in text):
                    hits.append(row)
            print('HITS',json.dumps(hits[:20],ensure_ascii=False)[:30000])
            for row in hits:
                for k in ('idProduct','idproduct','id','productId'):
                    if k in row and str(row[k]).isdigit(): product_id=int(row[k]); break
                if product_id: break
            if hits: break
        except Exception as e: print('ERR',repr(e))

    print('PRODUCT_ID',product_id)
    try:
        pg=get_json('https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',45)
        hits=[]
        for row in walk(pg):
            rid=row.get('idProduct') if isinstance(row,dict) else None
            if product_id and str(rid)==str(product_id): hits.append(row)
        print('PRICE_GUIDE_HITS',json.dumps(hits[:10],ensure_ascii=False))
    except Exception as e: print('PRICE_GUIDE_ERR',repr(e))

if __name__=='__main__': main()
