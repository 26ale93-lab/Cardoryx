#!/usr/bin/env python3
from __future__ import annotations
import concurrent.futures, importlib.util, json, sys
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

def row_pid(m,row):
    return m.cm_id(row)

def pricing_pid(row):
    cm=((row.get('pricing') or {}).get('cardmarket') or {})
    try: return int(cm.get('idProduct') or cm.get('id_product'))
    except (TypeError,ValueError): return None

def usable_price(row):
    cm=((row.get('pricing') or {}).get('cardmarket') or {})
    return any(isinstance(cm.get(k),(int,float)) and cm.get(k)>0 for k in ('trend','avg7','avg30','avg','low'))

def language_ok(row):
    langs=row.get('languages')
    return not isinstance(langs,list) or not langs or 'it' in langs

def exact_rows(m,card,kind):
    out=[]
    for r in card.get('variants_detailed') or []:
        st=stamps(r)
        if kind=='set-stamp':
            match='set-logo' in st and 'staff' not in st
        elif kind=='staff':
            match='staff' in st
        else:
            match=False
        if not match: continue
        pid=row_pid(m,r)
        pp=pricing_pid(r)
        out.append((r,pid,pp,usable_price(r),language_ok(r)))
    return out

def row_safe(t):
    r,pid,pp,price_ok,lang_ok=t
    return bool(pid and pp==pid and price_ok and lang_ok)

def main():
    if len(sys.argv)!=2: raise SystemExit('usage: temp_set_logo_runtime_rule_audit.py <tcgdex-db>')
    m=load_mod(); cards,errors,sha=m.load_snapshot(Path(sys.argv[1]))
    report=json.loads(P1.read_text(encoding='utf-8'))
    p1=set(report.get('p1AmbiguousProductIds') or [])
    counts=Counter(); bad=[]; svp=[]
    for c in cards:
        rows=c.get('variants_detailed') or []
        set_rows=[r for r in rows if 'set-logo' in stamps(r) and 'staff' not in stamps(r)]
        staff_rows=[r for r in rows if 'staff' in stamps(r)]
        if set_rows: counts['cardsSetStamp']+=1
        if staff_rows: counts['cardsStaff']+=1
        if set_rows and staff_rows: counts['cardsBoth']+=1
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

    # Live pricing validation for the residual SVP identities only.  A candidate
    # is exact only when one row exists for the requested physical stamp,
    # thirdParty.cardmarket equals pricing.cardmarket.idProduct, a real price is
    # present, and the row is Italian-compatible (or language-neutral).
    live={}; live_errors={}
    targets=sorted(x['id'] for x in svp)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        futures={pool.submit(m.live_card,cid,Path('/tmp/cardoryx-set-logo-live-cache')):cid for cid in targets}
        for fut in concurrent.futures.as_completed(futures):
            cid=futures[fut]
            value,error=fut.result()
            if value: live[cid]=value
            if error: live_errors[cid]=error

    live_counts=Counter(); live_cases=[]
    for item in svp:
        cid=item['id']; card=live.get(cid) or {}
        set_rows=exact_rows(m,card,'set-stamp')
        staff_rows=exact_rows(m,card,'staff')
        set_safe=[t for t in set_rows if row_safe(t)]
        staff_safe=[t for t in staff_rows if row_safe(t)]
        if len(set_safe)==1: live_counts['setStampExactPriced']+=1
        if len(staff_safe)==1: live_counts['staffExactPriced']+=1
        if len(set_safe)==1 and len(staff_safe)==1 and set_safe[0][1]!=staff_safe[0][1]:
            live_counts['exactDistinctPair']+=1
            cls='EXACT_DISTINCT_PRICED_PAIR'
        elif len(set_safe)==1 and not staff_rows:
            live_counts['setStampOnlyExactPriced']+=1; cls='SET_STAMP_ONLY_EXACT_PRICED'
        elif len(staff_safe)==1 and not set_rows:
            live_counts['staffOnlyExactPriced']+=1; cls='STAFF_ONLY_EXACT_PRICED'
        else:
            cls='KEEP_FAIL_CLOSED'; live_counts[cls]+=1
        live_cases.append({
            'id':cid,'classification':cls,
            'setStampProductIds':[t[1] for t in set_rows if t[1]],
            'staffProductIds':[t[1] for t in staff_rows if t[1]],
            'setStampSafeProductIds':[t[1] for t in set_safe],
            'staffSafeProductIds':[t[1] for t in staff_safe],
        })

    out={'snapshot':sha,'parseErrors':len(errors),'counts':dict(counts),'staffLeakCount':len(bad),
         'svpResidualCount':len(svp),'svpExactSetLogoStaffPairs':len(svp_pair),'svpOther':svp_other,
         'svpPairs':svp_pair,'liveFetched':len(live),'liveErrors':live_errors,
         'livePricingCounts':dict(live_counts),'liveCases':live_cases}
    OUT.write_text(json.dumps(out,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:out[k] for k in ('snapshot','parseErrors','counts','staffLeakCount','svpResidualCount','svpExactSetLogoStaffPairs','svpOther','liveFetched','liveErrors','livePricingCounts')},ensure_ascii=False,indent=2))

if __name__=='__main__': main()
