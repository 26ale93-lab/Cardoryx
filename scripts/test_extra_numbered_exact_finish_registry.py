#!/usr/bin/env python3
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.test_variant_finish_audit import VERIFIED_EXTRA_NUMBERED_MARKETPLACE_FINISHES
source=(ROOT/"index.html").read_text(encoding="utf-8")

def extract_function(name):
    marker=f"function {name}("
    start=source.find(marker); assert start>=0,name
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
    start=source.find(marker); assert start>=0,name
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

normal_ids={cid.lower() for cid,row in VERIFIED_EXTRA_NUMBERED_MARKETPLACE_FINISHES.items() if "Normal" in row["finishes"]}
holo_ids={cid.lower() for cid,row in VERIFIED_EXTRA_NUMBERED_MARKETPLACE_FINISHES.items() if "Holo" in row["finishes"]}
reverse_ids={cid.lower() for cid,row in VERIFIED_EXTRA_NUMBERED_MARKETPLACE_FINISHES.items() if "Reverse Holo" in row["finishes"]}

assert len(VERIFIED_EXTRA_NUMBERED_MARKETPLACE_FINISHES)==6
assert normal_ids=={"sm1-171"}
assert reverse_ids=={"sm1-171"}
assert holo_ids=={"sm1-153","sm1-162","sm12-242","sm12-257","sm12-271"}
for row in VERIFIED_EXTRA_NUMBERED_MARKETPLACE_FINISHES.values():
    assert set(row)=={"setId","localId","finishes","evidence"}

normal_obj=extract_object("VERIFIED_NORMAL_FINISHES")
holo_obj=extract_object("VERIFIED_HOLO_FINISHES")
reverse_obj=extract_object("VERIFIED_REVERSE_FINISHES")
for cid in normal_ids: assert f"'{cid}':" in normal_obj,cid
for cid in holo_ids: assert f"'{cid}':" in holo_obj,cid
for cid in reverse_ids: assert f"'{cid}':" in reverse_obj,cid

funcs="\n".join(extract_function(x) for x in (
    "normText","canonicalPrintedLocalId","printedLocalIdParts","exactLocalIdKey","cardSetId",
    "verifiedNormalFinish","verifiedHoloFinish","verifiedReverseFinish"
))
rows={cid.lower():{"setId":r["setId"],"localId":r["localId"]} for cid,r in VERIFIED_EXTRA_NUMBERED_MARKETPLACE_FINISHES.items()}
js=f"""
const VERIFIED_NORMAL_FINISHES={normal_obj};
const VERIFIED_HOLO_FINISHES={holo_obj};
const VERIFIED_REVERSE_FINISHES={reverse_obj};
{funcs}
const rows={json.dumps(rows,sort_keys=True)};
const normals={json.dumps(sorted(normal_ids))};
const holos={json.dumps(sorted(holo_ids))};
const reverses={json.dumps(sorted(reverse_ids))};
function card(id){{const r=rows[id];return {{id,tcgdexId:id,localId:r.localId,set:{{id:r.setId}}}}}}
for(const id of normals)if(!verifiedNormalFinish(card(id)))throw new Error('normal '+id);
for(const id of holos)if(!verifiedHoloFinish(card(id)))throw new Error('holo '+id);
for(const id of reverses)if(!verifiedReverseFinish(card(id)))throw new Error('reverse '+id);
for(const id of Object.keys(rows)){{
  const c=card(id);
  const wrongId={{...c,id:id+'-wrong',tcgdexId:id+'-wrong'}};
  const wrongSet={{...c,set:{{id:c.set.id+'-wrong'}}}};
  const wrongLocal={{...c,localId:String(c.localId)+'-wrong'}};
  for(const x of [wrongId,wrongSet,wrongLocal]){{
    if(verifiedNormalFinish(x)||verifiedHoloFinish(x)||verifiedReverseFinish(x))throw new Error('guard leaked '+id);
  }}
}}
for(const id of ['mep-028','svp-225']){{
  const fake={{id,tcgdexId:id,localId:id==='mep-028'?'028':'225',set:{{id:id.startsWith('mep')?'mep':'svp'}}}};
  if(verifiedNormalFinish(fake)||verifiedHoloFinish(fake)||verifiedReverseFinish(fake))throw new Error('stamped residual leaked into standard registry '+id);
}}
process.stdout.write(JSON.stringify({{
  exactIdentities:Object.keys(rows).length,
  exactNormals:normals.length,
  exactHolos:holos.length,
  exactReverses:reverses.length,
  wrongIdentityRejected:true,
  stampedResidualsExcluded:true,
  priceFieldsPresent:false
}}));
"""
print(subprocess.check_output(["node","-e",js],text=True).strip())
