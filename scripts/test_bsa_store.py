#!/usr/bin/env python3
import json, re, time, urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

BASE="https://www.bsastore.it"
COLLECTION="pokemon-carte-singole-ita"
PAGE_LIMIT=250
MAX_PAGES=40
HTTP_TIMEOUT=20
ANOMALY_PRICE=500.0
MAX_PAGE_PROBES=30

ROOT=Path(__file__).resolve().parents[1]
REPORT=ROOT/"bsa_store_test_report.json"
UA="Mozilla/5.0 (compatible; CardoryxBSAReadOnlyAudit/1.0; +https://github.com/)"

def now():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00","Z")

def get_text(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept":"application/json,text/html;q=0.9,*/*;q=0.8","Accept-Language":"it-IT,it;q=0.9,en;q=0.7","Connection":"close"})
    with urllib.request.urlopen(req,timeout=HTTP_TIMEOUT) as r:
        return r.read().decode("utf-8",errors="replace")

def get_json(url):
    return json.loads(get_text(url))

def parse_price(v):
    if v is None: return None
    s=str(v).strip().replace("€","").replace("EUR","").replace(",",".")
    if not re.fullmatch(r"\d{1,7}(?:\.\d{1,2})?",s): return None
    try: return round(float(s),2)
    except Exception: return None

def extract_page_prices(html):
    found=[]
    patterns=[
      (r'<meta[^>]+property=["\']product:price:amount["\'][^>]+content=["\']([^"\']+)["\']',"meta_product_price"),
      (r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']product:price:amount["\']',"meta_product_price"),
      (r'"price"\s*:\s*"?([0-9]+(?:[.,][0-9]{1,2})?)"?',"html_json_price"),
    ]
    for pat,src in patterns:
        for m in re.finditer(pat,html,re.I):
            p=parse_price(m.group(1))
            if p is not None: found.append({"source":src,"price":p})
    uniq=[]; seen=set()
    for x in found:
        k=(x["source"],x["price"])
        if k not in seen:
            seen.add(k); uniq.append(x)
    return uniq[:30]

def main():
    stats=Counter(); available_prices=[]; anomaly_products=[]; available_price_counts=Counter()
    for page in range(1,MAX_PAGES+1):
        url=f"{BASE}/collections/{COLLECTION}/products.json?limit={PAGE_LIMIT}&page={page}"
        products=get_json(url).get("products",[])
        if not products: break
        stats["pagesFetched"]+=1; stats["products"]+=len(products)
        for product in products:
            for v in product.get("variants",[]) or []:
                stats["variants"]+=1
                price=parse_price(v.get("price"))
                if v.get("available") is True:
                    stats["availableVariants"]+=1
                    if price is not None:
                        available_prices.append(price)
                        available_price_counts[f"{price:.2f}"]+=1
                if price is not None and price>=ANOMALY_PRICE:
                    stats["anomalousVariants"]+=1
                    handle=str(product.get("handle") or "")
                    anomaly_products.append({
                      "productId":product.get("id"),"variantId":v.get("id"),
                      "title":product.get("title"),"handle":handle,
                      "productUrl":f"{BASE}/products/{handle}",
                      "available":v.get("available"),"variantTitle":v.get("title"),
                      "rawPrice":v.get("price"),"parsedPrice":price,
                      "compareAtPrice":v.get("compare_at_price"),"sku":v.get("sku")
                    })
        if len(products)<PAGE_LIMIT: break

    anomaly_counts=Counter(f"{x['parsedPrice']:.2f}" for x in anomaly_products)
    probes=[]
    for item in anomaly_products[:MAX_PAGE_PROBES]:
        row=dict(item)
        try:
            row["pagePriceSignals"]=extract_page_prices(get_text(item["productUrl"]))
            row["pageFetchOk"]=True
        except Exception as exc:
            row["pageFetchOk"]=False; row["pageError"]=repr(exc)
        probes.append(row); time.sleep(0.05)

    s=sorted(available_prices)
    report={
      "schema":1,"source":"BSA Store","mode":"read-only raw Shopify price audit","generatedAt":now(),
      "rules":{"retailPricesModified":False,"cardmarketTouched":False,"anomalyThreshold":ANOMALY_PRICE,"noAutomaticCorrection":True},
      "stats":dict(stats),
      "availablePriceSummary":{"min":s[0] if s else None,"max":s[-1] if s else None,"count":len(s)},
      "topAvailableRawPrices":available_price_counts.most_common(40),
      "anomalousPriceCounts":anomaly_counts.most_common(30),
      "anomalousExamples":anomaly_products[:100],
      "pageCrosscheckExamples":probes,
      "knownTargets":{
        "rillaboomV_022_264":[x for x in anomaly_products if "rillaboom-v-022-264" in x["handle"].lower()],
        "rillaboomVMAX_023_264":[x for x in anomaly_products if "rillaboom-vmax-023-264" in x["handle"].lower()],
        "boltundVMAX_104_264":[x for x in anomaly_products if "boltund-vmax-104-264" in x["handle"].lower()],
        "boltundVMAX_267_264":[x for x in anomaly_products if "boltund-vmax-267-264" in x["handle"].lower()],
      }
    }
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps({"products":stats["products"],"anomalousVariants":stats["anomalousVariants"],"report":str(REPORT)},ensure_ascii=False,indent=2))

if __name__=="__main__":
    main()
