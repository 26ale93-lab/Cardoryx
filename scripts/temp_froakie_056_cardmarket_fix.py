#!/usr/bin/env python3
from pathlib import Path

INDEX = Path('index.html')
AUDIT = Path('scripts/test_card_identity_cardmarket_audit.py')


def replace_once(text, old, new, label):
    if text.count(old) != 1:
        raise SystemExit(f'{label}: expected exactly one anchor, found {text.count(old)}')
    return text.replace(old, new, 1)

idx = INDEX.read_text(encoding='utf-8')

idx = replace_once(
    idx,
    "  'sv03-062':{setId:'sv03',localId:'062',conflictingProduct:727118,baseProduct:725142},\n",
    "  'sv03-062':{setId:'sv03',localId:'062',conflictingProduct:727118,baseProduct:725142},\n"
    "  // Obsidian Flames — Froakie 056. Cardmarket Version 1 is the standard\n"
    "  // Normal/Reverse product; Version 2 is the later Cosmos Holo reprint.\n"
    "  'sv03-056':{setId:'sv03',localId:'056',conflictingProduct:781857,baseProduct:725136},\n",
    'index base override',
)

idx = replace_once(
    idx,
    "  'sv03-062':{\n    setId:'sv03',localId:'062',name:'Palafin',productId:725142,\n",
    "  'sv03-056':{\n"
    "    setId:'sv03',localId:'056',name:'Froakie',productId:725136,\n"
    "    verified:'2026-09-17T01:54:00+0200',\n"
    "    source:'Cardmarket Product Catalogue + Price Guide · Obsidian Flames · Froakie 056 Version 1 base · product 725136',\n"
    "    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',\n"
    "    pricing:{idProduct:725136,trend:0.03,avg7:0.03,avg30:0.04,avg:0.04,low:0.02,\n"
    "      'trend-holo':0.13,'avg7-holo':0.09,'avg30-holo':0.12,'avg-holo':0.13,'low-holo':0.02}\n"
    "  },\n"
    "  'sv03-062':{\n    setId:'sv03',localId:'062',name:'Palafin',productId:725142,\n",
    'index price guide',
)

idx = replace_once(
    idx,
    "  const exactPalafin062=id==='sv03-062'&&setId==='sv03'&&local==='062'&&name==='palafin';\n",
    "  const exactFroakie056=id==='sv03-056'&&setId==='sv03'&&local==='056'&&name==='froakie';\n"
    "  if((product===725136||product===781857)&&!exactFroakie056){\n"
    "    return {kind:'identity-mismatch',source:'Cardmarket · Obsidian Flames Froakie 056 prodotti verificati',\n"
    "      reason:`Il prodotto ${product} è consentito solo per Froakie sv03-056 / 056`};\n"
    "  }\n"
    "  const exactPalafin062=id==='sv03-062'&&setId==='sv03'&&local==='062'&&name==='palafin';\n",
    'index identity guard',
)

froakie_fn = """
function verifiedFroakie056CosmosCardmarketVariant(card,variant){
  const id=String(card?.tcgdexId||card?.id||'').trim().toLowerCase();
  const setId=String(card?._cardoryxSetId||card?.set?.id||'').trim().toLowerCase();
  const local=exactLocalIdKey(card?.localId||'');
  const name=normText(card?.name||'');
  if(id!=='sv03-056'||setId!=='sv03'||local!==exactLocalIdKey('056')||name!=='froakie')return null;
  if(canonicalVariant(variant)!=='Cosmos Holo')return null;
  const exactRow=tcgdexVariantDetails(card).find(row=>{
    const pid=Number(row?.thirdParty?.cardmarket||row?.pricing?.cardmarket?.idProduct||0);
    return pid===781857 && canonicalFinishFoilLabel(row?.foil||'')==='cosmos';
  });
  if(!exactRow)return {handled:true,matched:false,kind:'needs-exact-variant'};
  const pricing={idProduct:781857,trend:0.20,avg7:0.21,avg30:0.25,avg:0.25,low:0.02};
  return {handled:true,matched:true,pricing,productId:781857,
    source:'Cardmarket · Obsidian Flames · Froakie 056 Version 2 Cosmos Holo · prodotto esatto'};
}
"""
idx = replace_once(
    idx,
    "function verifiedGiratinaVstar201CardmarketVariant(card,variant){\n",
    froakie_fn + "function verifiedGiratinaVstar201CardmarketVariant(card,variant){\n",
    'index Froakie exact Cosmos resolver',
)

