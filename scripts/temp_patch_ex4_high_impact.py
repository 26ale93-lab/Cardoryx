from pathlib import Path

index = Path('index.html')
s = index.read_text(encoding='utf-8')

old = "  'pl3-7':{setId:'pl3',localId:'007',conflictingProduct:278689,baseProduct:278698}\n};"
new = """  'pl3-7':{setId:'pl3',localId:'007',conflictingProduct:278689,baseProduct:278698},
  // EX Team Magma vs Team Aqua — exact western expansion 1542 identities.
  // Each entry blocks only the proven wrong product currently exposed upstream.
  'ex4-6':{setId:'ex4',localId:'006',conflictingProduct:275783,baseProduct:275983},
  'ex4-7':{setId:'ex4',localId:'007',conflictingProduct:275784,baseProduct:275984},
  'ex4-89':{setId:'ex4',localId:'089',conflictingProduct:275866,baseProduct:276066},
  'ex4-94':{setId:'ex4',localId:'094',conflictingProduct:275871,baseProduct:276071},
  'ex4-95':{setId:'ex4',localId:'095',conflictingProduct:275872,baseProduct:276072}
};"""
if s.count(old) != 1:
    raise SystemExit(f'override marker count={s.count(old)}')
s = s.replace(old, new, 1)

marker = "  }\n};\nfunction exactCardmarketGuideIdentity(card,id,guide){"
insert = """  },
  'ex4-6':{
    setId:'ex4',localId:'006',name:\"Team Aqua's Walrein\",productId:275983,
    verified:'2026-09-16T12:24:34+0200',
    source:\"Cardmarket Product Catalogue + Price Guide · EX Team Magma vs Team Aqua · Team Aqua's Walrein · product 275983\",
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:275983,trend:4.40,avg7:3.52,avg30:4.08,avg:4.24,low:0.25,
      'trend-holo':5.88,'avg7-holo':7.05,'avg30-holo':8.13,'avg-holo':7.58,'low-holo':1.29}
  },
  'ex4-7':{
    setId:'ex4',localId:'007',name:\"Team Magma's Aggron\",productId:275984,
    verified:'2026-09-16T12:24:34+0200',
    source:\"Cardmarket Product Catalogue + Price Guide · EX Team Magma vs Team Aqua · Team Magma's Aggron · product 275984\",
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:275984,trend:5.80,avg7:8.52,avg30:11.81,avg:8.21,low:0.90,
      'trend-holo':10.47,'avg7-holo':10.36,'avg30-holo':6.56,'avg-holo':10.00,'low-holo':1.00}
  },
  'ex4-89':{
    setId:'ex4',localId:'089',name:'Blaziken ex',productId:276066,
    verified:'2026-09-16T12:24:34+0200',
    source:'Cardmarket Product Catalogue + Price Guide · EX Team Magma vs Team Aqua · Blaziken ex · product 276066',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:276066,trend:136.64,avg7:169.37,avg30:95.88,avg:167.50,low:18.90,
      'trend-holo':18.88,'avg7-holo':13.73,'avg30-holo':17.73,'avg-holo':null,'low-holo':null}
  },
  'ex4-94':{
    setId:'ex4',localId:'094',name:'Suicune ex',productId:276071,
    verified:'2026-09-16T12:24:34+0200',
    source:'Cardmarket Product Catalogue + Price Guide · EX Team Magma vs Team Aqua · Suicune ex · product 276071',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:276071,trend:714.52,avg7:723.00,avg30:343.07,avg:712.00,low:48.00,
      'trend-holo':26.84,'avg7-holo':32.85,'avg30-holo':26.66,'avg-holo':null,'low-holo':null}
  },
  'ex4-95':{
    setId:'ex4',localId:'095',name:'Swampert ex',productId:276072,
    verified:'2026-09-16T12:24:34+0200',
    source:'Cardmarket Product Catalogue + Price Guide · EX Team Magma vs Team Aqua · Swampert ex · product 276072',
    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',
    pricing:{idProduct:276072,trend:93.11,avg7:73.99,avg30:87.54,avg:81.73,low:19.00,
      'trend-holo':21.20,'avg7-holo':16.54,'avg30-holo':16.25,'avg-holo':null,'low-holo':null}
  }
};
function exactCardmarketGuideIdentity(card,id,guide){"""
if s.count(marker) != 1:
    raise SystemExit(f'guide marker count={s.count(marker)}')
