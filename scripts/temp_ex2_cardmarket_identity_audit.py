#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, re, sys, unicodedata, urllib.request
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
AUDIT=ROOT/'artifacts'/'card_identity_cardmarket_audit_report.json'
OUT=ROOT/'artifacts'/'ex2_cardmarket_identity_audit_report.json'
PRODUCTS='https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json'
PRICES='https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json'

def norm(v):
    s=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+','',s)

def product_base_name(v): return str(v or '').split(' [',1)[0].strip()
def english_name(card):
    v=card.get('name') or ''
    return str(v.get('en') or next(iter(v.values()),'')) if isinstance(v,dict) else str(v)
def get_json(url,timeout=300):
    req=urllib.request.Request(url,headers={'User-Agent':'Cardoryx-EX2-Identity-Audit/1.1'})
    with urllib.request.urlopen(req,timeout=timeout) as r: return json.load(r)
def rows(root,keys):
    if isinstance(root,list): return root
    for key in keys:
        value=root.get(key) if isinstance(root,dict) else None
        if isinstance(value,list): return value
    return []
def load_snapshot(db):
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('vf',ROOT/'scripts'/'test_variant_finish_audit.py')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.load_official_database(db)
def p1_ids():
    root=json.loads(AUDIT.read_text(encoding='utf-8')); out=set()
    def walk(obj):
        if isinstance(obj,dict):
            if obj.get('classification')=='P1_AMBIGUOUS_PRODUCT':
                cid=str(obj.get('tcgdexId') or obj.get('id') or '').strip()
                if cid: out.add(cid)
            for v in obj.values(): walk(v)
        elif isinstance(obj,list):
            for v in obj: walk(v)
    walk(root); return out
def current_pid(card):
    cm=((card.get('pricing') or {}).get('cardmarket') or {})
    try: return int(cm.get('idProduct') or cm.get('id_product'))
    except (TypeError,ValueError): return None
def variant_pids(card):
    out=[]
    for row in card.get('variants_detailed') or []:
        try: pid=int((row.get('thirdParty') or {}).get('cardmarket'))
        except (TypeError,ValueError): continue
        if pid not in out: out.append(pid)
    return out

def main():
    if len(sys.argv)!=2: raise SystemExit('usage: temp_ex2_cardmarket_identity_audit.py <tcgdex-db>')
    cards,errors,snapshot=load_snapshot(Path(sys.argv[1]))
    ex2=[c for c in cards if str((c.get('set') or {}).get('id') or '').lower()=='ex2']
    p1=p1_ids(); targets=[c for c in ex2 if c.get('id') in p1]
    products=rows(get_json(PRODUCTS),('products','product'))
    prices=rows(get_json(PRICES),('priceGuides','priceGuide','products'))
    byid={int(p['idProduct']):p for p in products if p.get('idProduct') is not None}
    price_byid={int(p['idProduct']):p for p in prices if p.get('idProduct') is not None}

    names={norm(english_name(c)):english_name(c) for c in ex2 if english_name(c)}
    expansion_name_hits=defaultdict(set)
    for p in products:
        try: exp=int(p.get('idExpansion') or 0)
        except (TypeError,ValueError): continue
        n=norm(product_base_name(p.get('name')))
        if n in names: expansion_name_hits[exp].add(n)
    ranked=sorted(((len(v),k) for k,v in expansion_name_hits.items()),reverse=True)
    if not ranked: raise SystemExit('No Cardmarket expansion candidates found')
    top_count,expected_expansion=ranked[0]; second_count=ranked[1][0] if len(ranked)>1 else 0
    if top_count < 80 or top_count-second_count < 20:
        raise SystemExit(f'Ambiguous expansion identification: top={ranked[:5]}')

    western=[p for p in products if int(p.get('idExpansion') or 0)==expected_expansion]
    by_name=defaultdict(list)
    for p in western: by_name[norm(product_base_name(p.get('name')))].append(p)

    result=[]; counts=Counter()
    for c in targets:
        cid=c['id']; name=english_name(c); cur=current_pid(c); current_row=byid.get(cur) if cur else None
        candidates=[]
        for p in by_name.get(norm(name),[]):
            pid=int(p['idProduct'])
            candidates.append({
                'productId':pid,'name':p.get('name'),'idExpansion':p.get('idExpansion'),
                'idMetacard':p.get('idMetacard'),'hasPriceGuide':pid in price_byid,
                'price':{k:price_byid.get(pid,{}).get(k) for k in ('trend','avg7','avg30','avg','low','trend-holo','avg7-holo','avg30-holo','avg-holo','low-holo')}
            })
        variants=variant_pids(c); candidate_ids=[x['productId'] for x in candidates]
        intersection=[pid for pid in variants if pid in candidate_ids]
        current_exp=int(current_row.get('idExpansion') or 0) if current_row else None
        if cur in candidate_ids:
            cls='TOP_LEVEL_EXACT'
        elif len(intersection)==1 and intersection[0] in price_byid:
            cls='EXACT_VARIANT_PRODUCT_NO_TOP_LEVEL' if cur is None else 'EXACT_VARIANT_PRODUCT_TOP_LEVEL_DIFFERS'
        elif len(intersection)>1:
            cls='MULTIPLE_VARIANT_PRODUCTS_NEEDS_REVIEW'
        elif len(candidate_ids)==1 and candidate_ids[0] in price_byid:
            cls='UNIQUE_CATALOG_TARGET_NOT_IN_VARIANTS'
        elif len(candidate_ids)>1:
            cls='MULTIPLE_CATALOG_TARGETS_NO_VARIANT_DISAMBIGUATION'
        elif len(candidate_ids)==1:
            cls='UNIQUE_TARGET_NO_PRICE_GUIDE'
        else:
            cls='NO_EXACT_NAME_TARGET'
        counts[cls]+=1
        result.append({
            'tcgdexId':cid,'localId':c.get('localId'),'name':name,'rarity':c.get('rarity'),
            'currentProductId':cur,'currentProduct':current_row,'variantProductIds':variants,
            'candidateProducts':candidates,'candidateVariantIntersection':intersection,'classification':cls
        })
    result.sort(key=lambda r:int(re.sub(r'\D','',str(r['localId']) or '999') or 999))
    report={
        'snapshot':snapshot,'parseErrors':len(errors),'ex2Cards':len(ex2),'ex2P1Count':len(targets),
        'expectedExpansionId':expected_expansion,
        'expansionIdentification':{'topExactNameHits':top_count,'secondExactNameHits':second_count,
          'topCandidates':[{'idExpansion':exp,'exactNameHits':count} for count,exp in ranked[:10]],'gatePassed':True},
        'classificationCounts':dict(counts),'rows':result
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k!='rows'},ensure_ascii=False,indent=2))
    print(json.dumps({'needsReview':[{'id':r['tcgdexId'],'variants':r['variantProductIds'],'candidates':[c['productId'] for c in r['candidateProducts']]} for r in result if 'NEEDS_REVIEW' in r['classification'] or 'NO_VARIANT' in r['classification'] or 'NOT_IN_VARIANTS' in r['classification']]},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
