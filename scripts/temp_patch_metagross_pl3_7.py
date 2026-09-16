from pathlib import Path

index=Path('index.html')
s=index.read_text(encoding='utf-8')

old="  'ecard1-66':{setId:'ecard1',localId:'066',conflictingProduct:274904,baseProduct:274941}\n};"
new="  'ecard1-66':{setId:'ecard1',localId:'066',conflictingProduct:274904,baseProduct:274941},\n  // Supreme Victors — TCGdex currently points Metagross 7/147 at Milotic\n  // product 278689. Cardmarket catalogue proves product 278698 is Metagross.\n  'pl3-7':{setId:'pl3',localId:'007',conflictingProduct:278689,baseProduct:278698}\n};"
if s.count(old)!=1:
    raise SystemExit(f'override marker count={s.count(old)}')
s=s.replace(old,new,1)

marker="  }\n};\nfunction exactCardmarketGuideIdentity(card,id,guide){"
insert="""  },
  'pl3-7':{
    setId:'pl3',localId:'007',name:'Metagross',productId:278698,
    verified:'2026-09-16T12:13:02+0200',
    source:'Cardmarket Product Catalogue + Price Guide · Supreme Victors · Metagross Lv.68 · product 278698',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:278698,trend:3.05,avg7:4.10,avg30:3.47,avg:3.55,low:0.45,
      'trend-holo':3.24,'avg7-holo':3.40,'avg30-holo':2.63,'avg-holo':3.40,'low-holo':0.45}
  }
};
function exactCardmarketGuideIdentity(card,id,guide){"""
if s.count(marker)!=1:
    raise SystemExit(f'guide marker count={s.count(marker)}')
s=s.replace(marker,insert,1)

marker="  const isTorkoal29=id==='sm12-29'||(setId==='sm12'&&local==='29'&&name==='torkoal');"
guard="""  const exactMetagrossPl3_7=id==='pl3-7'&&setId==='pl3'&&local==='7'&&name==='metagross';
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
  const isTorkoal29=id==='sm12-29'||(setId==='sm12'&&local==='29'&&name==='torkoal');"""
if s.count(marker)!=1:
    raise SystemExit(f'guard marker count={s.count(marker)}')
s=s.replace(marker,guard,1)
index.write_text(s,encoding='utf-8')

test=Path('scripts/test_card_identity_cardmarket_audit.py')
t=test.read_text(encoding='utf-8')

old='    "ecard1-66": {"base": 274941, "alternate": 274904, "stamp": "wrong-holo-number", "cardmarketCode": "EX66"},\n}'
new='    "ecard1-66": {"base": 274941, "alternate": 274904, "stamp": "wrong-holo-number", "cardmarketCode": "EX66"},\n    "pl3-7": {"base": 278698, "alternate": 278689, "stamp": "wrong-card-identity", "cardmarketCode": "SV7"},\n}'
if t.count(old)!=1:
    raise SystemExit(f'confirmed conflict marker count={t.count(old)}')
t=t.replace(old,new,1)

old='    "ecard1-66": {"setId": "ecard1", "localId": "066", "conflictingProduct": 274904, "baseProduct": 274941},\n}'
new='    "ecard1-66": {"setId": "ecard1", "localId": "066", "conflictingProduct": 274904, "baseProduct": 274941},\n    "pl3-7": {"setId": "pl3", "localId": "007", "conflictingProduct": 278689, "baseProduct": 278698},\n}'
if t.count(old)!=1:
    raise SystemExit(f'expected override marker count={t.count(old)}')
t=t.replace(old,new,1)

marker='    harness = r"""\n'
fixture='''    fixtures["metagross"] = {
        "id": "pl3-7", "tcgdexId": "pl3-7", "name": "Metagross", "localId": "7",
        "set": {"id": "pl3", "name": "Supreme Victors"}, "rarity": "Rare Holo",
        "variants": {"normal": False, "holo": True, "reverse": True},
        "variants_detailed": [
            {"type": "holo", "thirdParty": {"cardmarket": 278689}, "pricing": {"cardmarket": {"idProduct": 278689, "trend": 40.68, "trend-holo": 62.71}}},
            {"type": "reverse", "thirdParty": {"cardmarket": 278698}, "pricing": {"cardmarket": {"idProduct": 278698, "trend": 3.05, "trend-holo": 3.24}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 278689, "trend": 40.68, "trend-holo": 62.71}},
    }
    harness = r"""
'''
if t.count(marker)!=1:
    raise SystemExit(f'harness marker count={t.count(marker)}')
t=t.replace(marker,fixture,1)

marker="const normal=r.cardmarketValueForCardVariant(p,'Normal');\n"
checks="""const met=fixtures.metagross;
const metOverride=r.verifiedBaseCardmarketProductOverride(met);
assert.strictEqual(metOverride?.pricing?.idProduct,278698);
assert.strictEqual(r.resolvedCardmarketPricingForCard(met)?.idProduct,278698);
assert.strictEqual(r.knownCardmarketIdentityConflict(met,278689)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...met,id:'pl3-8',tcgdexId:'pl3-8',localId:'8'},278698)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...met,localId:'8'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...met,name:'Milotic'}),null);
const metHolo=r.cardmarketValueForCardVariant(met,'Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:metHolo.value,productId:metHolo.productId})),{value:3.05,productId:278698});
const normal=r.cardmarketValueForCardVariant(p,'Normal');
"""
if t.count(marker)!=1:
    raise SystemExit(f'runtime marker count={t.count(marker)}')
t=t.replace(marker,checks,1)

t=t.replace('Base Cardmarket override registry differs from the five audited P0 identities',
            'Base Cardmarket override registry differs from the six audited P0 identities',1)
t=t.replace('"p0Regression": {"before": 5, "after": len(known_phase_a_p0),',
            '"p0Regression": {"before": 6, "after": len(known_phase_a_p0),',1)
t=t.replace('"productionChangeScope": "Five exact Cardmarket base-product identity overrides; latest addition is Tyranitar ecard1-66",',
            '"productionChangeScope": "Six exact Cardmarket base-product identity overrides; latest addition is Metagross pl3-7",',1)

test.write_text(t,encoding='utf-8')
