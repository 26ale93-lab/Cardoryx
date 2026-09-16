from pathlib import Path

index = Path('index.html')
s = index.read_text(encoding='utf-8')

old = "  'sm12-54':{setId:'sm12',localId:'054',conflictingProduct:398504,baseProduct:407919}\n};"
new = "  'sm12-54':{setId:'sm12',localId:'054',conflictingProduct:398504,baseProduct:407919},\n  // Expedition Base Set — TCGdex currently exposes Tyranitar 029/165 Holo\n  // product 274904 for the exact 066/165 Rare base identity. Cardmarket V2\n  // is the 066/165 base product; keep this exact and fail closed elsewhere.\n  'ecard1-66':{setId:'ecard1',localId:'066',conflictingProduct:274904,baseProduct:274941}\n};"
if s.count(old) != 1:
    raise SystemExit(f'override marker count={s.count(old)}')
s = s.replace(old, new, 1)

marker = "  }\n};\nfunction exactCardmarketGuideIdentity(card,id,guide){"
tyrguide = """  },
  'ecard1-66':{
    setId:'ecard1',localId:'066',name:'Tyranitar',productId:274941,
    verified:'2026-09-16T11:50:00+0200',
    source:'Cardmarket Product Catalogue + Price Guide · Expedition Base Set Version 2 · product 274941',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:274941,trend:10.33,avg7:14.48,avg30:15.37,avg:15.07,low:1.50,
      'trend-holo':40.70,'avg7-holo':33.71,'avg30-holo':43.76,'avg-holo':12.49,'low-holo':3.99}
  }
};
function exactCardmarketGuideIdentity(card,id,guide){"""
if s.count(marker) != 1:
    raise SystemExit(f'guide marker count={s.count(marker)}')
s = s.replace(marker, tyrguide, 1)

marker = "  const isTorkoal29=id==='sm12-29'||(setId==='sm12'&&local==='29'&&name==='torkoal');"
tyrguard = """  const exactTyranitar66=id==='ecard1-66'&&setId==='ecard1'&&local==='66'&&name==='tyranitar';
  const targetsTyranitar66=id==='ecard1-66'||(setId==='ecard1'&&local==='66'&&name==='tyranitar');
  if((product===274904&&targetsTyranitar66)||(product===274941&&!exactTyranitar66)){
    return {
      kind:'identity-mismatch',
      source:'Cardmarket · Expedition Tyranitar 066/165 product 274941 verificato',
      reason:product===274904
        ?'Il prodotto 274904 appartiene a Tyranitar Expedition 029/165 Holo e non può valutare 066/165 Rare'
        :'Il prodotto 274941 è consentito solo per Tyranitar ecard1-66 / 066'
    };
  }
  const isTorkoal29=id==='sm12-29'||(setId==='sm12'&&local==='29'&&name==='torkoal');"""
if s.count(marker) != 1:
    raise SystemExit(f'conflict guard marker count={s.count(marker)}')
s = s.replace(marker, tyrguard, 1)
index.write_text(s, encoding='utf-8')

test = Path('scripts/test_card_identity_cardmarket_audit.py')
t = test.read_text(encoding='utf-8')
t = t.replace('It verifies the three exact\nproduction overrides already present in index.html,',
              'It verifies the exact\nproduction overrides already present in index.html,', 1)

old = '    "sm12-54": {"base": 407919, "alternate": 398504, "stamp": "character-rare", "cardmarketCode": "CEC54"},\n}'
new = '    "sm12-54": {"base": 407919, "alternate": 398504, "stamp": "character-rare", "cardmarketCode": "CEC54"},\n    "ecard1-66": {"base": 274941, "alternate": 274904, "stamp": "wrong-holo-number", "cardmarketCode": "EX66"},\n}'
if t.count(old) != 1:
    raise SystemExit(f'confirmed conflict marker count={t.count(old)}')
t = t.replace(old, new, 1)

old = '    "sm12-54": {"setId": "sm12", "localId": "054", "conflictingProduct": 398504, "baseProduct": 407919},\n}'
new = '    "sm12-54": {"setId": "sm12", "localId": "054", "conflictingProduct": 398504, "baseProduct": 407919},\n    "ecard1-66": {"setId": "ecard1", "localId": "066", "conflictingProduct": 274904, "baseProduct": 274941},\n}'
if t.count(old) != 1:
    raise SystemExit(f'expected override marker count={t.count(old)}')
t = t.replace(old, new, 1)

marker = '    harness = r"""\n'
fixture = '''    fixtures["tyranitar"] = {
        "id": "ecard1-66", "tcgdexId": "ecard1-66", "name": "Tyranitar", "localId": "66",
        "set": {"id": "ecard1", "name": "Expedition Base Set"}, "rarity": "Rare",
        "variants": {"normal": True, "holo": False, "reverse": True},
        "variants_detailed": [
            {"type": "normal", "thirdParty": {"cardmarket": 274904}, "pricing": {"cardmarket": {"idProduct": 274904, "trend": 311.31}}},
            {"type": "reverse", "thirdParty": {"cardmarket": 362890}, "pricing": {"cardmarket": {"idProduct": 362890, "trend": 36.28}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 274904, "trend": 311.31, "trend-holo": 136.66}},
    }
    harness = r"""
'''
if t.count(marker) != 1:
    raise SystemExit(f'harness marker count={t.count(marker)}')
t = t.replace(marker, fixture, 1)

marker = "assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...p,name:'Prinplup'}),null);\n"
checks = """assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...p,name:'Prinplup'}),null);
const tyr=fixtures.tyranitar;
const tyrOverride=r.verifiedBaseCardmarketProductOverride(tyr);
assert.strictEqual(tyrOverride?.pricing?.idProduct,274941);
assert.strictEqual(r.resolvedCardmarketPricingForCard(tyr)?.idProduct,274941);
assert.strictEqual(r.knownCardmarketIdentityConflict(tyr,274904)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...tyr,id:'ecard1-29',tcgdexId:'ecard1-29',localId:'29'},274941)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...tyr,localId:'29'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...tyr,name:'Tyranitar ex'}),null);
const tyrNormal=r.cardmarketValueForCardVariant(tyr,'Normal');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:tyrNormal.value,productId:tyrNormal.productId})),{value:10.33,productId:274941});
"""
if t.count(marker) != 1:
    raise SystemExit(f'runtime check marker count={t.count(marker)}')
t = t.replace(marker, checks, 1)

t = t.replace('Base Cardmarket override registry differs from the four audited P0 identities',
              'Base Cardmarket override registry differs from the five audited P0 identities', 1)
t = t.replace('"p0Regression": {"before": 4, "after": len(known_phase_a_p0),',
              '"p0Regression": {"before": 5, "after": len(known_phase_a_p0),', 1)
t = t.replace('"productionChangeScope": "Four exact Cardmarket base-product identity overrides; this phase adds only Piplup",',
              '"productionChangeScope": "Five exact Cardmarket base-product identity overrides; latest addition is Tyranitar ecard1-66",', 1)
test.write_text(t, encoding='utf-8')
