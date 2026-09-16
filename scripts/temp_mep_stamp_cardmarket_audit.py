#!/usr/bin/env python3
from __future__ import annotations
import json
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'artifacts'/'mep_stamp_cardmarket_audit_report.json'
API='https://api.tcgdex.net/v2/en/cards'
IDS=[
'mep-001','mep-002','mep-003','mep-004',
'mep-014','mep-015','mep-016','mep-017',
'mep-064','mep-065','mep-066','mep-067',
'mep-074','mep-075','mep-076','mep-077',
]

def get_card(cid):
    req=urllib.request.Request(f'{API}/{cid}',headers={'User-Agent':'Cardoryx-MEP-Audit/1.0'})
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.loads(r.read().decode('utf-8'))

def cm_pid(row):
    try:return int(((row.get('thirdParty') or {}).get('cardmarket')) or 0)
    except:return 0

def pricing_pid(row):
    cm=((row.get('pricing') or {}).get('cardmarket') or {})
    try:return int(cm.get('idProduct') or cm.get('id_product') or 0)
    except:return 0

def main():
    cards=[]; errors={}
    taxonomy={}
    exact_rows=0
    for cid in IDS:
        try:c=get_card(cid)
        except Exception as e:
            errors[cid]=repr(e); continue
        rows=[]
        for row in c.get('variants_detailed') or []:
            stamps=[str(x or '').strip().lower() for x in (row.get('stamp') or [])]
            pid=cm_pid(row); ppid=pricing_pid(row)
            cm=((row.get('pricing') or {}).get('cardmarket') or {})
            has_price=any(isinstance(cm.get(k),(int,float)) and cm.get(k)>0 for k in ('trend','avg7','avg30','avg','low'))
            key='+'.join(sorted(stamps)) or '(none)'
            taxonomy[key]=taxonomy.get(key,0)+1
            exact=bool(pid and pid==ppid and has_price)
            exact_rows+=int(exact)
            rows.append({
                'type':row.get('type'),'foil':row.get('foil'),'stamp':row.get('stamp'),
                'languages':row.get('languages'),'cardmarketProductId':pid or None,
                'pricingProductId':ppid or None,'hasRealPrice':has_price,'exactRow':exact,
                'trend':cm.get('trend'),'low':cm.get('low')
            })
        top=((c.get('pricing') or {}).get('cardmarket') or {})
        cards.append({
            'tcgdexId':cid,'name':c.get('name'),'localId':c.get('localId'),
            'topLevelProductId':top.get('idProduct') or top.get('id_product'),
            'variantsDetailed':rows,
        })
    report={
        'requested':len(IDS),'fetched':len(cards),'errors':errors,
        'stampTaxonomy':taxonomy,'exactVariantRows':exact_rows,'cards':cards
    }
    OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))
    if errors: raise SystemExit(2)

if __name__=='__main__': main()