s = s.replace(marker, insert, 1)

marker = "  const isTorkoal29=id==='sm12-29'||(setId==='sm12'&&local==='29'&&name==='torkoal');"
guards = """  const ex4ExactConflicts=[
    ['ex4-6','6','teamaquaswalrein',275783,275983],
    ['ex4-7','7','teammagmasaggron',275784,275984],
    ['ex4-89','89','blazikenex',275866,276066],
    ['ex4-94','94','suicuneex',275871,276071],
    ['ex4-95','95','swampertex',275872,276072]
  ];
  for(const [exactId,exactLocal,exactName,wrongProduct,correctProduct] of ex4ExactConflicts){
    const guide=VERIFIED_EXACT_CARDMARKET_PRICE_GUIDES[exactId];
    const exactIdentity=exactCardmarketGuideIdentity(card,exactId,guide);
    const targets=id===exactId||(setId==='ex4'&&local===exactLocal&&name===exactName);
    if((product===wrongProduct&&targets)||(product===correctProduct&&!exactIdentity)){
      return {
        kind:'identity-mismatch',
        source:`Cardmarket · EX Team Magma vs Team Aqua ${exactId} product ${correctProduct} verificato`,
        reason:product===wrongProduct
          ?`Il prodotto ${wrongProduct} appartiene a una carta diversa e non può valutare ${exactId}`
          :`Il prodotto ${correctProduct} è consentito solo per l'identità esatta ${exactId}`
      };
    }
  }
  const isTorkoal29=id==='sm12-29'||(setId==='sm12'&&local==='29'&&name==='torkoal');"""
if s.count(marker) != 1:
    raise SystemExit(f'guard marker count={s.count(marker)}')
s = s.replace(marker, guards, 1)
index.write_text(s, encoding='utf-8')

test = Path('scripts/test_card_identity_cardmarket_audit.py')
t = test.read_text(encoding='utf-8')

old = '    "pl3-7": {"base": 278698, "alternate": 278689, "stamp": "wrong-card-identity", "cardmarketCode": "SV7"},\n}'
new = '''    "pl3-7": {"base": 278698, "alternate": 278689, "stamp": "wrong-card-identity", "cardmarketCode": "SV7"},
    "ex4-6": {"base": 275983, "alternate": 275783, "stamp": "wrong-card-identity", "cardmarketCode": "MA6"},
    "ex4-7": {"base": 275984, "alternate": 275784, "stamp": "wrong-card-identity", "cardmarketCode": "MA7"},
    "ex4-89": {"base": 276066, "alternate": 275866, "stamp": "wrong-card-identity", "cardmarketCode": "MA89"},
    "ex4-94": {"base": 276071, "alternate": 275871, "stamp": "wrong-card-identity", "cardmarketCode": "MA94"},
    "ex4-95": {"base": 276072, "alternate": 275872, "stamp": "wrong-card-identity", "cardmarketCode": "MA95"},
}'''
if t.count(old) != 1:
    raise SystemExit(f'confirmed conflict marker count={t.count(old)}')
t = t.replace(old, new, 1)

old = '    "pl3-7": {"setId": "pl3", "localId": "007", "conflictingProduct": 278689, "baseProduct": 278698},\n}'
new = '''    "pl3-7": {"setId": "pl3", "localId": "007", "conflictingProduct": 278689, "baseProduct": 278698},
    "ex4-6": {"setId": "ex4", "localId": "006", "conflictingProduct": 275783, "baseProduct": 275983},
    "ex4-7": {"setId": "ex4", "localId": "007", "conflictingProduct": 275784, "baseProduct": 275984},
    "ex4-89": {"setId": "ex4", "localId": "089", "conflictingProduct": 275866, "baseProduct": 276066},
    "ex4-94": {"setId": "ex4", "localId": "094", "conflictingProduct": 275871, "baseProduct": 276071},
    "ex4-95": {"setId": "ex4", "localId": "095", "conflictingProduct": 275872, "baseProduct": 276072},
}'''
if t.count(old) != 1:
    raise SystemExit(f'expected override marker count={t.count(old)}')
