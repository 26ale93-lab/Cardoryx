#!/usr/bin/env python3
from pathlib import Path

path = Path('scripts/test_card_identity_cardmarket_audit.py')
text = path.read_text(encoding='utf-8')
needle = '    report = {\n'
insert = r'''    focus = next(c for c in cases if c.get("tcgdexId") == "sv10.5b-065")
    print("BISHARP_CASE " + json.dumps(focus, ensure_ascii=False, sort_keys=True))
    print("BISHARP_PRODUCTS " + json.dumps({
        str(pid): {"catalog": products.get(pid), "priceGuide": prices.get(pid)}
        for pid in (836009, 836043, 836444, 836445)
    }, ensure_ascii=False, sort_keys=True))

    report = {
'''
if needle not in text:
    raise SystemExit('report anchor missing')
path.write_text(text.replace(needle, insert, 1), encoding='utf-8')
print('focused Bisharp sv10.5b-065 diagnostic injection applied')
