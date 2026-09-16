#!/usr/bin/env python3
from __future__ import annotations
import json
from collections import defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'artifacts'/'card_identity_cardmarket_audit_report.json'

def walk(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values(): yield from walk(v)
    elif isinstance(obj,list):
        for v in obj: yield from walk(v)

def first(d,*keys):
    for k in keys:
        v=d.get(k)
        if v not in (None,'',[],{}): return v
    return None

def fallback_identity(cid):
    if '-' not in cid: return '', ''
    return cid.rsplit('-',1)[0],cid.rsplit('-',1)[1]

def main():
    root=json.loads(REPORT.read_text(encoding='utf-8'))
    seen={}
    for d in walk(root):
        if d.get('classification')!='P1_AMBIGUOUS_PRODUCT': continue
        cid=str(first(d,'tcgdexId','id') or '').strip()
        if not cid or cid in seen: continue
        fallback_set,fallback_local=fallback_identity(cid)
        set_id=str(first(d,'setId') or fallback_set).strip()
        local=str(first(d,'localId','normalizedLocalId') or fallback_local).strip()
        seen[cid]={'tcgdexId':cid,'setId':set_id,'localId':local,'name':str(first(d,'name','nameIT') or '').strip(),'currentProductId':first(d,'currentProductId','resolvedProductId'),'alternateProductIds':first(d,'alternateProductIds','allProductIds') or []}
    by_set=defaultdict(list)
    for r in seen.values(): by_set[r['setId']].append(r)
    rows=[]
    for sid,cards in by_set.items():
        rows.append({'setId':sid,'p1Count':len(cards),'samples':[r['tcgdexId'] for r in sorted(cards,key=lambda x:(x['localId'],x['tcgdexId']))[:20]]})
    rows.sort(key=lambda x:(-x['p1Count'],x['setId']))
    out={'classificationTotals':root.get('classificationTotals'),'uniqueP1Found':len(seen),'setCount':len(rows),'topSets':rows[:30]}
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
