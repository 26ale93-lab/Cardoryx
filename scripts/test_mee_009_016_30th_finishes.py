#!/usr/bin/env python3
import json
import re
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/"index.html").read_text(encoding="utf-8")

def extract_fn(name):
    marker=re.search(rf"\bfunction\s+{re.escape(name)}\s*\(",SOURCE)
    assert marker,name
    header=re.search(r"\)\s*\{",SOURCE[marker.start():])
    assert header,name
    brace=marker.start()+header.end()-1
    depth=0
    quote=None
    esc=False
    line=False
    block=False
    i=brace
    while i<len(SOURCE):
        c=SOURCE[i]
        n=SOURCE[i+1] if i+1<len(SOURCE) else ""
        if line:
            if c=="\n": line=False
            i+=1
            continue
        if block:
            if c=="*" and n=="/":
                block=False
                i+=2
                continue
            i+=1
            continue
        if quote:
            if esc: esc=False
            elif c=="\\": esc=True
            elif c==quote: quote=None
            i+=1
            continue
        if c=="/" and n=="/":
            line=True
            i+=2
            continue
        if c=="/" and n=="*":
            block=True
            i+=2
            continue
        if c in ("'", '"', "`"):
            quote=c
            i+=1
            continue
        if c=="{": depth+=1
        elif c=="}":
            depth-=1
            if depth==0:
                return SOURCE[marker.start():i+1]
        i+=1
    raise AssertionError(name)

names=[
    "normText","canonicalStamp","normalizedPlaySeries","is30thCelebrationSet",
    "isMee30CelebrationEnergy","stampExistsForCard","documentedVariantsForCard",
    "syncStampAvailability"
]
js="\n".join(extract_fn(n) for n in names)
js+=r'''
function tcgdexExactMfbPokeballRow(){return null}
function tcgdexExactMcdonaldsStampRow(){return null}
function tcgdexMcdonalds2021AnniversaryRows(){return null}
function tcgdexExactSwshp25thStandardRow(){return null}
function verifiedMepStampRule(){return false}
function tcgdexExactMepStampRow(){return null}
function stampEvidenceFromTCGdex(){return false}
function stampEvidenceVerified(card,stamp){
  const st=canonicalStamp(stamp);
  if(is30thCelebrationSet(card)||isMee30CelebrationEnergy(card)){
    if(st==='30° Anniversario')return true;
    if(st==='Play! Pokémon'||st==='Pokémon Day')return false;
  }
  return false;
}
function tcgdexExactSwshpSetLogoRow(){return null}
function verifiedPrimaryWorldsStamp(){return ''}
function syncEditPlaySeriesVisibility(){}
function syncPlaySeriesVisibility(){}

const mapping={
  9:'Grass Energy',10:'Fire Energy',11:'Water Energy',12:'Lightning Energy',
  13:'Psychic Energy',14:'Fighting Energy',15:'Darkness Energy',16:'Metal Energy'
};
const results=[];
for(const [n0,name] of Object.entries(mapping)){
  const n=Number(n0);
  const id='mee-'+String(n).padStart(3,'0');
  const card={id,tcgdexId:id,localId:String(n).padStart(3,'0'),name,set:{id:'mee',name:'Mega Evolution Energy'}};
  if(!isMee30CelebrationEnergy(card))throw new Error('identity guard failed '+id);
  if(!stampExistsForCard(card,'30° Anniversario'))throw new Error('30th stamp missing '+id);
  if(stampExistsForCard(card,'Play! Pokémon'))throw new Error('Play leaked '+id);
  if(stampExistsForCard(card,'None'))throw new Error('None leaked '+id);
  const finishes=[...documentedVariantsForCard(card,'30° Anniversario','')];
  const expected=['Holo','Speciale / Altro','Non so'];
  if(JSON.stringify(finishes)!==JSON.stringify(expected))throw new Error('finish mismatch '+id+' '+JSON.stringify(finishes));
  results.push({id,name,finishes});
}

if(isMee30CelebrationEnergy({id:'mee-008',localId:'008',set:{id:'mee'}}))throw new Error('MEE008 leaked into 30th');
if(isMee30CelebrationEnergy({id:'mee-017',localId:'017',set:{id:'mee'}}))throw new Error('MEE017 leaked into 30th');
if(isMee30CelebrationEnergy({id:'other-009',localId:'009',set:{id:'other'}}))throw new Error('wrong set leaked into 30th');

const stampOptions=['None','Play! Pokémon','Pokémon Day','30° Anniversario','Altro'].map(value=>({value,disabled:false}));
const stamp={
  value:'None',
  options:stampOptions,
  get selectedOptions(){return [this.options.find(o=>o.value===this.value)||this.options[0]]}
};
const playSeries={value:'9'};
const stampInfo={textContent:''};
const document={
  getElementById(id){
    return {stamp,playSeries,stampAvailabilityInfo:stampInfo}[id]||null;
  }
};
const probe={id:'mee-009',tcgdexId:'mee-009',localId:'009',name:'Grass Energy',set:{id:'mee',name:'Mega Evolution Energy'}};
const available=syncStampAvailability(probe,false,false);
if(stamp.value!=='30° Anniversario')throw new Error('30th stamp not auto-selected value='+stamp.value+' options='+JSON.stringify(stampOptions));
if(playSeries.value!=='')throw new Error('Play series not cleared');
if(JSON.stringify(available)!==JSON.stringify(['30° Anniversario']))throw new Error('stamp availability '+JSON.stringify(available));

console.log(JSON.stringify({
  verified:results.length,
  identities:results,
  exactRangeGuard:true,
  thirtyStampAutoSelected:true,
  playSeriesCleared:true,
  priceInferenceTested:false
}));
'''
out=json.loads(subprocess.check_output(["node","-e",js],text=True))
assert out["verified"]==8
assert out["exactRangeGuard"] is True
assert out["thirtyStampAutoSelected"] is True
assert out["playSeriesCleared"] is True
assert out["priceInferenceTested"] is False
print(json.dumps({"status":"PASS","regression":out},ensure_ascii=False,indent=2))
