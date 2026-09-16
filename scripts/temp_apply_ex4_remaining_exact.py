#!/usr/bin/env python3
from __future__ import annotations
import json, re, unicodedata, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'
TEST=ROOT/'scripts'/'test_card_identity_cardmarket_audit.py'
CM_PRODUCTS='https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json'
CM_PRICES='https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json'
EX4_EXPANSION=1542
VERIFIED='2026-09-16T15:00:00+0200'

# Every row is an independent verified identity. Never derive these by offset.
TARGETS=[
 ('ex4-1','1',"Team Aqua's Cacturne",275778,275978),
 ('ex4-3','3',"Team Aqua's Kyogre",275780,275980),
 ('ex4-9','9',"Team Magma's Groudon",275786,275986),
 ('ex4-12','12',"Team Magma's Torkoal",275789,275989),
 ('ex4-13','13','Raichu',275790,275990),
 ('ex4-17','17',"Team Aqua's Seviper",275794,275994),
 ('ex4-28','28',"Team Aqua's Lanturn",275805,276005),
 ('ex4-39','39','Bulbasaur',275816,276016),
 ('ex4-40','40','Cubone',275817,276017),
 ('ex4-41','41','Jigglypuff',275818,276018),
 ('ex4-42','42','Meowth',275819,276019),
 ('ex4-43','43','Pikachu',275820,276020),
 ('ex4-44','44','Psyduck',275821,276021),
 ('ex4-45','45','Slowpoke',275822,276022),
 ('ex4-46','46','Squirtle',275823,276023),
 ('ex4-49','49',"Team Aqua's Chinchou",275826,276026),
 ('ex4-69','69','Team Aqua Schemer',275846,276046),
 ('ex4-70','70','Team Magma Schemer',275847,276047),
 ('ex4-71','71','Archie',275848,276048),
 ('ex4-72','72','Dual Ball',275849,276049),
 ('ex4-74','74','Strength Charm',275851,276051),
 ('ex4-75','75','Team Aqua Ball',275852,276052),
 ('ex4-76','76','Team Aqua Belt',275853,276053),
 ('ex4-77','77','Team Aqua Conspirator',275854,276054),
 ('ex4-79','79','Team Aqua Technical Machine 01',275856,276056),
 ('ex4-81','81','Team Magma Belt',275858,276058),
 ('ex4-83','83','Team Magma Hideout',275860,276060),
 ('ex4-84','84','Team Magma Technical Machine 01',275861,276061),
 ('ex4-86','86','Aqua Energy',275863,276063),
 ('ex4-88','88','Double Rainbow Energy',275865,276065),
]

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Cardoryx-EX4-Remaining-Exact/1.0'})
    with urllib.request.urlopen(req,timeout=300) as r:return json.load(r)
def norm(v):
    s=unicodedata.normalize('NFKD',str(v or '')).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z0-9]+','',s)
def base_name(row): return str((row or {}).get('name') or '').split(' [',1)[0]
def replace_once(text,old,new,label):
    n=text.count(old)
    if n!=1: raise SystemExit(f'{label}: expected one marker, found {n}')
    return text.replace(old,new,1)
def price_compact(row):
    keys=('trend','avg7','avg30','avg','low','trend-holo','avg7-holo','avg30-holo','avg-holo','low-holo')
    return {k:row.get(k) for k in keys if k in row}

