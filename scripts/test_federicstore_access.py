#!/usr/bin/env python3
"""Diagnostica read-only per l'accesso pubblico a Federicstore.

Non modifica l'indice retail e non invia dati al sito. Prova la richiesta
attuale, una sessione con intestazioni browser e la Store API pubblica di
WooCommerce, riportando soltanto metadati tecnici della risposta.
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import urllib.error
import urllib.request


BASE_URL = "https://federicstore.it/"
CATEGORY_URL = BASE_URL + "categoria/carte-singole-pokemon/"
STORE_API_URL = BASE_URL + "wp-json/wc/store/v1/products?per_page=1"
REST_ROUTE_URL = (
    BASE_URL + "?rest_route=/wc/store/v1/products&per_page=1"
)
TIMEOUT_SECONDS = 20

CURRENT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Cardoryx Retail Index; +https://github.com/)",
    "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "it-IT,it;q=0.9,en;q=0.7",
    "Connection": "close",
}

BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/140.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;q=0.9,"
        "image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "it-IT,it;q=0.9,en-US;q=0.7,en;q=0.6",
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Upgrade-Insecure-Requests": "1",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
}

SAFE_RESPONSE_HEADERS = (
    "content-type",
    "server",
    "cf-ray",
    "x-sucuri-id",
    "x-cache",
    "x-powered-by",
)


def safe_headers(headers):
    return {
        name: headers.get(name)
        for name in SAFE_RESPONSE_HEADERS
        if headers.get(name)
    }


def body_hint(payload):
    text = payload.decode("utf-8", errors="replace")
    text = re.sub(r"\s+", " ", text).strip()
    return text[:160]


def request(opener, name, url, headers):
    req = urllib.request.Request(url, headers=headers)

    try:
        with opener.open(req, timeout=TIMEOUT_SECONDS) as response:
            payload = response.read()
            result = {
                "name": name,
                "ok": True,
                "status": response.status,
                "finalUrl": response.geturl(),
                "bytes": len(payload),
                "headers": safe_headers(response.headers),
            }

            content_type = response.headers.get("content-type", "")
            if "json" in content_type.lower():
                try:
                    parsed = json.loads(payload)
                    result["jsonType"] = type(parsed).__name__
                    result["jsonItems"] = (
                        len(parsed) if isinstance(parsed, list) else None
                    )
                except json.JSONDecodeError:
                    result["jsonValid"] = False
            else:
                lowered = payload.lower()
                result["hasProductMarkup"] = any(
                    marker in lowered
                    for marker in (
                        b"product-small",
                        b"woocommerce-loop-product",
                        b"class=\"product",
                    )
                )
            return result

    except urllib.error.HTTPError as exc:
        payload = exc.read()
        return {
            "name": name,
            "ok": False,
            "status": exc.code,
            "reason": exc.reason,
            "finalUrl": exc.geturl(),
            "bytes": len(payload),
            "headers": safe_headers(exc.headers),
            "bodyHint": body_hint(payload),
        }
    except Exception as exc:  # noqa: BLE001 - diagnostica controllata
        return {
            "name": name,
            "ok": False,
            "errorType": type(exc).__name__,
            "error": str(exc),
        }


def main():
    direct_opener = urllib.request.build_opener()
    cookie_jar = http.cookiejar.CookieJar()
    browser_opener = urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(cookie_jar)
    )

    results = [
        request(
            direct_opener,
            "current-category-request",
            CATEGORY_URL,
            CURRENT_HEADERS,
        )
    ]

    results.append(
        request(browser_opener, "browser-session-prime", BASE_URL, BROWSER_HEADERS)
    )

    category_headers = {
        **BROWSER_HEADERS,
        "Referer": BASE_URL,
        "Sec-Fetch-Site": "same-origin",
    }
    results.append(
        request(
            browser_opener,
            "browser-session-category",
            CATEGORY_URL,
            category_headers,
        )
    )

    api_headers = {
        **BROWSER_HEADERS,
        "Accept": "application/json,*/*;q=0.8",
        "Referer": CATEGORY_URL,
        "Sec-Fetch-Dest": "empty",
        "Sec-Fetch-Mode": "cors",
        "Sec-Fetch-Site": "same-origin",
    }
    results.append(
        request(browser_opener, "woocommerce-store-api", STORE_API_URL, api_headers)
    )
    results.append(
        request(browser_opener, "woocommerce-rest-route", REST_ROUTE_URL, api_headers)
    )

    successful = [result["name"] for result in results if result.get("ok")]
    report = {
        "name": "Cardoryx Federicstore access diagnostic",
        "readOnly": True,
        "successfulStrategies": successful,
        "results": results,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))

    if not successful:
        raise SystemExit("Nessuna strategia pubblica ha superato il blocco HTTP")


if __name__ == "__main__":
    main()
