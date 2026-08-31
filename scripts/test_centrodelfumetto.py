#!/usr/bin/env python3
# Cardoryx - Centro del Fumetto V5 ottimizzato
# TEST ISOLATO READ-ONLY - stesso filename
# Non modifica retail_prices.json e non tocca Cardmarket.

import json
import re
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from html import unescape
from pathlib import Path

BASE = "https://www.centrodelfumetto.it"
SITEMAP_INDEX = BASE + "/sitemap_index.xml"
RETAIL = Path("data/retail_prices.json")
REPORT = Path("centro_fumetto_test_report.json")
UA = "Mozilla/5.0 (compatible; CardoryxRetailAudit/5.1)"
TIMEOUT = 10
MAX_PRODUCTS = 100
POKEMON_SINGLE_PATH = "/pokemon/pokemon-single/"

LABELS = ("Espansione","Condizione","Rarità","Rarita","Foiling","Reverse Holo",
          "Lingua","N° Collezione","N° collezione","Numero Collezione","Numero collezione")

def norm(s):
    s = unicodedata.normalize("NFKD", str(s or ""))
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = unescape(s).lower().replace("’", "'")
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()

def get(url):
    req = urllib.request.Request(url, headers={
        "User-Agent": UA, "Accept-Language": "it-IT,it;q=0.9",
        "Accept": "text/html,application/xhtml+xml,application/xml,text/xml,*/*",
        "Connection": "close"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return r.read().decode("utf-8","replace"), r.geturl(), getattr(r,"status",None)

def locs(xml):
    return [unescape(x.strip()) for x in re.findall(r"<loc>(.*?)</loc>", xml, re.I|re.S)]

def plain(html):
    html = re.sub(r"<script\b.*?</script>", " ", html, flags=re.I|re.S)
    html = re.sub(r"<style\b.*?</style>", " ", html, flags=re.I|re.S)
    return re.sub(r"\s+", " ", unescape(re.sub(r"<[^>]+>", " ", html))).strip()

def collector(v):
    m = re.match(r"^([A-Za-z]*)(\d{1,4})(?:\s*[/\-]\s*([A-Za-z]*)(\d{1,4}))?$", str(v or "").strip())
    if not m: return None
    return (m.group(1).upper(), int(m.group(2)), (m.group(3) or "").upper(),
            int(m.group(4)) if m.group(4) else None)

def cards(data):
    x=data.get("cards",{})
    return x if isinstance(x,list) else x.values()

def indexes(data):
    exact=defaultdict(list); sets=set()
    for c in cards(data):
        cp=collector(c.get("number"))
        if not cp: continue
        sk=norm(c.get("set")); sets.add(sk)
        exact[(sk,cp,norm(c.get("name")),c.get("variant"))].append(c)
    return exact,sets

def store_count(c):
    return len({norm(o.get("store")) for o in c.get("offers",[]) if o.get("store")})

def field(text,label):
    nxt="|".join(re.escape(x) for x in LABELS)
    m=re.search(re.escape(label)+r"\s*:\s*(.*?)\s+(?=(?:"+nxt+r")\s*:|$)",text,re.I)
    return m.group(1).strip() if m else ""

def price(html,text):
    pats=[
      (html,r'property=["\']product:price:amount["\'][^>]*content=["\']([0-9]+(?:[.,][0-9]{1,2})?)'),
      (html,r'itemprop=["\']price["\'][^>]*content=["\']([0-9]+(?:[.,][0-9]{1,2})?)'),
      (text,r'€\s*([0-9]+(?:[.,][0-9]{1,2})?)')]
    for hay,pat in pats:
        m=re.search(pat,hay,re.I|re.S)
        if m:
            try:return float(m.group(1).replace(",","."))
            except ValueError:pass
    return None

def available(html,text):
    if re.search(r'schema\.org/OutOfStock|\b(?:Esaurito|Non disponibile|Out of stock)\b',html+" "+text,re.I):
        return False
    if re.search(r'schema\.org/InStock|single_add_to_cart_button|Aggiungi al carrello',html,re.I):
        return True
    return None

def variant(rarity,foiling,reverse):
    nr,nf,nv=norm(rarity),norm(foiling),norm(reverse)
    if nv in {"si","yes","true"} or "reverse holo" in nr or "reverse holo" in nf:
        return "Reverse Holo"
    if ("holo" in nr or "holo" in nf) and "reverse" not in nr+nf:
        return "Holo"
    if nv in {"no","false"} and nf in {"","no","none","non foil","non holo"} and "holo" not in nr and "reverse" not in nr:
        return "Normal"
    return None

def clean_name(title,number):
    s=re.sub(r"^\s*Carta\s+Pok[eé]mon\s+","",str(title or ""),flags=re.I)
    if number:
        pos=s.lower().find(str(number).lower())
        if pos>0:s=s[:pos]
    return s.strip(" -–—")

def parse(html,url):
    text=plain(html)
    h=re.search(r"<h1[^>]*>(.*?)</h1>",html,re.I|re.S)
    title=plain(h.group(1)) if h else ""
    num=field(text,"N° Collezione") or field(text,"N° collezione") or field(text,"Numero Collezione") or field(text,"Numero collezione")
    rar=field(text,"Rarità") or field(text,"Rarita")
    foil=field(text,"Foiling"); rev=field(text,"Reverse Holo")
    return {"url":url,"title":title,"name":clean_name(title,num),"set":field(text,"Espansione"),
            "condition":field(text,"Condizione"),"language":field(text,"Lingua"),"number":num,
            "rarity":rar,"foiling":foil,"reverseHolo":rev,"variant":variant(rar,foil,rev),
            "price":price(html,text),"available":available(html,text)}

def discover():
    xml,_,_=get(SITEMAP_INDEX)
    sms=[u for u in locs(xml) if "product-sitemap" in u.lower()]
    direct=BASE+"/product-sitemap.xml"
    if direct not in sms:sms.insert(0,direct)
    out=[]; seen=set(); smstats=[]
    for sm in sms:
        try:
            body,final,status=get(sm); ls=locs(body)
            smstats.append({"url":sm,"finalUrl":final,"status":status,"locs":len(ls)})
            for u in ls:
                if POKEMON_SINGLE_PATH in u.lower() and u not in seen:
                    seen.add(u);out.append(u)
        except Exception as e:smstats.append({"url":sm,"error":repr(e)})
    return out,smstats

def main():
    data=json.loads(RETAIL.read_text(encoding="utf-8"))
    exact,known_sets=indexes(data)
    urls,smstats=discover()
    st=Counter(discoveredPokemonSingleUrls=len(urls))
    eligible=sorted(u for u in urls if "near-mint" in u.lower() and "italiano" in u.lower())
    st["prefilteredNearMintItaliano"]=len(eligible)
    examples=[]; rejects=[]; unknown=Counter()

    for u in eligible[:MAX_PRODUCTS]:
        st["attempted"]+=1
        try:
            html,final,_=get(u);st["fetched"]+=1;p=parse(html,final)
            if norm(p["language"])!="italiano":st["pageLanguageRejected"]+=1;continue
            if norm(p["condition"])!="near mint":st["pageConditionRejected"]+=1;continue
            if p["available"] is False:st["unavailable"]+=1;continue
            if p["available"] is None:st["availabilityUnconfirmed"]+=1;continue
            if not p["price"] or p["price"]<=0:st["priceUnavailable"]+=1;continue
            cp=collector(p["number"])
            if not cp:st["numberUnavailable"]+=1;continue
            if not p["set"]:st["setUnavailable"]+=1;continue
            if not p["variant"]:st["variantUnconfirmed"]+=1;continue
            st["usableBeforeIdentity"]+=1
            sk=norm(p["set"])
            if sk not in known_sets:
                st["setNotExactCardoryx"]+=1;unknown[p["set"]]+=1;continue
            matches=exact.get((sk,cp,norm(p["name"]),p["variant"]),[])
            if len(matches)==1:
                st["exactMatches"]+=1;c=matches[0];n=store_count(c)
                if n>=3:st["matchedAlreadyReliable"]+=1
                elif n==2:st["newReliablePotential"]+=1
                else:st["matchedCurrentlyNotReliable"]+=1
                if len(examples)<50:examples.append({"shop":p,"cardoryx":{"set":c.get("set"),"number":c.get("number"),"name":c.get("name"),"variant":c.get("variant"),"currentStores":n}})
            elif len(matches)>1:st["identityAmbiguous"]+=1
            else:st["identityRejected"]+=1
        except Exception as e:
            st["errors"]+=1
            if len(rejects)<30:rejects.append({"url":u,"error":repr(e)})

    report={"schema":5,"source":"Centro del Fumetto","mode":"read-only conservative matching diagnostic - optimized",
      "rules":{"catalogPath":POKEMON_SINGLE_PATH,"urlPrefilter":"near-mint + italiano",
               "language":"Italiano exact on page","condition":"Near Mint exact on page",
               "availability":"explicit in-stock signal required",
               "identityRule":"exact set + collector number + exact normalized name + exact variant",
               "createsNewIdentity":False,"cardmarketTouched":False,"retailPricesModified":False},
      "limits":{"maxProductsFetched":MAX_PRODUCTS,"sampling":"deterministic sorted Near Mint Italiano URLs"},
      "stats":dict(st),"sitemaps":smstats,"topUnmappedSets":unknown.most_common(30),
      "exactExamples":examples,"errorExamples":rejects}
    REPORT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding="utf-8")
    print(json.dumps(report["stats"],ensure_ascii=False,indent=2))
    print("Report:",REPORT)

if __name__=="__main__":
    main()
