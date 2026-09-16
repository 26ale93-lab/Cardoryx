#!/usr/bin/env python3
from __future__ import annotations

import argparse
import concurrent.futures
import importlib.util
import json
import re
import subprocess
import sys
import unicodedata
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
TEST = ROOT / "scripts" / "test_card_identity_cardmarket_audit.py"
OUT = ROOT / "artifacts" / "ex4_verified_batch_audit.json"
CM_PRODUCTS = "https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json"
CM_PRICES = "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json"
TCGDEX_API = "https://api.tcgdex.net/v2/en/cards"
EX4_EXPANSION = 1542
ALREADY_FIXED = {"ex4-6", "ex4-7", "ex4-89", "ex4-94", "ex4-95"}


def args():
    p = argparse.ArgumentParser()
    p.add_argument("--tcgdex-db", type=Path, required=True)
    p.add_argument("--audit", action="store_true")
    p.add_argument("--apply", action="store_true")
    p.add_argument("--report", type=Path, default=OUT)
    return p.parse_args()


def get_json(url, timeout=300):
    req = urllib.request.Request(url, headers={"User-Agent": "Cardoryx-EX4-Verified-Batch/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def norm(value):
    s = unicodedata.normalize("NFKD", str(value or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"[^a-z0-9]+", "", s)


def product_base_name(row):
    return str((row or {}).get("name") or "").split(" [", 1)[0]


def english_name(card):
    value = card.get("name") or ""
    if isinstance(value, dict):
        return str(value.get("en") or next(iter(value.values()), ""))
    return str(value)


def cm_ids(card):
    out = []
    for row in card.get("variants_detailed") or []:
        try:
            pid = int(((row.get("thirdParty") or {}).get("cardmarket")))
        except (TypeError, ValueError):
            continue
        if pid not in out:
            out.append(pid)
    return out


def load_snapshot(db):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("vf", ROOT / "scripts" / "test_variant_finish_audit.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_official_database(db)


def live_card(card_id):
    try:
        return card_id, get_json(f"{TCGDEX_API}/{urllib.parse.quote(card_id)}", timeout=60), None
    except Exception as exc:
        return card_id, None, str(exc)


def current_pid(live):
    cm = (((live or {}).get("pricing") or {}).get("cardmarket") or {})
    try:
        return int(cm.get("idProduct") or cm.get("id_product"))
    except (TypeError, ValueError):
        return None


def js_number(value):
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return json.dumps(value, ensure_ascii=False)
    return json.dumps(value, ensure_ascii=False)


def price_fields(row):
    keys = ["trend", "avg7", "avg30", "avg", "low", "trend-holo", "avg7-holo", "avg30-holo", "avg-holo", "low-holo"]
    return {k: row.get(k) for k in keys if k in row}


def audit(db):
    cards, parse_errors, snapshot = load_snapshot(db)
    ex4 = [c for c in cards if str((c.get("set") or {}).get("id") or "").lower() == "ex4"]
    product_root = get_json(CM_PRODUCTS)
    price_root = get_json(CM_PRICES)
    products = product_root.get("products", [])
    prices_list = price_root.get("priceGuides", price_root.get("priceGuide", []))
    byid = {int(p["idProduct"]): p for p in products if p.get("idProduct") is not None}
    prices = {int(p["idProduct"]): p for p in prices_list if p.get("idProduct") is not None}
    western = [p for p in products if int(p.get("idExpansion") or 0) == EX4_EXPANSION]

    live = {}
    live_errors = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=16) as pool:
        futures = [pool.submit(live_card, c["id"]) for c in ex4]
        for f in concurrent.futures.as_completed(futures):
            cid, value, error = f.result()
            if value:
                live[cid] = value
            if error:
                live_errors[cid] = error

    rows = []
    candidates = []
    for card in sorted(ex4, key=lambda c: int(re.sub(r"\D", "", str(c.get("localId") or "999")) or 999)):
        cid = card["id"]
        name = english_name(card)
        matches = [p for p in western if norm(product_base_name(p)) == norm(name)]
        target = matches[0] if len(matches) == 1 else None
        live_value = live.get(cid) or {}
        cur = current_pid(live_value)
        variant_ids = set(cm_ids(card)) | set(cm_ids(live_value))
        current_row = byid.get(cur) if cur else None
        matching_meta_variants = []
        if target:
            target_meta = target.get("idMetacard")
            for pid in sorted(variant_ids):
                prow = byid.get(pid)
                if not prow:
                    continue
                if prow.get("idMetacard") == target_meta and norm(product_base_name(prow)) == norm(name):
                    matching_meta_variants.append(pid)
        target_pid = int(target["idProduct"]) if target else None
        target_price = prices.get(target_pid) if target_pid else None
        current_is_wrong_expansion = bool(current_row and int(current_row.get("idExpansion") or 0) != EX4_EXPANSION)
        current_differs = bool(cur and target_pid and cur != target_pid)
        has_meta_evidence = bool(matching_meta_variants)
        unique_exact = len(matches) == 1
        already_fixed = cid in ALREADY_FIXED
        price_available = bool(target_price and any(isinstance(target_price.get(k), (int, float)) for k in ("trend", "avg7", "avg30", "avg", "low")))
        eligible = bool(unique_exact and current_differs and current_is_wrong_expansion and has_meta_evidence and price_available and not already_fixed)
        row = {
            "tcgdexId": cid,
            "localId": card.get("localId"),
            "name": name,
            "rarity": card.get("rarity"),
            "currentProductId": cur,
            "currentProduct": current_row,
            "targetProductId": target_pid,
            "targetProduct": target,
            "targetPrice": price_fields(target_price or {}),
            "uniqueExactNameInExpansion1542": unique_exact,
            "matchingMetacardVariantIds": matching_meta_variants,
            "currentOutsideExpansion1542": current_is_wrong_expansion,
            "currentDiffersFromTarget": current_differs,
            "priceAvailable": price_available,
            "alreadyFixed": already_fixed,
            "eligible": eligible,
        }
        rows.append(row)
        if eligible:
            candidates.append(row)

    report = {
        "setId": "ex4",
        "snapshot": snapshot,
        "parseErrors": len(parse_errors),
        "cards": len(ex4),
        "catalogueProductsExpansion1542": len(western),
        "liveErrors": live_errors,
        "uniqueExactNameMatches": sum(1 for r in rows if r["uniqueExactNameInExpansion1542"]),
        "alreadyFixed": sorted(ALREADY_FIXED),
        "eligibleCount": len(candidates),
        "eligibleIds": [r["tcgdexId"] for r in candidates],
        "candidates": candidates,
        "rows": rows,
    }
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in {"rows", "candidates"}}, ensure_ascii=False, indent=2))
    print("ELIGIBLE")
    for r in candidates:
        print(json.dumps({k: r[k] for k in ("tcgdexId", "localId", "name", "currentProductId", "targetProductId", "matchingMetacardVariantIds")}, ensure_ascii=False))
    return report


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 marker, got {count}")
    return text.replace(old, new, 1)


