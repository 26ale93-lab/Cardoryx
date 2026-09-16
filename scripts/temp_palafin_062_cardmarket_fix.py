#!/usr/bin/env python3
from pathlib import Path

INDEX=Path('index.html')
AUDIT=Path('scripts/test_card_identity_cardmarket_audit.py')
idx=INDEX.read_text(encoding='utf-8')
aud=AUDIT.read_text(encoding='utf-8')

def rep(text, old, new, label):
    if old not in text:
        raise SystemExit(f'missing anchor: {label}')
    return text.replace(old,new,1)

# 1) Exact standard/base product: top-level is the legitimate Pre-release product,
# but it must not value the unstamped Holo/Reverse printing.
idx=rep(idx,
"  'swsh11-201':{setId:'swsh11',localId:'201',conflictingProduct:670816,baseProduct:674207},\n",
"  'swsh11-201':{setId:'swsh11',localId:'201',conflictingProduct:670816,baseProduct:674207},\n  // Obsidian Flames — Palafin 062. TCGdex exposes the legitimate Pre-release\n  // product 727118 at top level; the unstamped Holo/Reverse base product is 725142.\n  // Pre-release remains a separate exact stamped printing below.\n  'sv03-062':{setId:'sv03',localId:'062',conflictingProduct:727118,baseProduct:725142},\n",
'base override')

# 2) Exact base guide, used only for the exact identity and product.
idx=rep(idx,
"\n};\nfunction exactCardmarketGuideIdentity(card,id,guide){",
"\n  'sv03-062':{\n    setId:'sv03',localId:'062',name:'Palafin',productId:725142,\n    verified:'2026-09-17T00:47:03+0200',\n    source:'Cardmarket Product Catalogue + Price Guide · Obsidian Flames · Palafin 062 base · product 725142',\n    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',\n    pricing:{idProduct:725142,trend:0.02,avg7:0.05,avg30:0.06,avg:0.06,low:0.02,\n      'trend-holo':0.16,'avg7-holo':0.18,'avg30-holo':0.25,'avg-holo':0.24,'low-holo':0.02}\n  },\n};\nfunction exactCardmarketGuideIdentity(card,id,guide){",
'base guide')

# 3) Palafin Pre-release is a valid separate physical edition, Normal finish.
idx=rep(idx,
"  'sv05-051':{\n    setId:'sv05',localId:'051',name:'Pikachu',stamp:'Pokémon Day',\n    finishes:['Holo'],source:'TCGdex variants_detailed · pokemon-day · type holo · Cardmarket product 870424',\n    verified:'2026-09-11'\n  }\n};\nfunction verifiedSpecialStampFinishes",
"  'sv05-051':{\n    setId:'sv05',localId:'051',name:'Pikachu',stamp:'Pokémon Day',\n    finishes:['Holo'],source:'TCGdex variants_detailed · pokemon-day · type holo · Cardmarket product 870424',\n    verified:'2026-09-11'\n  },\n  'sv03-062':{\n    setId:'sv03',localId:'062',name:'Palafin',stamp:'Pre-release',\n    finishes:['Normal'],source:'TCGdex variants_detailed · pre-release · type normal · Cardmarket product 727118',\n    verified:'2026-09-17'\n  }\n};\nfunction verifiedSpecialStampFinishes",
'pre-release finish')

idx=rep(idx,
"  'sv05-051':{\n    setId:'sv05',localId:'051',name:'Pikachu',finish:'Holo',stamp:'Pokémon Day',productId:870424,\n    trend:3.88,avg7:2.89,avg30:3.57,avg1:2.79,\n    source:'Cardmarket · Pikachu V3 TEF051 · Pokémon Day · product 870424',\n    sourceUrl:'https://www.cardmarket.com/it/Pokemon/Products/Singles/Temporal-Forces/Pikachu-V3-TEF051',\n    verified:'2026-09-11'\n  }\n};\nfunction verifiedExactSpecialStampPrice",
"  'sv05-051':{\n    setId:'sv05',localId:'051',name:'Pikachu',finish:'Holo',stamp:'Pokémon Day',productId:870424,\n    trend:3.88,avg7:2.89,avg30:3.57,avg1:2.79,\n    source:'Cardmarket · Pikachu V3 TEF051 · Pokémon Day · product 870424',\n    sourceUrl:'https://www.cardmarket.com/it/Pokemon/Products/Singles/Temporal-Forces/Pikachu-V3-TEF051',\n    verified:'2026-09-11'\n  },\n  'sv03-062':{\n    setId:'sv03',localId:'062',name:'Palafin',finish:'Normal',stamp:'Pre-release',productId:727118,\n    low:0.02,trend:0.26,avg7:0.23,avg30:0.18,avg:0.16,\n    source:'Cardmarket Product Catalogue + Price Guide · Obsidian Flames · Palafin 062 Pre-release · product 727118',\n    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',\n    verified:'2026-09-17'\n  }\n};\nfunction verifiedExactSpecialStampPrice",
'pre-release price')

