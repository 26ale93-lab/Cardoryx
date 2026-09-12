#!/usr/bin/env python3
"""Regression: exact Frillish 044/086 Master Ball Reverse Cardmarket price only."""
import subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'

def slice_between(src,start_marker,end_marker):
    a=src.index(start_marker); b=src.index(end_marker,a); return src[a:b]

def main():
    src=INDEX.read_text(encoding='utf-8')
    block=slice_between(src,'const VERIFIED_EXACT_VARIANT_PRICES','function cardmarketValueForVariant')
    harness=r'''
function normText(v){return String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().trim()}
function canonicalVariant(v){
 const x=String(v||'').trim().toLowerCase();
 if(x.includes('master'))return 'Master Ball Reverse Holo';
 if(x.includes('poke'))return 'Poké Ball Reverse Holo';
 if(x==='reverse holo'||x==='reverse')return 'Reverse Holo';
 if(x==='holo')return 'Holo';
 return 'Normal';
}
function cardSetId(c){return String(c?.set?.id||c?._cardoryxSetId||'').trim().toLowerCase()}
function exactLocalIdKey(v){return String(v||'').toUpperCase().replace(/[^A-Z0-9]/g,'').replace(/^0+(?=\d)/,'')}
function assert(ok,msg){if(!ok)throw new Error(msg)}
const exactCard={id:'sv10.5w-044',tcgdexId:'sv10.5w-044',name:'Frillish',localId:'044',set:{id:'sv10.5w',name:'Fuoco Bianco'}};
const r=verifiedVariantPrice(exactCard,'Master Ball Reverse Holo');
assert(r,'exact Master Ball price missing');
assert(r.productId===836574,'wrong Cardmarket product');
assert(r.trend===3 && r.low===0.95 && r.avg1===3 && r.avg7===2.5 && r.avg30===2.5,'wrong price guide snapshot');
assert(String(r.sourceUrl||'').includes('Frillish-V2-xWHT044'),'exact Cardmarket source missing');
assert(!verifiedVariantPrice(exactCard,'Poké Ball Reverse Holo'),'Poké Ball must not inherit Master Ball price');
assert(!verifiedVariantPrice(exactCard,'Reverse Holo'),'ordinary Reverse must not inherit Master Ball price');
assert(!verifiedVariantPrice(exactCard,'Normal'),'Normal must not inherit Master Ball price');
assert(!verifiedVariantPrice({...exactCard,name:'Other'},'Master Ball Reverse Holo'),'wrong name inherited exact price');
assert(!verifiedVariantPrice({...exactCard,localId:'045'},'Master Ball Reverse Holo'),'wrong number inherited exact price');
assert(!verifiedVariantPrice({...exactCard,set:{id:'sv10.5b',name:'Black Bolt'}},'Master Ball Reverse Holo'),'wrong set inherited exact price');
assert(!verifiedVariantPrice({...exactCard,id:'sv10.5w-126',tcgdexId:'sv10.5w-126',localId:'126'},'Master Ball Reverse Holo'),'other Frillish inherited exact price');
console.log(JSON.stringify({test:'PASS',id:'sv10.5w-044',variant:'Master Ball Reverse Holo',productId:r.productId,trend:r.trend}));
'''
    result=subprocess.run(['node','-e',block+'\n'+harness],text=True,capture_output=True)
    if result.returncode: raise AssertionError(result.stderr.strip())
    assert "const exact=verifiedExactVariantPrice(card,variant);" in src
    assert "if(exact)return exact;" in src
    print(result.stdout.strip())
if __name__=='__main__':main()
