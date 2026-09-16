#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'index.html'
AUDIT = ROOT / 'scripts' / 'test_card_identity_cardmarket_audit.py'


def replace_once(text, old, new, label):
    n = text.count(old)
    if n != 1:
        raise SystemExit(f'{label}: expected 1 anchor, found {n}')
    return text.replace(old, new, 1)


def insert_after_block_containing(text, token, addition, label):
    pos = text.find(token)
    if pos < 0:
        raise SystemExit(f'{label}: token missing')
    end = text.find('\n  },', pos)
    if end < 0:
        raise SystemExit(f'{label}: block end missing')
    end += len('\n  },')
    return text[:end] + addition + text[end:]

idx = INDEX.read_text(encoding='utf-8')
aud = AUDIT.read_text(encoding='utf-8')

# 1) Exact production override: only the exact Bisharp identity while the
# upstream top-level product is the verified Throh product 836009.
anchor = "  'sv10.5b-014':{setId:'sv10.5b',localId:'014',conflictingProduct:835069,baseProduct:835929},"
addition = "\n  // Black Bolt / Luce Nera — Bisharp 065. TCGdex top-level 836009 is\n  // Cardmarket Throh [Shoulder Throw]; exact Normal/Reverse rows are Bisharp 836043.\n  // Poké Ball/Master Ball remain separate exact products.\n  'sv10.5b-065':{setId:'sv10.5b',localId:'065',conflictingProduct:836009,baseProduct:836043},"
idx = replace_once(idx, anchor, anchor + addition, 'index override')

# 2) Verified Cardmarket price-guide record used by runtime resolution.
record = """
  'sv10.5b-065':{
    setId:'sv10.5b',localId:'065',name:'Bisharp',productId:836043,
    verified:'2026-09-16T23:34:12+0200',
    source:'Cardmarket Product Catalogue + Price Guide · Black Bolt · Bisharp 065 · product 836043',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:836043,trend:0.03,avg7:0.03,avg30:0.03,avg:0.03,low:0.02,
      'trend-holo':0.12,'avg7-holo':0.15,'avg30-holo':0.16,'avg-holo':0.16,'low-holo':0.02}
  },"""
idx = insert_after_block_containing(
    idx,
    "source:'Cardmarket Product Catalogue + Price Guide · Black Bolt · Darmanitan 014 · product 835929'",
    record,
    'index verified pricing'
)

# 3) Exact identity-conflict guards. 836009 belongs to Throh, and 836043 is
# protected from accidental reuse on other identities.
dar_block = """  const exactDarmanitan014=id==='sv10.5b-014'&&setId==='sv10.5b'&&local==='014'&&name==='darmanitan';
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
bisharp_block = """  const exactBisharp065=id==='sv10.5b-065'&&setId==='sv10.5b'&&local==='065'&&name==='bisharp';
  const targetsBisharp065=id==='sv10.5b-065'||(setId==='sv10.5b'&&local==='065'&&name==='bisharp');
  if((product===836009&&targetsBisharp065)||(product===836043&&!exactBisharp065)){
    return {
      kind:'identity-mismatch',
      source:'Cardmarket · Black Bolt Bisharp 065 product 836043 verificato',
      reason:product===836009
        ?'Il prodotto 836009 appartiene a Throh [Shoulder Throw] e non può valutare Bisharp 065'
        :'Il prodotto 836043 è consentito solo per Bisharp sv10.5b-065 / 065'
    };
  }
