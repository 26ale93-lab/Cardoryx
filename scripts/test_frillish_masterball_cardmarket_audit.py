#!/usr/bin/env python3
"""READ-ONLY audit for Frillish 044/086 Master Ball Reverse Cardmarket runtime mapping."""
import json,re,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'
UA='Mozilla/5.0 AppleWebKit/537.36 Chrome/128 Safari/537.36'

def get_bytes(url,timeout=30):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'*/*'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.status,r.headers,r.read()

def get_json(url,timeout=30):
    _,_,b=get_bytes(url,timeout);return json.loads(b.decode('utf-8'))

def walk(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values():yield from walk(v)
    elif isinstance(obj,list):
        for v in obj:yield from walk(v)

def main():
    print('INDEX_LEN',len(INDEX.read_text(encoding='utf-8')))
    product_url='https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json'
    try:
        status,headers,b=get_bytes(product_url,45);text=b.decode('utf-8','replace')
        print('CM_PRODUCTS_STATUS',status,'BYTES',len(b),'FRILLISH_COUNT',text.lower().count('frillish'),'XWHT044_COUNT',text.lower().count('xwht044'))
        data=json.loads(text);hits=[]
        for row in walk(data):
            s=json.dumps(row,ensure_ascii=False).lower()
            if 'frillish' in s:hits.append(row)
        print('FRILLISH_HITS',json.dumps(hits[:30],ensure_ascii=False)[:30000])
    except Exception as e:print('PRODUCT_ERR',repr(e))
    for u in ['https://www.cardmarket.com/en/Pokemon/Products/Singles/White-Flare-Additionals/Frillish-V2-xWHT044','https://www.cardmarket.com/it/Pokemon/Products/Singles/White-Flare-Additionals/Frillish-V2-xWHT044']:
        print('CM_PAGE',u)
        try:
            status,headers,b=get_bytes(u,25);text=b.decode('utf-8','replace')
            print('STATUS',status,'BYTES',len(b))
            for pat in [r'idProduct[^0-9]{0,20}(\d+)',r'productId[^0-9]{0,20}(\d+)',r'product-id[^0-9]{0,20}(\d+)']:
                print('PAT',pat,re.findall(pat,text,re.I)[:20])
            for needle in ['Frillish','xWHT044','Master Ball','2.05','0.99']:
                p=text.lower().find(needle.lower());print('NEEDLE',needle,p,re.sub(r'\s+',' ',text[max(0,p-300):p+900]) if p>=0 else '')
        except Exception as e:print('PAGE_ERR',repr(e))
    try:
        pg=get_json('https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',45);rows=[]
        for row in walk(pg):
            if isinstance(row,dict) and row.get('idProduct'):
                trend=float(row.get('trend') or 0);low=float(row.get('low') or 0)
                if abs(trend-2.05)<0.0001 or abs(low-0.99)<0.0001:
                    rows.append({k:row.get(k) for k in ['idProduct','trend','avg1','avg7','avg30','low']})
        print('PRICE_CANDIDATES_BY_VALUES',json.dumps(rows[:100],ensure_ascii=False))
    except Exception as e:print('PRICE_GUIDE_ERR',repr(e))
if __name__=='__main__':main()
