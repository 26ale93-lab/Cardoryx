#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'index.html'
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

# Edit finish selector.
replace_once(
'''              <option value="Master Ball Reverse Holo">🟣 Master Ball Reverse Holo</option>\n              <option value="Speciale / Altro">Speciale / Altro</option>''',
'''              <option value="Master Ball Reverse Holo">🟣 Master Ball Reverse Holo</option>\n              <option value="Ditto Peelable Reverse Holo">🟡 Reverse Holo Ditto (rimovibile)</option>\n              <option value="Speciale / Altro">Speciale / Altro</option>''',
'edit finish option')

# Canonicalize exact Ditto peelable finish before generic Reverse.
replace_once(
'''  if(n==='cosmo'||n.includes('cosmos'))return 'Cosmos Holo';\n  if(n.includes('reverse'))return 'Reverse Holo';''',
'''  if(n==='cosmo'||n.includes('cosmos'))return 'Cosmos Holo';\n  if(n.includes('ditto')&&(n.includes('peelable')||n.includes('rimovibile')))return 'Ditto Peelable Reverse Holo';\n  if(n.includes('reverse'))return 'Reverse Holo';''',
'canonical Ditto finish')

# Render distinctly instead of falling through to Normal.
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

# Generic Cardmarket resolver must never inherit normal/reverse values for Ditto.
replace_once(
'''  if(v==='Cosmos Holo'||v==='Speciale / Altro'||v==='Non so'){\n    // Cosmos e altre finiture particolari non devono ereditare automaticamente''',
'''  if(v==='Cosmos Holo'||v==='Ditto Peelable Reverse Holo'||v==='Speciale / Altro'||v==='Non so'){\n    // Cosmos, Ditto peelable e altre finiture particolari non devono ereditare automaticamente''',
'generic Cardmarket fail closed')

# Card-aware resolver must fail closed before standard/reverse inference.
replace_once(
'''     v==='Poké Ball Reverse Holo'||v==='Master Ball Reverse Holo'||\n     v==='Cosmos Holo'||v==='Speciale / Altro'||v==='Non so'){''',
'''     v==='Poké Ball Reverse Holo'||v==='Master Ball Reverse Holo'||v==='Ditto Peelable Reverse Holo'||\n     v==='Cosmos Holo'||v==='Speciale / Altro'||v==='Non so'){''',
'card-aware Cardmarket fail closed')

INDEX.write_text(src, encoding='utf-8')
print('patched Numel Ditto finish separation')
