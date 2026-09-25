#!/usr/bin/env python3
import collections, json, urllib.request
from pathlib import Path

BASE="https://api.tcgdex.net/v2/en"
ROOT=Path(__file__).resolve().parents[1]
INDEX=(ROOT/"index.html").read_text(encoding="utf-8")

def get(url):
    req=urllib.request.Request(url,headers={"User-Agent":"Cardoryx-readonly-audit/1.0"})
    with urllib.request.urlopen(req,timeout=30) as r:
        return json.load(r)

def detailed(cid):
    return get(f"{BASE}/cards/{cid}")

expected={
    "energy":"Energy Reverse Holo",
    "friendball":"Friend Ball Reverse Holo",
    "loveball":"Love Ball Reverse Holo",
    "quickball":"Quick Ball Reverse Holo",
    "duskball":"Dusk Ball Reverse Holo",
    "pokeball":"Poké Ball Reverse Holo",
    "team-rocket":"Team Rocket Reverse Holo",
}
for foil,variant in expected.items():
    assert variant in INDEX, f"UI/canonical variant missing: {variant}"
    assert f"foil==='{foil}'" in INDEX, f"finish resolver missing foil {foil}"
    assert f"canonicalFinishFoilLabel(x?.foil)==='{foil}'" in INDEX, f"market resolver missing foil {foil}"

set_data=get(f"{BASE}/sets/me02.5")
cards=set_data.get("cards") or []
counts=collections.Counter()
errors=[]
for row in cards:
    cid=row.get("id")
    if not cid:
        continue
    try:
        card=detailed(cid)
    except Exception as e:
        errors.append([cid,repr(e)])
        continue
    for v in card.get("variants_detailed") or []:
        foil=str(v.get("foil") or "").lower()
        if foil:
            counts[foil]+=1

assert not errors, f"TCGdex errors: {errors[:3]}"
observed_pattern={x for x in counts if x not in {"cosmos","gold","masterball"}}
unknown=sorted(observed_pattern-set(expected))
assert not unknown, f"Unhandled Ascended Heroes foil labels: {unknown}"

noibat=detailed("me02.5-156")
rows=noibat.get("variants_detailed") or []
by_foil={str(x.get("foil") or "").lower():x for x in rows if str(x.get("type") or "").lower()=="reverse"}
assert "energy" in by_foil, "Noibat Energy reverse missing upstream"
assert "friendball" in by_foil, "Noibat Friend Ball reverse missing upstream"

for foil,expected_pid in [("energy",870379),("friendball",870380)]:
    row=by_foil[foil]
    row_pid=int((row.get("thirdParty") or {}).get("cardmarket") or 0)
    pricing=(row.get("pricing") or {}).get("cardmarket") or {}
    pricing_pid=int(pricing.get("idProduct") or 0)
    assert row_pid==expected_pid, (foil,row_pid,expected_pid)
    assert pricing_pid==expected_pid, (foil,pricing_pid,expected_pid)
    assert any(float(pricing.get(k) or 0)>0 for k in ("trend","avg7","avg30","avg","low")), foil

assert "function tcgdexExactPatternCardmarketPrice" in INDEX
assert "rowPid!==pricingPid" in INDEX
assert "isAscendedNamedPatternReverseVariant(target)" in INDEX

# Execute the actual production finish resolver on Noibat's live detailed rows.
import subprocess, tempfile

def slice_between(start_marker,end_marker):
    a=INDEX.index(start_marker)
    b=INDEX.index(end_marker,a)
    return INDEX[a:b]

