#!/usr/bin/env python3
from pathlib import Path

INDEX = Path('index.html')
AUDIT = Path('scripts/test_card_identity_cardmarket_audit.py')

index = INDEX.read_text(encoding='utf-8')
audit = AUDIT.read_text(encoding='utf-8')


def once(text, old, new, label):
    if old not in text:
        raise SystemExit(f'missing anchor: {label}')
    if text.count(old) != 1:
        raise SystemExit(f'non-unique anchor {label}: {text.count(old)}')
    return text.replace(old, new, 1)


def append_registry(text, marker, entry, label):
    start = text.find(marker)
    if start < 0:
        raise SystemExit(f'missing registry {label}')
    end = text.find('\n};', start)
    if end < 0:
        raise SystemExit(f'unclosed registry {label}')
    body = text[start:end]
    if entry.split(':', 1)[0].strip() in body:
        raise SystemExit(f'entry already exists in {label}')
    return text[:end] + ',\n' + entry + text[end:]

# Production exact base override.
index = once(
    index,
    "  'sv10.5b-065':{setId:'sv10.5b',localId:'065',conflictingProduct:836009,baseProduct:836043},",
    "  'sv10.5b-065':{setId:'sv10.5b',localId:'065',conflictingProduct:836009,baseProduct:836043},\n"
    "  // Lost Origin / Origine Perduta — Giratina VSTAR 201/196 Rainbow.\n"
    "  // TCGdex currently points this exact card at Cardmarket 670816, which is Giratina V.\n"
    "  // Cardmarket product 674207 is Giratina VSTAR LOR201.\n"
    "  'swsh11-201':{setId:'swsh11',localId:'201',conflictingProduct:670816,baseProduct:674207},",
    'production base override',
)

# Exact official Cardmarket guide row. Standard trend fields belong to the exact LOR201 product;
# *-holo fields are not used because Cardmarket models this Rainbow printing as its own product.
index = append_registry(
    index,
    'const VERIFIED_EXACT_CARDMARKET_PRICE_GUIDES = {',
    "  'swsh11-201':{\n"
    "    setId:'swsh11',localId:'201',name:'Giratina VSTAR',productId:674207,\n"
    "    verified:'2026-09-17T00:34:29+0200',\n"
    "    source:'Cardmarket Product Catalogue + Price Guide · Lost Origin · Giratina VSTAR 201 · product 674207',\n"
    "    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',\n"
    "    pricing:{idProduct:674207,trend:20.65,avg7:20.82,avg30:19.59,avg:19.03,low:9.90}\n"
    "  }",
    'verified price guides',
)

# Exact conflict guard: 670816 stays valid everywhere else, including swsh11-130 Giratina V.
guard = """  const exactGiratinaVstar201=id==='swsh11-201'&&setId==='swsh11'&&local==='201'&&name==='giratinavstar';
  const targetsGiratinaVstar201=id==='swsh11-201'||(setId==='swsh11'&&local==='201'&&name==='giratinavstar');
  if((product===670816&&targetsGiratinaVstar201)||(product===674207&&!exactGiratinaVstar201)){
    return {
      kind:'identity-mismatch',
      source:'Cardmarket · Lost Origin Giratina VSTAR 201 product 674207 verificato',
      reason:product===670816
        ?'Il prodotto 670816 appartiene a Giratina V [Abyss Seeking | Shred] e non può valutare Giratina VSTAR 201'
        :'Il prodotto 674207 è consentito solo per Giratina VSTAR swsh11-201 / 201'
    };
  }
"""
index = once(index, '  const ex4ExactConflicts=[', guard + '  const ex4ExactConflicts=[', 'Giratina conflict guard')

# Exact Rainbow runtime resolver. It activates only while the upstream row is exactly the known
# contaminated Holo+Rainbow row pointing at Giratina V product 670816.
handler = """function verifiedGiratinaVstar201CardmarketVariant(card,variant){
  const id=String(card?.tcgdexId||card?.id||'').trim().toLowerCase();
  const setId=String(card?._cardoryxSetId||card?.set?.id||'').trim().toLowerCase();
  const local=exactLocalIdKey(card?.localId||'');
  const name=normText(card?.name||'');
  if(id!=='swsh11-201'||setId!=='swsh11'||local!=='201'||name!=='giratinavstar')return null;
  const rows=tcgdexVariantDetails(card).filter(row=>
    canonicalFinishTypeLabel(row?.type)==='holo'&&canonicalFinishFoilLabel(row?.foil)==='rainbow'&&!row?.stamp?.length
  );
  if(rows.length!==1||Number(rows[0]?.thirdParty?.cardmarket||0)!==670816){
    return {handled:true,matched:false,kind:'needs-exact-variant'};
  }
  if(canonicalVariant(variant||'')!=='Holo')return {handled:true,matched:false,kind:'needs-exact-variant'};
  const guide=VERIFIED_EXACT_CARDMARKET_PRICE_GUIDES['swsh11-201'];
  if(!guide||Number(guide.productId)!==674207)return {handled:true,matched:false,kind:'needs-exact-variant'};
  return {handled:true,matched:true,pricing:guide.pricing,productId:674207,
    source:'Cardmarket · Lost Origin · Giratina VSTAR 201 Rainbow · prodotto esatto'};
}
"""
index = once(index, 'function cardmarketValueForCardVariant(card,variant){', handler + 'function cardmarketValueForCardVariant(card,variant){', 'Giratina runtime handler')
index = once(
    index,
    "function cardmarketValueForCardVariant(card,variant){\n  const mcd=verifiedMcdonalds2021CardmarketVariant(card,variant);",
    "function cardmarketValueForCardVariant(card,variant){\n  const giratina=verifiedGiratinaVstar201CardmarketVariant(card,variant);\n"
    "  if(giratina?.handled){\n"
    "    if(!giratina.matched)return {value:0,kind:giratina.kind||'needs-exact-variant'};\n"
    "    const value=Number(giratina.pricing?.trend||0);\n"
    "    return {value:Number.isFinite(value)&&value>0?value:0,kind:'exact-giratina-vstar-201',productId:giratina.productId,source:giratina.source};\n"
    "  }\n"
    "  const mcd=verifiedMcdonalds2021CardmarketVariant(card,variant);",
    'Giratina value dispatch',
)
index = once(
    index,
    "function cardmarketStatsForCardVariant(card,variant){\n  const mcd=verifiedMcdonalds2021CardmarketVariant(card,variant);",
    "function cardmarketStatsForCardVariant(card,variant){\n  const giratina=verifiedGiratinaVstar201CardmarketVariant(card,variant);\n"
    "  if(giratina?.handled){\n"
    "    if(!giratina.matched)return {low:null,trend:null,avg7:null,avg30:null};\n"
    "    const p=giratina.pricing||{};\n"
    "    return {low:p.low??null,trend:p.trend??null,avg7:p.avg7??null,avg30:p.avg30??null};\n"
    "  }\n"
    "  const mcd=verifiedMcdonalds2021CardmarketVariant(card,variant);",
    'Giratina stats dispatch',
)

