#!/usr/bin/env python3
from pathlib import Path

path = Path('scripts/test_card_identity_cardmarket_audit.py')
text = path.read_text(encoding='utf-8')
needle = '    over, under = [], []\n'
insert = r'''    # Read-only post-Palafin triage, phase 2: same-card products where the
    # top-level Cardmarket product is not among TCGdex's physical base rows but
    # another base-row product has the same exact card name. This surfaces
    # possible Pre-release/stamped/V1/V2 issues without auto-interpreting them.
    def _name_key(value):
        value = str(value or '').split(' [', 1)[0]
        return re.sub(r'[^a-z0-9]+', '', value.lower())

    skip_ids = {
        'sv09-055', 'me01-073', 'ex8-16', 'sv05-041', 'swshp-SWSH055',
        'pl3-70', 'sv10.5b-027', 'sv10.5b-014', 'sv10.5b-065',
        'swsh11-201', 'sv03-062',
    }
    ranked = []
    for c in cases:
        cid = c.get('tcgdexId') or ''
        if c.get('classification') != 'P1_AMBIGUOUS_PRODUCT':
            continue
        if cid.startswith(('base', 'gym', 'neo')) or cid in skip_ids:
            continue
        current_pid = c.get('currentProductId')
        base_ids = c.get('baseRowProductIdsAccordingToTcgdex') or []
        if not current_pid or current_pid in base_ids:
            continue
        target = _name_key(c.get('name'))
        current_catalog = products.get(current_pid) or {}
        if not target or _name_key(current_catalog.get('name')) != target:
            continue
        base_matches = [pid for pid in base_ids if _name_key((products.get(pid) or {}).get('name')) == target]
        if not base_matches:
            continue
        current_trend = (prices.get(current_pid) or {}).get('trend')
        candidate_trends = [(prices.get(pid) or {}).get('trend') for pid in base_matches]
        numeric = [v for v in candidate_trends if isinstance(v, (int, float))]
        delta = max((abs(current_trend - v) for v in numeric), default=0) if isinstance(current_trend, (int, float)) else 0
        ranked.append((delta, cid, {
            'tcgdexId': cid,
            'name': c.get('name'),
            'setId': c.get('setId'),
            'localId': c.get('localId'),
            'currentProductId': current_pid,
            'currentCatalog': current_catalog,
            'currentPriceGuide': prices.get(current_pid),
            'matchingBaseProductIds': base_matches,
            'matchingBaseCatalog': {str(pid): products.get(pid) for pid in base_matches},
            'matchingBasePriceGuide': {str(pid): prices.get(pid) for pid in base_matches},
            'allProductIds': c.get('allProductIds'),
            'physicalVariantsByProductId': c.get('physicalVariantsByProductId'),
            'sharedProductWithTcgdexIds': c.get('sharedProductWithTcgdexIds'),
            'reason': c.get('reason'),
            'priceDeltaForTriageOnly': round(delta, 2),
        }))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    print('POST_PALAFIN_SAME_CARD_SPECIAL_COUNT ' + str(len(ranked)))
    for _, _, row in ranked[:30]:
        print('POST_PALAFIN_SPECIAL_CANDIDATE ' + json.dumps(row, ensure_ascii=False, sort_keys=True))

    over, under = [], []
'''
if needle not in text:
    raise SystemExit('audit ranking anchor missing')
path.write_text(text.replace(needle, insert, 1), encoding='utf-8')
print('post-Palafin P1 same-card special-product diagnostic injected')
