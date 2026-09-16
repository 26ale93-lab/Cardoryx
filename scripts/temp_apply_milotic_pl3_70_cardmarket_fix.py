#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
index=ROOT/'index.html'
audit=ROOT/'scripts/test_card_identity_cardmarket_audit.py'

s=index.read_text(encoding='utf-8')

old="""  // Supreme Victors — TCGdex currently points Metagross 7/147 at Milotic
  // product 278689. Cardmarket catalogue proves product 278698 is Metagross.
  'pl3-7':{setId:'pl3',localId:'007',conflictingProduct:278689,baseProduct:278698},
"""
new=old+"""  // Supreme Victors — Milotic 70/147. TCGdex currently exposes the later
  // special V2 product 882910 at top level and points Reverse to Milotic SH7
  // product 278689. Cardmarket catalogue proves V1 product 278761 is the exact
  // Milotic Lv.49 70/147 standard product with standard + Reverse price fields.
  'pl3-70':{setId:'pl3',localId:'070',conflictingProduct:882910,baseProduct:278761},
"""
if old not in s: raise SystemExit('index override anchor missing')
s=s.replace(old,new,1)

old="""  'pl3-7':{
    setId:'pl3',localId:'007',name:'Metagross',productId:278698,
    verified:'2026-09-16T12:13:02+0200',
    source:'Cardmarket Product Catalogue + Price Guide · Supreme Victors · Metagross Lv.68 · product 278698',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:278698,trend:3.05,avg7:4.10,avg30:3.47,avg:3.55,low:0.45,
      'trend-holo':3.24,'avg7-holo':3.40,'avg30-holo':2.63,'avg-holo':3.40,'low-holo':0.45}
  },
"""
new=old+"""  'pl3-70':{
    setId:'pl3',localId:'070',name:'Milotic',productId:278761,
    verified:'2026-09-16T20:12:54+0200',
    source:'Cardmarket Product Catalogue + Price Guide · Supreme Victors · Milotic Lv.49 70/147 V1 · product 278761',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:278761,trend:0.97,avg7:1.27,avg30:0.87,avg:1.10,low:0.13,
      'trend-holo':14.54,'avg7-holo':13.73,'avg30-holo':8.01,'avg-holo':29.02,'low-holo':0.49}
  },
"""
if old not in s: raise SystemExit('index guide anchor missing')
s=s.replace(old,new,1)

old="""  const exactMetagrossPl3_7=id==='pl3-7'&&setId==='pl3'&&local==='7'&&name==='metagross';
  const targetsMetagrossPl3_7=id==='pl3-7'||(setId==='pl3'&&local==='7'&&name==='metagross');
  if((product===278689&&targetsMetagrossPl3_7)||(product===278698&&!exactMetagrossPl3_7)){
    return {
      kind:'identity-mismatch',
      source:'Cardmarket · Supreme Victors Metagross 7/147 product 278698 verificato',
      reason:product===278689
        ?'Il prodotto 278689 appartiene a Milotic Lv.52 e non può valutare Metagross 7/147'
        :'Il prodotto 278698 è consentito solo per Metagross pl3-7 / 007'
    };
  }
"""
new=old+"""  const exactMiloticPl3_70=id==='pl3-70'&&setId==='pl3'&&local==='70'&&name==='milotic';
  const targetsMiloticPl3_70=id==='pl3-70'||(setId==='pl3'&&local==='70'&&name==='milotic');
  if((product===278689&&targetsMiloticPl3_70)||(product===278761&&!exactMiloticPl3_70)){
    return {
      kind:'identity-mismatch',
      source:'Cardmarket · Supreme Victors Milotic Lv.49 70/147 V1 product 278761 verificato',
      reason:product===278689
        ?'Il prodotto 278689 appartiene a Milotic Lv.52 SH7 e non può valutare Milotic 70/147'
        :'Il prodotto 278761 è consentito solo per Milotic pl3-70 / 070'
    };
  }
"""
if old not in s: raise SystemExit('index conflict anchor missing')
s=s.replace(old,new,1)
index.write_text(s,encoding='utf-8')

