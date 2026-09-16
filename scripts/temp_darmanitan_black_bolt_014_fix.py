#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'index.html'
AUDIT = ROOT / 'scripts' / 'test_card_identity_cardmarket_audit.py'


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 anchor, found {count}')
    return text.replace(old, new, 1)

index = INDEX.read_text(encoding='utf-8')

index = replace_once(
    index,
    "  'sv10.5b-027':{setId:'sv10.5b',localId:'027',conflictingProduct:835994,baseProduct:835953},\n",
    "  'sv10.5b-027':{setId:'sv10.5b',localId:'027',conflictingProduct:835994,baseProduct:835953},\n"
    "  // Black Bolt / Luce Nera — Darmanitan 014. The current top-level product\n"
    "  // 835069 is absent from the official current Cardmarket Product Catalogue\n"
    "  // and Price Guide; exact Normal/Reverse rows resolve to product 835929.\n"
    "  // Poké Ball/Master Ball remain separate exact products.\n"
    "  'sv10.5b-014':{setId:'sv10.5b',localId:'014',conflictingProduct:835069,baseProduct:835929},\n",
    'index base override',
)

cry_guide = """  'sv10.5b-027':{
    setId:'sv10.5b',localId:'027',name:'Cryogonal',productId:835953,
    verified:'2026-09-16T21:04:13+0200',
    source:'Cardmarket Product Catalogue + Price Guide · Black Bolt · Cryogonal 027 · product 835953',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:835953,trend:0.05,avg7:0.08,avg30:0.04,avg:0.03,low:0.02,
      'trend-holo':0.18,'avg7-holo':0.20,'avg30-holo':0.19,'avg-holo':0.17,'low-holo':0.02}
  },
"""
darmanitan_guide = """  'sv10.5b-014':{
    setId:'sv10.5b',localId:'014',name:'Darmanitan',productId:835929,
    verified:'2026-09-16T23:16:44+0200',
    source:'Cardmarket Product Catalogue + Price Guide · Black Bolt · Darmanitan 014 · product 835929',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:835929,trend:0.03,avg7:0.02,avg30:0.03,avg:0.03,low:0.02,
      'trend-holo':0.20,'avg7-holo':0.26,'avg30-holo':0.25,'avg-holo':0.25,'low-holo':0.02}
  },
"""
index = replace_once(index, cry_guide, cry_guide + darmanitan_guide, 'index exact price guide')

cry_guard = """  const exactCryogonal027=id==='sv10.5b-027'&&setId==='sv10.5b'&&local==='027'&&name==='cryogonal';
  const targetsCryogonal027=id==='sv10.5b-027'||(setId==='sv10.5b'&&local==='027'&&name==='cryogonal');
  if((product===835994&&targetsCryogonal027)||(product===835953&&!exactCryogonal027)){
    return {
      kind:'identity-mismatch',
      source:'Cardmarket · Black Bolt Cryogonal 027 product 835953 verificato',
      reason:product===835994
        ?'Il prodotto 835994 appartiene a Golurk e non può valutare Cryogonal 027'
        :'Il prodotto 835953 è consentito solo per Cryogonal sv10.5b-027 / 027'
    };
  }
"""
darmanitan_guard = """  const exactDarmanitan014=id==='sv10.5b-014'&&setId==='sv10.5b'&&local==='014'&&name==='darmanitan';
  const targetsDarmanitan014=id==='sv10.5b-014'||(setId==='sv10.5b'&&local==='014'&&name==='darmanitan');
  if((product===835069&&targetsDarmanitan014)||(product===835929&&!exactDarmanitan014)){
    return {
      kind:'identity-mismatch',
      source:'Cardmarket · Black Bolt Darmanitan 014 product 835929 verificato',
      reason:product===835069
        ?'Il prodotto top-level 835069 non è verificabile nel Product Catalogue/Price Guide ufficiale corrente e non può valutare Darmanitan 014'
        :'Il prodotto 835929 è consentito solo per Darmanitan sv10.5b-014 / 014'
    };
  }
"""
index = replace_once(index, cry_guard, cry_guard + darmanitan_guard, 'index identity guard')
INDEX.write_text(index, encoding='utf-8')

audit = AUDIT.read_text(encoding='utf-8')
audit = replace_once(
    audit,
    '    "sv10.5b-027": {"base": 835953, "alternate": 835994, "stamp": "wrong-card-identity", "cardmarketCode": "BLK027"},\n',
    '    "sv10.5b-027": {"base": 835953, "alternate": 835994, "stamp": "wrong-card-identity", "cardmarketCode": "BLK027"},\n'
    '    "sv10.5b-014": {"base": 835929, "alternate": 835069, "stamp": "unverified-top-level-product", "cardmarketCode": "BLK014"},\n',
    'audit confirmed conflict',
)
audit = replace_once(
    audit,
    '    "sv10.5b-027": {"setId": "sv10.5b", "localId": "027", "conflictingProduct": 835994, "baseProduct": 835953},\n',
    '    "sv10.5b-027": {"setId": "sv10.5b", "localId": "027", "conflictingProduct": 835994, "baseProduct": 835953},\n'
    '    "sv10.5b-014": {"setId": "sv10.5b", "localId": "014", "conflictingProduct": 835069, "baseProduct": 835929},\n',
    'audit expected override',
)