"""
idx = replace_once(idx, dar_block, dar_block + bisharp_block, 'index conflict guard')

# Audit exact-pair dictionaries.
aud = replace_once(
    aud,
    '    "sv10.5b-014": {"base": 835929, "alternate": 835069, "stamp": "unverified-top-level-product", "cardmarketCode": "BLK014"},',
    '    "sv10.5b-014": {"base": 835929, "alternate": 835069, "stamp": "unverified-top-level-product", "cardmarketCode": "BLK014"},\n'
    '    "sv10.5b-065": {"base": 836043, "alternate": 836009, "stamp": "wrong-card-identity", "cardmarketCode": "BLK065"},',
    'audit confirmed pair'
)
aud = replace_once(
    aud,
    '    "sv10.5b-014": {"setId": "sv10.5b", "localId": "014", "conflictingProduct": 835069, "baseProduct": 835929},',
    '    "sv10.5b-014": {"setId": "sv10.5b", "localId": "014", "conflictingProduct": 835069, "baseProduct": 835929},\n'
    '    "sv10.5b-065": {"setId": "sv10.5b", "localId": "065", "conflictingProduct": 836009, "baseProduct": 836043},',
    'audit expected override'
)

# Runtime fixture before Metagross.
fixture_anchor = '    fixtures["metagross"] = {\n'
fixture = '''    fixtures["bisharp065"] = {
        "id": "sv10.5b-065", "tcgdexId": "sv10.5b-065", "name": "Bisharp", "localId": "065",
        "set": {"id": "sv10.5b", "name": "Black Bolt"}, "rarity": "Uncommon", "regulationMark": "I",
        "variants": {"normal": True, "holo": False, "reverse": True},
        "variants_detailed": [
            {"type": "normal", "thirdParty": {"cardmarket": 836043}},
            {"type": "reverse", "thirdParty": {"cardmarket": 836043}},
            {"type": "reverse", "foil": "pokeball", "thirdParty": {"cardmarket": 836444}},
            {"type": "reverse", "foil": "masterball", "thirdParty": {"cardmarket": 836445}},
        ],
        "pricing": {"cardmarket": {"idProduct": 836009, "trend": 0.03, "trend-holo": 0.19}},
    }
'''
aud = replace_once(aud, fixture_anchor, fixture + fixture_anchor, 'audit fixture')

# Runtime assertions before Metagross assertions.
assert_anchor = 'const met=fixtures.metagross;\n'
assertions = '''const bish=fixtures.bisharp065;
const bishOverride=r.verifiedBaseCardmarketProductOverride(bish);
assert.strictEqual(bishOverride?.pricing?.idProduct,836043);
assert.strictEqual(r.resolvedCardmarketPricingForCard(bish)?.idProduct,836043);
assert.strictEqual(r.knownCardmarketIdentityConflict(bish,836009)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...bish,id:'sv10.5b-066',tcgdexId:'sv10.5b-066',localId:'066'},836043)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...bish,id:'other-1',tcgdexId:'other-1',localId:'1',name:'Other',set:{id:'other'}},836009),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...bish,localId:'066'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...bish,name:'Pawniard'}),null);
const bishNormal=r.cardmarketValueForCardVariant(bish,'Normal');
const bishReverse=r.cardmarketValueForCardVariant(bish,'Reverse Holo');
const bishPoke=r.cardmarketValueForCardVariant(bish,'Poké Ball Reverse Holo');
const bishMaster=r.cardmarketValueForCardVariant(bish,'Master Ball Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:bishNormal.value,productId:bishNormal.productId})),{value:0.03,productId:836043});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:bishReverse.value,productId:bishReverse.productId})),{value:0.12,productId:836043});
assert.strictEqual(bishPoke.value,0);
assert.strictEqual(bishPoke.kind,'needs-exact-variant');
assert.strictEqual(bishMaster.value,0);
assert.strictEqual(bishMaster.kind,'needs-exact-variant');
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(bish,'Normal'))),{low:0.02,trend:0.03,avg7:0.03,avg30:0.03});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(bish,'Reverse Holo'))),{low:0.02,trend:0.12,avg7:0.15,avg30:0.16});
'''
aud = replace_once(aud, assert_anchor, assertions + assert_anchor, 'audit runtime assertions')

INDEX.write_text(idx, encoding='utf-8')
AUDIT.write_text(aud, encoding='utf-8')
print('Applied exact Bisharp sv10.5b-065 Cardmarket patch')
