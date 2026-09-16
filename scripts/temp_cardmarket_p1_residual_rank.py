#!/usr/bin/env python3
from pathlib import Path

path = Path('scripts/test_card_identity_cardmarket_audit.py')
text = path.read_text(encoding='utf-8')
needle = '    over, under = [], []\n'
insert = r'''    focus = next(c for c in cases if c.get("tcgdexId") == "swsh11-201")
    print("GIRATINA_CASE " + json.dumps(focus, ensure_ascii=False, sort_keys=True))
    print("GIRATINA_LIVE " + json.dumps(live.get("swsh11-201") or {}, ensure_ascii=False, sort_keys=True))
    print("GIRATINA_PRODUCTS " + json.dumps({
        str(pid): {"catalog": products.get(pid), "priceGuide": prices.get(pid)}
        for pid in (670816, 674207)
    }, ensure_ascii=False, sort_keys=True))
    print("GIRATINA_SHARED " + json.dumps(sorted(pid_to_cards.get(670816) or []), ensure_ascii=False))

    over, under = [], []
'''
if needle not in text:
    raise SystemExit('ranking anchor missing')
path.write_text(text.replace(needle, insert, 1), encoding='utf-8')
print('focused Giratina swsh11-201 diagnostic injection applied')
