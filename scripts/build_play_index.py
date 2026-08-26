#!/usr/bin/env python3
import json, re, unicodedata, urllib.request
from pathlib import Path
from datetime import datetime, timezone

BASE='https://downloads.s3.cardmarket.com/productCatalog'
URLS={
 'singles':f'{BASE}/productList/products_singles_6.json',
 'nonsingles':f'{BASE}/productList/products_nonsingles_6.json',
 'prices':f'{BASE}/priceGuide/price_guide_6.json',
}
SERIES_WORDS={1:'one',2:'two',3:'three',4:'four',5:'five',6:'six',7:'seven',8:'eight',9:'nine',10:'ten'}

def norm(s):
 s=unicodedata.normalize('NFKD',str(s or '')).encode('ascii','ignore').decode().lower()
 return re.sub(r'[^a-z0-9]+',' ',s).strip()

def rows(root, keys):
 if isinstance(root,list): return root
 if isinstance(root,dict):
  for k in keys:
   if isinstance(root.get(k),list): return root[k]
  for v in root.values():
   if isinstance(v,list) and v:return v
 return []

def get(url):
 req=urllib.request.Request(url,headers={'User-Agent':'Cardoryx-IndexBuilder/1.9'})
 with urllib.request.urlopen(req,timeout=90) as r:return json.load(r)

def iid(r,*names):
 for n in names:
  try:
   v=int(r.get(n))
   if v>0:return v
  except: pass
 return None

def main():
 singles_root=get(URLS['singles']); nons_root=get(URLS['nonsingles']); prices_root=get(URLS['prices'])
 singles=rows(singles_root,['products','product','data','items'])
 nons=rows(nons_root,['products','product','data','items'])
 prices=rows(prices_root,['priceGuides','priceGuide','prices','products','data','items'])
 price_by={iid(x,'idProduct','id_product'):x for x in prices if iid(x,'idProduct','id_product')}

 # Ricava gli idExpansion Prize Pack da prodotti sigillati: niente tabella manuale di expansion ID.
 exp_to_series={}
 evidence={}
 for r in nons:
  n=norm(r.get('name') or r.get('Name') or r.get('productName'))
  exp=iid(r,'idExpansion','id_expansion')
  if not exp: continue
  for ser,word in SERIES_WORDS.items():
   if f'play pokemon prize pack series {word}' in n:
    exp_to_series[exp]=ser; evidence[str(ser)]={'idExpansion':exp,'product':r.get('name') or r.get('Name')}; break
 if not exp_to_series:
  raise SystemExit('Nessuna espansione Prize Pack trovata nel catalogo non-singles')

 # Indicizza singles per metacard. I prodotti Prize Pack e la stampa base condividono idMetacard.
 by_meta={}
 for r in singles:
  meta=iid(r,'idMetacard','id_metacard'); pid=iid(r,'idProduct','id_product'); exp=iid(r,'idExpansion','id_expansion')
  if meta and pid: by_meta.setdefault(meta,[]).append((pid,exp,r))

 by_base={}; by_product={}; play_count=0
 price_fields=['low','trend','avg','avg1','avg7','avg30','low-holo','trend-holo','avg-holo','avg1-holo','avg7-holo','avg30-holo']
 generated=datetime.now(timezone.utc).date().isoformat()
 for meta, group in by_meta.items():
  play=[]; bases=[]
  for pid,exp,r in group:
   if exp in exp_to_series: play.append((pid,exp,r))
   else: bases.append((pid,exp,r))
  if not play: continue
  payloads=[]
  for pid,exp,r in play:
   pr=price_by.get(pid,{})
   payload={'idProduct':pid,'series':str(exp_to_series[exp]),'idExpansion':exp,'idMetacard':meta,'name':r.get('name') or r.get('Name') or '', 'updated':generated,
            'prices':{k:pr.get(k) for k in price_fields if pr.get(k) is not None}}
   payloads.append(payload); by_product[str(pid)]=payload; play_count+=1
  for basepid,_,_ in bases:
   ser_map={}
   for p in payloads: ser_map.setdefault(p['series'],[]).append(p)
   by_base[str(basepid)]=ser_map

 out={'schema':1,'generatedAt':generated,'source':'Cardmarket official Product Catalogue + Price Guide','expansions':evidence,
      'stats':{'singles':len(singles),'priceRows':len(prices),'playProducts':play_count,'baseProductsMapped':len(by_base)},
      'byBaseProduct':by_base,'byProduct':by_product}
 dest=Path(__file__).resolve().parents[1]/'data'/'cardmarket_play_index.json'; dest.parent.mkdir(parents=True,exist_ok=True)
 dest.write_text(json.dumps(out,ensure_ascii=False,separators=(',',':')))
 print(json.dumps(out['stats'],indent=2)); print('Prize expansions:',evidence); print('Wrote',dest)
if __name__=='__main__':main()