cry_fixture = """    fixtures[\"cryogonal027\"] = {
        \"id\": \"sv10.5b-027\", \"tcgdexId\": \"sv10.5b-027\", \"name\": \"Cryogonal\", \"localId\": \"027\",
        \"set\": {\"id\": \"sv10.5b\", \"name\": \"Black Bolt\"}, \"rarity\": \"Uncommon\", \"regulationMark\": \"I\",
        \"variants\": {\"normal\": True, \"holo\": False, \"reverse\": True},
        \"variants_detailed\": [
            {\"type\": \"normal\", \"thirdParty\": {\"cardmarket\": 835953}},
            {\"type\": \"reverse\", \"thirdParty\": {\"cardmarket\": 835953}},
            {\"type\": \"reverse\", \"foil\": \"pokeball\", \"thirdParty\": {\"cardmarket\": 836326}},
            {\"type\": \"reverse\", \"foil\": \"masterball\", \"thirdParty\": {\"cardmarket\": 836324}},
        ],
        \"pricing\": {\"cardmarket\": {\"idProduct\": 835994, \"trend\": 0.02, \"trend-holo\": 0.28}},
    }
"""
darmanitan_fixture = """    fixtures[\"darmanitan014\"] = {
        \"id\": \"sv10.5b-014\", \"tcgdexId\": \"sv10.5b-014\", \"name\": \"Darmanitan\", \"localId\": \"014\",
        \"set\": {\"id\": \"sv10.5b\", \"name\": \"Black Bolt\"}, \"rarity\": \"Uncommon\", \"regulationMark\": \"I\",
        \"variants\": {\"normal\": True, \"holo\": False, \"reverse\": True},
        \"variants_detailed\": [
            {\"type\": \"normal\", \"thirdParty\": {\"cardmarket\": 835929}},
            {\"type\": \"reverse\", \"thirdParty\": {\"cardmarket\": 835929}},
            {\"type\": \"reverse\", \"foil\": \"pokeball\", \"thirdParty\": {\"cardmarket\": 836285}},
            {\"type\": \"reverse\", \"foil\": \"masterball\", \"thirdParty\": {\"cardmarket\": 836286}},
        ],
        \"pricing\": {\"cardmarket\": {\"idProduct\": 835069}},
    }
"""
audit = replace_once(audit, cry_fixture, cry_fixture + darmanitan_fixture, 'audit runtime fixture')

cry_assertions = """assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(cry,'Reverse Holo'))),{low:0.02,trend:0.18,avg7:0.20,avg30:0.19});
"""
darmanitan_assertions = """const dar=fixtures.darmanitan014;
const darOverride=r.verifiedBaseCardmarketProductOverride(dar);
assert.strictEqual(darOverride?.pricing?.idProduct,835929);
assert.strictEqual(r.resolvedCardmarketPricingForCard(dar)?.idProduct,835929);
assert.strictEqual(r.knownCardmarketIdentityConflict(dar,835069)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...dar,id:'sv10.5b-015',tcgdexId:'sv10.5b-015',localId:'015'},835929)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...dar,id:'other-1',tcgdexId:'other-1',localId:'1',name:'Other',set:{id:'other'}},835069),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...dar,localId:'015'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...dar,name:'Darumaka'}),null);
const darNormal=r.cardmarketValueForCardVariant(dar,'Normal');
const darReverse=r.cardmarketValueForCardVariant(dar,'Reverse Holo');
const darPoke=r.cardmarketValueForCardVariant(dar,'Poké Ball Reverse Holo');
const darMaster=r.cardmarketValueForCardVariant(dar,'Master Ball Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:darNormal.value,productId:darNormal.productId})),{value:0.03,productId:835929});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:darReverse.value,productId:darReverse.productId})),{value:0.20,productId:835929});
assert.strictEqual(darPoke.value,0);
assert.strictEqual(darPoke.kind,'needs-exact-variant');
assert.strictEqual(darMaster.value,0);
assert.strictEqual(darMaster.kind,'needs-exact-variant');
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(dar,'Normal'))),{low:0.02,trend:0.03,avg7:0.02,avg30:0.03});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(dar,'Reverse Holo'))),{low:0.02,trend:0.20,avg7:0.26,avg30:0.25});
"""
audit = replace_once(audit, cry_assertions, cry_assertions + darmanitan_assertions, 'audit runtime assertions')
AUDIT.write_text(audit, encoding='utf-8')

print('Applied exact Darmanitan sv10.5b-014 Cardmarket patch')
