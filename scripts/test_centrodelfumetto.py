#!/usr/bin/env python3
import json
import urllib.error
import urllib.request
from pathlib import Path

URLS = [
    "https://www.centrodelfumetto.it/pokemon/pokemon-single/",
    "https://www.centrodelfumetto.it/pokemon/pokemon-single/page/2/",
    "https://www.centrodelfumetto.it/",
]
REPORT = Path("centrodelfumetto_test_report.json")
UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/2.0)"

def probe(url):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml",
            "Accept-Language": "it-IT,it;q=0.9",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            body = r.read(3000).decode("utf-8", "replace")
            return {
                "url": url,
                "ok": True,
                "status": getattr(r, "status", None),
                "finalUrl": r.geturl(),
                "contentType": r.headers.get("content-type"),
                "bodyPreview": body[:500],
            }
    except urllib.error.HTTPError as e:
        try:
            body = e.read(1200).decode("utf-8", "replace")
        except Exception:
            body = ""
        return {
            "url": url,
            "ok": False,
            "errorType": "HTTPError",
            "status": e.code,
            "reason": str(e.reason),
            "bodyPreview": body[:500],
        }
    except Exception as e:
        return {
            "url": url,
            "ok": False,
            "errorType": type(e).__name__,
            "error": repr(e),
        }

report = {
    "schema": 2,
    "source": "Centro del Fumetto",
    "mode": "read-only diagnostic",
    "rules": {
        "cardmarketTouched": False,
        "retailPricesModified": False,
        "catalogScan": False,
    },
    "probes": [probe(u) for u in URLS],
}
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
