#!/usr/bin/env python3
from pathlib import Path

p = Path('scripts/test_card_identity_cardmarket_audit.py')
s = p.read_text(encoding='utf-8')
needle = '    report = {\n'
insert = r'''    _focus = next(c for c in cases if c.get("tcgdexId") == "sv10.5b-014")
    print("DARMANITAN_CASE " + json.dumps(_focus, ensure_ascii=False, sort_keys=True))
    print("DARMANITAN_PRODUCTS " + json.dumps({
        str(pid): {"catalog": products.get(pid), "priceGuide": prices.get(pid)}
        for pid in (835069, 835929, 836285, 836286)
    }, ensure_ascii=False, sort_keys=True))

    report = {
'''
if needle not in s:
    raise SystemExit('report anchor missing')
p.write_text(s.replace(needle, insert, 1), encoding='utf-8')
print('focused Darmanitan diagnostic injection applied')