# 4) The TCGdex Cosmos row points to Frogadier 781858. Remove that one row only
# from Palafin's finish evidence; no generic Cosmos rule.
idx=rep(idx,
"  const d=tcgdexVariantDetails(card);\n  const it=d.filter(x=>!Array.isArray(x?.languages)||x.languages.includes('it'));\n  const pool=it.length?it:d;\n  const isPlayRow=x=>{",
"  const d=tcgdexVariantDetails(card);\n  const it=d.filter(x=>!Array.isArray(x?.languages)||x.languages.includes('it'));\n  const rawPool=it.length?it:d;\n  const exactPalafin062=String(card?.tcgdexId||card?.id||'').trim().toLowerCase()==='sv03-062' &&\n    cardSetId(card)==='sv03' && exactLocalIdKey(card?.localId||'')===exactLocalIdKey('062') && normText(card?.name||'')==='palafin';\n  const pool=exactPalafin062\n    ? rawPool.filter(x=>Number(x?.thirdParty?.cardmarket||0)!==781858)\n    : rawPool;\n  const isPlayRow=x=>{",
'Palafin finish filter')

# 5) Identity guards: preserve 727118 for exact Palafin, reject Frogadier product
# only when it is incorrectly attached to Palafin, and scope the base product.
idx=rep(idx,
"  const exactGiratinaVstar201=id==='swsh11-201'&&setId==='swsh11'&&local==='201'&&name==='giratinavstar';",
"  const exactPalafin062=id==='sv03-062'&&setId==='sv03'&&local==='062'&&name==='palafin';\n  const targetsPalafin062=id==='sv03-062'||(setId==='sv03'&&local==='062'&&name==='palafin');\n  if((product===781858&&targetsPalafin062)||((product===725142||product===727118)&&!exactPalafin062)){\n    return {\n      kind:'identity-mismatch',\n      source:'Cardmarket · Obsidian Flames Palafin 062 prodotti verificati',\n      reason:product===781858\n        ?'Il prodotto 781858 appartiene a Frogadier [Strafe] e non può valutare Palafin 062'\n        :`Il prodotto ${product} è consentito solo per Palafin sv03-062 / 062`\n    };\n  }\n  const exactGiratinaVstar201=id==='swsh11-201'&&setId==='swsh11'&&local==='201'&&name==='giratinavstar';",
'identity guards')

# Audit registries.
aud=rep(aud,
'    "swsh11-201": {"base": 674207, "alternate": 670816, "stamp": "wrong-card-identity", "cardmarketCode": "LOR201"},\n',
'    "swsh11-201": {"base": 674207, "alternate": 670816, "stamp": "wrong-card-identity", "cardmarketCode": "LOR201"},\n    "sv03-062": {"base": 725142, "alternate": 727118, "stamp": "pre-release-top-level", "cardmarketCode": "OBF062"},\n',
'audit confirmed conflict')
aud=rep(aud,
'    "swsh11-201": {"setId": "swsh11", "localId": "201", "conflictingProduct": 670816, "baseProduct": 674207},\n',
'    "swsh11-201": {"setId": "swsh11", "localId": "201", "conflictingProduct": 670816, "baseProduct": 674207},\n    "sv03-062": {"setId": "sv03", "localId": "062", "conflictingProduct": 727118, "baseProduct": 725142},\n',
'audit expected override')

