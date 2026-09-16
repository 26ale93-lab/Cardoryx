#!/usr/bin/env python3
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
index=ROOT/'index.html'
audit=ROOT/'scripts/test_card_identity_cardmarket_audit.py'

s=index.read_text(encoding='utf-8')

old="""  'pl3-70':{setId:'pl3',localId:'070',conflictingProduct:882910,baseProduct:278761},
  // EX Hidden Legends — Beldum 29/101. TCGdex exposes the Gym Challenge
"""
new="""  'pl3-70':{setId:'pl3',localId:'070',conflictingProduct:882910,baseProduct:278761},
  // Black Bolt / Luce Nera — Cryogonal 027. TCGdex top-level currently points
  // to Golurk product 835994, while its exact Normal/Reverse physical rows use
  // Cryogonal product 835953. Poké Ball/Master Ball stay separate products.
  'sv10.5b-027':{setId:'sv10.5b',localId:'027',conflictingProduct:835994,baseProduct:835953},
  // EX Hidden Legends — Beldum 29/101. TCGdex exposes the Gym Challenge
"""
if old not in s: raise SystemExit('index override anchor missing')
s=s.replace(old,new,1)

old="""  'pl3-70':{
    setId:'pl3',localId:'070',name:'Milotic',productId:278761,
    verified:'2026-09-16T20:12:54+0200',
    source:'Cardmarket Product Catalogue + Price Guide · Supreme Victors · Milotic Lv.49 70/147 V1 · product 278761',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:278761,trend:0.97,avg7:1.27,avg30:0.87,avg:1.10,low:0.13,
      'trend-holo':14.54,'avg7-holo':13.73,'avg30-holo':8.01,'avg-holo':29.02,'low-holo':0.49}
  },
  'ex4-6':{
"""
new="""  'pl3-70':{
    setId:'pl3',localId:'070',name:'Milotic',productId:278761,
    verified:'2026-09-16T20:12:54+0200',
    source:'Cardmarket Product Catalogue + Price Guide · Supreme Victors · Milotic Lv.49 70/147 V1 · product 278761',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:278761,trend:0.97,avg7:1.27,avg30:0.87,avg:1.10,low:0.13,
      'trend-holo':14.54,'avg7-holo':13.73,'avg30-holo':8.01,'avg-holo':29.02,'low-holo':0.49}
  },
  'sv10.5b-027':{
    setId:'sv10.5b',localId:'027',name:'Cryogonal',productId:835953,
    verified:'2026-09-16T21:04:13+0200',
    source:'Cardmarket Product Catalogue + Price Guide · Black Bolt · Cryogonal 027 · product 835953',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:835953,trend:0.05,avg7:0.08,avg30:0.04,avg:0.03,low:0.02,
      'trend-holo':0.18,'avg7-holo':0.20,'avg30-holo':0.19,'avg-holo':0.17,'low-holo':0.02}
  },
  'ex4-6':{
"""
if old not in s: raise SystemExit('index guide anchor missing')
s=s.replace(old,new,1)

old="""  const exactMiloticPl3_70=id==='pl3-70'&&setId==='pl3'&&local==='70'&&name==='milotic';
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
  const ex4ExactConflicts=[
"""
new="""  const exactMiloticPl3_70=id==='pl3-70'&&setId==='pl3'&&local==='70'&&name==='milotic';
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
  const exactCryogonal027=id==='sv10.5b-027'&&setId==='sv10.5b'&&local==='27'&&name==='cryogonal';
  const targetsCryogonal027=id==='sv10.5b-027'||(setId==='sv10.5b'&&local==='27'&&name==='cryogonal');
  if((product===835994&&targetsCryogonal027)||(product===835953&&!exactCryogonal027)){
    return {
      kind:'identity-mismatch',
      source:'Cardmarket · Black Bolt Cryogonal 027 product 835953 verificato',
      reason:product===835994
        ?'Il prodotto 835994 appartiene a Golurk e non può valutare Cryogonal 027'
        :'Il prodotto 835953 è consentito solo per Cryogonal sv10.5b-027 / 027'
    };
  }
  const ex4ExactConflicts=[
"""
if old not in s: raise SystemExit('index conflict anchor missing')
s=s.replace(old,new,1)
index.write_text(s,encoding='utf-8')

