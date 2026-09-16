#!/usr/bin/env python3
from pathlib import Path

p=Path('scripts/test_card_identity_cardmarket_audit.py')
s=p.read_text(encoding='utf-8')

old='''        live_exact_base_evidence = bool(
            live_pid and current_pid == live_pid and live_base_rows and
            live_usable_price and not live_explicit_rows
        )

        classification, priority, confidence = "SAFE", None, "HIGH"
'''
new='''        live_exact_base_evidence = bool(
            live_pid and current_pid == live_pid and live_base_rows and
            live_usable_price and not live_explicit_rows
        )

        # A residual ambiguity can also be fully explained by multiple exact
        # stamped products of the same physical card.  This is audit taxonomy
        # only: every product must be independently identified by explicit live
        # stamp metadata and by the official Cardmarket catalogue/Price Guide.
        live_product_rows = [row for row in (live_card_detail.get("variants_detailed") or []) if cm_id(row)]
        live_product_ids = sorted({cm_id(row) for row in live_product_rows if cm_id(row)})
        top_stamps, alternate_stamps = set(), set()
        stamped_rows_complete = bool(live_pid and len(live_product_ids) >= 2 and live_product_rows)
        row_pricing_exact = True
        for live_row in live_product_rows:
            stamps = live_row.get("stamp") or []
            if isinstance(stamps, str):
                stamps = [stamps]
            stamp_key = tuple(sorted(map(str, stamps)))
            if not stamp_key:
                stamped_rows_complete = False
            row_pid = cm_id(live_row)
            row_cm = ((live_row.get("pricing") or {}).get("cardmarket") or {})
            try:
                row_pricing_pid = int(row_cm.get("idProduct") or row_cm.get("id_product"))
            except (TypeError, ValueError):
                row_pricing_pid = None
            if row_pricing_pid != row_pid:
                row_pricing_exact = False
            if row_pid == live_pid:
                top_stamps.add(stamp_key)
            else:
                alternate_stamps.add(stamp_key)
        catalogue_rows = [products.get(pid) for pid in live_product_ids]
        catalogue_complete = bool(live_product_ids and all(catalogue_rows))
        catalogue_expansions = {row.get("idExpansion") for row in catalogue_rows if row}
        catalogue_metacards = {row.get("idMetacard") for row in catalogue_rows if row}
        catalogue_names = {str(row.get("name") or "").strip().lower() for row in catalogue_rows if row}
        official_same_identity = bool(
            catalogue_complete and len(catalogue_expansions) == 1 and
            None not in catalogue_metacards and len(catalogue_metacards) == 1 and
            len(catalogue_names) == 1
        )
        exact_product_prices = all(
            prices.get(pid) and any(
                isinstance((prices.get(pid) or {}).get(key), (int, float)) and
                (prices.get(pid) or {}).get(key) > 0
                for key in ("trend", "avg7", "avg30", "avg", "low")
            )
            for pid in live_product_ids
        ) if live_product_ids else False
        exact_stamped_product_group = bool(
            live_pid == current_pid and stamped_rows_complete and row_pricing_exact and
            top_stamps and alternate_stamps and top_stamps.isdisjoint(alternate_stamps) and
            official_same_identity and exact_product_prices
        )

        classification, priority, confidence = "SAFE", None, "HIGH"
'''
if old not in s: raise SystemExit('evidence anchor not found')
s=s.replace(old,new,1)

old='''        elif live_exact_base_evidence and not snapshot_exact_alternate_product:
            classification, priority, confidence = "SAFE", None, "HIGH"
'''
new='''        elif exact_stamped_product_group:
            classification, priority, confidence = "EXACT_STAMPED_PRODUCT_GROUP", "P2", "HIGH"
            resolved_pid = live_pid
            resolved_value = next(
                (live_cm.get(key) for key in ("trend", "avg7", "avg30", "avg", "low")
                 if isinstance(live_cm.get(key), (int, float)) and live_cm.get(key) > 0),
                None,
            )
            reason = ("Più prodotti Cardmarket rappresentano la stessa metacard/espansione ma sono "
                      "fisicamente distinti da stamp espliciti e disgiunti; ogni productId possiede "
                      "Price Guide reale e coincide con il productId della propria riga live.")
            action = "Nessun mapping aggiuntivo: mantenere i productId separati per stamp esatto."
        elif live_exact_base_evidence and not snapshot_exact_alternate_product:
            classification, priority, confidence = "SAFE", None, "HIGH"
'''
if old not in s: raise SystemExit('classification anchor not found')
s=s.replace(old,new,1)

old='''            "liveExplicitVariantUsesSameProduct": bool(live_explicit_rows),
            "snapshotExactAlternateProductProtected": snapshot_exact_alternate_product,
'''
new='''            "liveExplicitVariantUsesSameProduct": bool(live_explicit_rows),
            "snapshotExactAlternateProductProtected": snapshot_exact_alternate_product,
            "exactStampedProductGroup": exact_stamped_product_group,
            "exactStampedProductIds": live_product_ids if exact_stamped_product_group else [],
            "exactStampedTopStamps": [list(value) for value in sorted(top_stamps)] if exact_stamped_product_group else [],
            "exactStampedAlternateStamps": [list(value) for value in sorted(alternate_stamps)] if exact_stamped_product_group else [],
'''
if old not in s: raise SystemExit('case fields anchor not found')
s=s.replace(old,new,1)

old='''        "classificationTotals": {name: counts.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
'''
new='''        "classificationTotals": {name: counts.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "EXACT_STAMPED_PRODUCT_GROUP", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
'''
if old not in s: raise SystemExit('classification totals anchor not found')
s=s.replace(old,new,1)

old='''        "multiProductClassificationTotals": {name: multi_classifications.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
        "historical4252CandidateClassificationTotals": {name: historical_classifications.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
'''
new='''        "multiProductClassificationTotals": {name: multi_classifications.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "EXACT_STAMPED_PRODUCT_GROUP", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
        "historical4252CandidateClassificationTotals": {name: historical_classifications.get(name, 0) for name in ("SAFE", "EXACT_ALTERNATE_PRODUCT", "EXACT_STAMPED_PRODUCT_GROUP", "P0_WRONG_PRODUCT", "P1_AMBIGUOUS_PRODUCT", "SOURCE_CONFLICT", "UNMAPPED_EXACT_PRODUCT")},
'''
if old not in s: raise SystemExit('secondary totals anchor not found')
s=s.replace(old,new,1)

old='''        "p1AmbiguousProductIds": [c["tcgdexId"] for c in p1],
        "sourceConflicts": [c for c in cases if c["classification"] == "SOURCE_CONFLICT"],
'''
new='''        "p1AmbiguousProductIds": [c["tcgdexId"] for c in p1],
        "exactStampedProductGroups": [c for c in cases if c["classification"] == "EXACT_STAMPED_PRODUCT_GROUP"],
        "sourceConflicts": [c for c in cases if c["classification"] == "SOURCE_CONFLICT"],
'''
if old not in s: raise SystemExit('report list anchor not found')
s=s.replace(old,new,1)

p.write_text(s,encoding='utf-8')
print('patched',p)
