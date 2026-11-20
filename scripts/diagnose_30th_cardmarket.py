#!/usr/bin/env python3
"""Read-only probe: 30th Celebration Cardmarket pricing in TCGdex IT/EN."""
import json
import sys
import urllib.error
import urllib.request

SAMPLES = ["30th-001", "30th-015", "30th-030", "30th-c-001", "30th-c-015", "30th-c-030"]
URL = "https://api.tcgdex.net/v2/{lang}/cards/{card_id}"
PRICE_KEYS = ("trend-holo", "avg7-holo", "avg30-holo", "avg-holo",
              "trend", "avg7", "avg30", "avg", "low")
results = []
for card_id in SAMPLES:
    for lang in ("it", "en"):
        url = URL.format(lang=lang, card_id=card_id)
        row = {"id": card_id, "lang": lang, "url": url}
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Cardoryx-ReadOnly-Diagnostic/1.0", "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                data = json.load(resp)
            cm = (data.get("pricing") or {}).get("cardmarket") or {}
            row.update(returned_id=data.get("id"), set_id=(data.get("set") or {}).get("id"),
                       local_id=data.get("localId"), product_id=cm.get("idProduct"),
                       usable_keys=[key for key in PRICE_KEYS if isinstance(cm.get(key), (float, int)) and cm[key] > 0],
                       price_present=bool(cm), error=None)
        except (urllib.error.URLError, ValueError, OSError, KeyError) as exc:
            row.update(error=str(exc))
        results.append(row)
        print(json.dumps(row, ensure_ascii=False), flush=True)
with open("cardmarket_30th_diagnostic.json", "w", encoding="utf-8") as out:
    json.dump(results, out, ensure_ascii=False, indent=2)
matched = [x for x in results if x.get("returned_id") == x["id"] and x.get("product_id") and x.get("usable_keys")]
print(f"SUMMARY checked={len(results)} complete_exact_price_rows={len(matched)}", flush=True)
if not matched:
    print("FAIL CLOSED: no verified priced Cardmarket rows returned by TCGdex", file=sys.stderr)
    sys.exit(1)
