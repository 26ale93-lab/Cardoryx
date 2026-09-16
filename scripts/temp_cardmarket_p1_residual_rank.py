#!/usr/bin/env python3
from pathlib import Path

path = Path('scripts/test_card_identity_cardmarket_audit.py')
text = path.read_text(encoding='utf-8')
needle = '    p1 = [case for case in cases if case["classification"] == "P1_AMBIGUOUS_PRODUCT"]\n'
insert = r'''    p1 = [case for case in cases if case["classification"] == "P1_AMBIGUOUS_PRODUCT"]

    # Temporary read-only ranking diagnostic. Exclude legacy Base/Gym/Neo
    # clusters already known to require separate taxonomy work. Rank only by
    # observed Cardmarket trend divergence; never infer a corrected product.
    residual = []
    for c in p1:
        cid = str(c.get("tcgdexId") or "")
        low = cid.lower()
        if low.startswith(("base", "gym", "neo")):
            continue
        deltas = [abs(v) for v in (c.get("trendDeltaVersusCurrent") or {}).values()
                  if isinstance(v, (int, float))]
        spread = max(deltas, default=0.0)
        residual.append((spread, c))
    residual.sort(key=lambda item: (-item[0], item[1].get("tcgdexId") or ""))
    print("P1_RESIDUAL_COUNT " + str(len(residual)))
    print("P1_RESIDUAL_TOP_BEGIN")
    for spread, c in residual[:50]:
        compact = {
            "tcgdexId": c.get("tcgdexId"),
            "name": c.get("name"),
            "setId": c.get("setId"),
            "localId": c.get("localId"),
            "currentProductId": c.get("currentProductId"),
            "alternateProductIds": c.get("alternateProductIds"),
            "allProductIds": c.get("allProductIds"),
            "baseRowProductIds": c.get("baseRowProductIdsAccordingToTcgdex"),
            "sharedProductWithTcgdexIds": c.get("sharedProductWithTcgdexIds"),
            "currentValue": c.get("currentCardoryxValue"),
            "trendDeltas": c.get("trendDeltaVersusCurrent"),
            "maxAbsTrendDelta": spread,
            "reason": c.get("reason"),
            "physicalVariantsByProductId": c.get("physicalVariantsByProductId"),
            "cardmarketProductCatalog": c.get("cardmarketProductCatalog"),
            "realPriceGuideValues": c.get("realPriceGuideValues"),
        }
        print("P1_RESIDUAL " + json.dumps(compact, ensure_ascii=False, sort_keys=True))
    print("P1_RESIDUAL_TOP_END")
'''
if needle not in text:
    raise SystemExit('P1 anchor missing')
path.write_text(text.replace(needle, insert, 1), encoding='utf-8')
print('post-Darmanitan P1 residual rank injection applied')