runtime_funcs="\n".join([
    slice_between("function canonicalFinishTypeLabel(", "function canonicalFinishFoilLabel("),
    slice_between("function canonicalFinishFoilLabel(", "function canonicalFinishSubtypeLabel("),
    slice_between("function canonicalFinishSubtypeLabel(", "function isPeelableDittoVariantRow("),
    slice_between("function isPeelableDittoVariantRow(", "function isManualVariantChoice("),
    slice_between("function addDetailedFinishes(", "function addModernStandardStructure("),
])
runtime_js=r"""
function normText(v){return String(v||'').normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim()}
""" + runtime_funcs + "\n" + f"""
const rows={json.dumps(rows)};
const allowed=new Set();
addDetailedFinishes(allowed,rows,{{base:true,special:true}});
const got=[...allowed].sort();
const expected=['Energy Reverse Holo','Friend Ball Reverse Holo','Normal'].sort();
if(JSON.stringify(got)!==JSON.stringify(expected)){{
  console.error(JSON.stringify({{got,expected}}));
  process.exit(1);
}}
console.log(JSON.stringify({{runtimeAllowed:got}}));
"""
with tempfile.NamedTemporaryFile("w",suffix=".js",delete=False,encoding="utf-8") as tmp:
    tmp.write(runtime_js)
    runtime_path=tmp.name
result=subprocess.run(["node",runtime_path],text=True,capture_output=True)
assert result.returncode==0, result.stderr or result.stdout
runtime_result=json.loads(result.stdout.strip())

print(json.dumps({
    "set":{"id":set_data.get("id"),"name":set_data.get("name"),"cards":len(cards)},
    "foilCounts":dict(sorted(counts.items())),
    "noibat":{
        "id":noibat.get("id"),
        "normalProduct":869767,
        "energyProduct":870379,
        "friendBallProduct":870380,
        "expectedSelectable":["Normal","Energy Reverse Holo","Friend Ball Reverse Holo"]
    },
    "unknownPatternFoils":unknown,
    "runtimeAllowed":runtime_result["runtimeAllowed"],
    "errors":len(errors),
    "result":"PASS"
},ensure_ascii=False,indent=2))def extract_between(name,next_name):
    start=INDEX.find(f"function {name}(")
    end=INDEX.find(f"function {next_name}(", start)
    assert start>=0 and end>start, f"Production function boundary missing: {name} -> {next_name}"
    return INDEX[start:end].strip()

runtime_funcs="\n".join([
    extract_between("canonicalFinishTypeLabel","canonicalFinishFoilLabel"),
    extract_between("canonicalFinishFoilLabel","canonicalFinishSubtypeLabel"),
    extract_between("canonicalFinishSubtypeLabel","isPeelableDittoVariantRow"),
    extract_between("isPeelableDittoVariantRow","isManualVariantChoice"),
    extract_between("addDetailedFinishes","addModernStandardStructure"),
])
runtime_js=r"""
function normText(v){return String(v||'').normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim()}
""" + runtime_funcs + "\n" + f"""
const rows={json.dumps(rows)};
const allowed=new Set();
addDetailedFinishes(allowed,rows,{{base:true,special:true}});
const got=[...allowed].sort();
const expected=['Energy Reverse Holo','Friend Ball Reverse Holo','Normal'].sort();
if(JSON.stringify(got)!==JSON.stringify(expected)){{
  console.error(JSON.stringify({{got,expected}}));
  process.exit(1);
}}
console.log(JSON.stringify({{runtimeAllowed:got}}));
"""
with tempfile.NamedTemporaryFile("w",suffix=".js",delete=False,encoding="utf-8") as tmp:
    tmp.write(runtime_js)
    runtime_path=tmp.name
result=subprocess.run(["node",runtime_path],text=True,capture_output=True)
assert result.returncode==0, result.stderr or result.stdout
runtime_result=json.loads(result.stdout.strip())

print(json.dumps({
    "set":{"id":set_data.get("id"),"name":set_data.get("name"),"cards":len(cards)},
    "foilCounts":dict(sorted(counts.items())),
    "noibat":{
        "id":noibat.get("id"),
        "normalProduct":869767,
        "energyProduct":870379,
        "friendBallProduct":870380,
        "expectedSelectable":["Normal","Energy Reverse Holo","Friend Ball Reverse Holo"]
    },
    "unknownPatternFoils":unknown,
    "runtimeAllowed":runtime_result["runtimeAllowed"],
    "errors":len(errors),
    "result":"PASS"
},ensure_ascii=False,indent=2))