s=audit.read_text(encoding='utf-8')
old='''    "pl3-70": {"base": 278761, "alternate": 882910, "stamp": "special-v2-source-conflict", "cardmarketCode": "SV70"},\n'''
new=old+'''    "sv10.5b-027": {"base": 835953, "alternate": 835994, "stamp": "wrong-card-identity", "cardmarketCode": "BLK027"},\n'''
if old not in s: raise SystemExit('audit confirmed conflict anchor missing')
s=s.replace(old,new,1)

old='''    "pl3-70": {"setId": "pl3", "localId": "070", "conflictingProduct": 882910, "baseProduct": 278761},\n'''
new=old+'''    "sv10.5b-027": {"setId": "sv10.5b", "localId": "027", "conflictingProduct": 835994, "baseProduct": 835953},\n'''
if old not in s: raise SystemExit('audit expected override anchor missing')
s=s.replace(old,new,1)

old='''    fixtures["metagross"] = {\n'''
insert='''    fixtures["cryogonal027"] = {\n        "id": "sv10.5b-027", "tcgdexId": "sv10.5b-027", "name": "Cryogonal", "localId": "027",\n        "set": {"id": "sv10.5b", "name": "Black Bolt"}, "rarity": "Uncommon", "regulationMark": "I",\n        "variants": {"normal": True, "holo": False, "reverse": True},\n        "variants_detailed": [\n            {"type": "normal", "thirdParty": {"cardmarket": 835953}},\n            {"type": "reverse", "thirdParty": {"cardmarket": 835953}},\n            {"type": "reverse", "foil": "pokeball", "thirdParty": {"cardmarket": 836326}},\n            {"type": "reverse", "foil": "masterball", "thirdParty": {"cardmarket": 836324}},\n        ],\n        "pricing": {"cardmarket": {"idProduct": 835994, "trend": 0.02, "trend-holo": 0.28}},\n    }\n'''+old
if old not in s: raise SystemExit('audit fixture anchor missing')
s=s.replace(old,insert,1)

old="""assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(mil,'Reverse Holo'))),{low:0.49,trend:14.54,avg7:13.73,avg30:8.01});
for(const card of fixtures.ex4_high_impact){
"""
new="""assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(mil,'Reverse Holo'))),{low:0.49,trend:14.54,avg7:13.73,avg30:8.01});
const cry=fixtures.cryogonal027;
const cryOverride=r.verifiedBaseCardmarketProductOverride(cry);
assert.strictEqual(cryOverride?.pricing?.idProduct,835953);
assert.strictEqual(r.resolvedCardmarketPricingForCard(cry)?.idProduct,835953);
assert.strictEqual(r.knownCardmarketIdentityConflict(cry,835994)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...cry,id:'sv10.5b-028',tcgdexId:'sv10.5b-028',localId:'028'},835953)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...cry,localId:'028'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...cry,name:'Golurk'}),null);
const cryNormal=r.cardmarketValueForCardVariant(cry,'Normal');
const cryReverse=r.cardmarketValueForCardVariant(cry,'Reverse Holo');
const cryPoke=r.cardmarketValueForCardVariant(cry,'Poké Ball Reverse Holo');
const cryMaster=r.cardmarketValueForCardVariant(cry,'Master Ball Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:cryNormal.value,productId:cryNormal.productId})),{value:0.05,productId:835953});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:cryReverse.value,productId:cryReverse.productId})),{value:0.18,productId:835953});
assert.strictEqual(cryPoke.value,0);
assert.strictEqual(cryPoke.kind,'needs-exact-variant');
assert.strictEqual(cryMaster.value,0);
assert.strictEqual(cryMaster.kind,'needs-exact-variant');
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(cry,'Normal'))),{low:0.02,trend:0.05,avg7:0.08,avg30:0.04});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(cry,'Reverse Holo'))),{low:0.02,trend:0.18,avg7:0.20,avg30:0.19});
for(const card of fixtures.ex4_high_impact){
"""
if old not in s: raise SystemExit('audit runtime assertion anchor missing')
s=s.replace(old,new,1)

audit.write_text(s,encoding='utf-8')
print('patched exact Cryogonal sv10.5b-027 Cardmarket base identity')