t = t.replace(old, new, 1)

marker = '    harness = r"""\n'
fixture = '''    fixtures["ex4_high_impact"] = [
        {"id":"ex4-6","tcgdexId":"ex4-6","name":"Team Aqua's Walrein","localId":"6","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Holo Rare","wrong":275783,"correct":275983,"expected":4.40},
        {"id":"ex4-7","tcgdexId":"ex4-7","name":"Team Magma's Aggron","localId":"7","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Holo Rare","wrong":275784,"correct":275984,"expected":5.80},
        {"id":"ex4-89","tcgdexId":"ex4-89","name":"Blaziken ex","localId":"89","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Rare","wrong":275866,"correct":276066,"expected":136.64},
        {"id":"ex4-94","tcgdexId":"ex4-94","name":"Suicune ex","localId":"94","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Rare","wrong":275871,"correct":276071,"expected":714.52},
        {"id":"ex4-95","tcgdexId":"ex4-95","name":"Swampert ex","localId":"95","set":{"id":"ex4","name":"EX Team Magma vs Team Aqua"},"rarity":"Rare","wrong":275872,"correct":276072,"expected":93.11},
    ]
    for card in fixtures["ex4_high_impact"]:
        card["variants"] = {"normal": False, "holo": True, "reverse": False}
        card["variants_detailed"] = [{"type":"holo","thirdParty":{"cardmarket":card["wrong"]},"pricing":{"cardmarket":{"idProduct":card["wrong"],"trend":1}}}]
        card["pricing"] = {"cardmarket":{"idProduct":card["wrong"],"trend":1}}
    harness = r"""
'''
if t.count(marker) != 1:
    raise SystemExit(f'harness marker count={t.count(marker)}')
t = t.replace(marker, fixture, 1)

marker = "const normal=r.cardmarketValueForCardVariant(p,'Normal');\n"
checks = """for(const card of fixtures.ex4_high_impact){
  const o=r.verifiedBaseCardmarketProductOverride(card);
  assert.strictEqual(o?.pricing?.idProduct,card.correct);
  assert.strictEqual(r.resolvedCardmarketPricingForCard(card)?.idProduct,card.correct);
  assert.strictEqual(r.knownCardmarketIdentityConflict(card,card.wrong)?.kind,'identity-mismatch');
  assert.strictEqual(r.knownCardmarketIdentityConflict({...card,id:card.id+'x',tcgdexId:card.tcgdexId+'x',localId:'999'},card.correct)?.kind,'identity-mismatch');
  assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...card,name:card.name+' wrong'}),null);
  const value=r.cardmarketValueForCardVariant(card,'Holo');
  assert.deepStrictEqual(JSON.parse(JSON.stringify({value:value.value,productId:value.productId})),{value:card.expected,productId:card.correct});
}
const normal=r.cardmarketValueForCardVariant(p,'Normal');
"""
if t.count(marker) != 1:
    raise SystemExit(f'runtime marker count={t.count(marker)}')
t = t.replace(marker, checks, 1)

t = t.replace('Base Cardmarket override registry differs from the six audited P0 identities',
              'Base Cardmarket override registry differs from the eleven audited P0 identities', 1)
t = t.replace('"p0Regression": {"before": 6, "after": len(known_phase_a_p0),',
              '"p0Regression": {"before": 11, "after": len(known_phase_a_p0),', 1)
t = t.replace('"productionChangeScope": "Six exact Cardmarket base-product identity overrides; latest addition is Metagross pl3-7",',
              '"productionChangeScope": "Eleven exact Cardmarket base-product identity overrides; latest block adds five exact EX Team Magma vs Team Aqua identities",', 1)

test.write_text(t, encoding='utf-8')
