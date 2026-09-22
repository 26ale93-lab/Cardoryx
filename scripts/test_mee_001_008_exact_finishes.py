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
        if c in ("'", '"'):
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
 "normText","canonicalStamp","normalizedPlaySeries","canonicalVariant",
 "canonicalFinishTypeLabel","canonicalFinishFoilLabel","canonicalFinishSubtypeLabel",
 "isPeelableDittoVariantRow","cardSetId","cardRegulationMark","isModernParallelEra",
 "rarityForcesStandardHolo","tcgdexVariantDetails","addDetailedFinishes",
 "addModernStandardStructure","addCoarseStandardFinishes","addMarketplaceStandardFinishes",
 "is30thCelebrationSet","isMee30CelebrationEnergy","isMeePrizePackEnergy",
 "documentedVariantsForCard"
]
js="\n".join(extract_fn(n) for n in names)
js+=r'''
function exactLocalIdKey(v){return String(v||'').replace(/^0+/,'')||'0';}
function verifiedSpecialStampFinishes(){return []}
function verifiedMcdonaldsStampFinishes(){return []}
function verifiedMcdonalds2021AnniversaryFinishes(){return []}
function verifiedSwshp25thStandardFinishes(){return []}
function verifiedSwshpSetLogoFinishes(){return []}
function verifiedMepStampFinishes(){return []}
function verifiedResidualStampFinishes(){return []}
function verifiedNormalFinish(){return false}
function verifiedHoloFinish(){return false}
function verifiedReverseFinish(){return false}
function verifiedVariantPrice(){return null}
function verifiedStampPrice(){return null}
function verifiedPlaySeriesPrice(){return null}
function prizePackFinishPlan(){return {authoritative:false,finishes:[]}}
function verifiedPlaySeriesFinishes(){return []}

function card(n){
  const id='mee-'+String(n).padStart(3,'0');
  return {
    id,tcgdexId:id,localId:String(n).padStart(3,'0'),
    name:'Energy',rarity:'Common',category:'Energy',set:{id:'mee',name:'Mega Evolution Energy'},
    variants_detailed:[
      {type:'normal',thirdParty:{cardmarket:851007+n,tcgplayer:656262+n}},
      {type:'reverse',thirdParty:{cardmarket:851007+n,tcgplayer:656262+n}}
    ]
  };
}
const rows=[];
for(let n=1;n<=8;n++){
  const c=card(n);
  const standard=[...documentedVariantsForCard(c,'None','')];
  const play=[...documentedVariantsForCard(c,'Play! Pokémon','8')];
  if(!standard.includes('Normal')||!standard.includes('Reverse Holo'))throw new Error('standard '+c.id+' '+standard);
  if(standard.includes('Holo')||standard.includes('Cosmos Holo'))throw new Error('standard leaked '+c.id+' '+standard);
  if(!play.includes('Normal')||!play.includes('Cosmos Holo'))throw new Error('play '+c.id+' '+play);
  rows.push({id:c.id,standard,play});
}
const nine={id:'mee-009',tcgdexId:'mee-009',localId:'009',name:'Energy',set:{id:'mee',name:'Mega Evolution Energy'}};
const nine30=[...documentedVariantsForCard(nine,'30° Anniversario','')];
if(JSON.stringify(nine30)!==JSON.stringify(['Holo','Speciale / Altro','Non so']))throw new Error('MEE009 path '+nine30);
const nineNone=[...documentedVariantsForCard(nine,'None','')];
if(nineNone.includes('Reverse Holo'))throw new Error('MEE009 inherited reverse');
console.log(JSON.stringify({standardRowsVerified:8,mee001to008:rows,mee009ThirtyPathPreserved:true,mee009NoReverseInheritance:true}));
'''
out=json.loads(subprocess.check_output(["node","-e",js],text=True))
assert out["standardRowsVerified"]==8
assert out["mee009ThirtyPathPreserved"] is True
assert out["mee009NoReverseInheritance"] is True
assert "return new Set(['Normal','Speciale / Altro','Non so']);" not in extract_fn("documentedVariantsForCard")
print(json.dumps({"status":"PASS","regression":out},ensure_ascii=False,indent=2))