# Audit registries.
audit = once(
    audit,
    '    "sv10.5b-065": {"base": 836043, "alternate": 836009, "stamp": "wrong-card-identity", "cardmarketCode": "BLK065"},',
    '    "sv10.5b-065": {"base": 836043, "alternate": 836009, "stamp": "wrong-card-identity", "cardmarketCode": "BLK065"},\n'
    '    "swsh11-201": {"base": 674207, "alternate": 670816, "stamp": "wrong-card-identity", "cardmarketCode": "LOR201"},',
    'audit confirmed conflict',
)
audit = once(
    audit,
    '    "sv10.5b-065": {"setId": "sv10.5b", "localId": "065", "conflictingProduct": 836009, "baseProduct": 836043},',
    '    "sv10.5b-065": {"setId": "sv10.5b", "localId": "065", "conflictingProduct": 836009, "baseProduct": 836043},\n'
    '    "swsh11-201": {"setId": "swsh11", "localId": "201", "conflictingProduct": 670816, "baseProduct": 674207},',
    'audit expected override',
)

fixture = '''    fixtures["giratina201"] = {
        "id": "swsh11-201", "tcgdexId": "swsh11-201", "name": "Giratina VSTAR", "localId": "201",
        "set": {"id": "swsh11", "name": "Lost Origin"}, "rarity": "Secret Rare", "regulationMark": "F",
        "variants": {"normal": False, "holo": True, "reverse": False},
        "variants_detailed": [
            {"type": "holo", "foil": "rainbow", "thirdParty": {"cardmarket": 670816},
             "pricing": {"cardmarket": {"idProduct": 670816, "trend": 1.46}}},
        ],
        "pricing": {"cardmarket": {"idProduct": 670816, "trend": 1.46}},
    }
'''
audit = once(audit, '    fixtures["metagross"] = {', fixture + '    fixtures["metagross"] = {', 'Giratina fixture')

assertions = '''const gir=fixtures.giratina201;
const girOverride=r.verifiedBaseCardmarketProductOverride(gir);
assert.strictEqual(girOverride?.pricing?.idProduct,674207);
assert.strictEqual(r.resolvedCardmarketPricingForCard(gir)?.idProduct,674207);
assert.strictEqual(r.knownCardmarketIdentityConflict(gir,670816)?.kind,'identity-mismatch');
assert.strictEqual(r.knownCardmarketIdentityConflict({...gir,id:'swsh11-202',tcgdexId:'swsh11-202',localId:'202'},674207)?.kind,'identity-mismatch');
const correctGiratinaV={...gir,id:'swsh11-130',tcgdexId:'swsh11-130',name:'Giratina V',localId:'130',variants_detailed:[{type:'holo',thirdParty:{cardmarket:670816}}],pricing:{cardmarket:{idProduct:670816,trend:1.46}}};
assert.strictEqual(r.knownCardmarketIdentityConflict(correctGiratinaV,670816),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...gir,localId:'202'}),null);
assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...gir,name:'Giratina V'}),null);
const girHolo=r.cardmarketValueForCardVariant(gir,'Holo');
assert.deepStrictEqual(JSON.parse(JSON.stringify({value:girHolo.value,productId:girHolo.productId,kind:girHolo.kind})),{value:20.65,productId:674207,kind:'exact-giratina-vstar-201'});
assert.deepStrictEqual(JSON.parse(JSON.stringify(r.cardmarketStatsForCardVariant(gir,'Holo'))),{low:9.9,trend:20.65,avg7:20.82,avg30:19.59});
const girWrongFinish=r.cardmarketValueForCardVariant(gir,'Normal');
assert.strictEqual(girWrongFinish.value,0);
assert.strictEqual(girWrongFinish.kind,'needs-exact-variant');
const girUpstreamChanged={...gir,variants_detailed:[{type:'holo',foil:'rainbow',thirdParty:{cardmarket:674207}}]};
const changedResult=r.cardmarketValueForCardVariant(girUpstreamChanged,'Holo');
assert.strictEqual(changedResult.value,0);
assert.strictEqual(changedResult.kind,'needs-exact-variant');
'''
audit = once(audit, 'const met=fixtures.metagross;', assertions + 'const met=fixtures.metagross;', 'Giratina runtime assertions')

INDEX.write_text(index, encoding='utf-8')
AUDIT.write_text(audit, encoding='utf-8')
print('Applied exact Giratina VSTAR swsh11-201 Cardmarket patch')
