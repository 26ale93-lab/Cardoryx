#!/usr/bin/env python3
import hashlib, json, re, sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
import build_retail_index as retail

def markers(html):
    low=html.lower()
    return {
        "bytes": len(html.encode("utf-8","ignore")),
        "sha256": hashlib.sha256(html.encode("utf-8","ignore")).hexdigest(),
        "trCount": len(re.findall(r"<tr\b", html, re.I)),
        "tdCount": len(re.findall(r"<td\b", html, re.I)),
        "skuCount": len(re.findall(r"\bPO-[A-Z0-9-]+_(?:ita|eng)\b", html, re.I)),
        "euroCount": html.count("€"),
        "basketinCount": low.count("basketin.php"),
        "formCount": len(re.findall(r"<form\b", html, re.I)),
        "tableCount": len(re.findall(r"<table\b", html, re.I)),
        "scriptCount": len(re.findall(r"<script\b", html, re.I)),
        "hasDataTable": "datatable" in low,
        "hasJson": "application/json" in low,
        "parsedRows": len(retail.lpp_rows(html)),
    }

discovery_url=retail.lpp_search_url(retail.LPP_DISCOVERY_SET_ID)
discovery=retail.lpp_get_text(discovery_url)
options=retail.lpp_set_options(discovery)

print("DISCOVERY",json.dumps({
    "url":discovery_url,
    "markers":markers(discovery),
    "setCount":len(options),
    "firstSets":options[:8],
    "shortBody": re.sub(r"\\s+"," ",discovery).strip()[:1500] if len(discovery) < 2000 else None,
},ensure_ascii=False,sort_keys=True))

if not options:
    print("FINDING","DISCOVERY_PAGE_NO_LONGER_EXPOSES_SERVER_RENDERED_SET_SELECTOR")
    raise SystemExit(0)

samples=[]
for set_id,set_name in options[:6]:
    url=retail.lpp_search_url(set_id)
    html=retail.lpp_get_text(url)
    info=markers(html)
    info.update({"setId":set_id,"setName":set_name,"url":url})
    # Capture only structure-oriented fragments, never full page.
    sku=re.search(r".{0,250}\bPO-[A-Z0-9-]+_(?:ita|eng)\b.{0,700}",html,re.I|re.S)
    basket=re.search(r".{0,250}basketin\.php.{0,700}",html,re.I|re.S)
    info["skuFragment"]=re.sub(r"\s+"," ",sku.group(0)).strip()[:1000] if sku else None
    info["basketFragment"]=re.sub(r"\s+"," ",basket.group(0)).strip()[:1000] if basket else None
    samples.append(info)

print("SAMPLES",json.dumps(samples,ensure_ascii=False,sort_keys=True))

# Diagnostic classification only.
if all(x["skuCount"]==0 for x in samples):
    finding="SKU_PATTERN_DISAPPEARED_OR_RESULTS_NOT_SERVER_RENDERED"
elif all(x["trCount"]==0 or x["tdCount"]==0 for x in samples):
    finding="TABLE_STRUCTURE_CHANGED"
elif any(x["skuCount"]>0 and x["parsedRows"]==0 for x in samples):
    finding="ROW_FIELD_LAYOUT_CHANGED"
else:
    finding="MIXED_OR_UNRESOLVED"

print("FINDING",finding)