idx = replace_once(
    idx,
    "function cardmarketValueForCardVariant(card,variant){\n  const giratina=verifiedGiratinaVstar201CardmarketVariant(card,variant);\n",
    "function cardmarketValueForCardVariant(card,variant){\n"
    "  const froakieCosmos=verifiedFroakie056CosmosCardmarketVariant(card,variant);\n"
    "  if(froakieCosmos?.handled){\n"
    "    if(!froakieCosmos.matched)return {value:0,kind:froakieCosmos.kind||'needs-exact-variant'};\n"
    "    const value=Number(froakieCosmos.pricing?.trend||0);\n"
    "    return {value:Number.isFinite(value)&&value>0?value:0,kind:'exact-froakie-056-cosmos',productId:froakieCosmos.productId,source:froakieCosmos.source};\n"
    "  }\n"
    "  const giratina=verifiedGiratinaVstar201CardmarketVariant(card,variant);\n",
    'index Froakie value resolver',
)

idx = replace_once(
    idx,
    "function cardmarketStatsForCardVariant(card,variant){\n  const giratina=verifiedGiratinaVstar201CardmarketVariant(card,variant);\n",
    "function cardmarketStatsForCardVariant(card,variant){\n"
    "  const froakieCosmos=verifiedFroakie056CosmosCardmarketVariant(card,variant);\n"
    "  if(froakieCosmos?.handled){\n"
    "    if(!froakieCosmos.matched)return {low:null,trend:null,avg7:null,avg30:null};\n"
    "    const p=froakieCosmos.pricing||{};\n"
    "    return {low:p.low??null,trend:p.trend??null,avg7:p.avg7??null,avg30:p.avg30??null};\n"
    "  }\n"
    "  const giratina=verifiedGiratinaVstar201CardmarketVariant(card,variant);\n",
    'index Froakie stats resolver',
)

INDEX.write_text(idx, encoding='utf-8')

aud = AUDIT.read_text(encoding='utf-8')

aud = replace_once(
    aud,
    '    "sv03-062": {"base": 725142, "alternate": 727118, "stamp": "pre-release-top-level", "cardmarketCode": "OBF062"},\n',
    '    "sv03-062": {"base": 725142, "alternate": 727118, "stamp": "pre-release-top-level", "cardmarketCode": "OBF062"},\n'
    '    "sv03-056": {"base": 725136, "alternate": 781857, "stamp": "cosmos-reprint-top-level", "cardmarketCode": "OBF056"},\n',
    'audit confirmed conflict',
)

aud = replace_once(
    aud,
    '    "sv03-062": {"setId": "sv03", "localId": "062", "conflictingProduct": 727118, "baseProduct": 725142},\n',
    '    "sv03-062": {"setId": "sv03", "localId": "062", "conflictingProduct": 727118, "baseProduct": 725142},\n'
    '    "sv03-056": {"setId": "sv03", "localId": "056", "conflictingProduct": 781857, "baseProduct": 725136},\n',
    'audit expected override',
)

