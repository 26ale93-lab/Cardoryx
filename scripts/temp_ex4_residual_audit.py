#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures, importlib.util, json, re, sys, unicodedata, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'
CM_PRODUCTS='https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json'
API='https://api.tcgdex.net/v2/en/cards'
EX4_EXPANSION=1542

def norm(v):
    s=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+','',s)

def base_name(row): return str((row or {}).get('name') or '').split(' [',1)[0]
def english_name(card):
    v=card.get('name') or ''
    return str(v.get('en') or next(iter(v.values()),'')) if isinstance(v,dict) else str(v)
def get_json(url,timeout=120):
    req=urllib.request.Request(url,headers={'User-Agent':'Cardoryx-EX4-Residual-Audit/1.0'})
    with urllib.request.urlopen(req,timeout=timeout) as r: return json.load(r)
def cm_ids(card):
    out=[]
    for row in card.get('variants_detailed') or []:
        try: pid=int((row.get('thirdParty') or {}).get('cardmarket'))
        except (TypeError,ValueError): continue
        if pid not in out: out.append(pid)
    return out
def load_snapshot(db):
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('vf',ROOT/'scripts'/'test_variant_finish_audit.py')
    mod=importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
    return mod.load_official_database(db)
def live_one(cid):
    try: return cid,get_json(f'{API}/{urllib.parse.quote(cid)}',60),None
    except Exception as e: return cid,None,str(e)
def current_pid(card):
    cm=(((card or {}).get('pricing') or {}).get('cardmarket') or {})
    try: return int(cm.get('idProduct') or cm.get('id_product'))
    except (TypeError,ValueError): return None

def main():
    if len(sys.argv)!=2: raise SystemExit('usage: temp_ex4_residual_audit.py <tcgdex-db>')
    cards,errors,snapshot=load_snapshot(Path(sys.argv[1]))
    ex4=[c for c in cards if str((c.get('set') or {}).get('id') or '').lower()=='ex4']
    source=INDEX.read_text(encoding='utf-8')
    block=source.split('const VERIFIED_BASE_CARDMARKET_PRODUCT_OVERRIDES = {',1)[1].split('\n};',1)[0]
    already=set(re.findall(r"['\"](ex4-[^'\"]+)['\"]\s*:",block))
    root=get_json(CM_PRODUCTS,300); products=root.get('products',[])
    byid={int(p['idProduct']):p for p in products if p.get('idProduct') is not None}
    western=[p for p in products if int(p.get('idExpansion') or 0)==EX4_EXPANSION]
    live={}; live_errors={}
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        fs=[pool.submit(live_one,c['id']) for c in ex4]
        for f in concurrent.futures.as_completed(fs):
            cid,val,err=f.result()
            if val: live[cid]=val
            if err: live_errors[cid]=err
    rows=[]
    for c in ex4:
        cid=c['id']; name=english_name(c)
        matches=[p for p in western if norm(base_name(p))==norm(name)]
        if len(matches)!=1 or cid in already: continue
        target=matches[0]; target_pid=int(target['idProduct']); meta=target.get('idMetacard')
        cur=current_pid(live.get(cid)); currow=byid.get(cur) if cur else None
        variants=sorted(set(cm_ids(c))|set(cm_ids(live.get(cid) or {})))
        same_meta=[]; same_name=[]
        for pid in variants:
            p=byid.get(pid)
            if not p: continue
            if norm(base_name(p))==norm(name): same_name.append(pid)
            if p.get('idMetacard')==meta and norm(base_name(p))==norm(name): same_meta.append(pid)
        rows.append({
            'tcgdexId':cid,'localId':c.get('localId'),'name':name,'rarity':c.get('rarity'),
            'currentProductId':cur,'currentProduct':currow,'targetProductId':target_pid,'targetProduct':target,
            'variantProductIds':variants,'sameNameVariantIds':same_name,'sameMetacardVariantIds':same_meta,
            'currentOutsideExpansion1542':bool(currow and int(currow.get('idExpansion') or 0)!=EX4_EXPANSION)
        })
    rows.sort(key=lambda r:int(re.sub(r'\D','',str(r['localId']) or '999') or 999))
    report={'snapshot':snapshot,'parseErrors':len(errors),'cards':len(ex4),'alreadyFixed':sorted(already),
            'uniqueResidualCount':len(rows),'liveErrors':live_errors,'rows':rows}
    print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__': main()
