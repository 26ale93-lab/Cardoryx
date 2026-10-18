#!/usr/bin/env python3
"""Read-only verification of official Cardmarket Pokemon singles 30C identities."""
import json
import re
import urllib.request
from collections import Counter
from datetime import datetime, timezone

url = "https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json"
req = urllib.request.Request(url, headers={"User-Agent": "Cardoryx-Catalogue-Check/1.0"})
with urllib.request.urlopen(req, timeout=150) as response:
    payload = json.load(response)
    modified = response.headers.get("Last-Modified")
rows = payload if isinstance(payload, list) else payload.get("products", [])
def nm(row): return str(row.get("name") or row.get("Name") or row.get("productName") or "")
def expansion(row): return str(row.get("idExpansion") or row.get("id_expansion") or "")
def product_id(row): return row.get("idProduct") or row.get("id_product")
matches = [row for row in rows if re.search(r"30C\s*0?90\b", nm(row), re.I) and "gengar" in nm(row).lower()]
code_rows = [row for row in rows if re.search(r"\b30C\s*\d{1,3}\b", nm(row), re.I)]
expansions = Counter(expansion(row) for row in code_rows)
ids = set(expansion(row) for row in matches)
result = {
  "checkedUTC": datetime.now(timezone.utc).isoformat(),
  "catalogueLastModified": modified,
  "totalSingles": len(rows),
  "exactGengar30C090": [{"idProduct": product_id(row), "idExpansion": expansion(row), "name": nm(row)} for row in matches],
  "30CCodeRows": len(code_rows),
  "30CExpansionCounts": dict(expansions),
  "exactExpansionProducts": {eid: sum(expansion(row)==eid for row in rows) for eid in ids},
  "sample": [row for row in rows if expansion(row) in ids][:10],
  "firstRow": rows[0] if rows else None
}
print("CARDORYX_30C_CATALOGUE_RESULT=" + json.dumps(result, ensure_ascii=False))
