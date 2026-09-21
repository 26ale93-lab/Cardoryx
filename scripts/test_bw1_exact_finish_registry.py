#!/usr/bin/env python3
import json
import re
import subprocess
from pathlib import Path

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

normal_ids={"bw1-1","bw1-2","bw1-13","bw1-38","bw1-44","bw1-56","bw1-62","bw1-68","bw1-74","bw1-80","bw1-87","bw1-92","bw1-99","bw1-105","bw1-110"}
reverse_ids=normal_ids-{"bw1-105","bw1-110"}

normal_obj=extract_object("VERIFIED_NORMAL_FINISHES")
reverse_obj=extract_object("VERIFIED_REVERSE_FINISHES")
for cid in normal_ids:
    assert f"'{cid}':" in normal_obj,cid
for cid in reverse_ids:
    assert f"'{cid}':" in reverse_obj,cid
for cid in ("bw1-105","bw1-110"):
    assert f"'{cid}':" not in reverse_obj,cid

doc=extract_function("documentedVariantsForCard")
assert "verifiedNormalFinish(card)" in doc
assert "verifiedReverseFinish(card)" in doc

funcs="\n".join(extract_function(x) for x in (
    "normText","canonicalPrintedLocalId","printedLocalIdParts","exactLocalIdKey","cardSetId",
    "verifiedNormalFinish","verifiedReverseFinish"
))
js=f"""
const VERIFIED_NORMAL_FINISHES={normal_obj};
const VERIFIED_REVERSE_FINISHES={reverse_obj};
{funcs}
function card(id,localId){{return {{id,tcgdexId:id,localId,set:{{id:'bw1'}}}}}}
const normals={json.dumps(sorted(normal_ids))};
const reverses={json.dumps(sorted(reverse_ids))};
for(const id of normals){{
  const local=id.split('-')[1];
  if(!verifiedNormalFinish(card(id,local)))throw new Error('normal '+id);
}}
for(const id of reverses){{
  const local=id.split('-')[1];
  if(!verifiedReverseFinish(card(id,local)))throw new Error('reverse '+id);
}}
for(const id of ['bw1-105','bw1-110']){{
  const local=id.split('-')[1];
  if(verifiedReverseFinish(card(id,local)))throw new Error('energy reverse leaked '+id);
}}
if(verifiedNormalFinish(card('bw1-3','3')))throw new Error('unregistered normal leaked');
if(verifiedReverseFinish(card('bw1-3','3')))throw new Error('unregistered reverse leaked');
if(verifiedNormalFinish({{id:'bw1-1',tcgdexId:'bw1-1',localId:'1',set:{{id:'wrong'}}}}))throw new Error('wrong set leaked');
process.stdout.write(JSON.stringify({{
  exactNormals:normals.length,
  exactReverses:reverses.length,
  basicEnergiesNormalOnly:true,
  unregisteredIdentityRejected:true,
  wrongSetRejected:true
}}));
"""
print(subprocess.check_output(["node","-e",js],text=True).strip())
