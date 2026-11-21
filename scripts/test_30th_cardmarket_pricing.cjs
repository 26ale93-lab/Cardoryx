#!/usr/bin/env node
// Read-only regression against the actual Cardoryx pricing functions and live TCGdex audit rows.
const fs = require('fs');
const vm = require('vm');
const assert = require('assert/strict');

const source = fs.readFileSync('index.html','utf8');
const audit = JSON.parse(fs.readFileSync('cardmarket_30th_diagnostic.json','utf8'));
function between(a,b) {
  const begin = source.indexOf(a);
  assert(begin >= 0, 'missing production function '+a);
  const end = source.indexOf(b,begin);
  assert(end > begin, 'missing end boundary '+b);
  return source.slice(begin,end);
}
const real = between('function verified30thAnniversaryCardmarketPrice(', 'function cardUnitPrice(c){');
const dependencies = {
  canonicalStamp:x=>x,
  canonicalVariant:x=>x,
  is30thCelebrationSet:c=>['30th','30th-c'].includes(c?._cardoryxSetId),
  sameExactLocalId:(a,b)=>String(a).replace(/^0+/,'')===String(b).replace(/^0+/,''),
  resolvedCardmarketPricingForCard:c=>c?.pricing?.cardmarket||null,
  normalizedPlaySeries:x=>String(x||''),
  storedLivePlayPrice:()=>null,
  playAutoValuation:()=>null,
  verifiedPlaySeriesPrice:()=>null,
  verifiedStampPrice:()=>null,
  verifiedVariantPrice:()=>null,
  verifiedStandardEnergyPrice:()=>null,
  cardmarketValueForCardVariant:()=>({value:0,kind:'none'}),
  playAutoSeries:()=>[]
};
const scope = vm.createContext(dependencies);
vm.runInContext(real,scope,{timeout:1000});
let checked=0;
const products=new Map();
for(const r of audit.source_rows) {
  if(!r.usable) continue;
  const [set,localId] = [r.set,r.id.slice(r.set.length+1)];
  const c = {id:r.id,tcgdexId:r.id,_cardoryxSetId:set,localId,
    stamp:'30° Anniversario',variant:'Holo',
    pricing:{cardmarket:{idProduct:r.product_id,...r.price_keys}}};
  const price=scope.cardPriceInfo(c);
  assert(price.value>0 && price.exact && price.kind==='30th-exact-foil', 'unpriced real identity '+r.id);
  const previous=products.get(r.id);
  if(previous) assert.equal(previous,r.product_id,'ITA/EN product mismatch '+r.id);
  products.set(r.id,r.product_id);
  for(const [change,value] of [
    ['wrong-stamp',{...c,stamp:'Staff'}],
    ['wrong-finish',{...c,variant:'Normal'}],
    ['wrong-number',{...c,localId:'WRONG'}],
    ['wrong-set',{...c,_cardoryxSetId:'sv01'}],
    ['missing-price',{...c,pricing:{cardmarket:{idProduct:r.product_id}}}],
    ['missing-product',{...c,pricing:{cardmarket:{trend:1}}}]
  ]) {
    assert.equal(scope.cardPriceInfo(value).value,null,change+' must not be priced for '+r.id);
  }
  checked++;
}
assert.equal(products.size,audit.summary.identities_total, 'coverage mismatch');
assert.equal(products.size,191,'unexpected complete set size: halt and re-audit');
console.log(JSON.stringify({source:'production cardPriceInfo + verified30thAnniversaryCardmarketPrice',requests_checked:checked,unique_cards:products.size,negative_scenarios:checked*6,passed:true}));
