#!/usr/bin/env python3
from pathlib import Path

p=Path('scripts/test_card_identity_cardmarket_audit.py')
s=p.read_text(encoding='utf-8')
needle='    report = {\n'
insert='''    _focus=next(c for c in cases if c.get("tcgdexId")=="sv10.5b-027")
    print("CRYOGONAL_CASE " + json.dumps(_focus,ensure_ascii=False,sort_keys=True))
    print("CRYOGONAL_PRODUCTS " + json.dumps({str(pid):{"catalog":products.get(pid),"priceGuide":prices.get(pid)} for pid in (835953,835994,836324,836326)},ensure_ascii=False,sort_keys=True))

    report = {
'''
if needle not in s:
    raise SystemExit('report anchor missing')
p.write_text(s.replace(needle,insert,1),encoding='utf-8')
print('focused Cryogonal diagnostic injection applied')
