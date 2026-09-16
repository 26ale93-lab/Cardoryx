#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures, importlib.util, json, sys, urllib.parse, urllib.request
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'artifacts'/'card_identity_cardmarket_audit_report.json'
API='https://api.tcgdex.net/v2/en/cards'


def load_mod():
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('cm',ROOT/'scripts'/'test_card_identity_cardmarket_audit.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod


def p1_ids():
    root=json.loads(AUDIT.read_text(encoding='utf-8'));out=set()
    def walk(o):
        if isinstance(o,dict):
            if o.get('classification')=='P1_AMBIGUOUS_PRODUCT':
                cid=str(o.get('tcgdexId') or o.get('id') or '').strip()
                if cid.startswith('ex2-'):out.add(cid)
            for v in o.values():walk(v)
        elif isinstance(o,list):
            for v in o:walk(v)
    walk(root);return sorted(out)


def fetch(cid):
    req=urllib.request.Request(f'{API}/{urllib.parse.quote(cid)}',headers={'User-Agent':'Cardoryx-EX2-Live-Validation/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=60) as r:return cid,json.load(r),None
    except Exception as e:return cid,None,str(e)


def int_pid(v):
    try:return int(v)
    except (TypeError,ValueError):return None


def main():
    mod=load_mod(); ids=p1_ids(); live={}; errors={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:
        fs=[pool.submit(fetch,cid) for cid in ids]
        for f in concurrent.futures.as_completed(fs):
            cid,card,err=f.result()
            if card:live[cid]=card
            if err:errors[cid]=err
    rows=[];counts=Counter()
    for cid in ids:
        card=live.get(cid)
        if not card:
            cls='LIVE_FETCH_ERROR'; counts[cls]+=1; rows.append({'tcgdexId':cid,'classification':cls,'error':errors.get(cid)});continue
        cm=((card.get('pricing') or {}).get('cardmarket') or {})
        top=int_pid(cm.get('idProduct') or cm.get('id_product'))
        base=[]; explicit=[]
        for row in card.get('variants_detailed') or []:
            pid=int_pid((row.get('thirdParty') or {}).get('cardmarket'))
            pcm=((row.get('pricing') or {}).get('cardmarket') or {})
            pricing_pid=int_pid(pcm.get('idProduct') or pcm.get('id_product'))
            item={'type':row.get('type'),'pid':pid,'pricingPid':pricing_pid,'stamp':row.get('stamp'),'foil':row.get('foil'),'firstEdition':row.get('firstEdition')}
            if mod.is_base_row(row): base.append(item)
            else: explicit.append(item)
        top_base=[r for r in base if r['pid']==top and r['pricingPid']==top]
        usable_price=any(isinstance(cm.get(k),(int,float)) and cm.get(k)>0 for k in ('trend','avg7','avg30','avg','low'))
        explicit_overlap=[r for r in explicit if r['pid']==top]
        if not top:
            cls='NO_LIVE_TOP_PRODUCT'
        elif not top_base:
            cls='TOP_PRODUCT_NOT_EXACT_BASE_ROW'
        elif not usable_price:
            cls='NO_USABLE_LIVE_PRICE'
        elif explicit_overlap:
            cls='TOP_PRODUCT_ALSO_EXPLICIT_VARIANT'
        else:
            cls='LIVE_EXACT_BASE_SAFE'
        counts[cls]+=1
        rows.append({'tcgdexId':cid,'localId':card.get('localId'),'name':card.get('name'),'topProductId':top,'usablePrice':usable_price,'baseRows':base,'explicitRows':explicit,'classification':cls})
    print(json.dumps({'targetCount':len(ids),'liveFetched':len(live),'errors':errors,'counts':dict(counts),'notSafe':[r for r in rows if r['classification']!='LIVE_EXACT_BASE_SAFE']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
