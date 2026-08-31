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

BASE="https://www.centrodelfumetto.it"
START=BASE+"/pokemon/pokemon-single/"
REPORT=Path("centrodelfumetto_test_report.json")
MAX_PAGES=12; MAX_PRODUCTS=180

def links(h):
    out=[]; seen=set()
    for x in re.findall(r'href=["\']([^"\']+)["\']',h,re.I):
        u=urljoin(BASE,unescape(x)); p=urlparse(u)
        if p.netloc not in ("www.centrodelfumetto.it","centrodelfumetto.it"): continue
        if "/pokemon/pokemon-single/" not in p.path or p.path.rstrip("/")=="/pokemon/pokemon-single": continue
        u=f"https://www.centrodelfumetto.it{p.path}"
        if not u.endswith("/"): u+="/"
        if u not in seen: seen.add(u); out.append(u)
    return out

def field(t,label):
    m=re.search(rf"{re.escape(label)}\s*:\s*(.+?)(?=\s+(?:Espansione|Condizione|Rarità|Grading|First Edition|Foiling|Reverse Holo|Firmata|Alterata|Lingua|N° Collezione|Numero Collezione|Costo Mana|Legale nei Tornei|Colore)\s*:|$)",t,re.I)
    return m.group(1).strip() if m else ""

def main():
    idx,sets=indexes(); st=Counter(); urls=[]
    for page in range(1,MAX_PAGES+1):
        u=START if page==1 else START+f"page/{page}/"
        try:
            h,_=get(u); st["catalogPagesFetched"]+=1; urls+=links(h)
        except Exception: st["catalogPageErrors"]+=1
    urls=list(dict.fromkeys(urls)); st["uniqueProductLinks"]=len(urls)
    examples=[]
    for u in urls[:MAX_PRODUCTS]:
        st["attempted"]+=1
        try:
            h,final=get(u); t=text(h); st["fetched"]+=1
            title=re.search(r"<h1[^>]*>(.*?)</h1>",h,re.I|re.S)
            title=text(title.group(1)) if title else ""
            exp=field(t,"Espansione"); cond=field(t,"Condizione"); lang=field(t,"Lingua")
            num=field(t,"N° Collezione") or field(t,"Numero Collezione")
            rar=field(t,"Rarità"); rev=field(t,"Reverse Holo")
            price=money(t)
            available=not bool(re.search(r"\b(?:0 disponibili|esaurito|out of stock)\b",t,re.I))
            variant=finish_from_fields(rar,rev)
            name=title.split("—")[0].strip()
            if not (norm(lang)=="italiano" and norm(cond)=="near mint" and available and num and exp and price is not None):
                st["prefilterRejected"]+=1; continue
            st["usable"]+=1
            p=parts(num)
            candidates=[]
            if p:
                candidates=idx.get((norm(exp),p,norm(name),variant),[])
            if len(candidates)==1: st["exactMatches"]+=1
            else: st["identityRejected"]+=1
            if len(examples)<25:
                examples.append({"title":title,"set":exp,"number":num,"variant":variant,"price":price,"exactMatch":len(candidates)==1,"url":final})
        except Exception as e:
            st["errors"]+=1
    report={"schema":1,"source":"Centro del Fumetto","mode":"read-only diagnostic","ok":True,
            "rules":{"cardmarketTouched":False,"retailPricesModified":False,"createsNewIdentity":False,
                     "identity":"exact set + full number + exact name + exact variant","language":"Italiano","condition":"Near Mint","availability":"available only"},
            "stats":dict(st),"examples":examples}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report["stats"],ensure_ascii=False,indent=2)); print("Report:",REPORT)
if __name__=="__main__": main()
