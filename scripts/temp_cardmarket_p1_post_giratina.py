#!/usr/bin/env python3
from pathlib import Path

path = Path('scripts/test_card_identity_cardmarket_audit.py')
text = path.read_text(encoding='utf-8')
needle = '    over, under = [], []\n'
insert = r'''    focus = next(c for c in cases if c.get("tcgdexId") == "sv03-062")
    print("PALAFIN_CASE " + json.dumps(focus, ensure_ascii=False, sort_keys=True))
    print("PALAFIN_LIVE " + json.dumps(live.get("sv03-062") or {}, ensure_ascii=False, sort_keys=True))
    print("PALAFIN_PRODUCTS " + json.dumps({
        str(pid): {"catalog": products.get(pid), "priceGuide": prices.get(pid)}
        for pid in (725142, 727118, 781858)
    }, ensure_ascii=False, sort_keys=True))
    print("PALAFIN_SHARED_727118 " + json.dumps(sorted(pid_to_cards.get(727118) or []), ensure_ascii=False))
    print("PALAFIN_SHARED_725142 " + json.dumps(sorted(pid_to_cards.get(725142) or []), ensure_ascii=False))

    over, under = [], []
'''
if needle not in text:
    raise SystemExit('audit anchor missing')
path.write_text(text.replace(needle, insert, 1), encoding='utf-8')
print('focused Palafin sv03-062 diagnostic injection applied')
