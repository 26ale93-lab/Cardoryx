#!/usr/bin/env python3
from pathlib import Path

p=Path('scripts/test_card_identity_cardmarket_audit.py')
s=p.read_text(encoding='utf-8')
old="""    live_targets = (multi_ids - historical_ids) | set(CONFIRMED_BASE_PRODUCT_CONFLICTS) | {\"sm12-29\", \"sm12-54\", \"sm12-237\"} | PROTECTED_REVERSE
"""
new="""    # Shared-product ambiguity is only actionable when current live TCGdex can
    # prove the top-level Cardmarket product against an exact physical base row.
    # Fetch shared identities as evidence; failed/missing live evidence remains
    # fail-closed and cannot downgrade a P1.
    live_targets = ((multi_ids - historical_ids) | shared_identity_ids |
                    set(CONFIRMED_BASE_PRODUCT_CONFLICTS) |
                    {\"sm12-29\", \"sm12-54\", \"sm12-237\"} | PROTECTED_REVERSE)
"""
if old not in s: raise SystemExit('live_targets anchor not found')
s=s.replace(old,new,1)

old="""        base_ids = sorted({cm_id(row) for row in (card.get(\"variants_detailed\") or []) if cm_id(row) and is_base_row(row)})
        alt_ids = sorted(set(ids) - ({current_pid} if current_pid else set()))
        shared = sorted({other for pid in ids for other in pid_to_cards[pid] if other != card_id})
        classification, priority, confidence = \"SAFE\", None, \"HIGH\"
"""
new="""        base_ids = sorted({cm_id(row) for row in (card.get(\"variants_detailed\") or []) if cm_id(row) and is_base_row(row)})
        alt_ids = sorted(set(ids) - ({current_pid} if current_pid else set()))
        shared = sorted({other for pid in ids for other in pid_to_cards[pid] if other != card_id})

        # Strict live evidence can clear stale snapshot ambiguity only when all
        # identity signals agree on the same physical base product. Special
        # stamp/foil/1st Edition rows never qualify and a reused product stays P1.
        live_card_detail = live.get(card_id) or {}
        live_cm = ((live_card_detail.get(\"pricing\") or {}).get(\"cardmarket\") or {})
        try:
            live_pid = int(live_cm.get(\"idProduct\") or live_cm.get(\"id_product\"))
        except (TypeError, ValueError):
            live_pid = None
        live_base_rows = []
        live_explicit_rows = []
        for live_row in live_card_detail.get(\"variants_detailed\") or []:
            pid = cm_id(live_row)
            pricing_cm = ((live_row.get(\"pricing\") or {}).get(\"cardmarket\") or {})
            try:
                pricing_pid = int(pricing_cm.get(\"idProduct\") or pricing_cm.get(\"id_product\"))
            except (TypeError, ValueError):
                pricing_pid = None
            if is_base_row(live_row):
                if pid == live_pid and pricing_pid == live_pid:
                    live_base_rows.append(live_row)
            elif pid == live_pid:
                live_explicit_rows.append(live_row)
        live_usable_price = any(
            isinstance(live_cm.get(key), (int, float)) and live_cm.get(key) > 0
            for key in (\"trend\", \"avg7\", \"avg30\", \"avg\", \"low\")
        )
        live_exact_base_evidence = bool(
            live_pid and current_pid == live_pid and live_base_rows and
            live_usable_price and not live_explicit_rows
        )

        classification, priority, confidence = \"SAFE\", None, \"HIGH\"
"""
if old not in s: raise SystemExit('base evidence anchor not found')
s=s.replace(old,new,1)

old="""        elif not current_pid and len(ids) > 1:
            classification, priority, confidence = \"P1_AMBIGUOUS_PRODUCT\", \"P1\", \"LOW\"
            reason = \"La sorgente espone più prodotti ma non un product ID top-level corrente verificabile.\"
            action = \"Restare fail-closed finché il prodotto principale non è dimostrato.\"
        elif shared and current_pid and current_pid in shared_pids:
"""
new="""        elif live_exact_base_evidence:
            classification, priority, confidence = \"SAFE\", None, \"HIGH\"
            resolved_pid = live_pid
            resolved_value = next(
                (live_cm.get(key) for key in (\"trend\", \"avg7\", \"avg30\", \"avg\", \"low\")
                 if isinstance(live_cm.get(key), (int, float)) and live_cm.get(key) > 0),
                None,
            )
            reason = (\"TCGdex live conferma lo stesso productId Cardmarket sia a livello top-level sia \"
                      \"in una riga fisica base unstamped/unfoiled, con prezzo reale disponibile e senza \"
                      \"riuso dello stesso prodotto da parte di varianti speciali.\")
            action = \"Nessuna modifica di produzione: identità base live esatta, falso positivo dello snapshot statico.\"
        elif not current_pid and len(ids) > 1:
            classification, priority, confidence = \"P1_AMBIGUOUS_PRODUCT\", \"P1\", \"LOW\"
            reason = \"La sorgente espone più prodotti ma non un product ID top-level corrente verificabile.\"
            action = \"Restare fail-closed finché il prodotto principale non è dimostrato.\"
        elif shared and current_pid and current_pid in shared_pids:
"""
if old not in s: raise SystemExit('classification anchor not found')
s=s.replace(old,new,1)

old='''            "baseOverrideApplied": applied_override, "resolvedProductId": resolved_pid,
            "resolvedCardoryxValue": resolved_value, "baseOverrideGuardTests": override_tests,
'''
new='''            "baseOverrideApplied": applied_override, "resolvedProductId": resolved_pid,
            "resolvedCardoryxValue": resolved_value, "baseOverrideGuardTests": override_tests,
            "liveExactBaseEvidence": live_exact_base_evidence,
            "liveExactBaseProductId": live_pid if live_exact_base_evidence else None,
            "liveExactBasePriceAvailable": live_usable_price,
            "liveExplicitVariantUsesSameProduct": bool(live_explicit_rows),
'''
if old not in s: raise SystemExit('case fields anchor not found')
s=s.replace(old,new,1)

old='''        "classificationTotals": {name: counts.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
'''
new='''        "classificationTotals": {name: counts.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
        "liveExactBaseEvidence": {
            "count": sum(bool(case.get("liveExactBaseEvidence")) for case in cases),
            "ids": [case["tcgdexId"] for case in cases if case.get("liveExactBaseEvidence")],
            "policy": "live top-level product == live physical base-row product == live row pricing product; usable real price; no explicit special row reuses product",
        },
'''
if old not in s: raise SystemExit('report totals anchor not found')
s=s.replace(old,new,1)

p.write_text(s,encoding='utf-8')
print('patched',p)
