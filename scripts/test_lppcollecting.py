#!/usr/bin/env python3
# Cardoryx - LPPCollecting V5 HTTP diagnostic
# READ-ONLY: non modifica retail_prices.json e non tocca Cardmarket.

import json
import re
import urllib.parse
import urllib.request
from pathlib import Path

BASE = "https://www.lppcollecting.it"
SEARCH = BASE + "/pokemon/ricercacarte.php"
REPORT = Path("lppcollecting_test_report.json")
SNIPPET = Path("lppcollecting_response_snippet.txt")

UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/5.0)"
TIMEOUT = 15

TEST_SET_ID = "103"

KEYWORDS = [
    "cloudflare",
    "captcha",
    "cookie",
    "javascript",
    "ricercacarte",
    "pokemon",
    "poke_idserie",
    "non disponibile",
    "mint/near mint",
    "_ita",
    "carta",
    "codice",
    "numero",
    "rarit",
]

def main():
    url = SEARCH + "?" + urllib.parse.urlencode(
        {
            "poke_idrarita": "0",
            "poke_idserie": TEST_SET_ID,
            "poke_ricerca": "",
            "poke_tipocarta": "tutte",
        }
    )

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept-Language": "it-IT,it;q=0.9",
            "Accept": "text/html,application/xhtml+xml",
        },
    )

    result = {
        "schema": 5,
        "source": "LPPCollecting",
        "mode": "read-only diagnostic",
        "rules": {
            "cardmarketTouched": False,
            "retailPricesModified": False,
            "purpose": "inspect raw HTTP response from GitHub Actions",
        },
        "request": {
            "url": url,
            "setId": TEST_SET_ID,
        },
    }

    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as response:
            raw = response.read()
            text = raw.decode("utf-8", "replace")

            headers = {
                k: v
                for k, v in response.headers.items()
                if k.lower() in {
                    "content-type",
                    "content-length",
                    "server",
                    "location",
                    "set-cookie",
                    "cache-control",
                    "cf-ray",
                    "cf-cache-status",
                    "x-powered-by",
                }
            }

            lower = text.lower()
            found = {kw: (kw in lower) for kw in KEYWORDS}

            title_match = re.search(
                r"<title[^>]*>(.*?)</title>",
                text,
                re.I | re.S,
            )
            title = (
                re.sub(r"\s+", " ", title_match.group(1)).strip()
                if title_match
                else ""
            )

            result.update(
                {
                    "ok": True,
                    "http": {
                        "status": getattr(response, "status", None),
                        "finalUrl": response.geturl(),
                        "redirected": response.geturl() != url,
                        "headers": headers,
                    },
                    "response": {
                        "bytes": len(raw),
                        "characters": len(text),
                        "title": title,
                        "keywordPresence": found,
                        "startsWith": text[:200].replace("\n", "\\n"),
                    },
                }
            )

            # Salva un estratto sufficiente per capire cosa arriva a GitHub.
            SNIPPET.write_text(text[:12000], encoding="utf-8")

    except Exception as e:
        result.update(
            {
                "ok": False,
                "error": repr(e),
            }
        )
        SNIPPET.write_text(
            "Nessun corpo risposta disponibile.\nErrore: " + repr(e),
            encoding="utf-8",
        )

    REPORT.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("Report:", REPORT)
    print("Snippet:", SNIPPET)

if __name__ == "__main__":
    main()
