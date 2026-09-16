#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'index.html'
TEST = ROOT / 'scripts' / 'test_numel_ditto_finish_runtime.py'

src = INDEX.read_text(encoding='utf-8')


def replace_once(old, new, label):
    global src
    count = src.count(old)
    if count != 1:
        raise SystemExit(f'{label}: expected exactly 1 match, found {count}')
    src = src.replace(old, new, 1)

# Scanner finish selector.
replace_once(
'''<option value="Master Ball Reverse Holo">🟣 Master Ball Reverse Holo</option>\n<option value="Speciale / Altro">Speciale / Altro</option>''',
'''<option value="Master Ball Reverse Holo">🟣 Master Ball Reverse Holo</option>\n<option value="Ditto Peelable Reverse Holo">🟡 Reverse Holo Ditto (rimovibile)</option>\n<option value="Speciale / Altro">Speciale / Altro</option>''',
'scanner finish option')

# Edit finish selector (same markup is indented differently).
replace_once(
'''              <option value="Master Ball Reverse Holo">🟣 Master Ball Reverse Holo</option>\n              <option value="Speciale / Altro">Speciale / Altro</option>''',
'''              <option value="Master Ball Reverse Holo">🟣 Master Ball Reverse Holo</option>\n              <option value="Ditto Peelable Reverse Holo">🟡 Reverse Holo Ditto (rimovibile)</option>\n              <option value="Speciale / Altro">Speciale / Altro</option>''',
'edit finish option')

# Canonicalize the exact Ditto peelable finish before the generic Reverse rule.
replace_once(
'''  if(n==='cosmo'||n.includes('cosmos'))return 'Cosmos Holo';\n  if(n.includes('reverse'))return 'Reverse Holo';''',
'''  if(n==='cosmo'||n.includes('cosmos'))return 'Cosmos Holo';\n  if(n.includes('ditto')&&(n.includes('peelable')||n.includes('rimovibile')))return 'Ditto Peelable Reverse Holo';\n  if(n.includes('reverse'))return 'Reverse Holo';''',
'canonical Ditto finish')

# Render it distinctly instead of falling through to Normal.
replace_once(
'''  if(x==='Master Ball Reverse Holo')return '<span class="variant-badge variant-masterball">🟣 Master Ball Reverse Holo</span>';\n  if(x==='Reverse Holo')return '<span class="variant-badge variant-reverse">Reverse Holo</span>';''',
'''  if(x==='Master Ball Reverse Holo')return '<span class="variant-badge variant-masterball">🟣 Master Ball Reverse Holo</span>';\n  if(x==='Ditto Peelable Reverse Holo')return '<span class="variant-badge variant-reverse">🟡 Reverse Holo Ditto (rimovibile)</span>';\n  if(x==='Reverse Holo')return '<span class="variant-badge variant-reverse">Reverse Holo</span>';''',
'Ditto badge')

# Keep TCGdex peelable-ditto evidence as its own physical finish.
replace_once(
'''      if(type==='reverse'&&foil==='pokeball')allowed.add('Poké Ball Reverse Holo');\n      if(type==='reverse'&&foil==='masterball')allowed.add('Master Ball Reverse Holo');''',
'''      if(type==='reverse'&&foil==='pokeball')allowed.add('Poké Ball Reverse Holo');\n      if(type==='reverse'&&foil==='masterball')allowed.add('Master Ball Reverse Holo');\n      if(type==='reverse'&&foil==='peelableditto')allowed.add('Ditto Peelable Reverse Holo');''',
'Ditto detailed finish')

# Route the new finish only to the peelable-ditto TCGdex row.
replace_once(
'''  else if(target==='Master Ball Reverse Holo') matches=pool.filter(x=>x?.type==='reverse'&&x?.foil==='masterball');\n  else if(target==='Holo') matches=pool.filter(x=>canonicalFinishTypeLabel(x?.type)==='holo'&&!canonicalFinishFoilLabel(x?.foil)&&!x?.stamp?.length);''',
'''  else if(target==='Master Ball Reverse Holo') matches=pool.filter(x=>x?.type==='reverse'&&x?.foil==='masterball');\n  else if(target==='Ditto Peelable Reverse Holo') matches=pool.filter(x=>canonicalFinishTypeLabel(x?.type)==='reverse'&&canonicalFinishFoilLabel(x?.foil)==='peelableditto'&&!x?.stamp?.length);\n  else if(target==='Holo') matches=pool.filter(x=>canonicalFinishTypeLabel(x?.type)==='holo'&&!canonicalFinishFoilLabel(x?.foil)&&!x?.stamp?.length);''',
'tcgdex Ditto row')

# Generic Cardmarket resolver must never inherit normal/reverse values for the Ditto identity.
replace_once(
'''  if(v==='Cosmos Holo'||v==='Speciale / Altro'||v==='Non so'){\n    // Cosmos e altre finiture particolari non devono ereditare automaticamente''',
'''  if(v==='Cosmos Holo'||v==='Ditto Peelable Reverse Holo'||v==='Speciale / Altro'||v==='Non so'){\n    // Cosmos, Ditto peelable e altre finiture particolari non devono ereditare automaticamente''',
'generic Cardmarket fail closed')

# Card-aware Cardmarket resolver must fail closed before standard/reverse inference.
replace_once(
'''     v==='Poké Ball Reverse Holo'||v==='Master Ball Reverse Holo'||\n     v==='Cosmos Holo'||v==='Speciale / Altro'||v==='Non so'){''',
'''     v==='Poké Ball Reverse Holo'||v==='Master Ball Reverse Holo'||v==='Ditto Peelable Reverse Holo'||\n     v==='Cosmos Holo'||v==='Speciale / Altro'||v==='Non so'){''',
'card-aware Cardmarket fail closed')

INDEX.write_text(src, encoding='utf-8')

TEST.write_text(r'''#!/usr/bin/env python3
"""Runtime regression for Numel PGO 013 peelable Ditto finish separation."""

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
            elif ch == '\\\\':
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
        'function cardmarketValueForVariant',
    ]
    js = '\\n'.join(js_function(source, x) for x in required)

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

const generic=cardmarketValueForVariant(numel.pricing.cardmarket,'Ditto Peelable Reverse Holo');
assert(generic.value===0 && generic.kind==='needs-exact-variant','Ditto inherited a generic Cardmarket price');

console.log(JSON.stringify({
  test:'PASS',
  standardReverseProduct:Number(standard.thirdParty.cardmarket),
  dittoFoil:ditto.foil,
  dittoPrice:generic.value,
  dittoPriceKind:generic.kind
}));
'''
    result = subprocess.run(['node', '-e', js + '\\n' + harness], text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.strip())

    # UI and card-aware fail-closed guards.
    assert source.count('value="Ditto Peelable Reverse Holo"') == 2
    assert "v==='Master Ball Reverse Holo'||v==='Ditto Peelable Reverse Holo'" in source
    assert "foil==='peelableditto'" in source
    print(result.stdout.strip())


if __name__ == '__main__':
    main()
''', encoding='utf-8')

print('patched Numel Ditto finish separation')
