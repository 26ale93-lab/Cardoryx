#!/usr/bin/env python3
# Focused regression for Numel PGO 013 peelable Ditto finish separation.

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'index.html'


def require(source, needle, label):
    if needle not in source:
        raise AssertionError(f'{label}: missing expected production code')


def main():
    source = INDEX.read_text(encoding='utf-8')

    # Both scanner and edit UI expose the physical Ditto identity separately.
    if source.count('value="Ditto Peelable Reverse Holo"') != 2:
        raise AssertionError('Ditto finish must exist exactly in scanner and edit selectors')

    # Canonicalization must happen before generic Reverse, otherwise Ditto collapses again.
    ditto_rule = "if(n.includes('ditto')&&(n.includes('peelable')||n.includes('rimovibile')))return 'Ditto Peelable Reverse Holo';"
    reverse_rule = "if(n.includes('reverse'))return 'Reverse Holo';"
    require(source, ditto_rule, 'Ditto canonical rule')
    require(source, reverse_rule, 'generic Reverse rule')
    if source.index(ditto_rule) > source.index(reverse_rule):
        raise AssertionError('Ditto canonical rule must precede generic Reverse rule')

    # TCGdex detailed evidence remains physically distinct.
    require(
        source,
        "if(type==='reverse'&&foil==='peelableditto')allowed.add('Ditto Peelable Reverse Holo');",
        'detailed finish separation',
    )

    # Standard Reverse explicitly rejects any foil tag; peelable-ditto cannot enter this path.
    require(
        source,
        "else if(target==='Reverse Holo') matches=pool.filter(x=>canonicalFinishTypeLabel(x?.type)==='reverse'&&!canonicalFinishFoilLabel(x?.foil)&&!x?.stamp?.length);",
        'standard Reverse row guard',
    )

    # Ditto selection resolves only to the exact peelable row.
    require(
        source,
        "else if(target==='Ditto Peelable Reverse Holo') matches=pool.filter(x=>canonicalFinishTypeLabel(x?.type)==='reverse'&&canonicalFinishFoilLabel(x?.foil)==='peelableditto'&&!x?.stamp?.length);",
        'Ditto TCGdex row resolver',
    )

    # Both generic and card-aware Cardmarket paths must fail closed until an exact product exists.
    require(
        source,
        "if(v==='Cosmos Holo'||v==='Ditto Peelable Reverse Holo'||v==='Speciale / Altro'||v==='Non so')",
        'generic Cardmarket fail-closed guard',
    )
    require(
        source,
        "v==='Master Ball Reverse Holo'||v==='Ditto Peelable Reverse Holo'||",
        'card-aware Cardmarket fail-closed guard',
    )

    # Distinct badge prevents a saved Ditto card from rendering as Normal/standard Reverse.
    require(
        source,
        "if(x==='Ditto Peelable Reverse Holo')return '<span class=\"variant-badge variant-reverse\">🟡 Reverse Holo Ditto (rimovibile)</span>';",
        'Ditto badge',
    )

    print('{"test":"PASS","numel":"swsh10.5-013","standardReverse":"preserved","ditto":"separate","cardmarketDitto":"fail-closed"}')


if __name__ == '__main__':
    main()
