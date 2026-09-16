#!/usr/bin/env python3
import concurrent.futures
import json
import urllib.request
from collections import Counter
from pathlib import Path
from test_card_identity_cardmarket_audit import download_if_needed, rows as catalogue_rows

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
    return {'type':row.get('type'),'subtype':row.get('subtype'),'foil':row.get('foil'),'stamp':row.get('stamp'),'cardmarket':cm_pid(row),'pricingProduct':pricing_pid(row)}

def tax(row):
    stamp=row.get('stamp')
    if isinstance(stamp,list): stamp='+'.join(sorted(map(str,stamp)))
    return (str(row.get('type') or ''),str(row.get('subtype') or ''),str(row.get('foil') or ''),str(stamp or ''))

def compact_product(row):
    if not row: return None
    preferred=('idProduct','idMetacard','idExpansion','name','number','rarity','categoryName','expansionName','dateAdded')
    out={k:row.get(k) for k in preferred if k in row}
    # Preserve any version/collector-number style fields the current catalogue exposes.
    for k,v in row.items():
        lk=k.lower()
        if k not in out and any(token in lk for token in ('version','collector','number','metacard')):
            out[k]=v
    return out

report=json.loads(REPORT.read_text(encoding='utf-8'))
targets=sorted(x for x in report.get('p1AmbiguousProductIds',[]) if x.startswith('svp-'))
results={}; errors={}
with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:
    futures=[pool.submit(fetch,x) for x in targets]
    for f in concurrent.futures.as_completed(futures):
        card_id,card,error=f.result()
        if error: errors[card_id]=error
        else: results[card_id]=card

product_ids=set()
for card in results.values():
    cm=((card.get('pricing') or {}).get('cardmarket') or {})
    try: product_ids.add(int(cm.get('idProduct')))
    except (TypeError,ValueError): pass
    for row in card.get('variants_detailed') or []:
        if cm_pid(row): product_ids.add(cm_pid(row))
products_path=download_if_needed(None,'products_singles_6.json')
prices_path=download_if_needed(None,'price_guide_6.json')
product_root=json.loads(products_path.read_text(encoding='utf-8'))
price_root=json.loads(prices_path.read_text(encoding='utf-8'))
products={int(r['idProduct']):r for r in catalogue_rows(product_root,('products',)) if r.get('idProduct') and int(r['idProduct']) in product_ids}
prices={int(r['idProduct']):r for r in catalogue_rows(price_root,('priceGuides','priceGuide')) if r.get('idProduct') and int(r['idProduct']) in product_ids}

classes=Counter(); top_taxonomy=Counter(); alternate_taxonomy=Counter(); pair_checks=Counter(); output=[]
for card_id in targets:
    card=results.get(card_id)
    if not card:
        classes['LIVE_FETCH_ERROR']+=1; output.append({'id':card_id,'class':'LIVE_FETCH_ERROR'}); continue
    cm=((card.get('pricing') or {}).get('cardmarket') or {})
    try: top=int(cm.get('idProduct'))
    except (TypeError,ValueError): top=None
    variants=card.get('variants_detailed') or []
    same=[r for r in variants if cm_pid(r)==top] if top else []
    base=[r for r in same if not (r.get('stamp') or r.get('foil') or r.get('subtype'))]
    special=[r for r in same if (r.get('stamp') or r.get('foil') or r.get('subtype'))]
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
    product_rows=[products.get(pid) for pid in all_pids]
    expansion_ids={r.get('idExpansion') for r in product_rows if r}
    meta_ids={r.get('idMetacard') for r in product_rows if r}
    names={str(r.get('name') or '').strip().lower() for r in product_rows if r}
    catalog_complete=len(product_rows)==len(all_pids) and all(product_rows)
    pair_same_expansion=catalog_complete and len(expansion_ids)==1
    pair_same_metacard=catalog_complete and None not in meta_ids and len(meta_ids)==1
    pair_same_name=catalog_complete and len(names)==1
    real_prices=all(pid in prices for pid in all_pids)
    if cls=='TOP_PRODUCT_SPECIAL_ONLY' and len(all_pids)==2:
        if pair_same_expansion and pair_same_metacard and pair_same_name and real_prices:
            pair='OFFICIAL_SAME_METACARD_PAIR'
        else: pair='OFFICIAL_PAIR_NEEDS_REVIEW'
    else: pair='OTHER'
    pair_checks[pair]+=1
    output.append({
        'id':card_id,'name':card.get('name'),'localId':card.get('localId'),'class':cls,'pairClass':pair,
        'topProductId':top,'allProductIds':all_pids,'topRows':[flags(r) for r in same],
        'alternateRows':[flags(r) for r in variants if cm_pid(r) and cm_pid(r)!=top],
        'catalogue':[compact_product(products.get(pid)) for pid in all_pids],
        'pricePresent':{str(pid):pid in prices for pid in all_pids},
        'sameExpansion':pair_same_expansion,'sameMetacard':pair_same_metacard,'sameName':pair_same_name,
    })

summary={
    'targetCount':len(targets),'fetched':len(results),'errors':errors,'classes':dict(classes),'pairChecks':dict(pair_checks),
    'topProductTaxonomy':[{"type":k[0],"subtype":k[1],"foil":k[2],"stamp":k[3],"count":v} for k,v in top_taxonomy.most_common()],
    'alternateProductTaxonomy':[{"type":k[0],"subtype":k[1],"foil":k[2],"stamp":k[3],"count":v} for k,v in alternate_taxonomy.most_common()],
    'rows':output,
}
Path('artifacts/cardmarket_svp_residual_audit_report.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({k:summary[k] for k in ('targetCount','fetched','classes','pairChecks','topProductTaxonomy','alternateProductTaxonomy')},ensure_ascii=False,indent=2))
print('PAIR_DETAILS')
for row in output:
    print(json.dumps(row,ensure_ascii=False))
