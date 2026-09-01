#!/usr/bin/env python3
"""Audit read-only dell'adapter LPP destinato alla produzione."""

import copy
import hashlib
import json
import runpy
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
BUILDER = ROOT / "scripts" / "build_retail_index.py"
RETAIL = ROOT / "data" / "retail_prices.json"
REPORT = ROOT / "lpp_production_audit_report.json"


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def stores(card):
    return {
        str(offer.get("store") or "").strip()
        for offer in card.get("offers", [])
        if str(offer.get("store") or "").strip()
    }


before_hash = sha256(RETAIL)
namespace = runpy.run_path(
    str(BUILDER),
    run_name="__lpp_production_read_only_audit__",
)

for required in (
    "collect_lppcollecting",
    "lpp_rows",
    "lpp_set_options",
    "lpp_variant",
):
    if not callable(namespace.get(required)):
        raise SystemExit(f"Builder incompatibile: manca {required}")

with RETAIL.open("r", encoding="utf-8") as stream:
    retail = json.load(stream)

if retail.get("rules", {}).get("cardmarketExcluded") is not True:
    raise SystemExit("Safety check fallito: Cardmarket non escluso")

original_cards = retail.get("cards")
if not isinstance(original_cards, dict) or not original_cards:
    raise SystemExit("Indice retail vuoto o non valido")

cards = copy.deepcopy(original_cards)
original_keys = set(cards)
stores_before = {
    key: stores(card)
    for key, card in cards.items()
}
offers_before = {
    key: len(card.get("offers", []))
    for key, card in cards.items()
}

stats = namespace["collect_lppcollecting"](cards)

if stats.get("ok") is not True:
    raise SystemExit(f"Adapter LPP non disponibile: {stats}")

if set(cards) != original_keys:
    raise SystemExit("Safety check fallito: create nuove identita")

added = []
impact = Counter()

for key, card in cards.items():
    difference = len(card.get("offers", [])) - offers_before[key]
    if difference not in {0, 1}:
        raise SystemExit(f"Numero offerte LPP non valido per {key}: {difference}")
    if difference == 0:
        continue

    offer = card["offers"][-1]
    if offer.get("store") != "LPP Collecting":
        raise SystemExit(f"Negozio inatteso per {key}: {offer.get('store')}")
    if offer.get("language") != "IT":
        raise SystemExit(f"Lingua non valida per {key}")
    if offer.get("condition") != "NM/MINT":
        raise SystemExit(f"Condizione non valida per {key}")
    if offer.get("variant") != card.get("variant"):
        raise SystemExit(f"Variante non coerente per {key}")
    if not isinstance(offer.get("price"), (int, float)) or offer["price"] <= 0:
        raise SystemExit(f"Prezzo non valido per {key}")
    if "lppcollecting.it/pokemon/ricercacarte.php" not in offer.get("url", ""):
        raise SystemExit(f"URL non valido per {key}")
    if "Cardmarket" in stores(card):
        raise SystemExit(f"Cardmarket rilevato per {key}")

    before_count = len(stores_before[key])
    impact[f"{before_count}->{before_count + 1}"] += 1
    added.append({
        "cardKey": key,
        "set": card.get("set"),
        "number": card.get("number"),
        "name": card.get("name"),
        "variant": card.get("variant"),
        "price": offer.get("price"),
        "url": offer.get("url"),
        "impact": f"{before_count}->{before_count + 1}",
    })

if len(added) != stats.get("accepted"):
    raise SystemExit(
        f"Conteggio incoerente: {len(added)} aggiunte, "
        f"{stats.get('accepted')} dichiarate"
    )

if len(added) < 800:
    raise SystemExit(f"Copertura LPP inattesa: soltanto {len(added)} offerte")

after_hash = sha256(RETAIL)
if after_hash != before_hash:
    raise SystemExit("Safety check fallito: retail_prices.json modificato")

report = {
    "generatedAt": datetime.now(timezone.utc).isoformat(
        timespec="seconds"
    ).replace("+00:00", "Z"),
    "mode": "read-only production adapter audit",
    "retailHashBefore": before_hash,
    "retailHashAfter": after_hash,
    "identityCountBefore": len(original_keys),
    "identityCountAfter": len(cards),
    "newIdentities": 0,
    "cardmarketExcluded": True,
    "stats": stats,
    "impact": dict(sorted(impact.items())),
    "addedOffers": added,
}

REPORT.write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(json.dumps({
    "ok": True,
    "accepted": len(added),
    "impact": dict(sorted(impact.items())),
    "newIdentities": 0,
    "retailUnchanged": True,
    "cardmarketExcluded": True,
}, ensure_ascii=False, indent=2))