def main():
    products=get(CM_PRODUCTS).get('products',[])
    price_root=get(CM_PRICES); price_rows=price_root.get('priceGuides',price_root.get('priceGuide',[]))
    byid={int(p['idProduct']):p for p in products if p.get('idProduct') is not None}
    prices={int(p['idProduct']):p for p in price_rows if p.get('idProduct') is not None}
    western=[p for p in products if int(p.get('idExpansion') or 0)==EX4_EXPANSION]
    seen_targets=set()
    validated=[]
    for cid,local,name,wrong,correct in TARGETS:
        if correct in seen_targets: raise SystemExit(f'duplicate target product {correct}')
        seen_targets.add(correct)
        wrongrow=byid.get(wrong); target=byid.get(correct); price=prices.get(correct)
        matches=[p for p in western if norm(base_name(p))==norm(name)]
        if len(matches)!=1 or int(matches[0]['idProduct'])!=correct:
            raise SystemExit(f'{cid}: target is not unique exact-name product in expansion 1542')
        if not wrongrow or int(wrongrow.get('idExpansion') or 0)==EX4_EXPANSION:
            raise SystemExit(f'{cid}: conflicting product is not outside expansion 1542')
        if not target or int(target.get('idExpansion') or 0)!=EX4_EXPANSION or norm(base_name(target))!=norm(name):
            raise SystemExit(f'{cid}: target identity mismatch')
        if not price or not any(isinstance(price.get(k),(int,float)) and price.get(k)>0 for k in ('trend','avg7','avg30','avg','low')):
            raise SystemExit(f'{cid}: no valid Cardmarket Price Guide row')
        validated.append((cid,local,name,wrong,correct,price_compact(price)))

    source=INDEX.read_text(encoding='utf-8')
    test=TEST.read_text(encoding='utf-8')
    for cid,_,_,_,_,_ in validated:
        if re.search(rf"['\"]{re.escape(cid)}['\"]\s*:\s*\{{setId:['\"]ex4",source):
            raise SystemExit(f'{cid}: production override already exists')

    # 1) Exact base-product override registry.
    override_lines=[]
    for cid,local,name,wrong,correct,price in validated:
        override_lines.append(f"  {json.dumps(cid)}:{{setId:'ex4',localId:{json.dumps(str(local).zfill(3))},conflictingProduct:{wrong},baseProduct:{correct}}}")
    marker='  "ex4-87":{setId:\'ex4\',localId:"087",conflictingProduct:275864,baseProduct:276064}\n};'
    source=replace_once(source,marker,marker[:-3]+',\n'+',\n'.join(override_lines)+'\n};','override registry')

    # 2) Exact official Price Guide rows. These are evidence rows, never estimates.
    guide_entries=[]
    for cid,local,name,wrong,correct,price in validated:
        pricing={'idProduct':correct,**price}
        guide_entries.append(
            f"  {json.dumps(cid)}:{{\n"
            f"    setId:'ex4',localId:{json.dumps(str(local).zfill(3))},name:{json.dumps(name)},productId:{correct},\n"
            f"    verified:{json.dumps(VERIFIED)},\n"
            f"    source:{json.dumps('Cardmarket Product Catalogue + Price Guide · EX Team Magma vs Team Aqua · exact checklist-verified product '+str(correct))},\n"
            f"    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',\n"
            f"    pricing:{json.dumps(pricing,separators=(',',':'))}\n"
            f"  }}")
    source=replace_once(source,'\n};\nfunction exactCardmarketGuideIdentity(card,id,guide){',',\n'+',\n'.join(guide_entries)+'\n};\nfunction exactCardmarketGuideIdentity(card,id,guide){','price guide registry')

    # 3) Conflict guard list: exact identity only.
    conflict_lines=[]
    for cid,local,name,wrong,correct,price in validated:
        conflict_lines.append(f"    [{json.dumps(cid)},{json.dumps(str(int(local)))},{json.dumps(norm(name))},{wrong},{correct}]")
    marker='    ["ex4-87","87","magmaenergy",275864,276064]\n  ];'
    source=replace_once(source,marker,marker[:-5]+',\n'+',\n'.join(conflict_lines)+'\n  ];','conflict guard')

    # 4) Extend the existing audit constants, preserving one permanent audit file.
    confirmed=[]; expected=[]; fixtures=[]
    for cid,local,name,wrong,correct,price in validated:
        confirmed.append(f'    {json.dumps(cid)}: {{"base": {correct}, "alternate": {wrong}, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-{local}"}}')
        expected.append(f'    {json.dumps(cid)}: {{"setId": "ex4", "localId": {json.dumps(str(local).zfill(3))}, "conflictingProduct": {wrong}, "baseProduct": {correct}}}')
        fixtures.append(f'        {{"id":{json.dumps(cid)},"tcgdexId":{json.dumps(cid)},"name":{json.dumps(name)},"localId":{json.dumps(str(local))},"set":{{"id":"ex4","name":"EX Team Magma vs Team Aqua"}},"wrong":{wrong},"correct":{correct}}},')
    marker='    "ex4-87": {"base": 276064, "alternate": 275864, "stamp": "wrong-card-identity", "cardmarketCode": "EX4-87"}\n}'
    test=replace_once(test,marker,marker[:-2]+',\n'+',\n'.join(confirmed)+'\n}','confirmed conflicts')
    marker='    "ex4-87": {"setId": "ex4", "localId": "087", "conflictingProduct": 275864, "baseProduct": 276064}\n}'
    test=replace_once(test,marker,marker[:-2]+',\n'+',\n'.join(expected)+'\n}','expected overrides')

    # Add the 30 exact cards to the existing EX4 runtime fixture and reuse its guard checks.
    marker='        {"id":"ex4-87","tcgdexId":"ex4-87","name":"Magma Energy","localId":"87","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"wrong":275864,"correct":276064},\n    ]\n    for card in fixtures["ex4_verified_batch"]:'
    replacement=marker.split('\n    ]',1)[0]+'\n'+ '\n'.join(fixtures) +'\n    ]\n    for card in fixtures["ex4_verified_batch"]:'
    test=replace_once(test,marker,replacement,'runtime EX4 fixture')

    # Remove stale fixed-count wording; the registry is intentionally extensible via exact proofs.
    test=test.replace('Base Cardmarket override registry differs from the eleven audited P0 identities','Base Cardmarket override registry differs from the audited exact P0 identities')
    test=test.replace('Eleven exact Cardmarket base-product identity overrides; latest block adds five exact EX Team Magma vs Team Aqua identities','Exact Cardmarket base-product identity overrides; EX Team Magma vs Team Aqua entries are independent per-card mappings')

    INDEX.write_text(source,encoding='utf-8')
    TEST.write_text(test,encoding='utf-8')
    print(json.dumps({'validated':len(validated),'ids':[x[0] for x in validated],'totalExpectedOverrides':50},indent=2))

if __name__=='__main__': main()
