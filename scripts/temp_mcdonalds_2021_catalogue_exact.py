#!/usr/bin/env python3
import importlib.util, json
from pathlib import Path

spec=importlib.util.spec_from_file_location('audit',Path('scripts/test_card_identity_cardmarket_audit.py'))
a=importlib.util.module_from_spec(spec); spec.loader.exec_module(a)
products=json.loads(Path(a.download_if_needed(None,'products_singles_6.json')).read_text(encoding='utf-8'))
prices=json.loads(Path(a.download_if_needed(None,'price_guide_6.json')).read_text(encoding='utf-8'))

def walk(x):
    if isinstance(x,dict):
        yield x
        for v in x.values(): yield from walk(v)
    elif isinstance(x,list):
        for v in x: yield from walk(v)

p={int(d['idProduct']):d for d in walk(products) if isinstance(d.get('idProduct'),int) and d.get('idExpansion')==3738}
g={int(d['idProduct']):d for d in walk(prices) if isinstance(d.get('idProduct'),int)}
fields=('trend','avg7','avg30','avg','low','trend-holo','avg7-holo','avg30-holo','avg-holo','low-holo')
rows=[]
for pid,d in sorted(p.items()):
    if 538700 <= pid <= 539100:
        q=g.get(pid,{})
        row={'idProduct':pid,'idMetacard':d.get('idMetacard'),'name':d.get('name')}
        for k in fields: row[k]=q.get(k)
        rows.append(row)
print('MCD2021_OFFICIAL_COUNT',len(rows))
for r in rows: print('MCD2021_OFFICIAL_FULL '+json.dumps(r,ensure_ascii=False,sort_keys=True))
