#!/usr/bin/env python3
import json, urllib.request, concurrent.futures, time, importlib.util
from pathlib import Path

root=Path(__file__).resolve().parents[1]
index_path=root/"index.html"
index=index_path.read_text(encoding="utf-8")

spec=importlib.util.spec_from_file_location("finish_audit", root/"scripts/test_variant_finish_audit.py")
mod=importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
cards, parse_errors, upstream_sha=mod.load_official_database(Path("/tmp/tcgdex-cards-database"))

exact=mod.extract_js_object(index,"VERIFIED_EXACT_VARIANT_PRICES")
legacy=mod.extract_js_object(index,"VERIFIED_VARIANT_PRICES")

def canonical_local(v):
    s=str(v or "").strip()
    return s.lstrip("0") or s or "0"

raw=[]
for c in cards:
    for row in c.get("variants_detailed") or []:
        finish=mod.canonical_row_finish(row)
        if finish not in ("Poké Ball Reverse Holo","Master Ball Reverse Holo"):
            continue
        pid=int((row.get("thirdParty") or {}).get("cardmarket") or 0)
        if not pid:
            continue
        cid=str(c.get("id") or "").strip().lower()
        set_id=str((c.get("set") or {}).get("id") or "").strip().lower()
        local=str(c.get("localId") or "")
        rule=exact.get(cid)
        if (isinstance(rule,dict)
            and str(rule.get("setId") or "").lower()==set_id
            and canonical_local(rule.get("localId"))==canonical_local(local)
            and int(rule.get("productId") or 0)==pid
            and mod.canonical_finish(rule.get("finish"))==finish):
            continue
        raw.append({"tcgdexId":cid,"setId":set_id,"localId":local,"finish":finish,"productId":pid})

raw=list({(x["tcgdexId"],x["finish"],x["productId"]):x for x in raw}.values())

def get(lang,cid):
    url=f"https://api.tcgdex.net/v2/{lang}/cards/{cid}"
    last=None
    for attempt in range(3):
        try:
            req=urllib.request.Request(url,headers={"User-Agent":"Cardoryx-ball-index-generator/1.0"})
            with urllib.request.urlopen(req,timeout=30) as response:
                return json.load(response)
        except Exception as exc:
            last=exc
            time.sleep(.35*(attempt+1))
    raise RuntimeError(f"{lang} {cid}: {last}")

def live_legacy_covered(x,en,it):
    names={
        mod.norm((en.get("set") or {}).get("name") or ""),
        mod.norm((it.get("set") or {}).get("name") or "")
    }
    for k in legacy:
        try:
            ks,kn,kf=k.split("|",2)
        except ValueError:
            continue
        if (mod.norm(ks) in names
            and canonical_local(kn)==canonical_local(x["localId"])
            and mod.canonical_finish(kf)==x["finish"]):
            return True
    return False

def one(x):
    en=get("en",x["tcgdexId"])
    it=get("it",x["tcgdexId"])
    if live_legacy_covered(x,en,it):
        return None
    matched=[]
    for lang,card in (("en",en),("it",it)):
        rows=[]
        for row in card.get("variants_detailed") or []:
            if mod.canonical_row_finish(row)!=x["finish"]:
                continue
            pid=int((row.get("thirdParty") or {}).get("cardmarket") or 0)
            cm=(row.get("pricing") or {}).get("cardmarket") or {}
            ppid=int(cm.get("idProduct") or cm.get("id_product") or 0)
            if pid==x["productId"] and ppid==x["productId"]:
                rows.append((row,cm))
        if len(rows)!=1:
            raise AssertionError(f"{lang} exact row count {x}: {len(rows)}")
        matched.append(rows[0][1])
    cm=matched[0]
    if not any(float(cm.get(k) or 0)>0 for k in ("trend","avg7","avg30","avg","low")):
        raise AssertionError(f"No price {x}")
    return {
        **x,
        "en":en.get("name") or "",
        "it":it.get("name") or "",
        "low":cm.get("low"),"trend":cm.get("trend"),"avg1":cm.get("avg1"),
        "avg7":cm.get("avg7"),"avg30":cm.get("avg30"),"avg":cm.get("avg"),
        "updated":cm.get("updated") or ""
    }

