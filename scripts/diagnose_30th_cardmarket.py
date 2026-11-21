#!/usr/bin/env python3
"""Read-only full coverage audit of 30th and 30th-c via TCGdex IT/EN.

Does not modify Cardoryx collections or Cardmarket/retail data. Missing or
ambiguous identities are reported, never assigned inferred prices.
"""
import concurrent.futures
import json
import re
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone

SETS = ("30th", "30th-c")
LANGUAGES = ("it", "en")
PRICE_KEYS = ("trend-holo", "avg7-holo", "avg30-holo", "avg-holo",
              "trend", "avg7", "avg30", "avg", "low")
BASE = "https://api.tcgdex.net/v2/{lang}"
HEADERS = {"User-Agent": "Cardoryx-30th-ReadOnly-Audit/1.1", "Accept": "application/json"}


def get_json(url):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as resp:
        return json.load(resp)


def discover():
    found = {}
    source = {}
    errors = []
    for set_id in SETS:
        identities = set()
        for lang in LANGUAGES:
            url = BASE.format(lang=lang) + "/sets/" + set_id
            try:
                obj = get_json(url)
                cards = obj.get("cards")
                if not isinstance(cards, list) or not cards:
                    raise ValueError("missing or empty official set card list")
                for card in cards:
                    cid = card.get("id", "") if isinstance(card, dict) else ""
                    if re.fullmatch(re.escape(set_id) + r"-[a-zA-Z0-9]+", cid, re.I):
                        identities.add(cid.lower())
                source[set_id + ":" + lang] = {"listed": len(cards), "matched": len(identities)}
            except (urllib.error.URLError, ValueError, OSError, KeyError, TypeError) as exc:
                errors.append({"set": set_id, "lang": lang, "error": str(exc)})
        found[set_id] = sorted(identities)
    return found, source, errors


def probe(request):
    set_id, card_id, lang = request
    url = BASE.format(lang=lang) + "/cards/" + card_id
    result = {"set": set_id, "id": card_id, "lang": lang}
    try:
        obj = get_json(url)
        cm = (obj.get("pricing") or {}).get("cardmarket") or {}
        actual_id = str(obj.get("id", "")).lower()
        actual_set = str((obj.get("set") or {}).get("id", "")).lower()
        actual_local = str(obj.get("localId", "")).lower()
        expected_local = card_id[len(set_id) + 1:].lower()
        same_number = actual_local.lstrip("0") == expected_local.lstrip("0")
        exact = actual_id == card_id and actual_set == set_id and same_number
        pid = cm.get("idProduct")
        verified_pid = isinstance(pid, int) and not isinstance(pid, bool) and pid > 0
        prices = {key: cm[key] for key in PRICE_KEYS
                  if isinstance(cm.get(key), (int, float))
                  and not isinstance(cm[key], bool) and cm[key] > 0}
        result.update(exact_identity=exact, product_id=pid if verified_pid else None,
                      price_keys=prices, usable=bool(exact and verified_pid and prices),
                      pricing_present=bool(cm), error=None)
    except (urllib.error.URLError, ValueError, OSError, KeyError, TypeError) as exc:
        result.update(exact_identity=False, usable=False, error=str(exc))
    return result


def main():
    found, source, discovery_errors = discover()
    queries = [(set_id, card_id, lang) for set_id, ids in found.items()
               for card_id in ids for lang in LANGUAGES]
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        rows = list(pool.map(probe, queries))
    identities = {}
    for set_id, ids in found.items():
        for card_id in ids:
            variants = [r for r in rows if r["id"] == card_id]
            usable = [r for r in variants if r.get("usable")]
            products = sorted(set(int(r["product_id"]) for r in usable))
            identities[card_id] = {
                "set": set_id, "usable_languages": [r["lang"] for r in usable],
                "products": products, "verified": bool(usable) and len(products) == 1,
                "conflict": len(products) > 1
            }
    summary = {
        "timestamp_utc": datetime.now(timezone.utc).isoformat(),
        "discovery": source, "discovery_errors": discovery_errors,
        "identities_by_set": {k: len(v) for k, v in found.items()},
        "identities_total": len(identities),
        "verified": sum(v["verified"] for v in identities.values()),
        "ambiguous_products": sum(v["conflict"] for v in identities.values()),
        "without_usable_price": sum(not v["verified"] for v in identities.values()),
        "requests": len(rows), "errors": sum(bool(r.get("error")) for r in rows)
    }
    with open("cardmarket_30th_diagnostic.json", "w", encoding="utf-8") as out:
        json.dump({"summary": summary, "identity_results": identities,
                   "source_rows": rows}, out, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    if discovery_errors or any(not found[x] for x in SETS) or summary["verified"] == 0:
        print("FAIL CLOSED: incomplete source discovery or no verified priced cards",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
