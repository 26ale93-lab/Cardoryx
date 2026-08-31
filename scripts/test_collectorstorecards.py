#!/usr/bin/env python3
import json, re, time, unicodedata, urllib.request
from collections import Counter, defaultdict
from html import unescape
from pathlib import Path
from urllib.parse import urljoin, urlparse

RETAIL = Path("data/retail_prices.json")
UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/1.0)"
TIMEOUT = 15

def norm(s):
    s=unicodedata.normalize("NFKD",str(s or ""))
    s="".join(c for c in s if not unicodedata.combining(c))
    s=unescape(s).lower().replace("’","'")
    return re.sub(r"\s+"," ",re.sub(r"[^a-z0-9]+"," ",s)).strip()

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":UA,"Accept-Language":"it-IT,it;q=0.9"})
    with urllib.request.urlopen(req,timeout=TIMEOUT) as r:
        return r.read().decode("utf-8","replace"),r.geturl()

def text(h):
    h=re.sub(r"<script\b.*?</script>"," ",h,flags=re.I|re.S)
    h=re.sub(r"<style\b.*?</style>"," ",h,flags=re.I|re.S)
    return re.sub(r"\s+"," ",unescape(re.sub(r"<[^>]+>"," ",h))).strip()

def parts(n):
    m=re.match(r"^\s*([A-Za-z]*)(\d+)\s*[-/]\s*([A-Za-z]*)(\d+)\s*$",str(n or ""))
    return (m.group(1).upper(),int(m.group(2)),m.group(3).upper(),int(m.group(4))) if m else None

def indexes():
    d=json.loads(RETAIL.read_text(encoding="utf-8"))
    exact=defaultdict(list); sets={}
    for c in d.get("cards",{}).values():
        p=parts(c.get("number"))
        if p:
            exact[(norm(c.get("set")),p,norm(c.get("name")),c.get("variant"))].append(c)
        if c.get("set"): sets[norm(c["set"])]=c["set"]
    return exact,sets

def money(s):
    m=re.search(r"€\s*([0-9]+(?:[.,][0-9]{1,2})?)",s)
    return float(m.group(1).replace(",",".")) if m else None

def finish_from_fields(rarity="", reverse=""):
    nr=norm(rarity); nv=norm(reverse)
    if nv in ("si","yes","true"): return "Reverse Holo"
    if "reverse" in nr: return "Reverse Holo"
    if "holo" in nr: return "Holo"
    return "Normal"

BASE="https://collectorstorecards.it"
COLL=BASE+"/collections/carte-singole-pokemon"
REPORT=Path("collectorstorecards_test_report.json")
MAX_PAGES=12

def main():
    idx,sets=indexes(); st=Counter(); examples=[]
    # Shopify products.json: test isolato, sola lettura.
    products=[]
    for page in range(1,MAX_PAGES+1):
        u=f"{COLL}/products.json?limit=250&page={page}"
        try:
            h,_=get(u); obj=json.loads(h); batch=obj.get("products",[])
            st["catalogPagesFetched"]+=1
            if not batch: break
            products+=batch
            if len(batch)<250: break
        except Exception:
            st["catalogPageErrors"]+=1; break
    st["products"]=len(products)
    for p in products:
        st["attempted"]+=1
        handle=p.get("handle","")
        u=f"{BASE}/products/{handle}"
        try:
            h,final=get(u); t=text(h); st["fetched"]+=1
            title=p.get("title","")
            if not re.search(r"\bITA\b",title,re.I) or not re.search(r"\bNear Mint\b",t,re.I):
                st["prefilterRejected"]+=1; continue
            if re.search(r"\bEsaurito\b",t,re.I):
                st["unavailable"]+=1; continue
            sm=re.search(r"\bSet:\s*(.+?)(?=\s+(?:Rarità|Numerazione|Lingua):)",t,re.I)
            nm=re.search(r"\bNumerazione:\s*([A-Za-z]*\d+(?:\s*[/\-]\s*[A-Za-z]*\d+)?)",t,re.I)
            rm=re.search(r"\bRarità:\s*(.+?)(?=\s+(?:Numerazione|Lingua):)",t,re.I)
            if not(sm and nm and rm):
                st["identityFieldsMissing"]+=1; continue
            setname=sm.group(1).strip(); num=nm.group(1).replace(" ","").replace("-","/")
            # Se la pagina mostra solo il numeratore, prova il denominatore dal titolo.
            if "/" not in num:
                tm=re.search(r"\b([A-Za-z]*\d+)\s*/\s*([A-Za-z]*\d+)\b",title)
                if tm and norm(tm.group(1))==norm(num): num=f"{tm.group(1)}/{tm.group(2)}"
            rarity=rm.group(1).strip()
            variant=finish_from_fields(rarity,"")
            # Rarità speciali non equivalgono automaticamente a Holo: fail closed.
            if variant=="Normal" and any(x in norm(rarity) for x in ["illustration rare","ultra rare","double rare","special illustration","shiny rare"]):
                st["variantAmbiguous"]+=1; continue
            price=None
            variants=p.get("variants",[])
            available_prices={float(v["price"]) for v in variants if v.get("available") and v.get("price")}
            if len(available_prices)==1: price=next(iter(available_prices))
            if price is None:
                st["priceUnavailable"]+=1; continue
            name=re.sub(r"^\s*Pok[eé]mon\s+","",title,flags=re.I)
            name=re.split(r"\s+[A-Za-z]*\d+\s*/\s*[A-Za-z]*\d+\s+",name,maxsplit=1)[0].strip()
            pp=parts(num)
            candidates=idx.get((norm(setname),pp,norm(name),variant),[]) if pp else []
            st["usable"]+=1
            if len(candidates)==1: st["exactMatches"]+=1
            else: st["identityRejected"]+=1
            if len(examples)<25:
                examples.append({"title":title,"set":setname,"number":num,"rarity":rarity,"variant":variant,"price":price,"exactMatch":len(candidates)==1,"url":final})
        except Exception:
            st["errors"]+=1
        time.sleep(.02)
    report={"schema":1,"source":"Collector Store Cards","mode":"read-only diagnostic","ok":True,
            "rules":{"cardmarketTouched":False,"retailPricesModified":False,"createsNewIdentity":False,
                     "identity":"exact set + full number + exact name + exact variant","language":"Italiano","condition":"Near Mint","availability":"available only",
                     "ambiguousRarity":"rejected"},
            "stats":dict(st),"examples":examples}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report["stats"],ensure_ascii=False,indent=2)); print("Report:",REPORT)
if __name__=="__main__": main()
