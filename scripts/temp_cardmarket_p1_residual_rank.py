#!/usr/bin/env python3
from pathlib import Path

path = Path('scripts/test_card_identity_cardmarket_audit.py')
text = path.read_text(encoding='utf-8')
needle = '    over, under = [], []\n'
insert = r'''    def compact_name(value):
        return re.sub(r"[^a-z0-9]+", "", str(value or "").lower())

    wrong_name = []
    excluded_prefixes = ("base", "gym", "neo")
    excluded_ids = {
        "sv09-055", "me01-073", "ex8-16", "sv05-041", "sv10.5b-065",
        "swshp-SWSH055", "pl3-70", "sv10.5b-027", "sv10.5b-014",
    }
    for case in p1:
        cid = str(case.get("tcgdexId") or "")
        if cid.startswith(excluded_prefixes) or cid in excluded_ids:
            continue
        current_pid = case.get("currentProductId")
        product = products.get(current_pid) if current_pid else None
        card_name = str(case.get("name") or "")
        product_name = str((product or {}).get("name") or "").split(" [", 1)[0]
        if current_pid and product_name and compact_name(product_name) != compact_name(card_name):
            alts = []
            for pid in case.get("alternateProductIds") or []:
                p = products.get(pid) or {}
                pg = prices.get(pid) or {}
                alts.append({
                    "idProduct": pid,
                    "name": p.get("name"),
                    "idExpansion": p.get("idExpansion"),
                    "idMetacard": p.get("idMetacard"),
                    "trend": pg.get("trend"),
                    "trendHolo": pg.get("trend-holo"),
                })
            cur_pg = prices.get(current_pid) or {}
            wrong_name.append({
                "tcgdexId": cid,
                "setId": case.get("setId"),
                "localId": case.get("localId"),
                "cardName": card_name,
                "currentProductId": current_pid,
                "currentProductName": (product or {}).get("name"),
                "currentExpansion": (product or {}).get("idExpansion"),
                "currentMetacard": (product or {}).get("idMetacard"),
                "currentTrend": cur_pg.get("trend"),
                "currentTrendHolo": cur_pg.get("trend-holo"),
                "alternates": alts,
                "reason": case.get("reason"),
            })
    wrong_name.sort(key=lambda row: (
        -max([abs((a.get("trend") or 0) - (row.get("currentTrend") or 0)) for a in row["alternates"]] or [0]),
        row["tcgdexId"],
    ))
    print("WRONG_NAME_COUNT " + str(len(wrong_name)))
    for row in wrong_name[:40]:
        print("WRONG_NAME_CASE " + json.dumps(row, ensure_ascii=False, sort_keys=True))

    giratina_catalog = []
    for pid, product in products.items():
        name = str((product or {}).get("name") or "")
        if int((product or {}).get("idExpansion") or 0) == 5093 and name.startswith("Giratina VSTAR"):
            pg = prices.get(pid) or {}
            giratina_catalog.append({
                "idProduct": pid,
                "name": name,
                "idExpansion": product.get("idExpansion"),
                "idMetacard": product.get("idMetacard"),
                "dateAdded": product.get("dateAdded"),
                "trend": pg.get("trend"),
                "trendHolo": pg.get("trend-holo"),
                "low": pg.get("low"),
            })
    print("GIRATINA_VSTAR_LOST_ORIGIN " + json.dumps(sorted(giratina_catalog, key=lambda x: x["idProduct"]), ensure_ascii=False, sort_keys=True))

    over, under = [], []
'''
if needle not in text:
    raise SystemExit('ranking anchor missing')
path.write_text(text.replace(needle, insert, 1), encoding='utf-8')
print('wrong-card-name P1 + Giratina catalogue diagnostic injection applied')