def apply(report):
    candidates = report.get("candidates") or []
    if not candidates:
        raise SystemExit("No eligible EX4 candidates; refusing empty production patch")
    for row in candidates:
        required = [row.get("tcgdexId"), row.get("localId"), row.get("name"), row.get("currentProductId"), row.get("targetProductId")]
        if not all(required) or not row.get("uniqueExactNameInExpansion1542") or not row.get("matchingMetacardVariantIds") or not row.get("priceAvailable"):
            raise SystemExit(f"Unsafe candidate in report: {row.get('tcgdexId')}")

    source = INDEX.read_text(encoding="utf-8")
    test = TEST.read_text(encoding="utf-8")

    override_lines = []
    guide_entries = []
    conflict_lines = []
    confirmed_lines = []
    expected_lines = []
    fixture_rows = []

    verified_stamp = "2026-09-16T13:44:00+0200"
    for r in candidates:
        cid = r["tcgdexId"]
        local = str(r["localId"]).zfill(3)
        wrong = int(r["currentProductId"])
        correct = int(r["targetProductId"])
        name = r["name"]
        nm = norm(name)
        pricing = {"idProduct": correct, **(r.get("targetPrice") or {})}
        override_lines.append(f"  {json.dumps(cid)}:{{setId:'ex4',localId:{json.dumps(local)},conflictingProduct:{wrong},baseProduct:{correct}}}")
        pricing_js = json.dumps(pricing, ensure_ascii=False, separators=(",", ":"))
        guide_entries.append(
            f"  {json.dumps(cid)}:{{\n"
            f"    setId:'ex4',localId:{json.dumps(local)},name:{json.dumps(name, ensure_ascii=False)},productId:{correct},\n"
            f"    verified:{json.dumps(verified_stamp)},\n"
            f"    source:{json.dumps('Cardmarket Product Catalogue + Price Guide · EX Team Magma vs Team Aqua · exact metacard-verified product ' + str(correct), ensure_ascii=False)},\n"
            f"    sourceUrl:'https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json',\n"
            f"    pricing:{pricing_js}\n"
            f"  }}"
        )
        conflict_lines.append(f"    [{json.dumps(cid)},{json.dumps(str(int(str(r['localId']))))},{json.dumps(nm)},{wrong},{correct}]")
        confirmed_lines.append(f"    {json.dumps(cid)}: {{\"base\": {correct}, \"alternate\": {wrong}, \"stamp\": \"wrong-card-identity\", \"cardmarketCode\": \"EX4-{r['localId']}\"}}")
        expected_lines.append(f"    {json.dumps(cid)}: {{\"setId\": \"ex4\", \"localId\": {json.dumps(local)}, \"conflictingProduct\": {wrong}, \"baseProduct\": {correct}}}")
        fixture_rows.append(
            "        {" + ",".join([
                f"\"id\":{json.dumps(cid)}", f"\"tcgdexId\":{json.dumps(cid)}", f"\"name\":{json.dumps(name, ensure_ascii=False)}",
                f"\"localId\":{json.dumps(str(r['localId']))}", "\"set\":{\"id\":\"ex4\",\"name\":\"EX Team Magma vs Team Aqua\"}",
                f"\"wrong\":{wrong}", f"\"correct\":{correct}",
            ]) + "},"
        )

    old = "  'ex4-95':{setId:'ex4',localId:'095',conflictingProduct:275872,baseProduct:276072}\n};"
    new = "  'ex4-95':{setId:'ex4',localId:'095',conflictingProduct:275872,baseProduct:276072},\n" + ",\n".join(override_lines) + "\n};"
    source = replace_once(source, old, new, "override registry")

    old = "  }\n};\nfunction exactCardmarketGuideIdentity(card,id,guide){"
    new = "  },\n" + ",\n".join(guide_entries) + "\n};\nfunction exactCardmarketGuideIdentity(card,id,guide){"
    source = replace_once(source, old, new, "price guide registry")

    old = "    ['ex4-95','95','swampertex',275872,276072]\n  ];"
    new = "    ['ex4-95','95','swampertex',275872,276072],\n" + ",\n".join(conflict_lines) + "\n  ];"
    source = replace_once(source, old, new, "EX4 conflict guard")

    old = '    "ex4-95": {"base": 276072, "alternate": 275872, "stamp": "wrong-card-identity", "cardmarketCode": "MA95"},\n}'
    new = '    "ex4-95": {"base": 276072, "alternate": 275872, "stamp": "wrong-card-identity", "cardmarketCode": "MA95"},\n' + ",\n".join(confirmed_lines) + "\n}"
    test = replace_once(test, old, new, "confirmed conflicts")

    old = '    "ex4-95": {"setId": "ex4", "localId": "095", "conflictingProduct": 275872, "baseProduct": 276072},\n}'
    new = '    "ex4-95": {"setId": "ex4", "localId": "095", "conflictingProduct": 275872, "baseProduct": 276072},\n' + ",\n".join(expected_lines) + "\n}"
    test = replace_once(test, old, new, "expected overrides")

    marker = '    harness = r"""\n'
    fixture = '    fixtures["ex4_verified_batch"] = [\n' + "\n".join(fixture_rows) + '\n    ]\n    for card in fixtures["ex4_verified_batch"]:\n        card["variants"] = {"normal": False, "holo": True, "reverse": True}\n        card["variants_detailed"] = [{"type":"holo","thirdParty":{"cardmarket":card["wrong"]},"pricing":{"cardmarket":{"idProduct":card["wrong"],"trend":1}}}]\n        card["pricing"] = {"cardmarket":{"idProduct":card["wrong"],"trend":1}}\n    harness = r"""\n'
    test = replace_once(test, marker, fixture, "runtime fixture marker")

    marker = "const normal=r.cardmarketValueForCardVariant(p,'Normal');\n"
    checks = """for(const card of fixtures.ex4_verified_batch){
  const o=r.verifiedBaseCardmarketProductOverride(card);
  assert.strictEqual(o?.pricing?.idProduct,card.correct);
  assert.strictEqual(r.resolvedCardmarketPricingForCard(card)?.idProduct,card.correct);
  assert.strictEqual(r.knownCardmarketIdentityConflict(card,card.wrong)?.kind,'identity-mismatch');
  assert.strictEqual(r.knownCardmarketIdentityConflict({...card,id:card.id+'-wrong',tcgdexId:card.tcgdexId+'-wrong',localId:'999'},card.correct)?.kind,'identity-mismatch');
  assert.strictEqual(r.verifiedBaseCardmarketProductOverride({...card,name:card.name+' wrong'}),null);
}
const normal=r.cardmarketValueForCardVariant(p,'Normal');
"""
    test = replace_once(test, marker, checks, "runtime check marker")

    total = 11 + len(candidates)
    test = test.replace("Base Cardmarket override registry differs from the eleven audited P0 identities", f"Base Cardmarket override registry differs from the {total} audited P0 identities", 1)
    test = test.replace('"p0Regression": {"before": 11, "after": len(known_phase_a_p0),', f'"p0Regression": {{"before": {total}, "after": len(known_phase_a_p0),', 1)
    test = test.replace('"productionChangeScope": "Eleven exact Cardmarket base-product identity overrides; latest block adds five exact EX Team Magma vs Team Aqua identities",', f'"productionChangeScope": "{total} exact Cardmarket base-product identity overrides; latest batch adds {len(candidates)} metacard-verified EX Team Magma vs Team Aqua identities",', 1)

    INDEX.write_text(source, encoding="utf-8")
    TEST.write_text(test, encoding="utf-8")
    print(json.dumps({"applied": len(candidates), "ids": [r["tcgdexId"] for r in candidates], "totalExpectedOverrides": total}, ensure_ascii=False, indent=2))


def main():
    a = args()
    if a.audit:
        audit(a.tcgdex_db)
        return
    if a.apply:
        report = json.loads(a.report.read_text(encoding="utf-8"))
        apply(report)
        return
    raise SystemExit("Choose --audit or --apply")


if __name__ == "__main__":
    main()
