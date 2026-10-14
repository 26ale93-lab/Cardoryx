#!/usr/bin/env python3
"""Read-only audit of official Cardmarket Pokemon product catalogue for 30C."""
import json
import re
import urllib.request
from datetime import datetime, timezone

url = "https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json"
print("Checked:", datetime.now(timezone.utc).isoformat(), flush=True)
print("Official source:", url, flush=True)
req = urllib.request.Request(url, headers={"User-Agent": "Cardoryx-30C-Catalogue-Audit/1.0"})
with urllib.request.urlopen(req, timeout=360) as response:
    data = json.load(response)
print("Top-level:", type(data).__name__, flush=True)
rows = data if isinstance(data, list) else next((data[k] for k in ("products", "product", "data", "items") if isinstance(data.get(k), list)), [])
print("Total singles:", len(rows), flush=True)
found = []
gengar = []
for r in rows:
    if not isinstance(r, dict):
        continue
    expansion = str(r.get("expansionName") or r.get("expansion") or "")
    name = str(r.get("name") or "")
    number = str(r.get("number") or "")
    if re.search(r"30th.Celebration|30.? Anniversario|30.? Jahre|30.? Anniversaire", expansion, re.I) and not re.search(r"JP|Japan", expansion, re.I):
        found.append(r)
        if re.search(r"Gengar.?ex|Ectoplasma.?ex", name, re.I) and ("090" in number or "090" in name):
            gengar.append(r)
print("30C products:", len(found), flush=True)
print("Expansions:", sorted({str(x.get("expansionName")) for x in found}), flush=True)
print("Gengar ex 30C 090:", json.dumps(gengar, ensure_ascii=False), flush=True)
print("Sample:", json.dumps(found[:5], ensure_ascii=False), flush=True)
print("Audit can rerun:", bool(found and gengar), flush=True)
