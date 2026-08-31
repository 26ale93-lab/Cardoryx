#!/usr/bin/env python3
import json,re,time,unicodedata,urllib.parse,urllib.request
from collections import Counter,defaultdict
from html import unescape
from pathlib import Path

BASE="https://www.lppcollecting.it"
HOME=BASE+"/pokemon/"
SEARCH=BASE+"/pokemon/ricercacarte.php"
RETAIL=Path("data/retail_prices.json")
REPORT=Path("lppcollecting_test_report.json")
UA="Mozilla/5.0 (compatible; CardoryxRetailAudit/1.0)"

def norm(s):
    s=unicodedata.normalize("NFKD",str(s or ""))
    s="".join(c for c in s if not unicodedata.combining(c))
    s=unescape(s).lower().replace("’","'")
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",s)).strip()

def get(url):
    q=urllib.request.Request(url,headers={"User-Agent":UA,"Accept-Language":"it-IT,it;q=0.9"})
    with urllib.request.urlopen(q,timeout=25) as r:
        return r.read().decode("utf-8","replace")

def plain(s):
    s=re.sub(r"<script\\b.*?</script>"," ",s,flags=re.I|re.S)
    s=re.sub(r"<style\\b.*?</style>"," ",s,flags=re.I|re.S)
    return re.sub(r"\\s+"," ",unescape(re.sub(r"<[^>]+>"," ",s))).strip()

def cparts(n):
    m=re.match(r"^\\s*([A-Za-z]*)(\\d+)\\s*/\\s*([A-Za-z]*)(\\d+)\\s*$",str(n or ""))
    return (m.group(1).upper(),int(m.group(2)),m.group(3).upper(),int(m.group(4))) if m else None

def rarity_variant(r):
    x=norm(r)
    if "reverse" in x: return "Reverse Holo"
    if x in {"h","holo","olografica","olografiche"}: return "Holo"
    return None

def discover_ids(html):
    ids=[]
    for m in re.finditer(r"poke_idserie(?:=|%3D)(\\d{1,12})",html,re.I):
        if m.group(1) not in ids and m.group(1)!="0": ids.append(m.group(1))
    for m in re.finditer(r"<option[^>]+value=[\"'](\\d{1,12})[\"']",html,re.I):
        if m.group(1) not in ids and m.group(1)!="0": ids.append(m.group(1))
    return ids[:250]

def set_name(html):
    t=plain(html[:160000])
    m=re.search(r"in inglese\\s+(.{2,120}?)\\s+carta\\s+codice\\s+numero\\s+rarit",t,re.I)
    if not m: return ""
    return m.group(1).split("/")[0].strip()

ROW=re.compile(r"(?P<name>[A-Za-zÀ-ÿ0-9'’.:\\- ]+?)\\s+(?P<sku>PO-[A-Z0-9\\-]+_(?P<lang>ita|eng))\\s+(?P<number>[A-Za-z]*\\d+\\s*/\\s*[A-Za-z]*\\d+)\\s+(?P<rarity>[A-Za-z0-9*+\\- ]{1,30})\\s+(?P<condition>mint/near mint|near mint|mint)\\s+€\\s*(?P<price>\\d+(?:[.,]\\d{1,2})?)",re.I)

def rows(html):
    t=plain(html); out=[]
    for m in ROW.finditer(t):
        d=m.groupdict(); d["price"]=float(d["price"].replace(",","."))
        d["available"]=not bool(re.match(r"\\s*al momento\\s+non disponibile",t[m.end():m.end()+100],re.I))
        out.append(d)
    return out

def main():
    data=json.loads(RETAIL.read_text(encoding="utf-8"))
    idx=defaultdict(list)
    for c in data.get("cards",{}).values():
        cp=cparts(c.get("number"))
        if cp: idx[(norm(c.get("set")),cp,norm(c.get("name")),c.get("variant"))].append(c)

    st=Counter(); examples=[]; seen=set(); sets=[]
    ids=discover_ids(get(HOME)); st["discoveredSetIds"]=len(ids)
    for sid in ids:
        try:
            url=SEARCH+"?"+urllib.parse.urlencode({"poke_idrarita":"0","poke_idserie":sid,"poke_ricerca":"","poke_tipocarta":"tutte"})
            html=get(url); rr=rows(html)
            if not rr: continue
            sn=set_name(html)
            st["setPagesWithRows"]+=1; st["rows"]+=len(rr); sets.append({"id":sid,"set":sn,"rows":len(rr)})
            for r in rr:
                if r["lang"].lower()!="ita": st["languageRejected"]+=1; continue
                if not r["available"]: st["unavailable"]+=1; continue
                v=rarity_variant(r["rarity"])
                if not v: st["variantAmbiguous"]+=1; continue
                cp=cparts(r["number"])
                cand=idx.get((norm(sn),cp,norm(r["name"]),v),[]) if cp and sn else []
                if len(cand)!=1: st["identityRejected"]+=1; continue
                c=cand[0]; k=(norm(c["set"]),c["number"],norm(c["name"]),v)
                if k in seen: st["duplicateIdentity"]+=1; continue
                seen.add(k); st["acceptedMatches"]+=1
                stores={o.get("store") for o in c.get("offers",[]) if o.get("store")}
                gain=not c.get("stats",{}).get("reliable") and len(stores|{"LPPCollecting"})>=3
                if gain: st["newReliablePotential"]+=1
                if len(examples)<50:
                    examples.append({"set":c["set"],"number":c["number"],"name":c["name"],"variant":v,"price":r["price"],"rarityRaw":r["rarity"],"existingStores":sorted(stores),"newReliablePotential":gain,"sourceUrl":url})
            time.sleep(.1)
        except Exception as e:
            st["errors"]+=1
            if len(examples)<50: examples.append({"setId":sid,"error":str(e)})
    report={"schema":1,"source":"LPPCollecting","mode":"read-only diagnostic","rules":{"language":"ITA only","condition":"mint/near mint / near mint / mint","availability":"reject explicit al momento non disponibile","variantsAccepted":["Holo","Reverse Holo"],"identity":"exact set + full collector number + exact normalized name + exact variant","cardmarketTouched":False,"retailPricesModified":False},"stats":dict(st),"sets":sets,"examples":examples}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report["stats"],ensure_ascii=False,indent=2))
    print("Report:",REPORT)

if __name__=="__main__":
    main()
