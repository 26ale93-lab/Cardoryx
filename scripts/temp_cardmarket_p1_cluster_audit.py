#!/usr/bin/env python3
from __future__ import annotations
import json
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/'artifacts'/'card_identity_cardmarket_audit_report.json'
OUT=ROOT/'artifacts'/'cardmarket_p1_cluster_audit_report.json'

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

def richness(d):
    keys=('setId','setNameEN','setNameIT','localId','normalizedLocalId','name','nameIT',
          'currentProductId','resolvedProductId','alternateProductIds','allProductIds',
          'cardmarketProductCatalog','reason','recommendedAction','currentCardoryxValue')
    return sum(1 for k in keys if d.get(k) not in (None,'',[],{}))

def normalized(d):
    cid=str(first(d,'tcgdexId','id') or '').strip()
    set_id=str(first(d,'setId') or '').strip()
    set_name=str(first(d,'setNameEN','setNameIT') or '').strip()
    local=str(first(d,'localId','normalizedLocalId') or '').strip()
    name=str(first(d,'name','nameIT') or '').strip()
    current=first(d,'currentProductId','resolvedProductId')
    alternatives=first(d,'alternateProductIds','allProductIds') or []
    if not isinstance(alternatives,list): alternatives=[alternatives]
    catalog=d.get('cardmarketProductCatalog') or {}
    current_expansion=None
    try:
        row=catalog.get(str(current)) or catalog.get(int(current))
        if isinstance(row,dict): current_expansion=row.get('idExpansion')
    except Exception: pass
    alt_expansions=[]
    for pid in alternatives:
        try: row=catalog.get(str(pid)) or catalog.get(int(pid))
        except Exception: row=None
        if isinstance(row,dict) and row.get('idExpansion') is not None:
            alt_expansions.append(row.get('idExpansion'))
    return {
        'tcgdexId':cid,'setId':set_id,'setName':set_name,'localId':local,'name':name,
        'currentProductId':current,'alternateProductIds':alternatives,
        'currentExpansion':current_expansion,'alternateExpansions':sorted(set(alt_expansions),key=str),
        'reason':d.get('reason'),'recommendedAction':d.get('recommendedAction'),
        'currentCardoryxValue':d.get('currentCardoryxValue'),
        'trendDeltaVersusCurrent':d.get('trendDeltaVersusCurrent'),
        '_richness':richness(d)
    }

def main():
    root=json.loads(REPORT.read_text(encoding='utf-8'))
    seen={}
    occurrences=Counter()
    for d in walk(root):
        if d.get('classification')!='P1_AMBIGUOUS_PRODUCT': continue
        cid=str(first(d,'tcgdexId','id') or '').strip()
        if not cid: continue
        occurrences[cid]+=1
        candidate=normalized(d)
        if cid not in seen or candidate['_richness']>seen[cid]['_richness']:
            seen[cid]=candidate
    for row in seen.values(): row.pop('_richness',None)
    by_set=defaultdict(list)
    for r in seen.values(): by_set[r['setId']].append(r)
    set_rows=[]
    for sid,rows in by_set.items():
        names=Counter(r['setName'] for r in rows if r['setName'])
        current_exp=Counter(str(r['currentExpansion']) for r in rows if r['currentExpansion'] is not None)
        alt_exp=Counter(str(x) for r in rows for x in r['alternateExpansions'])
        set_rows.append({
            'setId':sid,'setName':names.most_common(1)[0][0] if names else '',
            'p1Count':len(rows),'currentExpansionCounts':dict(current_exp),
            'alternateExpansionCounts':dict(alt_exp),
            'sample':sorted(rows,key=lambda x:(x['localId'],x['tcgdexId']))[:12]
        })
    set_rows.sort(key=lambda x:(-x['p1Count'],x['setId']))
    report={
        'sourceClassificationTotals':root.get('classificationTotals'),
        'uniqueP1Found':len(seen),'duplicateOccurrences':sum(occurrences.values())-len(seen),
        'richRowsWithSetId':sum(1 for r in seen.values() if r['setId']),
        'setCount':len(set_rows),'topSets':set_rows[:25],
        'allSets':[{k:v for k,v in row.items() if k!='sample'} for row in set_rows]
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
