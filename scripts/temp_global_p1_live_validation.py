#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures, importlib.util, json, sys, urllib.parse, urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'artifacts'/'card_identity_cardmarket_audit_report.json'
API='https://api.tcgdex.net/v2/en/cards'
OUT=ROOT/'artifacts'/'global_p1_live_validation_report.json'


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
                if cid:out.add(cid)
            for v in o.values():walk(v)
        elif isinstance(o,list):
            for v in o:walk(v)
    walk(root);return sorted(out)


def fetch(cid):
    req=urllib.request.Request(f'{API}/{urllib.parse.quote(cid)}',headers={'User-Agent':'Cardoryx-Global-P1-Live-Validation/1.0'})
    try:
        with urllib.request.urlopen(req,timeout=60) as r:return cid,json.load(r),None
    except Exception as e:return cid,None,str(e)


def ipid(v):
    try:return int(v)
    except (TypeError,ValueError):return None


def set_prefix(cid): return cid.rsplit('-',1)[0] if '-' in cid else ''


def main():
    mod=load_mod();ids=p1_ids();live={};errors={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=32) as pool:
        futures=[pool.submit(fetch,cid) for cid in ids]
        for f in concurrent.futures.as_completed(futures):
            cid,card,err=f.result()
            if card:live[cid]=card
            if err:errors[cid]=err
    counts=Counter();by_set=defaultdict(Counter);rows=[]
    for cid in ids:
        card=live.get(cid)
        if not card:
            cls='LIVE_FETCH_ERROR';counts[cls]+=1;by_set[set_prefix(cid)][cls]+=1;rows.append({'tcgdexId':cid,'classification':cls,'error':errors.get(cid)});continue
        cm=((card.get('pricing') or {}).get('cardmarket') or {});top=ipid(cm.get('idProduct') or cm.get('id_product'))
        usable=any(isinstance(cm.get(k),(int,float)) and cm.get(k)>0 for k in ('trend','avg7','avg30','avg','low'))
        base=[];explicit=[]
        for row in card.get('variants_detailed') or []:
            pid=ipid((row.get('thirdParty') or {}).get('cardmarket'));pcm=((row.get('pricing') or {}).get('cardmarket') or {});ppid=ipid(pcm.get('idProduct') or pcm.get('id_product'))
            record={'pid':pid,'pricingPid':ppid,'type':row.get('type'),'stamp':row.get('stamp'),'foil':row.get('foil'),'firstEdition':row.get('firstEdition')}
            (base if mod.is_base_row(row) else explicit).append(record)
        matching=[r for r in base if r['pid']==top and r['pricingPid']==top]
        overlap=[r for r in explicit if r['pid']==top]
        if not top:cls='NO_LIVE_TOP_PRODUCT'
        elif not matching:cls='TOP_PRODUCT_NOT_EXACT_BASE_ROW'
        elif not usable:cls='NO_USABLE_LIVE_PRICE'
        elif overlap:cls='TOP_PRODUCT_ALSO_EXPLICIT_VARIANT'
        else:cls='LIVE_EXACT_BASE_SAFE'
        counts[cls]+=1;by_set[set_prefix(cid)][cls]+=1
        rows.append({'tcgdexId':cid,'setId':set_prefix(cid),'localId':card.get('localId'),'name':card.get('name'),'topProductId':top,'classification':cls,'explicitOverlapCount':len(overlap)})
    set_rows=[]
    for sid,c in by_set.items():
        set_rows.append({'setId':sid,'total':sum(c.values()),**dict(c)})
    set_rows.sort(key=lambda r:(-r.get('LIVE_EXACT_BASE_SAFE',0),-r['total'],r['setId']))
    report={'targetCount':len(ids),'liveFetched':len(live),'errorCount':len(errors),'counts':dict(counts),'bySet':set_rows,'notSafe':[r for r in rows if r['classification']!='LIVE_EXACT_BASE_SAFE']}
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'targetCount':len(ids),'liveFetched':len(live),'errorCount':len(errors),'counts':dict(counts),'topSafeSets':set_rows[:25],'notSafeCount':len(report['notSafe'])},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
