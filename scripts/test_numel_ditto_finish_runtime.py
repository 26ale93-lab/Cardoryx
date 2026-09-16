#!/usr/bin/env python3
# Runtime regression for Numel PGO 013 peelable Ditto finish separation.

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'index.html'


def js_function(source, marker):
    start = source.index(marker)
    brace = source.index('{', start)
    depth = 0
    quote = None
    escape = False
    for pos in range(brace, len(source)):
        ch = source[pos]
        if quote:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in ("'", '"', '`'):
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    raise AssertionError(f'Unclosed function: {marker}')


def main():
    source = INDEX.read_text(encoding='utf-8')

    required = [
        'function normText',
        'function canonicalVariant',
        'function canonicalFinishTypeLabel',
        'function canonicalFinishFoilLabel',
        'function addDetailedFinishes',
        'function tcgdexMarketplaceVariant',
    ]
    js = '\n'.join(js_function(source, x) for x in required)

    harness = r'''
function assert(ok,msg){if(!ok)throw new Error(msg)}
const numel={
  id:'swsh10.5-013',tcgdexId:'swsh10.5-013',name:'Numel',localId:'013',
  variants_detailed:[
    {type:'normal',languages:['it'],thirdParty:{cardmarket:665652}},
    {type:'reverse',languages:['it'],thirdParty:{cardmarket:665652}},
    {type:'reverse',foil:'peelable-ditto',languages:['it'],thirdParty:{}}
  ],
  pricing:{cardmarket:{idProduct:665652,trend:0.05,'trend-reverse-holo':0.12}}
};

const allowed=new Set();
addDetailedFinishes(allowed,numel.variants_detailed,{base:true,special:true});
assert(allowed.has('Normal'),'Normal finish missing');
assert(allowed.has('Reverse Holo'),'standard Reverse missing');
assert(allowed.has('Ditto Peelable Reverse Holo'),'Ditto peelable finish missing');
assert(canonicalVariant('Reverse Holo Ditto (rimovibile)')==='Ditto Peelable Reverse Holo','Italian Ditto label canonicalization failed');
assert(canonicalVariant('Ditto Peelable Reverse Holo')==='Ditto Peelable Reverse Holo','Ditto canonicalization failed');

const standard=tcgdexMarketplaceVariant(numel,'Reverse Holo');
assert(standard && !standard.foil,'standard Reverse resolved to special foil');
assert(Number(standard.thirdParty?.cardmarket)===665652,'standard Reverse Cardmarket row changed');

const ditto=tcgdexMarketplaceVariant(numel,'Ditto Peelable Reverse Holo');
assert(ditto && ditto.foil==='peelable-ditto','Ditto finish did not resolve to peelable row');
assert(!Number(ditto.thirdParty?.cardmarket||0),'Ditto fixture unexpectedly has exact Cardmarket product');

console.log(JSON.stringify({
  test:'PASS',
  standardReverseProduct:Number(standard.thirdParty.cardmarket),
  dittoFoil:ditto.foil
}));
'''
    result = subprocess.run(['node', '-e', js + '\n' + harness], text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.strip())

    # UI and both Cardmarket resolvers must explicitly fail closed for Ditto peelable.
    assert source.count('value="Ditto Peelable Reverse Holo"') == 2
    assert "if(v==='Cosmos Holo'||v==='Ditto Peelable Reverse Holo'||v==='Speciale / Altro'||v==='Non so')" in source
    assert "v==='Master Ball Reverse Holo'||v==='Ditto Peelable Reverse Holo'" in source
    assert "foil==='peelableditto'" in source
    print(result.stdout.strip())
    print('{"cardmarketDitto":"fail-closed","expectedValue":null}')


if __name__ == '__main__':
    main()
