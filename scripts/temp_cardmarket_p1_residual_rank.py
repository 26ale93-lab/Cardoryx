#!/usr/bin/env python3
from pathlib import Path

p=Path('scripts/test_card_identity_cardmarket_audit.py')
s=p.read_text(encoding='utf-8')
needle='    report = {\n'
insert='''    _skip={"sv09-055","me01-073","ex8-16","sv05-041","sv10.5b-065","swshp-SWSH055","pl3-70"}
    _historical_prefixes=("base1-","base2-","base3-","base5-","gym1-","gym2-","neo1-","neo2-","neo3-","neo4-")
    _rank=[]
    for _c in cases:
        _cid=_c.get("tcgdexId") or ""
        if _c.get("classification")!="P1_AMBIGUOUS_PRODUCT" or _cid in _skip or _cid.startswith(_historical_prefixes):
            continue
        _cur=_c.get("currentCardoryxValue")
        if not isinstance(_cur,(int,float)):
            continue
        for _pid,_g in (_c.get("realPriceGuideValues") or {}).items():
            _v=_g.get("trend") if isinstance(_g,dict) else None
            if isinstance(_v,(int,float)) and _v>0 and int(_pid)!=int(_c.get("currentProductId") or 0):
                _rank.append((abs(_v-_cur),_c,_pid,_v))
    _rank.sort(key=lambda x:x[0],reverse=True)
    print("P1_CASE_COUNT",sum(1 for _c in cases if _c.get("classification")=="P1_AMBIGUOUS_PRODUCT"))
    _seen=set()
    for _delta,_c,_pid,_v in _rank:
        _cid=_c.get("tcgdexId")
        if _cid in _seen:
            continue
        _seen.add(_cid)
        print("RANK " + json.dumps({
            "delta":round(_delta,2),"tcgdexId":_cid,"name":_c.get("name"),"set":_c.get("setNameEN"),
            "currentProductId":_c.get("currentProductId"),"currentTrend":_c.get("currentCardoryxValue"),
            "alternateProductId":int(_pid),"alternateTrend":_v,
            "physicalVariantsByProductId":_c.get("physicalVariantsByProductId"),
            "cardmarketProductCatalog":_c.get("cardmarketProductCatalog")
        },ensure_ascii=False,sort_keys=True))
        if len(_seen)>=25:
            break

    report = {
'''
if needle not in s:
    raise SystemExit('report anchor missing')
p.write_text(s.replace(needle,insert,1),encoding='utf-8')
print('diagnostic rank injection applied')
