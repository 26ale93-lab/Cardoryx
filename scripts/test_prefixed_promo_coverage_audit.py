#!/usr/bin/env python3
"""Read-only audit for prefixed promo identities (MEP first).

Goals:
- discover which official MEP promo numbers are already available in TCGdex;
- identify exact official identities missing upstream;
- never write production data, Cardmarket data, or retail data.
"""

import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "prefixed_promo_coverage_audit_report.json"
OFFICIAL_URL = "https://www.pokemon.com/it/play-pokemon/info/entrata-in-vigore-delle-carte-promozionali-del-gcc-pokemon"
TCGDEX = "https://api.tcgdex.net/v2"
UA = "Cardoryx-prefixed-promo-audit/1.0"

# Exact current official identities highlighted by Pokemon's promo legality page.
# These are used only as a conservative fallback if the page layout cannot be parsed.
# The audit itself remains read-only.
OFFICIAL_CURRENT = {
    "MEP089": "Mega Zeraora-ex",
    "MEP090": "Mega Darkrai-ex",
    "MEP091": "Mega Dragonite-ex",
    "MEP092": "Resort Paradiso",
    "MEP093": "Pikachu",
    "MEP094": "Exeggutor di Alola",
    "MEP095": "Lucario",
    "MEP096": "Moltres",
    "MEP097": "Articuno",
    "MEP098": "Zapdos",
    "MEP099": "Greninja-ex",
    "MEP100": "Sylveon-ex",
    "MEP101": "Nidorina",
}


def fetch_text(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9,en;q=0.6"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def official_rows():
    rows = dict(OFFICIAL_CURRENT)
    source = "verified-static-fallback"
    try:
        html = fetch_text(OFFICIAL_URL)
        text = re.sub(r"<[^>]+>", " ", html)
        text = re.sub(r"\s+", " ", text)
        # Capture a short name window immediately before MEP nnn.
        for m in re.finditer(r"([^|<>]{2,80}?)\s+MEP\s*0*(\d{1,3})\b", text, flags=re.I):
            number = int(m.group(2))
            if not (1 <= number <= 199):
                continue
            name = m.group(1).strip(" -–—|:\t\r\n")
            name = re.sub(r"\s+", " ", name)
            if len(name) > 60:
                name = name[-60:].strip()
            if name:
                rows[f"MEP{number:03d}"] = name
        source = "pokemon.com+verified-static-fallback"
    except Exception as exc:
        source = f"verified-static-fallback ({type(exc).__name__})"
    return rows, source


def tcgdex_card(code: str):
    set_id = code[:3].lower()
    num = str(int(code[3:]))
    candidates = [
        f"{set_id}-{num}",
        f"{set_id}-{num.zfill(3)}",
    ]
    checked = []
    for lang in ("it", "en"):
        for card_id in candidates:
            url = f"{TCGDEX}/{lang}/cards/{card_id}"
            try:
                data = json.loads(fetch_text(url))
                if isinstance(data, dict) and data.get("id"):
                    return {
                        "found": True,
                        "language": lang,
                        "requestedId": card_id,
                        "id": data.get("id"),
                        "name": data.get("name"),
                        "localId": data.get("localId"),
                        "image": data.get("image"),
                        "hasCardmarket": bool((data.get("pricing") or {}).get("cardmarket")),
                        "cardmarketProduct": ((data.get("pricing") or {}).get("cardmarket") or {}).get("idProduct"),
                    }
            except urllib.error.HTTPError as exc:
                checked.append({"lang": lang, "id": card_id, "status": exc.code})
                if exc.code != 404:
                    break
            except Exception as exc:
                checked.append({"lang": lang, "id": card_id, "error": type(exc).__name__})
    return {"found": False, "checked": checked}


def main():
    rows, official_source = official_rows()
    # Focus on all exact MEP rows we could confidently identify from the official page,
    # plus the current 089-101 block even if parsing fails.
    records = []
    for code, official_name in sorted(rows.items(), key=lambda kv: int(kv[0][3:])):
        if not re.fullmatch(r"MEP\d{3}", code):
            continue
        result = tcgdex_card(code)
        records.append({"code": code, "officialName": official_name, "tcgdex": result})

    found = [r for r in records if r["tcgdex"].get("found")]
    missing = [r for r in records if not r["tcgdex"].get("found")]
    with_image = [r for r in found if r["tcgdex"].get("image")]
    with_cm = [r for r in found if r["tcgdex"].get("hasCardmarket")]

    report = {
        "audit": "prefixed-promo-coverage",
        "mode": "read-only",
        "officialSource": official_source,
        "officialUrl": OFFICIAL_URL,
        "scope": "MEP",
        "counts": {
            "officialIdentities": len(records),
            "tcgdexFound": len(found),
            "tcgdexMissing": len(missing),
            "tcgdexWithImage": len(with_image),
            "tcgdexWithCardmarket": len(with_cm),
        },
        "missingCodes": [r["code"] for r in missing],
        "records": records,
        "safety": {
            "productionFilesChanged": False,
            "retailPricesChanged": False,
            "cardmarketDataChanged": False,
            "automaticFallbacksAdded": False,
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["counts"], ensure_ascii=False))
    print("missing:", ", ".join(report["missingCodes"]) or "none")

    # Fail safe only if the concrete regression case disappears from the official set
    # known to the audit. Missing TCGdex coverage itself is an audit result, not a test failure.
    if "MEP091" not in {r["code"] for r in records}:
        print("MEP091 absent from official audit scope", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
