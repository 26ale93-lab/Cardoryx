#!/usr/bin/env python3
from __future__ import annotations
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'artifacts'/'card_identity_cardmarket_audit_report.json'

def walk(obj):
    if isinstance(obj,dict):
        yield obj
        for v in obj.values(): yield from walk(v)
    elif isinstance(obj,list):
        for v in obj: yield from walk(v)

def main():
    r=json.loads(REPORT.read_text(encoding='utf-8'))
    rows=[]; seen=set()
    for d in walk(r):
        if d.get('classification')!='P1_AMBIGUOUS_PRODUCT': continue
        cid=str(d.get('tcgdexId') or d.get('id') or '')
        if not cid or cid in seen: continue
        deltas=d.get('trendDeltaVersusCurrent') or {}
        vals=[]
        for pid,delta in deltas.items():
            try: vals.append((abs(float(delta)),float(delta),int(pid)))
            except Exception: pass
        if not vals: continue
        vals.sort(reverse=True)
        seen.add(cid)
        rows.append({'tcgdexId':cid,'currentProductId':d.get('currentProductId'),'currentTrend':d.get('currentCardoryxValue'),'largestAbsDelta':vals[0][0],'signedDelta':vals[0][1],'alternateProductId':vals[0][2],'allDeltas':deltas})
    rows.sort(key=lambda x:(-x['largestAbsDelta'],x['tcgdexId']))
    print(json.dumps({'classificationTotals':r.get('classificationTotals'),'rankedCount':len(rows),'top20':rows[:20]},ensure_ascii=False,indent=2))
if __name__=='__main__': main()