fixture_anchor = '    fixtures["palafin062"] = {\n'
fro_fixture = '''    fixtures["froakie056"] = {
        "id": "sv03-056", "tcgdexId": "sv03-056", "name": "Froakie", "localId": "056",
        "set": {"id": "sv03", "name": "Obsidian Flames"}, "rarity": "Common", "regulationMark": "G",
        "variants": {"normal": True, "holo": True, "reverse": True},
        "variants_detailed": [
            {"type": "reverse", "thirdParty": {"cardmarket": 725136},
             "pricing": {"cardmarket": {"idProduct": 725136, "trend": 0.03, "avg7": 0.03, "avg30": 0.04, "avg": 0.04, "low": 0.02, "trend-holo": 0.13, "avg7-holo": 0.09, "avg30-holo": 0.12, "avg-holo": 0.13, "low-holo": 0.02}}},
            {"type": "normal", "thirdParty": {"cardmarket": 781857},
             "pricing": {"cardmarket": {"idProduct": 781857, "trend": 0.20, "avg7": 0.21, "avg30": 0.25, "avg": 0.25, "low": 0.02}}},
            {"type": "holo", "foil": "cosmos", "thirdParty": {"cardmarket": 781857},
             "pricing": {"cardmarket": {"idProduct": 781857, "trend": 0.20, "avg7": 0.21, "avg30": 0.25, "avg": 0.25, "low": 0.02}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 781857, "trend": 0.20, "avg7": 0.21, "avg30": 0.25, "avg": 0.25, "low": 0.02}},
    }
'''
aud = replace_once(aud, fixture_anchor, fro_fixture + fixture_anchor, 'audit Froakie fixture')

assert_anchor = 'const pal=fixtures.palafin062;\n'
fro_assert = '''const fro=fixtures.froakie056;
const froOverride=r.verifiedBaseCardmarketProductOverride(fro);
assert.strictEqual(froOverride?.pricing?.idProduct,725136);
assert.strictEqual(r.resolvedCardmarketPricingForCard(fro)?.idProduct,725136);
assert.strictEqual(r.knownCardmarketIdentityConflict(fro,781857),null);
assert.strictEqual(r.knownCardmarketIdentityConflict({...fro,id:'sv03-057',tcgdexId:'sv03-057',localId:'057',name:'Frogadier'},781857)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...fro,id:'sv03-055',tcgdexId:'sv03-055',localId:'055',name:'Buizel'},725136)?.kind,'identity-mismatch');
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...fro,localId:'057'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...fro,name:'Frogadier'}),null);
const froFinishes=[...r.documentedVariantsForCard(fro,'None','')];
assert(froFinishes.includes('Normal'));
assert(froFinishes.includes('Reverse Holo'));
assert(froFinishes.includes('Cosmos Holo'));
const froNormal=r.cardmarketValueForCardVariant(fro,'Normal');
const froReverse=r.cardmarketValueForCardVariant(fro,'Reverse Holo');
const froCosmos=r.cardmarketValueForCardVariant(fro,'Cosmos Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:froNormal.value,productId:froNormal.productId})),{value:0.03,productId:725136});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:froReverse.value,productId:froReverse.productId})),{value:0.13,productId:725136});
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:froCosmos.value,productId:froCosmos.productId,kind:froCosmos.kind})),{value:0.2,productId:781857,kind:'exact-froakie-056-cosmos'});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(fro,'Normal'))),{low:0.02,trend:0.03,avg7:0.03,avg30:0.04});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(fro,'Reverse Holo'))),{low:0.02,trend:0.13,avg7:0.09,avg30:0.12});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(fro,'Cosmos Holo'))),{low:0.02,trend:0.2,avg7:0.21,avg30:0.25});
const froNoCosmosRow={...fro,variants_detailed:fro.variants_detailed.filter(x=>canonicalFinishFoilLabel(x.foil||'')!=='cosmos')};
const froFailClosed=r.cardmarketValueForCardVariant(froNoCosmosRow,'Cosmos Holo');
assert.strictEqual(froFailClosed.value,0);
assert.strictEqual(froFailClosed.kind,'needs-exact-variant');
'''
aud = replace_once(aud, assert_anchor, fro_assert + assert_anchor, 'audit Froakie assertions')

AUDIT.write_text(aud, encoding='utf-8')
print('Applied exact Froakie sv03-056 Cardmarket patch')
