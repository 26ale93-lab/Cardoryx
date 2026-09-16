#!/usr/bin/env python3
import json, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'artifacts'/'mfb_stamp_cardmarket_audit_report.json'; API='https://api.tcgdex.net/v2/en/cards'
IDS=('mfb-1','mfb-8','mfb-9','mfb-16','mfb-17','mfb-24','mfb-25','mfb-33','mfb-34')
def get(cid):
 r=urllib.request.Request(f'{API}/{cid}',headers={'User-Agent':'Cardoryx-MFB-Audit/1.0'}); return json.loads(urllib.request.urlopen(r,timeout=20).read())
def main():
 cards=[]; tax={}; errors={}
 for cid in IDS:
  try:c=get(cid)
  except Exception as e: errors[cid]=repr(e); continue
  rows=[]
  for x in c.get('variants_detailed') or []:
   stamps=[str(v or '').strip().lower() for v in (x.get('stamp') or [])]; key='+'.join(sorted(stamps)) or '(none)'; tax[key]=tax.get(key,0)+1
   cm=((x.get('pricing') or {}).get('cardmarket') or {}); pid=int(((x.get('thirdParty') or {}).get('cardmarket')) or 0); ppid=int(cm.get('idProduct') or cm.get('id_product') or 0)
   price=any(isinstance(cm.get(k),(int,float)) and cm.get(k)>0 for k in ('trend','avg7','avg30','avg','low'))
   rows.append({'type':x.get('type'),'foil':x.get('foil'),'stamp':x.get('stamp'),'languages':x.get('languages'),'pid':pid or None,'pricingPid':ppid or None,'exact':bool(pid and pid==ppid and price),'trend':cm.get('trend'),'low':cm.get('low')})
  cards.append({'tcgdexId':cid,'name':c.get('name'),'localId':c.get('localId'),'rows':rows})
 report={'requested':9,'fetched':len(cards),'errors':errors,'stampTaxonomy':tax,'cards':cards}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)); print(json.dumps(report,ensure_ascii=False,indent=2))
 if errors: raise SystemExit(2)
if __name__=='__main__': main()
