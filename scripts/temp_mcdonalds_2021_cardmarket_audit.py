#!/usr/bin/env python3
from pathlib import Path
p=Path('scripts/test_card_identity_cardmarket_audit.py')
s=p.read_text(encoding='utf-8')
needle='    report = {\n'
insert='''    _mcd=[c for c in cases if str(c.get("tcgdexId") or "").startswith("2021swsh-")]
    print("MCD2021_SUMMARY " + json.dumps({
        "totalCases":len(_mcd),
        "classifications":dict(Counter(c.get("classification") for c in _mcd)),
        "p1Ids":[c.get("tcgdexId") for c in _mcd if c.get("classification")=="P1_AMBIGUOUS_PRODUCT"]
    },ensure_ascii=False,sort_keys=True))
    for _c in sorted(_mcd,key=lambda x:str(x.get("tcgdexId") or "")):
        print("MCD2021_CASE " + json.dumps({
            "tcgdexId":_c.get("tcgdexId"),"name":_c.get("name"),"localId":_c.get("localId"),
            "classification":_c.get("classification"),"currentProductId":_c.get("currentProductId"),
            "currentCardoryxValue":_c.get("currentCardoryxValue"),
            "baseRows":_c.get("baseRowProductIdsAccordingToTcgdex"),
            "allProductIds":_c.get("allProductIds"),
            "physicalVariantsByProductId":_c.get("physicalVariantsByProductId"),
            "cardmarketProductCatalog":_c.get("cardmarketProductCatalog"),
            "realPriceGuideValues":_c.get("realPriceGuideValues"),
            "reason":_c.get("reason")
        },ensure_ascii=False,sort_keys=True))

    report = {
'''
if needle not in s: raise SystemExit('report anchor missing')
p.write_text(s.replace(needle,insert,1),encoding='utf-8')
print('McDonalds 2021 diagnostic injection applied')
