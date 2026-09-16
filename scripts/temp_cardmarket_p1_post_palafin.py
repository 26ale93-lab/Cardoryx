#!/usr/bin/env python3
from pathlib import Path

path = Path('scripts/test_card_identity_cardmarket_audit.py')
text = path.read_text(encoding='utf-8')
needle = '    over, under = [], []\n'
insert = r'''    # Read-only post-Palafin triage, phase 3: inspect modern P1 cases with
    # multiple products/base products. Price delta is triage only; catalogue,
    # metacard, expansion and physical rows are emitted for exact verification.
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
        all_ids = c.get('allProductIds') or []
        if len(all_ids) < 2:
            continue
        current_trend = (prices.get(current_pid) or {}).get('trend') if current_pid else None
        deltas = []
        for pid in all_ids:
            if pid == current_pid:
                continue
            tr = (prices.get(pid) or {}).get('trend')
            if isinstance(current_trend, (int, float)) and isinstance(tr, (int, float)):
                deltas.append(abs(current_trend - tr))
        delta = max(deltas, default=0)
        ranked.append((delta, cid, {
            'tcgdexId': cid,
            'name': c.get('name'),
            'setId': c.get('setId'),
            'localId': c.get('localId'),
            'currentProductId': current_pid,
            'baseRowProductIdsAccordingToTcgdex': c.get('baseRowProductIdsAccordingToTcgdex'),
            'allProductIds': all_ids,
            'catalog': {str(pid): products.get(pid) for pid in all_ids},
            'priceGuide': {str(pid): prices.get(pid) for pid in all_ids},
            'physicalVariantsByProductId': c.get('physicalVariantsByProductId'),
            'sharedProductWithTcgdexIds': c.get('sharedProductWithTcgdexIds'),
            'reason': c.get('reason'),
            'priceDeltaForTriageOnly': round(delta, 2),
        }))
    ranked.sort(key=lambda row: (-row[0], row[1]))
    print('POST_PALAFIN_MODERN_MULTI_COUNT ' + str(len(ranked)))
    for _, _, row in ranked[:30]:
        print('POST_PALAFIN_MULTI_CANDIDATE ' + json.dumps(row, ensure_ascii=False, sort_keys=True))

    over, under = [], []
'''
if needle not in text:
    raise SystemExit('audit ranking anchor missing')
path.write_text(text.replace(needle, insert, 1), encoding='utf-8')
print('post-Palafin P1 modern multi-product diagnostic injected')
