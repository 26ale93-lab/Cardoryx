#!/usr/bin/env python3
"""Focused offline regression for the Piplup CEC54 Cardmarket runtime guard."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
AUDIT_REPORT = ROOT / "artifacts" / "card_identity_cardmarket_audit_report.json"


def js_declaration(source, marker):
    start = source.index(marker)
    brace = source.index("{", start)
    depth = 0
    quote = None
    escape = False
    for pos in range(brace, len(source)):
        ch = source[pos]
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in ("'", '"', "`"):
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = pos + 1
                while end < len(source) and source[end] in " \t\r\n;":
                    end += 1
                return source[start:end]
    raise AssertionError(f"Unclosed JavaScript declaration: {marker}")


def main():
    source = INDEX.read_text(encoding="utf-8")
    declarations = [
        "const VERIFIED_BASE_CARDMARKET_PRODUCT_OVERRIDES",
        "const VERIFIED_EXACT_CARDMARKET_PRICE_GUIDES",
        "function exactCardmarketGuideIdentity",
        "function verifiedBaseCardmarketProductOverride",
        "function knownCardmarketIdentityConflict",
        "function resolvedCardmarketPricingForCard",
        "function pricingWithResolvedCardmarket",
        "function cardmarketValueForCardVariant",
        "function cardmarketStatsForCardVariant",
        "async function refreshPriceForRecord",
    ]
    actual = "\n".join(js_declaration(source, marker) for marker in declarations)
    harness = r"""
function canonicalPrintedLocalId(v){const s=String(v||'').trim();return /^\d+$/.test(s)?String(Number(s)):s.toLowerCase()}
function normText(v){return String(v||'').trim().toLowerCase()}
function tcgdexVariantDetails(card){return Array.isArray(card?.variants_detailed)?card.variants_detailed:[]}
function canonicalVariant(v){return String(v||'Normal')}
function documentedVariantsForCard(card){return new Set(card?._testVariants||[])}
function knownReverseCardmarketProductConflict(){return null}
function cardmarketValueForVariant(){return {value:0,kind:'none'}}
function canonicalStamp(v){return String(v||'None')}
function normalizedPlaySeries(){return ''}
async function resolveOfficialPlayPrice(){return null}
async function resolveTcgdexIdForRecord(){return 'sm12-54'}
async function fetchFullCardForPrice(){return exact}
function assert(ok,message){if(!ok)throw new Error(message)}

const exact={
  id:'sm12-54',tcgdexId:'sm12-54',name:'Piplup',localId:'054',
  set:{id:'sm12'},_cardoryxSetId:'sm12',_testVariants:['Normal','Reverse Holo'],
  variants_detailed:[],
  pricing:{cardmarket:{idProduct:398504,trend:66.4,'trend-holo':11.29}}
};
const resolved=resolvedCardmarketPricingForCard(exact);
assert(resolved?.idProduct===407919,'398504 was not replaced by exact product 407919');
assert(resolved.trend===0.17,'Normal must use the verified 407919 standard trend');
assert(resolved['trend-holo']===0.76,'Reverse must use the verified 407919 holo trend');
assert(knownCardmarketIdentityConflict(exact,398504)?.kind==='identity-mismatch','398504 must be refused for CEC54');

const normal=cardmarketValueForCardVariant(exact,'Normal');
const reverse=cardmarketValueForCardVariant(exact,'Reverse Holo');
assert(normal.value===0.17&&normal.productId===407919,'Normal runtime value/product mismatch');
assert(reverse.value===0.76&&reverse.productId===407919,'Reverse runtime value/product mismatch');
assert(normal.value!==reverse.value,'Normal price must never be reused as Reverse');
assert(normal.source.includes('407919')&&normal.verified==='2026-09-10T02:48:22+0200','Price evidence missing');
assert(cardmarketStatsForCardVariant(exact,'Normal').trend===0.17,'Normal stats mismatch');
assert(cardmarketStatsForCardVariant(exact,'Reverse Holo').trend===0.76,'Reverse stats mismatch');
assert(pricingWithResolvedCardmarket(exact).cardmarket.idProduct===407919,'Saved pricing was not sanitized');

const exact407919={...exact,pricing:{cardmarket:{...resolved}}};
assert(resolvedCardmarketPricingForCard(exact407919)?.idProduct===407919,'407919 rejected for exact identity');
for(const [label,patch] of [
  ['id',{id:'sm12-55',tcgdexId:'sm12-55'}],
  ['set',{set:{id:'sm11'},_cardoryxSetId:'sm11'}],
  ['local',{localId:'055'}],
  ['name',{name:'Prinplup'}]
]){
  const wrong={...exact407919,...patch};
  assert(resolvedCardmarketPricingForCard(wrong)===null,`407919 accepted with wrong ${label}`);
}

const expectedSurging={
  'sv08-029':[794946,794286],
  'sv08-050':[794947,794316],
  'sv08-161':[794948,794534]
};
for(const [id,[conflicting,base]] of Object.entries(expectedSurging)){
  const rule=VERIFIED_BASE_CARDMARKET_PRODUCT_OVERRIDES[id];
  assert(rule?.conflictingProduct===conflicting&&rule?.baseProduct===base,`${id} registry regression`);
  const card={id,tcgdexId:id,localId:rule.localId,set:{id:rule.setId},_cardoryxSetId:rule.setId,
    pricing:{cardmarket:{idProduct:conflicting}},
    variants_detailed:[{thirdParty:{cardmarket:base},pricing:{cardmarket:{idProduct:base,trend:1}}}]};
  assert(resolvedCardmarketPricingForCard(card)?.idProduct===base,`${id} runtime regression`);
}
assert(Object.keys(VERIFIED_BASE_CARDMARKET_PRODUCT_OVERRIDES).length===4,'Unexpected base override/P1 mapping');
assert(JSON.stringify(Object.keys(VERIFIED_EXACT_CARDMARKET_PRICE_GUIDES))==='["sm12-54"]','Guide scope expanded beyond Piplup');
console.log(JSON.stringify({normal,reverse,product398504:'rejected',product407919:'exact-only',surging:'3/3'}));
const refreshed={id:'sm12-54',tcgdexId:'sm12-54'};
refreshPriceForRecord(refreshed).then(ok=>{
  assert(ok&&refreshed.pricing?.cardmarket?.idProduct===407919,'Refresh persisted the conflicting product');
  assert(refreshed.pricing.cardmarket.trend===0.17,'Refresh did not persist exact 407919 pricing');
  console.log(JSON.stringify({refresh:'398504 -> 407919',refreshResult:'ok'}));
}).catch(error=>{console.error(error);process.exitCode=1});
"""
    result = subprocess.run(["node", "-e", actual + "\n" + harness], check=True, text=True, capture_output=True)
    report = json.loads(AUDIT_REPORT.read_text(encoding="utf-8"))
    assert report["classificationTotals"]["P1_AMBIGUOUS_PRODUCT"] == 1292
    assert "resolvedCardmarketPricingForCard(full)" in source
    assert "pricing:pricingWithResolvedCardmarket(selectedCard)" in source
    print(result.stdout.strip())
    print(json.dumps({"p1Unchanged": 1292, "refreshSanitized": True, "newCollectionRecordSanitized": True}))


if __name__ == "__main__":
    main()
