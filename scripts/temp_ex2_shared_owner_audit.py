#!/usr/bin/env python3
from __future__ import annotations
import importlib.util,json,sys
from collections import defaultdict,Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'
AUDIT=ROOT/'artifacts'/'card_identity_cardmarket_audit_report.json'

def load_module():
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('cm',ROOT/'scripts'/'test_card_identity_cardmarket_audit.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod

def p1_ids():
    root=json.loads(AUDIT.read_text(encoding='utf-8'));out=set()
    def walk(o):
        if isinstance(o,dict):
            if o.get('classification')=='P1_AMBIGUOUS_PRODUCT':
                cid=str(o.get('tcgdexId') or o.get('id') or '')
                if cid:out.add(cid)
            for v in o.values():walk(v)
        elif isinstance(o,list):
            for v in o:walk(v)
    walk(root);return out

def main():
    if len(sys.argv)!=2:raise SystemExit('usage: temp_ex2_shared_owner_audit.py <tcgdex-db>')
    mod=load_module();cards,errors,snapshot=mod.load_snapshot(Path(sys.argv[1]));byid={c['id']:c for c in cards}
    pid_to_cards=defaultdict(set)
    for c in cards:
        for pid in mod.product_ids(c):pid_to_cards[pid].add(c['id'])
    overrides=mod.extract_js_object(INDEX.read_text(encoding='utf-8'),'VERIFIED_BASE_CARDMARKET_PRODUCT_OVERRIDES')
    p1=p1_ids();targets=[cid for cid in sorted(p1) if cid.startswith('ex2-')]
    rows=[];counts=Counter()
    for cid in targets:
        c=byid[cid];pids=mod.product_ids(c);physical=[]
        for pid in pids:
            raw=sorted(pid_to_cards[pid]);effective=[];removed=[]
            for owner in raw:
                rule=overrides.get(owner) or {}
                if int(rule.get('conflictingProduct') or 0)==pid and int(rule.get('baseProduct') or 0)!=pid:
                    removed.append(owner)
                else:effective.append(owner)
            physical.append({'productId':pid,'rawOwners':raw,'removedVerifiedConflicts':removed,'effectiveOwners':effective})
        base_rows=[r for r in (c.get('variants_detailed') or []) if mod.is_base_row(r)]
        base_pids=sorted({mod.cm_id(r) for r in base_rows if mod.cm_id(r)})
        base_clean=all(len(next(x['effectiveOwners'] for x in physical if x['productId']==pid))==1 for pid in base_pids)
        explicit_alt=all(any(mod.physical_variant(r).get(k) for k in ('stamp','foil') ) or r.get('firstEdition') or mod.cm_id(r) in base_pids for r in (c.get('variants_detailed') or []))
        cls='BASE_PRODUCTS_UNSHARED_AFTER_VERIFIED_CONFLICT_REMOVAL' if base_clean else 'STILL_SHARED'
        counts[cls]+=1
        rows.append({'tcgdexId':cid,'localId':c.get('localId'),'baseProductIds':base_pids,'allProductIds':pids,'products':physical,'classification':cls,'explicitAlternatesOnly':explicit_alt})
    report={'snapshot':snapshot,'parseErrors':len(errors),'ex2P1':len(targets),'counts':dict(counts),'rows':rows}
    print(json.dumps({'snapshot':snapshot,'ex2P1':len(targets),'counts':dict(counts),'stillShared':[r['tcgdexId'] for r in rows if r['classification']=='STILL_SHARED']},ensure_ascii=False,indent=2))

if __name__=='__main__':main()
