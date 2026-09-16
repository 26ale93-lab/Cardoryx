#!/usr/bin/env python3
import concurrent.futures
import json
import urllib.request
from collections import Counter,defaultdict
from pathlib import Path
from test_card_identity_cardmarket_audit import download_if_needed, rows as catalogue_rows

REPORT=Path('artifacts/card_identity_cardmarket_audit_report.json')
API='https://api.tcgdex.net/v2/en/cards/'

def fetch(card_id):
    try:
        with urllib.request.urlopen(API+card_id, timeout=20) as r: return card_id,json.load(r),None
    except Exception as e: return card_id,None,str(e)

def pid(row):
    try:return int(((row.get('thirdParty') or {}).get('cardmarket')))
    except (TypeError,ValueError):return None

def ppid(row):
    try:return int((((row.get('pricing') or {}).get('cardmarket') or {}).get('idProduct')))
    except (TypeError,ValueError):return None

def stamp_tuple(row):
    s=row.get('stamp') or []
    if isinstance(s,str):s=[s]
    return tuple(sorted(map(str,s)))

def has_price(cm):
    return any(isinstance(cm.get(k),(int,float)) and cm.get(k)>0 for k in ('trend','avg7','avg30','avg','low'))

report=json.loads(REPORT.read_text())
targets=report.get('p1AmbiguousProductIds') or []
live={};errors={}
with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
    futs=[pool.submit(fetch,x) for x in targets]
    for f in concurrent.futures.as_completed(futs):
        cid,card,err=f.result()
        if card:live[cid]=card
        else:errors[cid]=err

all_pids=set()
for card in live.values():
    for row in card.get('variants_detailed') or []:
        if pid(row):all_pids.add(pid(row))
products_path=download_if_needed(None,'products_singles_6.json')
prices_path=download_if_needed(None,'price_guide_6.json')
proot=json.loads(products_path.read_text()); groot=json.loads(prices_path.read_text())
products={int(r['idProduct']):r for r in catalogue_rows(proot,('products',)) if r.get('idProduct') and int(r['idProduct']) in all_pids}
prices={int(r['idProduct']):r for r in catalogue_rows(groot,('priceGuides','priceGuide')) if r.get('idProduct') and int(r['idProduct']) in all_pids}

counts=Counter(); byset=defaultdict(Counter); exact=[]; rejected=[]
for cid in targets:
    card=live.get(cid)
    if not card:
        cls='LIVE_FETCH_ERROR';counts[cls]+=1;byset[cid.rsplit('-',1)[0]][cls]+=1;continue
    cm=((card.get('pricing') or {}).get('cardmarket') or {})
    try:top=int(cm.get('idProduct'))
    except (TypeError,ValueError):top=None
    rows=card.get('variants_detailed') or []
    top_rows=[r for r in rows if pid(r)==top] if top else []
    other_rows=[r for r in rows if pid(r) and pid(r)!=top]
    product_ids=sorted({pid(r) for r in rows if pid(r)})
    top_stamps={stamp_tuple(r) for r in top_rows}
    other_stamps={stamp_tuple(r) for r in other_rows}
    explicit_top=bool(top_rows) and all(stamp_tuple(r) for r in top_rows)
    explicit_other=bool(other_rows) and all(stamp_tuple(r) for r in other_rows)
    physically_distinct=explicit_top and explicit_other and top_stamps.isdisjoint(other_stamps)
    cats=[products.get(x) for x in product_ids]
    complete=bool(product_ids) and len(product_ids)==len(cats) and all(cats)
    expansions={x.get('idExpansion') for x in cats if x}
    metas={x.get('idMetacard') for x in cats if x}
    names={str(x.get('name') or '').strip().lower() for x in cats if x}
    official_same_identity=complete and len(expansions)==1 and None not in metas and len(metas)==1 and len(names)==1
    price_exact=all(x in prices and has_price(prices[x]) for x in product_ids)
    row_price_exact=all(ppid(r)==pid(r) for r in rows if pid(r))
    if top and len(product_ids)>=2 and physically_distinct and official_same_identity and price_exact and row_price_exact:
        cls='EXACT_STAMPED_PRODUCT_GROUP'
        exact.append({'id':cid,'name':card.get('name'),'topProductId':top,'productIds':product_ids,'topStamps':[list(x) for x in sorted(top_stamps)],'alternateStamps':[list(x) for x in sorted(other_stamps)],'idExpansion':next(iter(expansions)),'idMetacard':next(iter(metas))})
    else:
        cls='KEEP_P1'
        rejected.append({'id':cid,'top':top,'productIds':product_ids,'topStamps':[list(x) for x in sorted(top_stamps)],'otherStamps':[list(x) for x in sorted(other_stamps)],'officialSameIdentity':official_same_identity,'priceExact':price_exact,'rowPriceExact':row_price_exact})
    counts[cls]+=1;byset[cid.rsplit('-',1)[0]][cls]+=1

out={'targets':len(targets),'liveFetched':len(live),'errors':errors,'counts':dict(counts),'exact':exact,'bySet':{k:dict(v) for k,v in sorted(byset.items())},'rejected':rejected}
Path('artifacts/cardmarket_residual_stamp_audit_report.json').write_text(json.dumps(out,ensure_ascii=False,indent=2))
print(json.dumps({'targets':len(targets),'liveFetched':len(live),'errors':len(errors),'counts':dict(counts)},ensure_ascii=False,indent=2))
print('EXACT_BY_SET')
for set_id,c in sorted(((k,v.get('EXACT_STAMPED_PRODUCT_GROUP',0)) for k,v in byset.items()),key=lambda x:(-x[1],x[0])):
    if c: print(json.dumps({'setId':set_id,'exactStamped':c},ensure_ascii=False))
print('EXACT_IDS')
print(json.dumps(exact,ensure_ascii=False))
