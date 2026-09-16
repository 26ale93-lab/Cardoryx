#!/usr/bin/env python3
from pathlib import Path

p = Path('scripts/test_card_identity_cardmarket_audit.py')
s = p.read_text(encoding='utf-8')
needle = '    report = {\n'
insert = r'''    _excluded_exact = {
        "sv09-055", "me01-073", "ex8-16", "sv05-041", "sv10.5b-065",
        "swshp-SWSH055", "pl3-70", "sv10.5b-027",
    }

    def _econ_score(case):
        vals = []
        v = case.get("currentCardoryxValue")
        if isinstance(v, (int, float)):
            vals.append(abs(float(v)))
        for row in (case.get("realPriceGuideValues") or {}).values():
            if not isinstance(row, dict):
                continue
            for k in ("trend", "trend-holo", "low", "low-holo", "avg", "avg-holo", "avg7", "avg7-holo", "avg30", "avg30-holo"):
                x = row.get(k)
                if isinstance(x, (int, float)):
                    vals.append(abs(float(x)))
        return max(vals) if vals else 0.0

    _p1_all = [c for c in cases if c.get("classification") == "P1_AMBIGUOUS_PRODUCT"]
    _p1_filtered = []
    for c in _p1_all:
        tid = str(c.get("tcgdexId") or "")
        sid = str(c.get("setId") or "")
        if tid in _excluded_exact:
            continue
        if sid.startswith(("base", "gym", "neo")) or tid.startswith(("base", "gym", "neo")):
            continue
        _p1_filtered.append(c)

    _p1_filtered.sort(key=lambda c: (-_econ_score(c), str(c.get("tcgdexId") or "")))
    print("P1_RESIDUAL_SUMMARY " + json.dumps({
        "p1All": len(_p1_all),
        "p1AfterExclusions": len(_p1_filtered),
        "excludedPrefixes": ["base*", "gym*", "neo*"],
        "excludedExact": sorted(_excluded_exact),
    }, ensure_ascii=False, sort_keys=True))

    for rank, c in enumerate(_p1_filtered[:80], 1):
        compact = {
            "rank": rank,
            "score": _econ_score(c),
            "tcgdexId": c.get("tcgdexId"),
            "setId": c.get("setId"),
            "setNameEN": c.get("setNameEN"),
            "localId": c.get("localId"),
            "name": c.get("name"),
            "rarity": c.get("rarity"),
            "currentProductId": c.get("currentProductId"),
            "alternateProductIds": c.get("alternateProductIds"),
            "allProductIds": c.get("allProductIds"),
            "currentCardoryxValue": c.get("currentCardoryxValue"),
            "realPriceGuideValues": c.get("realPriceGuideValues"),
            "cardmarketProductCatalog": c.get("cardmarketProductCatalog"),
            "physicalVariantsByProductId": c.get("physicalVariantsByProductId"),
            "tcgdexVariantsDetailed": c.get("tcgdexVariantsDetailed"),
            "reason": c.get("reason"),
            "recommendedAction": c.get("recommendedAction"),
        }
        print("P1_RESIDUAL_CASE " + json.dumps(compact, ensure_ascii=False, sort_keys=True))

    report = {
'''
if needle not in s:
    raise SystemExit('report anchor missing')
p.write_text(s.replace(needle, insert, 1), encoding='utf-8')
print('P1 residual ranking diagnostic injection applied')
