#!/usr/bin/env python3
"""Regression: exact Aromatisse 039/131 Master Ball Cardmarket price slot only."""
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'

def extract_function(src,name):
    marker=re.search(rf"\bfunction\s+{re.escape(name)}\s*\(",src)
    if not marker:
        raise AssertionError(f"missing function {name}")
    brace=src.find("{",marker.end())
    depth=0
    quote=None
    esc=False
    for i in range(brace,len(src)):
        ch=src[i]
        if quote:
            if esc:
                esc=False
            elif ch=="\\":
                esc=True
            elif ch==quote:
                quote=None
            continue
        if ch in "'\"\`":
            quote=ch
        elif ch=="{":
            depth+=1
        elif ch=="}":
            depth-=1
            if depth==0:
                return src[marker.start():i+1]
    raise AssertionError(f"unterminated function {name}")

def main():
    src=INDEX.read_text(encoding='utf-8')
    m=re.search(r'("sv08\.5-039\|Master Ball Reverse Holo"\s*:\s*\{[^\n]+\})',src)
    if not m:
        raise AssertionError("Aromatisse exact Ball registry row missing")
    registry="const VERIFIED_EXACT_BALL_VARIANT_PRICES={"+m.group(1)+"};"
    fn=extract_function(src,"verifiedExactBallVariantPrice")
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
const card={id:'sv08.5-039',tcgdexId:'sv08.5-039',name:'Aromatisse',localId:'039',set:{id:'sv08.5',name:'Evoluzioni Prismatiche'}};
const r=verifiedExactBallVariantPrice(card,'Master Ball Reverse Holo');
assert(r,'exact Master Ball price missing');
assert(r.productId===806459,'wrong Cardmarket product');
assert(r.low===3.59,'wrong low');
assert(r.trend===5.24,'wrong trend');
assert(r.avg1===4.5,'wrong avg1');
assert(r.avg7===5.9,'wrong avg7');
assert(r.avg30===6.28,'wrong avg30');
assert(r.avg===6.52,'wrong avg');
assert(!verifiedExactBallVariantPrice(card,'Poké Ball Reverse Holo'),'Poké Ball must not inherit Master Ball price');
assert(!verifiedExactBallVariantPrice(card,'Reverse Holo'),'ordinary Reverse must not inherit Master Ball price');
assert(!verifiedExactBallVariantPrice({...card,name:'Other'},'Master Ball Reverse Holo'),'wrong name inherited exact price');
assert(!verifiedExactBallVariantPrice({...card,localId:'040'},'Master Ball Reverse Holo'),'wrong number inherited exact price');
assert(!verifiedExactBallVariantPrice({...card,set:{id:'sv08.5x',name:'Other'}},'Master Ball Reverse Holo'),'wrong set inherited exact price');
console.log(JSON.stringify({test:'PASS',id:'sv08.5-039',variant:'Master Ball Reverse Holo',productId:r.productId,trend:r.trend,avg7:r.avg7}));
'''
    code=registry+'\n'+fn+'\n'+harness
    result=subprocess.run(['node','-'],input=code,text=True,capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.strip())
    print(result.stdout.strip())

if __name__=='__main__':
    main()
