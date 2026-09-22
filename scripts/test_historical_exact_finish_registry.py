#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path
from scripts.test_variant_finish_audit import VERIFIED_HISTORICAL_CHECKLIST_FINISHES

ROOT=Path(__file__).resolve().parents[1]
source=(ROOT/"index.html").read_text(encoding="utf-8")

def extract_function(name):
    marker=f"function {name}("
    start=source.find(marker)
    assert start>=0,name
    brace=source.find("{",start)
    depth=0; quote=None; esc=False
    for i in range(brace,len(source)):
        ch=source[i]
        if quote:
            if esc: esc=False
            elif ch=="\\": esc=True
            elif ch==quote: quote=None
            continue
        if ch in ("'",'"',"`"): quote=ch; continue
        if ch=="{": depth+=1
        elif ch=="}":
            depth-=1
            if depth==0:return source[start:i+1]
    raise AssertionError(name)

def extract_object(name):
    marker=f"const {name} ="
    start=source.find(marker)
    assert start>=0,name
    brace=source.find("{",start)
    depth=0; quote=None; esc=False
    for i in range(brace,len(source)):
        ch=source[i]
        if quote:
            if esc: esc=False
            elif ch=="\\": esc=True
            elif ch==quote: quote=None
            continue
        if ch in ("'",'"',"`"): quote=ch; continue
        if ch=="{": depth+=1
        elif ch=="}":
            depth-=1
            if depth==0:return source[brace:i+1]
    raise AssertionError(name)

normal_ids={cid for cid,row in VERIFIED_HISTORICAL_CHECKLIST_FINISHES.items() if "Normal" in row["finishes"]}
reverse_ids={cid for cid,row in VERIFIED_HISTORICAL_CHECKLIST_FINISHES.items() if "Reverse Holo" in row["finishes"]}
holo_only={cid for cid,row in VERIFIED_HISTORICAL_CHECKLIST_FINISHES.items() if row["finishes"]==["Holo"]}

assert len(VERIFIED_HISTORICAL_CHECKLIST_FINISHES)==59
assert len(normal_ids)==45
assert len(reverse_ids)==50
assert len(holo_only)==5

normal_obj=extract_object("VERIFIED_NORMAL_FINISHES")
reverse_obj=extract_object("VERIFIED_REVERSE_FINISHES")
for cid in normal_ids:
    assert f"'{cid}':" in normal_obj,cid
for cid in reverse_ids:
    assert f"'{cid}':" in reverse_obj,cid
for cid in holo_only:
    assert f"'{cid}':" not in normal_obj,cid
    assert f"'{cid}':" not in reverse_obj,cid

doc=extract_function("documentedVariantsForCard")
assert "verifiedNormalFinish(card)" in doc
assert "verifiedReverseFinish(card)" in doc

funcs="\n".join(extract_function(x) for x in (
    "normText","canonicalPrintedLocalId","printedLocalIdParts","exactLocalIdKey","cardSetId",
    "verifiedNormalFinish","verifiedReverseFinish"
))
rows={cid:{"setId":r["setId"],"localId":r["localId"]} for cid,r in VERIFIED_HISTORICAL_CHECKLIST_FINISHES.items()}
js=f"""
const VERIFIED_NORMAL_FINISHES={normal_obj};
const VERIFIED_REVERSE_FINISHES={reverse_obj};
{funcs}
const rows={json.dumps(rows,sort_keys=True)};
const normals={json.dumps(sorted(normal_ids))};
const reverses={json.dumps(sorted(reverse_ids))};
function card(id){{
  const r=rows[id];
  return {{id,tcgdexId:id,localId:r.localId,set:{{id:r.setId}}}};
}}
for(const id of normals){{
  if(!verifiedNormalFinish(card(id)))throw new Error('normal '+id);
}}
for(const id of reverses){{
  if(!verifiedReverseFinish(card(id)))throw new Error('reverse '+id);
}}
for(const id of Object.keys(rows)){{
  const c=card(id);
  const wrongSet={{...c,set:{{id:c.set.id+'-wrong'}}}};
  const wrongLocal={{...c,localId:String(c.localId)+'-wrong'}};
  if(verifiedNormalFinish(wrongSet)||verifiedReverseFinish(wrongSet))throw new Error('wrong set '+id);
  if(verifiedNormalFinish(wrongLocal)||verifiedReverseFinish(wrongLocal))throw new Error('wrong local '+id);
}}
if(verifiedNormalFinish({{id:'xy1-999',tcgdexId:'xy1-999',localId:'999',set:{{id:'xy1'}}}}))throw new Error('unregistered normal leaked');
if(verifiedReverseFinish({{id:'xy1-999',tcgdexId:'xy1-999',localId:'999',set:{{id:'xy1'}}}}))throw new Error('unregistered reverse leaked');
process.stdout.write(JSON.stringify({{
  exactHistoricalIdentities:Object.keys(rows).length,
  exactNormals:normals.length,
  exactReverses:reverses.length,
  holoOnlyAuditEvidence:{len(holo_only)},
  wrongSetRejected:true,
  wrongLocalRejected:true,
  unregisteredIdentityRejected:true
}}));
"""
print(subprocess.check_output(["node","-e",js],text=True).strip())
