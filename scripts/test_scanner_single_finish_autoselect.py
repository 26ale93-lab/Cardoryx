#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

INDEX=Path(__file__).resolve().parents[1]/"index.html"
source=INDEX.read_text(encoding="utf-8")

def extract_function(name):
    marker=f"function {name}("
    start=source.find(marker)
    assert start>=0, name
    brace=source.find("{",start)
    depth=0
    quote=None
    escape=False
    for i in range(brace,len(source)):
        ch=source[i]
        if quote:
            if escape:
                escape=False
            elif ch=="\\":
                escape=True
            elif ch==quote:
                quote=None
            continue
        if ch in ("'",'"',"`"):
            quote=ch
            continue
        if ch=="{":
            depth+=1
        elif ch=="}":
            depth-=1
            if depth==0:
                return source[start:i+1]
    raise AssertionError(f"Unclosed function: {name}")

choose=extract_function("chooseCard")
sync=extract_function("syncVariantAvailability")

# Binding timing gate: local finish evidence must be applied before the optional
# Play! lookup. Awaiting the lookup or relying on it for the first sync caused
# single-finish cards to stay unselected and previously caused an iOS freeze.
needle_sync="syncVariantAvailability(selectedCard,false);"
needle_refresh="refreshOfficialPlayAvailability(selectedCard,false);"
assert needle_sync in choose
assert needle_refresh in choose
# The regular API/search path must sync immediately before its non-blocking
# refresh. The separate _cardoryxLocal branch intentionally has its own awaited
# evidence flow and is outside this regression.
regular_tail=choose[choose.rfind("applyPlayAutoSeries(selectedCard,false);"):]
assert regular_tail.index(needle_sync) < regular_tail.index(needle_refresh)
assert "await refreshOfficialPlayAvailability(selectedCard,false" not in regular_tail

js=f"""
const assert=require('assert');

function canonicalVariant(v){{
  const x=String(v||'').trim();
  if(x==='Normale')return 'Normal';
  return x;
}}
let allowed=new Set();
function documentedVariantsForCard(){{return new Set(allowed)}}
function normalizedPlaySeries(v){{return String(v||'')}}
function canonicalStamp(v){{return v||'None'}}

function makeOption(value){{
  return {{
    value,
    disabled:false,
    attrs:{{}},
    setAttribute(k,v){{this.attrs[k]=v}}
  }};
}}
const variant={{
  value:'Non so',
  options:[
    makeOption('Normal'),makeOption('Holo'),makeOption('Reverse Holo'),
    makeOption('Speciale / Altro'),makeOption('Non so')
  ],
  get selectedOptions(){{
    return [this.options.find(o=>o.value===this.value)||this.options[0]]
  }}
}};
const stamp={{value:'None'}};
const playSeries={{value:''}};
const editVariant={{
  value:'Holo',
  options:[
    makeOption('Normal'),makeOption('Holo'),makeOption('Reverse Holo'),
    makeOption('Speciale / Altro'),makeOption('Non so')
  ],
  get selectedOptions(){{
    return [this.options.find(o=>o.value===this.value)||this.options[0]]
  }}
}};
const editStamp={{value:'None'}};
const editPlaySeries={{value:''}};
const document={{
  getElementById(id){{
    return {{variant,stamp,playSeries,editVariant,editStamp,editPlaySeries}}[id]||null;
  }}
}};

{sync}

allowed=new Set(['Normal','Speciale / Altro','Non so']);
variant.value='Non so';
let result=syncVariantAvailability({{}},false);
assert.strictEqual(variant.value,'Normal');
assert.deepStrictEqual(result.sort(),['Non so','Normal','Speciale / Altro'].sort());

allowed=new Set(['Normal','Reverse Holo','Speciale / Altro','Non so']);
variant.value='Non so';
syncVariantAvailability({{}},false);
assert.strictEqual(variant.value,'Non so');

allowed=new Set(['Normal','Speciale / Altro','Non so']);
editVariant.value='Holo';
syncVariantAvailability({{}},true);
assert.strictEqual(editVariant.value,'Normal');

allowed=new Set(['Normal','Holo','Speciale / Altro','Non so']);
editVariant.value='Holo';
syncVariantAvailability({{}},true);
assert.strictEqual(editVariant.value,'Holo');

console.log(JSON.stringify({{
  immediateSyncBeforePlayLookup:true,
  noBlockingPlayAwait:true,
  soleNormalAutoselected:true,
  multiplePhysicalRemainManual:true,
  editValidFinishPreserved:true
}}));
"""

out=subprocess.check_output(["node","-e",js],text=True)
print(out.strip())
