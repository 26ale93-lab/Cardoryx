#!/usr/bin/env python3
import json, urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; OUT=ROOT/'artifacts'/'swshp_cardmarket_residual_report.json'; API='https://api.tcgdex.net/v2/en/cards'
IDS=('swshp-SWSH028','swshp-SWSH039','swshp-SWSH055','swshp-SWSH132','swshp-SWSH133','swshp-SWSH134','swshp-SWSH136','swshp-SWSH137','swshp-SWSH138','swshp-SWSH163','swshp-SWSH296')
def get(cid):
 req=urllib.request.Request(f'{API}/{cid}',headers={'User-Agent':'Cardoryx-SWSHP-Audit/1.0'}); return json.loads(urllib.request.urlopen(req,timeout=20).read())
def main():
 cards=[]; errors={}
 for cid in IDS:
  try:c=get(cid)
  except Exception as e: errors[cid]=repr(e); continue
  top=((c.get('pricing') or {}).get('cardmarket') or {})
  rows=[]
  for x in c.get('variants_detailed') or []:
   cm=((x.get('pricing') or {}).get('cardmarket') or {})
   try: pid=int(((x.get('thirdParty') or {}).get('cardmarket')) or 0)
   except: pid=0
   try: ppid=int(cm.get('idProduct') or cm.get('id_product') or 0)
   except: ppid=0
   rows.append({'type':x.get('type'),'foil':x.get('foil'),'stamp':x.get('stamp'),'languages':x.get('languages'),'pid':pid or None,'pricingPid':ppid or None,'trend':cm.get('trend'),'low':cm.get('low'),'tcgplayer':((x.get('thirdParty') or {}).get('tcgplayer'))})
  cards.append({'tcgdexId':cid,'name':c.get('name'),'localId':c.get('localId'),'topProductId':top.get('idProduct') or top.get('id_product'),'topTrend':top.get('trend'),'rows':rows})
 report={'requested':len(IDS),'fetched':len(cards),'errors':errors,'cards':cards}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2)); print(json.dumps(report,ensure_ascii=False,indent=2))
 if errors: raise SystemExit(2)
if __name__=='__main__': main()
