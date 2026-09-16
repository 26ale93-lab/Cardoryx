#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, sys
from collections import Counter
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
MOD=ROOT/'scripts'/'test_card_identity_cardmarket_audit.py'
OUT=ROOT/'artifacts'/'set_logo_runtime_rule_audit_report.json'
P1=ROOT/'artifacts'/'card_identity_cardmarket_audit_report.json'

def load_mod():
    spec=importlib.util.spec_from_file_location('cm_audit',MOD)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def stamps(row):
    return {str(x).strip().lower() for x in (row.get('stamp') or []) if str(x).strip()}

def main():
    if len(sys.argv)!=2: raise SystemExit('usage: temp_set_logo_runtime_rule_audit.py <tcgdex-db>')
    m=load_mod(); cards,errors,sha=m.load_snapshot(Path(sys.argv[1]))
    by_id={c['id']:c for c in cards}
    report=json.loads(P1.read_text(encoding='utf-8'))
    p1=set(report.get('p1AmbiguousProductIds') or [])
    counts=Counter(); bad=[]; svp=[]
    for c in cards:
        rows=c.get('variants_detailed') or []
        set_rows=[r for r in rows if 'set-logo' in stamps(r) and 'staff' not in stamps(r)]
        staff_rows=[r for r in rows if 'staff' in stamps(r)]
        mixed_rows=[r for r in rows if 'set-logo' in stamps(r) and 'staff' in stamps(r)]
        if set_rows: counts['cardsSetStamp']=counts['cardsSetStamp']+1
        if staff_rows: counts['cardsStaff']=counts['cardsStaff']+1
        if set_rows and staff_rows: counts['cardsBoth']=counts['cardsBoth']+1
        # The narrow rule must never classify a Staff row as the plain Set Stamp row.
        leaked=[r for r in set_rows if 'staff' in stamps(r)]
        if leaked: bad.append({'id':c['id'],'kind':'STAFF_LEAK'})
        if c['id'].startswith('svp-') and c['id'] in p1:
            set_pids=sorted({m.cm_id(r) for r in set_rows if m.cm_id(r)})
            staff_pids=sorted({m.cm_id(r) for r in staff_rows if m.cm_id(r)})
            svp.append({'id':c['id'],'setStampProducts':set_pids,'staffProducts':staff_pids,
                        'setStampRows':len(set_rows),'staffRows':len(staff_rows),
                        'separated':bool(set_rows) and not any(r in staff_rows for r in set_rows)})
    svp_pair=[x for x in svp if x['setStampProducts'] and x['staffProducts']]
    svp_other=[x for x in svp if not (x['setStampProducts'] and x['staffProducts'])]
    out={'snapshot':sha,'parseErrors':len(errors),'counts':dict(counts),'staffLeakCount':len(bad),
         'svpResidualCount':len(svp),'svpExactSetLogoStaffPairs':len(svp_pair),'svpOther':svp_other,
         'svpPairs':svp_pair}
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:out[k] for k in ('snapshot','parseErrors','counts','staffLeakCount','svpResidualCount','svpExactSetLogoStaffPairs','svpOther')},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