# Runtime fixture mirrors the live evidence exactly.
aud=rep(aud,
'    fixtures["metagross"] = {\n',
'''    fixtures["palafin062"] = {
        "id": "sv03-062", "tcgdexId": "sv03-062", "name": "Palafin", "localId": "062",
        "set": {"id": "sv03", "name": "Obsidian Flames"}, "rarity": "Rare", "regulationMark": "G",
        "variants": {"normal": True, "holo": True, "reverse": True},
        "variants_detailed": [
            {"type": "normal", "stamp": ["pre-release"], "thirdParty": {"cardmarket": 727118},
             "pricing": {"cardmarket": {"idProduct": 727118, "trend": 0.26, "avg7": 0.23, "avg30": 0.18, "avg": 0.16, "low": 0.02}}},
            {"type": "holo", "thirdParty": {"cardmarket": 725142},
             "pricing": {"cardmarket": {"idProduct": 725142, "trend": 0.02, "avg7": 0.05, "avg30": 0.06, "avg": 0.06, "low": 0.02, "trend-holo": 0.16, "avg7-holo": 0.18, "avg30-holo": 0.25, "avg-holo": 0.24, "low-holo": 0.02}}},
            {"type": "holo", "foil": "cosmos", "thirdParty": {"cardmarket": 781858},
             "pricing": {"cardmarket": {"idProduct": 781858, "trend": 0.22}}},
            {"type": "reverse", "thirdParty": {"cardmarket": 725142},
             "pricing": {"cardmarket": {"idProduct": 725142, "trend": 0.02, "trend-holo": 0.16}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 727118, "trend": 0.26, "avg7": 0.23, "avg30": 0.18, "avg": 0.16, "low": 0.02}},
    }
    fixtures["metagross"] = {
''',
'Palafin fixture')

# Expose documented finishes to the regression harness only.
aud=rep(aud,
'  verifiedVariantPrice,verifiedStampPrice,renderScanValue,cardPriceInfo,\n',
'  verifiedVariantPrice,verifiedStampPrice,documentedVariantsForCard,renderScanValue,cardPriceInfo,\n',
'export documentedVariants')

# Add Palafin runtime assertions before the existing Metagross block.
aud=rep(aud,
'const met=fixtures.metagross;\n',
'''const pal=fixtures.palafin062;
const palOverride=r.verifiedBaseCardmarketProductOverride(pal);
assert.strictEqual(palOverride?.pricing?.idProduct,725142);
assert.strictEqual(r.resolvedCardmarketPricingForCard(pal)?.idProduct,725142);
assert.strictEqual(r.knownCardmarketIdentityConflict(pal,781858)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...pal,id:'sv03-057',tcgdexId:'sv03-057',localId:'057',name:'Frogadier'},781858),null);
assert.strictEqual(r.knownCardmarketIdentityConflict({...pal,id:'other-1',tcgdexId:'other-1',localId:'1',name:'Other',set:{id:'other'}},725142)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...pal,localId:'063'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...pal,name:'Finizen'}),null);
const palBaseFinishes=[...r.documentedVariantsForCard(pal,'None','')];
assert(palBaseFinishes.includes('Holo'));
assert(palBaseFinishes.includes('Reverse Holo'));
assert(!palBaseFinishes.includes('Normal'));
assert(!palBaseFinishes.includes('Cosmos Holo'));
const palPreFinishes=[...r.documentedVariantsForCard(pal,'Pre-release','')];
assert(palPreFinishes.includes('Normal'));
const palHolo=r.cardmarketValueForCardVariant(pal,'Holo');
const palReverse=r.cardmarketValueForCardVariant(pal,'Reverse Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:palHolo.value,productId:palHolo.productId})),{value:0.02,productId:725142});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:palReverse.value,productId:palReverse.productId})),{value:0.16,productId:725142});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(pal,'Holo'))),{low:0.02,trend:0.02,avg7:0.05,avg30:0.06});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(pal,'Reverse Holo'))),{low:0.02,trend:0.16,avg7:0.18,avg30:0.25});
const palPre=r.verifiedStampPrice(pal,'Normal','Pre-release');
assert.strictEqual(palPre?.productId,727118);
assert.strictEqual(palPre?.trend,0.26);
assert.strictEqual(r.verifiedStampPrice(pal,'Holo','Pre-release'),null);
assert.strictEqual(r.verifiedStampPrice(pal,'Normal','None'),null);
const palSaved={...pal,pricing:r.pricingWithResolvedCardmarket(pal),variant:'Normal',stamp:'Pre-release',_cardoryxSetId:'sv03'};
assert.strictEqual(palSaved.pricing.cardmarket.idProduct,725142);
assert.strictEqual(r.cardPriceInfo(palSaved).value,0.26);
const met=fixtures.metagross;
''',
'Palafin assertions')

INDEX.write_text(idx,encoding='utf-8')
AUDIT.write_text(aud,encoding='utf-8')
print('Applied exact Palafin sv03-062 Cardmarket patch')
