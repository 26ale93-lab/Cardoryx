#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MOD=ROOT/'scripts'/'test_card_identity_cardmarket_audit.py'
OUT=ROOT/'artifacts'/'set_logo_taxonomy_audit_report.json'

def load_mod():
    spec=importlib.util.spec_from_file_location('cm_audit',MOD)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def main():
    if len(sys.argv)!=2: raise SystemExit('usage: temp_set_logo_taxonomy_audit.py <tcgdex-db>')
    m=load_mod(); cards,errors,sha=m.load_snapshot(Path(sys.argv[1]))
    rows=[]; by_set=Counter(); combos=Counter(); with_staff=0; with_cm=0
    related=Counter()
    for c in cards:
        for r in c.get('variants_detailed') or []:
            stamps=tuple(sorted(str(x).strip().lower() for x in (r.get('stamp') or []) if str(x).strip()))
            if 'set-logo' not in stamps: continue
            pid=m.cm_id(r)
            row={'id':c.get('id'),'setId':(c.get('set') or {}).get('id'),'localId':c.get('localId'),'name':c.get('name'),'type':r.get('type'),'foil':r.get('foil'),'stamps':list(stamps),'cardmarket':pid}
            rows.append(row); by_set[row['setId']]+=1; combos[stamps]+=1
            if 'staff' in stamps: with_staff+=1
            if pid: with_cm+=1
            for s in stamps:
                if s!='set-logo': related[s]+=1
    report={
      'snapshot':sha,'parseErrors':len(errors),'setLogoRows':len(rows),'cardsWithSetLogo':len({r['id'] for r in rows}),
      'setsWithSetLogo':len(by_set),'rowsWithCardmarketProduct':with_cm,'rowsWithStaff':with_staff,
      'stampCombinations':[{'stamps':list(k),'count':v} for k,v in combos.most_common()],
      'relatedStampTokens':dict(related.most_common()),
      'topSets':[{'setId':k,'rows':v} for k,v in by_set.most_common(40)],
      'samples':rows[:100]
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:report[k] for k in ('snapshot','parseErrors','setLogoRows','cardsWithSetLogo','setsWithSetLogo','rowsWithCardmarketProduct','rowsWithStaff','stampCombinations','relatedStampTokens','topSets')},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
