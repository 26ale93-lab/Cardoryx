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
        'type':row.get('type'),
        'subtype':row.get('subtype'),
        'foil':row.get('foil'),
        'stamp':row.get('stamp'),
        'cardmarket':cm_pid(row),
        'pricingProduct':pricing_pid(row),
    }

report=json.loads(REPORT.read_text(encoding='utf-8'))
targets=sorted(x for x in report.get('p1AmbiguousProductIds',[]) if x.startswith('svp-'))
results={}
errors={}
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    futures=[pool.submit(fetch,x) for x in targets]
    for f in concurrent.futures.as_completed(futures):
        card_id,card,error=f.result()
        if error: errors[card_id]=error
        else: results[card_id]=card

classes=Counter()
rows=[]
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
        stamp=r.get('stamp')
        foil=r.get('foil')
        subtype=r.get('subtype')
        # Conservative: anything with stamp/foil/subtype metadata is product-specific.
        if stamp or foil or subtype:
            special.append(r)
        else:
            base.append(r)
    all_pids=sorted({p for r in variants for p in [cm_pid(r)] if p})
    if not top:
        cls='NO_LIVE_TOP_PRODUCT'
    elif not same:
        cls='TOP_PRODUCT_ABSENT_FROM_VARIANTS'
    elif special and not base:
        cls='TOP_PRODUCT_SPECIAL_ONLY'
    elif special and base:
        cls='TOP_PRODUCT_REUSED_BASE_AND_SPECIAL'
    elif len(all_pids)>1:
        cls='TOP_PRODUCT_BASE_WITH_ALTERNATE_PRODUCTS'
    else:
        cls='TOP_PRODUCT_BASE_ONLY'
    classes[cls]+=1
    rows.append({
        'id':card_id,
        'name':card.get('name'),
        'localId':card.get('localId'),
        'topProductId':top,
        'topTrend':cm.get('trend'),
        'allProductIds':all_pids,
        'sameProductRows':[flags(r) for r in same],
        'allRows':[flags(r) for r in variants],
        'class':cls,
    })

summary={'targetCount':len(targets),'fetched':len(results),'errors':errors,'classes':dict(classes),'rows':rows}
Path('artifacts/cardmarket_svp_residual_audit_report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'targetCount':len(targets),'fetched':len(results),'errors':len(errors),'classes':dict(classes)},ensure_ascii=False,indent=2))
for row in rows:
    print(json.dumps({k:row.get(k) for k in ('id','name','localId','topProductId','allProductIds','class')},ensure_ascii=False))
