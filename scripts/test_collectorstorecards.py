#!/usr/bin/env python3
# Cardoryx - Collector Store Cards V5
# Test finale read-only prima dell'eventuale adapter di produzione.
# Non modifica retail_prices.json. Non tocca Cardmarket.

import json, re, unicodedata, urllib.request
from collections import Counter, defaultdict
from html import unescape
from pathlib import Path

BASE = "https://collectorstorecards.it"
COLL = BASE + "/collections/carte-singole-pokemon"
RETAIL = Path("data/retail_prices.json")
REPORT = Path("collectorstorecards_test_report.json")
UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/5.0)"

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = unescape(s).lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def plain(s):
    s = re.sub(r"<[^>]+>", " ", str(s or ""))
    return re.sub(r"\s+", " ", unescape(s)).strip()

def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read().decode("utf-8", "replace"))

def numkey(number):
    m = re.match(r"^\s*([A-Za-z]*)(\d+)\s*[/\-]\s*([A-Za-z]*)(\d+)\s*$", str(number or ""))
    if not m: return None
    return (m.group(1).upper(), int(m.group(2)), m.group(3).upper(), int(m.group(4)))

def parse_title(title):
    t = str(title or "").strip()
    m = re.search(r"\b([A-Za-z]*\d{1,3})\s*[/\-]\s*([A-Za-z]*\d{1,3})\b", t)
    if not m: return None
    before = re.sub(r"^\s*Pok[eé]mon\s+", "", t[:m.start()].strip(" -–—"), flags=re.I).strip()
    tail = re.sub(r"\bITA\b.*$", "", t[m.end():], flags=re.I).strip(" -–—")

    variant = None
    marker = None
    patterns = [
        (r"\breverse\s+master\s*ball\b", "Master Ball Reverse Holo", "Reverse Masterball"),
        (r"\breverse\s+masterball\b", "Master Ball Reverse Holo", "Reverse Masterball"),
        (r"\bmaster\s*ball\s+reverse\b", "Master Ball Reverse Holo", "Master Ball Reverse"),
        (r"\bholo\s+reverse\b", "Reverse Holo", "Holo Reverse"),
        (r"\breverse\s+holo\b", "Reverse Holo", "Reverse Holo"),
        (r"\bholo\b", "Holo", "Holo"),
    ]

    # Il marker può essere prima del numero o all'inizio della parte-set.
    for pat, v, label in patterns:
        if re.search(pat, before, re.I):
            before = re.sub(pat, "", before, flags=re.I).strip(" -–—")
            variant, marker = v, label
            break
        if re.search(r"^" + pat, tail, re.I):
            tail = re.sub(r"^" + pat, "", tail, flags=re.I).strip(" -–—")
            variant, marker = v, label
            break

    return {
        "name": before,
        "number": f"{m.group(1)}/{m.group(2)}",
        "setFromTitle": tail,
        "variant": variant,
        "variantMarker": marker,
        "language": "IT" if re.search(r"\bITA\b", t, re.I) else None,
    }

def tag_set(tags):
    vals=[]
    if isinstance(tags, str):
        tags=[x.strip() for x in tags.split(",") if x.strip()]
    for x in tags or []:
        m=re.match(r"^\s*(.+?)\s*\[([A-Za-z0-9]+)\]\s*$", str(x))
        if m: vals.append((m.group(1).strip(), m.group(2).upper()))
    return vals

def fields(body):
    t=plain(body)
    def f(label, following):
        m=re.search(rf"\b{re.escape(label)}:\s*(.+?)(?=\s+(?:{following})\s*:|$)", t, re.I)
        return m.group(1).strip() if m else ""
    return {
        "condition":f("Condizione","Set|Rarità|Numerazione|Lingua"),
        "set":f("Set","Rarità|Numerazione|Lingua"),
        "rarity":f("Rarità","Numerazione|Lingua"),
        "number":f("Numerazione","Lingua"),
        "language":f("Lingua","ZZZ"),
        "text":t,
    }

def body_variant(rarity, text):
    r=norm(rarity)
    n=norm(text)
    if "reverse holo" in r or "holo reverse" in r: return "Reverse Holo", "rarity"
    if r in ("holo rare","rara holo"): return "Holo", "rarity"
    if re.search(r"\breverse holo\b|\bholo reverse\b", n): return "Reverse Holo", "body"
    return None, None

