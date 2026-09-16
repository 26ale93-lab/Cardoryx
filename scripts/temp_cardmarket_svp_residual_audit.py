#!/usr/bin/env python3
import concurrent.futures
import json
import urllib.request
from collections import Counter
from pathlib import Path

REPORT=Path('artifacts/card_identity_cardmarket_audit_report.json')
API='https://api.tcgdex.net/v2/en/cards/'

def fetch(card_id):
    try:
        with urllib.request.urlopen(API+card_id, timeout=20) as r:
            return card_id, json.load(r), None
    except Exception as e:
        return card_id, None, str(e)

def cm_pid(row):
    value=((row.get('thirdParty') or {}).get('cardmarket'))
    try: return int(value)
    except (TypeError,ValueError): return None

def pricing_pid(row):
    value=(((row.get('pricing') or {}).get('cardmarket') or {}).get('idProduct'))
    try: return int(value)
    except (TypeError,ValueError): return None

def flags(row):
    return {
        'type':row.get('type'), 'subtype':row.get('subtype'), 'foil':row.get('foil'),
        'stamp':row.get('stamp'), 'cardmarket':cm_pid(row), 'pricingProduct':pricing_pid(row),
    }

def tax(row):
    stamp=row.get('stamp')
    if isinstance(stamp,list): stamp='+'.join(sorted(map(str,stamp)))
    return (str(row.get('type') or ''),str(row.get('subtype') or ''),str(row.get('foil') or ''),str(stamp or ''))

report=json.loads(REPORT.read_text(encoding='utf-8'))
targets=sorted(x for x in report.get('p1AmbiguousProductIds',[]) if x.startswith('svp-'))
results={}; errors={}
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    futures=[pool.submit(fetch,x) for x in targets]
    for f in concurrent.futures.as_completed(futures):
        card_id,card,error=f.result()
        if error: errors[card_id]=error
        else: results[card_id]=card

classes=Counter(); top_taxonomy=Counter(); alternate_taxonomy=Counter(); rows=[]
for card_id in targets:
    card=results.get(card_id)
    if not card:
        classes['LIVE_FETCH_ERROR']+=1
        rows.append({'id':card_id,'class':'LIVE_FETCH_ERROR','error':errors.get(card_id)})
        continue
    cm=((card.get('pricing') or {}).get('cardmarket') or {})
    try: top=int(cm.get('idProduct'))
    except (TypeError,ValueError): top=None
    variants=card.get('variants_detailed') or []
    same=[r for r in variants if cm_pid(r)==top] if top else []
    base=[]; special=[]
    for r in same:
        if r.get('stamp') or r.get('foil') or r.get('subtype'): special.append(r)
        else: base.append(r)
    all_pids=sorted({p for r in variants for p in [cm_pid(r)] if p})
    if not top: cls='NO_LIVE_TOP_PRODUCT'
    elif not same: cls='TOP_PRODUCT_ABSENT_FROM_VARIANTS'
    elif special and not base: cls='TOP_PRODUCT_SPECIAL_ONLY'
    elif special and base: cls='TOP_PRODUCT_REUSED_BASE_AND_SPECIAL'
    elif len(all_pids)>1: cls='TOP_PRODUCT_BASE_WITH_ALTERNATE_PRODUCTS'
    else: cls='TOP_PRODUCT_BASE_ONLY'
    classes[cls]+=1
    for r in same: top_taxonomy[tax(r)]+=1
    for r in variants:
        if cm_pid(r) and cm_pid(r)!=top: alternate_taxonomy[tax(r)]+=1
    rows.append({
        'id':card_id,'name':card.get('name'),'localId':card.get('localId'),
        'topProductId':top,'topTrend':cm.get('trend'),'allProductIds':all_pids,
        'sameProductRows':[flags(r) for r in same],
        'alternateRows':[flags(r) for r in variants if cm_pid(r) and cm_pid(r)!=top],
        'class':cls,
    })

summary={
    'targetCount':len(targets),'fetched':len(results),'errors':errors,
    'classes':dict(classes),
    'topProductTaxonomy':[{"type":k[0],"subtype":k[1],"foil":k[2],"stamp":k[3],"count":v} for k,v in top_taxonomy.most_common()],
    'alternateProductTaxonomy':[{"type":k[0],"subtype":k[1],"foil":k[2],"stamp":k[3],"count":v} for k,v in alternate_taxonomy.most_common()],
    'rows':rows,
}
Path('artifacts/cardmarket_svp_residual_audit_report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:summary[k] for k in ('targetCount','fetched','classes','topProductTaxonomy','alternateProductTaxonomy')},ensure_ascii=False,indent=2))
print('SPECIAL_ONLY_DETAIL')
for row in rows:
    if row.get('class')=='TOP_PRODUCT_SPECIAL_ONLY':
        print(json.dumps({'id':row['id'],'name':row['name'],'top':row['topProductId'],'topRows':row['sameProductRows'],'alternates':row['alternateRows']},ensure_ascii=False))
print('OTHER_DETAIL')
for row in rows:
    if row.get('class')!='TOP_PRODUCT_SPECIAL_ONLY':
        print(json.dumps(row,ensure_ascii=False))
