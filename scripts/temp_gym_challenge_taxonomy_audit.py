#!/usr/bin/env python3
from __future__ import annotations
import json, os
from collections import Counter, defaultdict
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
DB=Path(os.environ.get('TCGDEX_DB',''))

def walk_json_files(root):
    for p in root.rglob('*.json'):
        try:
            obj=json.loads(p.read_text(encoding='utf-8'))
        except Exception:
            continue
        if isinstance(obj,dict) and (obj.get('variants_detailed') or obj.get('variants')):
            yield p,obj

def main():
    if not DB.exists(): raise SystemExit('TCGDEX_DB missing')
    rows=[]; combos=Counter(); sets=Counter(); cards=set(); bad=[]
    for p,c in walk_json_files(DB):
        cid=str(c.get('id') or '').strip()
        sid=str((c.get('set') or {}).get('id') or (cid.rsplit('-',1)[0] if '-' in cid else '')).strip()
        for r in c.get('variants_detailed') or []:
            stamps=[str(x or '').strip().lower() for x in (r.get('stamp') or [])]
            if 'gym-challenge' not in stamps: continue
            pid=(r.get('thirdParty') or {}).get('cardmarket')
            cm=((r.get('pricing') or {}).get('cardmarket') or {})
            ppid=cm.get('idProduct') or cm.get('id_product')
            usable=any(isinstance(cm.get(k),(int,float)) and cm.get(k)>0 for k in ('trend','avg7','avg30','avg','low'))
            rec={'id':cid,'setId':sid,'localId':c.get('localId'),'name':c.get('name'),'type':r.get('type'),'foil':r.get('foil'),'stamp':stamps,'productId':pid,'pricingProductId':ppid,'usablePrice':usable}
            rows.append(rec); cards.add(cid); sets[sid]+=1; combos[tuple(stamps)]+=1
            if not pid or not ppid or int(pid)!=int(ppid) or not usable: bad.append(rec)
    out={'rowCount':len(rows),'cardCount':len(cards),'setCounts':dict(sets.most_common()),'stampCombinations':{' + '.join(k):v for k,v in combos.items()},'productPricingMismatchOrMissing':bad,'rows':rows}
    print(json.dumps(out,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