def main():
    data=json.loads(RETAIL.read_text(encoding="utf-8"))
    base=defaultdict(list)
    exact=defaultdict(list)
    for c in data.get("cards",{}).values():
        nk=numkey(c.get("number"))
        if not nk: continue
        k=(norm(c.get("set")),nk,norm(c.get("name")))
        base[k].append(c)
        exact[k+(c.get("variant"),)].append(c)

    products=[]
    stats=Counter()
    for page in range(1,9):
        batch=get_json(f"{COLL}/products.json?limit=250&page={page}").get("products",[])
        stats["catalogPagesFetched"]+=1
        products += batch
        if len(batch)<250: break
    stats["products"]=len(products)

    accepted=[]
    unique_diag=[]
    conflicts=[]
    masterball=[]

    for p in products:
        stats["productsInspected"]+=1
        pt=parse_title(p.get("title"))
        if not pt or pt["language"]!="IT":
            stats["titleRejected"]+=1; continue

        ts=tag_set(p.get("tags"))
        if len(ts)!=1:
            stats["setTagRejected"]+=1; continue
        setname,setcode=ts[0]

        # Dopo aver rimosso un marker variante noto, titolo e tag devono concordare.
        if norm(pt["setFromTitle"]) != norm(setname):
            stats["setConflict"]+=1
            if len(conflicts)<30:
                conflicts.append({"title":p.get("title"),"titleSet":pt["setFromTitle"],"tagSet":setname})
            continue

        av=[v for v in p.get("variants",[]) if v.get("available")]
        if not av:
            stats["unavailable"]+=1; continue
        prices={float(v["price"]) for v in av if v.get("price") not in (None,"")}
        if len(prices)!=1:
            stats["priceRejected"]+=1; continue
        price=next(iter(prices))

        bf=fields(p.get("body_html"))
        if norm(bf["condition"])!="near mint":
            stats["conditionRejected"]+=1; continue
        stats["nearMintConfirmed"]+=1

        nk=numkey(pt["number"])
        if not nk:
            stats["numberRejected"]+=1; continue

        k=(norm(setname),nk,norm(pt["name"]))
        candidates=base.get(k,[])
        variants=sorted({c.get("variant") for c in candidates if c.get("variant")})

        v=pt["variant"]
        sig="title" if v else None
        if not v:
            v,sig=body_variant(bf["rarity"],bf["text"])

        if pt["variant"]=="Master Ball Reverse Holo":
            stats["masterBallTitleDetected"]+=1
            if len(masterball)<30:
                masterball.append({
                    "title":p.get("title"),"name":pt["name"],"number":pt["number"],
                    "set":setname,"candidateVariants":variants,
                    "url":f"{BASE}/products/{p.get('handle')}"
                })

        if v:
            stats["explicitVariantConfirmed"]+=1
            matches=exact.get(k+(v,),[])
            if len(matches)==1:
                stats["safeExactMatches"]+=1
                c=matches[0]
                if bool((c.get("stats") or {}).get("reliable")):
                    stats["safeAlreadyReliable"]+=1
                else:
                    stats["safeCurrentlyNotReliable"]+=1
                if len(accepted)<60:
                    accepted.append({
                        "title":p.get("title"),"name":pt["name"],"number":pt["number"],
                        "set":setname,"setCode":setcode,"variant":v,"signal":sig,
                        "rarity":bf["rarity"],"price":price,
                        "currentlyReliable":bool((c.get("stats") or {}).get("reliable")),
                        "url":f"{BASE}/products/{p.get('handle')}"
                    })
            else:
                stats["explicitVariantIdentityRejected"]+=1
            continue

        # Diagnostica delle rarità senza conversione automatica.
        r=norm(bf["rarity"])
        if r:
            stats["rarityWithoutExplicitVariant"]+=1
            if len(candidates)==1:
                stats["uniqueExistingIdentityDiagnostic"]+=1
                c=candidates[0]
                if bool((c.get("stats") or {}).get("reliable")):
                    stats["uniqueDiagnosticAlreadyReliable"]+=1
                else:
                    stats["uniqueDiagnosticCurrentlyNotReliable"]+=1
                if len(unique_diag)<80:
                    unique_diag.append({
                        "title":p.get("title"),"name":pt["name"],"number":pt["number"],
                        "set":setname,"rarity":bf["rarity"],"price":price,
                        "cardoryxVariant":c.get("variant"),
                        "currentlyReliable":bool((c.get("stats") or {}).get("reliable")),
                        "url":f"{BASE}/products/{p.get('handle')}"
                    })
            elif len(candidates)>1:
                stats["ambiguousExistingIdentity"]+=1
            else:
                stats["noExistingIdentity"]+=1

    report={
        "schema":5,
        "source":"Collector Store Cards",
        "mode":"final read-only diagnostic",
        "ok":True,
        "rules":{
            "cardmarketTouched":False,
            "retailPricesModified":False,
            "createsNewIdentity":False,
            "masterBallReverse":"recognized only when explicitly written in title",
            "set":"Shopify set tag plus cleaned title agreement",
            "condition":"Near Mint required",
            "specialRarity":"diagnostic only; never converted automatically",
            "productionEligible":"only safeExactMatches"
        },
        "stats":dict(stats),
        "safeExactExamples":accepted,
        "uniqueIdentityDiagnosticExamples":unique_diag,
        "masterBallExamples":masterball,
        "setConflicts":conflicts
    }
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report["stats"],ensure_ascii=False,indent=2))
    print("Report:",REPORT)

if __name__=="__main__":
    main()
