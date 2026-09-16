#!/usr/bin/env python3
from __future__ import annotations
import json, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'artifacts'/'card_identity_cardmarket_audit_report.json'
TARGETS={'ex5-29','ex5-98'}

def walk(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values(): yield from walk(v)
    elif isinstance(obj,list):
        for v in obj: yield from walk(v)

def fetch_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Cardoryx-Cardmarket-Identity-Audit/2.0'})
    with urllib.request.urlopen(req,timeout=120) as r:
        return json.load(r)

def cm_pid(d):
    for k in ('idProduct','id_product','id'):
        try:
            if d.get(k) is not None: return int(d[k])
        except Exception: pass
    return None

def main():
    report=json.loads(REPORT.read_text(encoding='utf-8'))
    cases={}
    pids=set()
    for d in walk(report):
        cid=str(d.get('tcgdexId') or d.get('id') or '')
        if cid in TARGETS and d.get('classification')=='P1_AMBIGUOUS_PRODUCT':
            cases[cid]=d
            for k in ('currentProductId','resolvedProductId'):
                try:
                    if d.get(k): pids.add(int(d[k]))
                except Exception: pass
            for k in ('alternateProductIds','allProductIds'):
                for x in d.get(k) or []:
                    try:pids.add(int(x))
                    except Exception:pass
    live={}
    for cid in sorted(TARGETS):
        try:
            live[cid]=fetch_json('https://api.tcgdex.net/v2/en/cards/'+cid)
            for row in live[cid].get('variants_detailed') or []:
                for x in (row.get('thirdParty',{}).get('cardmarket'),(row.get('pricing',{}).get('cardmarket') or {}).get('idProduct')):
                    try:
                        if x:pids.add(int(x))
                    except Exception:pass
        except Exception as e:
            live[cid]={'error':repr(e)}
    cat=fetch_json('https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json')
    pg=fetch_json('https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json')
    cat_rows=[d for d in walk(cat) if isinstance(d,dict) and cm_pid(d) in pids]
    pg_rows=[d for d in walk(pg) if isinstance(d,dict) and cm_pid(d) in pids]
    out={'targets':sorted(TARGETS),'cases':cases,'live':live,'productIds':sorted(pids),'catalogRows':cat_rows,'priceGuideRows':pg_rows}
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