s=audit.read_text(encoding='utf-8')
old='''    "pl3-7": {"base": 278698, "alternate": 278689, "stamp": "wrong-card-identity", "cardmarketCode": "SV7"},\n'''
new=old+'''    "pl3-70": {"base": 278761, "alternate": 882910, "stamp": "special-v2-source-conflict", "cardmarketCode": "SV70"},\n'''
if old not in s: raise SystemExit('audit confirmed conflict anchor missing')
s=s.replace(old,new,1)
old='''    "pl3-7": {"setId": "pl3", "localId": "007", "conflictingProduct": 278689, "baseProduct": 278698},\n'''
new=old+'''    "pl3-70": {"setId": "pl3", "localId": "070", "conflictingProduct": 882910, "baseProduct": 278761},\n'''
if old not in s: raise SystemExit('audit expected override anchor missing')
s=s.replace(old,new,1)

old='''    fixtures["metagross"] = {\n        "id": "pl3-7", "tcgdexId": "pl3-7", "name": "Metagross", "localId": "7",\n'''
insert='''    fixtures["milotic70"] = {\n        "id": "pl3-70", "tcgdexId": "pl3-70", "name": "Milotic", "localId": "70",\n        "set": {"id": "pl3", "name": "Supreme Victors"}, "rarity": "Uncommon",\n        "variants": {"normal": True, "holo": False, "reverse": True},\n        "variants_detailed": [\n            {"type": "normal", "thirdParty": {"cardmarket": 882910}, "pricing": {"cardmarket": {"idProduct": 882910, "trend": 34.74}}},\n            {"type": "reverse", "thirdParty": {"cardmarket": 278689}, "pricing": {"cardmarket": {"idProduct": 278689, "trend": 40.68}}},\n            {"type": "normal", "stamp": ["pre-release"], "thirdParty": {"cardmarket": 882910}, "pricing": {"cardmarket": {"idProduct": 882910, "trend": 34.74}}},\n        ],\n        "pricing": {"cardmarket": {"idProduct": 882910, "trend": 34.74}},\n    }\n'''+old
if old not in s: raise SystemExit('audit fixture anchor missing')
s=s.replace(old,insert,1)

old="""const metHolo=r.cardmarketValueForCardVariant(met,'Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:metHolo.value,productId:metHolo.productId})),{value:3.05,productId:278698});
"""
new=old+"""const mil=fixtures.milotic70;
const milOverride=r.verifiedBaseCardmarketProductOverride(mil);
assert.strictEqual(milOverride?.pricing?.idProduct,278761);
assert.strictEqual(r.resolvedCardmarketPricingForCard(mil)?.idProduct,278761);
assert.strictEqual(r.knownCardmarketIdentityConflict(mil,278689)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...mil,id:'pl3-SH7',tcgdexId:'pl3-SH7',localId:'SH7'},278761)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...mil,localId:'71'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...mil,name:'Milotic Lv.52'}),null);
const milNormal=r.cardmarketValueForCardVariant(mil,'Normal');
const milReverse=r.cardmarketValueForCardVariant(mil,'Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:milNormal.value,productId:milNormal.productId})),{value:0.97,productId:278761});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:milReverse.value,productId:milReverse.productId})),{value:14.54,productId:278761});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(mil,'Normal'))),{low:0.13,trend:0.97,avg7:1.27,avg30:0.87});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(mil,'Reverse Holo'))),{low:0.49,trend:14.54,avg7:13.73,avg30:8.01});
"""
if old not in s: raise SystemExit('audit runtime assertion anchor missing')
s=s.replace(old,new,1)

audit.write_text(s,encoding='utf-8')
print('patched exact Milotic pl3-70 Cardmarket base and reverse identity')