rows=[]
with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
    for value in ex.map(one,raw):
        if value:
            rows.append(value)

rows.sort(key=lambda x:(x["setId"],x["tcgdexId"],x["finish"]))
assert len(rows)==508, f"Expected 508 exact missing rows, got {len(rows)}"
seen={}
for row in rows:
    assert row["productId"] not in seen, f"Duplicate productId {row['productId']}"
    seen[row["productId"]]=(row["tcgdexId"],row["finish"])

def js(v):
    return json.dumps(v,ensure_ascii=False,separators=(",",":"))

lines=[
    "// CARDORYX GENERATED EXACT BALL VARIANT PRICES — BEGIN",
    "// Generated from exact TCGdex EN+IT physical rows; do not infer outside these identities.",
    "const VERIFIED_EXACT_BALL_VARIANT_PRICES={"
]
for row in rows:
    key=f"{row['tcgdexId']}|{row['finish']}"
    obj={
        "setId":row["setId"],"localId":row["localId"],"names":[row["en"],row["it"]],
        "finish":row["finish"],"productId":row["productId"],
        "low":row["low"],"trend":row["trend"],"avg1":row["avg1"],
        "avg7":row["avg7"],"avg30":row["avg30"],"avg":row["avg"],
        "verified":row["updated"]
    }
    lines.append(f"  {js(key)}:{js(obj)},")
lines += [
    "};",
    "function verifiedExactBallVariantPrice(card,variant){",
    "  const id=String(card?.tcgdexId||card?.id||'').trim().toLowerCase();",
    "  const finish=canonicalVariant(variant||'Normal');",
    "  const rule=VERIFIED_EXACT_BALL_VARIANT_PRICES[`${id}|${finish}`];",
    "  if(!rule||cardSetId(card)!==rule.setId||exactLocalIdKey(card?.localId||'')!==exactLocalIdKey(rule.localId)||canonicalVariant(rule.finish)!==finish)return null;",
    "  const names=Array.isArray(rule.names)?rule.names:[];",
    "  if(names.length&&!names.some(name=>normText(card?.name||'')===normText(name)))return null;",
    "  return {...rule,source:`Cardmarket · TCGdex EN/IT exact Ball row · product ${rule.productId}`};",
    "}",
    "// CARDORYX GENERATED EXACT BALL VARIANT PRICES — END",
]
block="\n".join(lines)

begin="// CARDORYX GENERATED EXACT BALL VARIANT PRICES — BEGIN"
end="// CARDORYX GENERATED EXACT BALL VARIANT PRICES — END"
if begin in index:
    a=index.index(begin)
    b=index.index(end,a)+len(end)
    index=index[:a]+block+index[b:]
else:
    anchor="// Exact physical-identity variant prices. Keep these stricter than the legacy"
    pos=index.index(anchor)
    index=index[:pos]+block+"\n\n"+index[pos:]

old="""  const exact=verifiedExactVariantPrice(card,variant);
  if(exact)return exact;"""
new="""  const exact=verifiedExactVariantPrice(card,variant);
  if(exact)return exact;
  const exactBall=verifiedExactBallVariantPrice(card,variant);
  if(exactBall)return exactBall;"""
if new not in index:
    if old not in index:
        raise AssertionError("verifiedVariantPrice anchor missing")
    index=index.replace(old,new,1)

index_path.write_text(index,encoding="utf-8")
final=index_path.read_text(encoding="utf-8")
assert final.count(begin)==1 and final.count(end)==1
print(json.dumps({
    "generated":len(rows),
    "pokeball":sum(r["finish"].startswith("Poké") for r in rows),
    "masterball":sum(r["finish"].startswith("Master") for r in rows),
    "sets":sorted(set(r["setId"] for r in rows)),
    "upstreamSha":upstream_sha,
    "parseErrors":len(parse_errors)
},ensure_ascii=False,indent=2))
