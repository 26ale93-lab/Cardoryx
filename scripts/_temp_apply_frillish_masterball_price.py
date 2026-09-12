#!/usr/bin/env python3
from pathlib import Path
p=Path('index.html')
s=p.read_text(encoding='utf-8')
needle="const VERIFIED_VARIANT_PRICES = {\n"
if needle not in s: raise SystemExit('VERIFIED_VARIANT_PRICES marker missing')
if "const VERIFIED_EXACT_VARIANT_PRICES = {" not in s:
    block="""// Exact physical-identity variant prices. Keep these stricter than the legacy\n// set-name registry: no other card/finish may inherit a special parallel price.\nconst VERIFIED_EXACT_VARIANT_PRICES = {\n  'sv10.5w-044':{\n    setId:'sv10.5w',localId:'044',name:'Frillish',finish:'Master Ball Reverse Holo',productId:836574,\n    low:0.95,trend:3.00,avg1:3.00,avg7:2.50,avg30:2.50,\n    source:'Cardmarket · White Flare: Additionals · Frillish V2 xWHT044 · product 836574',\n    sourceUrl:'https://www.cardmarket.com/en/Pokemon/Products/Singles/White-Flare-Additionals/Frillish-V2-xWHT044',\n    priceGuideUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',\n    verified:'2026-09-11T12:09:34+0200'\n  }\n};\nfunction verifiedExactVariantPrice(card,variant){\n  const id=String(card?.tcgdexId||card?.id||'').trim().toLowerCase();\n  const rule=VERIFIED_EXACT_VARIANT_PRICES[id];\n  if(!rule || cardSetId(card)!==rule.setId ||\n     exactLocalIdKey(card?.localId||'')!==exactLocalIdKey(rule.localId) ||\n     normText(card?.name||'')!==normText(rule.name||'') ||\n     canonicalVariant(variant||'Normal')!==canonicalVariant(rule.finish))return null;\n  return rule;\n}\n\n"""
    s=s.replace(needle,block+needle,1)
fn="function verifiedVariantPrice(card,variant){\n"
if fn not in s: raise SystemExit('verifiedVariantPrice function missing')
if "const exact=verifiedExactVariantPrice(card,variant);" not in s:
    repl=fn+"  const exact=verifiedExactVariantPrice(card,variant);\n  if(exact)return exact;\n"
    s=s.replace(fn,repl,1)
p.write_text(s,encoding='utf-8')
print('Applied exact Frillish Master Ball Cardmarket price mapping')
