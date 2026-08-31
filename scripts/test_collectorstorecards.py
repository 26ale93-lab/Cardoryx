#!/usr/bin/env python3
import json
import re
import unicodedata
import urllib.request
from collections import Counter
from pathlib import Path

BASE = "https://collectorstorecards.it"
COLL = BASE + "/collections/carte-singole-pokemon"
REPORT = Path("collectorstorecards_test_report.json")
UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/2.0)"
MAX_PAGES = 8

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = s.lower()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def get_json(url):
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Accept": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def parse_title(title):
    t = str(title or "").strip()
    num = None
    m = re.search(r"\b([A-Za-z]*\d{1,3})\s*[/\-]\s*([A-Za-z]*\d{1,3})\b", t)
    if m:
        num = f"{m.group(1)}/{m.group(2)}"

    language = "IT" if re.search(r"\bITA\b", t, re.I) else None

    # set candidate = text between collector number and trailing ITA when title follows usual shop pattern
    set_name = None
    if m:
        tail = t[m.end():]
        tail = re.sub(r"\bITA\b.*$", "", tail, flags=re.I).strip(" -–—")
        if tail:
            set_name = tail.strip()

    name = t[:m.start()].strip(" -–—") if m else t
    name = re.sub(r"^\s*Pok[eé]mon\s+", "", name, flags=re.I).strip()

    return {
        "name": name,
        "number": num,
        "setFromTitle": set_name,
        "languageFromTitle": language,
    }

products = []
stats = Counter()
page_errors = []

for page in range(1, MAX_PAGES + 1):
    url = f"{COLL}/products.json?limit=250&page={page}"
    try:
        obj = get_json(url)
        batch = obj.get("products", [])
        stats["catalogPagesFetched"] += 1
        products.extend(batch)
        if len(batch) < 250:
            break
    except Exception as e:
        stats["catalogPageErrors"] += 1
        page_errors.append({"page": page, "error": repr(e)})
        break

stats["products"] = len(products)
examples = []

for p in products:
    title = p.get("title", "")
    parsed = parse_title(title)
    stats["productsInspected"] += 1

    if parsed["languageFromTitle"] == "IT":
        stats["italianFromTitle"] += 1
    if parsed["number"]:
        stats["numberFromTitle"] += 1
    if parsed["setFromTitle"]:
        stats["setCandidateFromTitle"] += 1

    tags = p.get("tags") or []
    if isinstance(tags, str):
        tags = [x.strip() for x in tags.split(",") if x.strip()]
    options = p.get("options") or []
    variants = p.get("variants") or []

    if tags:
        stats["withTags"] += 1
    if options:
        stats["withOptions"] += 1
    if variants:
        stats["withVariants"] += 1

    available_variants = [v for v in variants if v.get("available")]
    if available_variants:
        stats["productsWithAvailableVariant"] += 1

    option_names = [o.get("name") for o in options if isinstance(o, dict)]
    joined_meta = " | ".join(
        [str(x) for x in tags]
        + [str(x) for x in option_names]
        + [str(p.get("product_type", "")), str(p.get("vendor", ""))]
    )
    nmeta = norm(joined_meta)
    if "near mint" in nmeta or re.search(r"\bnm\b", nmeta):
        stats["nearMintSignalInCatalogData"] += 1
    if "reverse" in nmeta:
        stats["reverseSignalInCatalogData"] += 1
    if "holo" in nmeta:
        stats["holoSignalInCatalogData"] += 1

    # Count option names/values to understand whether variant identity is encoded in Shopify.
    option_values = []
    for v in variants[:20]:
        for k in ("option1", "option2", "option3"):
            val = v.get(k)
            if val:
                option_values.append(str(val))
    nov = norm(" | ".join(option_values))
    if "near mint" in nov or re.search(r"\bnm\b", nov):
        stats["nearMintSignalInVariantOptions"] += 1
    if "reverse" in nov:
        stats["reverseSignalInVariantOptions"] += 1
    if "holo" in nov:
        stats["holoSignalInVariantOptions"] += 1
    if "italiano" in nov or re.search(r"\bita\b", nov):
        stats["italianSignalInVariantOptions"] += 1

    if len(examples) < 30:
        examples.append({
            "title": title,
            "handle": p.get("handle"),
            "productType": p.get("product_type"),
            "vendor": p.get("vendor"),
            "tags": tags[:20],
            "options": options,
            "variantSample": [
                {
                    "available": v.get("available"),
                    "price": v.get("price"),
                    "sku": v.get("sku"),
                    "option1": v.get("option1"),
                    "option2": v.get("option2"),
                    "option3": v.get("option3"),
                }
                for v in variants[:5]
            ],
            "parsed": parsed,
        })

report = {
    "schema": 2,
    "source": "Collector Store Cards",
    "mode": "read-only diagnostic",
    "rules": {
        "cardmarketTouched": False,
        "retailPricesModified": False,
        "productPagesOpened": False,
        "shopifyCatalogOnly": True,
        "createsNewIdentity": False,
    },
    "stats": dict(stats),
    "pageErrors": page_errors,
    "examples": examples,
}
REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report["stats"], ensure_ascii=False, indent=2))
print("Report:", REPORT)
