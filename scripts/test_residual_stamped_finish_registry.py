#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
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

for label in ("Worlds 2025","Ace Trainer","Winner"):
    assert source.count(f'<option value="{label}">{label}</option>')==3,label

for registry in ("VERIFIED_NORMAL_FINISHES","VERIFIED_HOLO_FINISHES","VERIFIED_REVERSE_FINISHES"):
    obj=extract_object(registry)
    assert "'mep-028':" not in obj
    assert "'svp-225':" not in obj

registry=extract_object("VERIFIED_RESIDUAL_STAMP_FINISHES")
funcs="\n".join(extract_function(x) for x in (
    "normText","canonicalStamp","canonicalVariant",
    "canonicalFinishTypeLabel","canonicalFinishFoilLabel",
    "canonicalPrintedLocalId","printedLocalIdParts","exactLocalIdKey","cardSetId",
    "tcgdexVariantDetails","verifiedResidualStampFinishes","stampEvidenceFromTCGdex"
))

fixtures={
    "mep":{"id":"mep-028","tcgdexId":"mep-028","localId":"028","name":"Celebratory Fanfare","set":{"id":"mep"},
           "variants_detailed":[{"type":"holo","stamp":["ace-trainer"],"thirdParty":{"cardmarket":850977,"tcgplayer":681244}}]},
    "svp":{"id":"svp-225","tcgdexId":"svp-225","localId":"225","name":"Pikachu","set":{"id":"svp"},
           "variants_detailed":[
               {"type":"normal","stamp":["worlds-2025"],"thirdParty":{"tcgplayer":648631}},
               {"type":"reverse","foil":"league","stamp":["winner"],"thirdParty":{"tcgplayer":649940}},
           ]},
}
js=f"""
const VERIFIED_RESIDUAL_STAMP_FINISHES={registry};
{funcs}
const cards={json.dumps(fixtures,ensure_ascii=False)};
function fail(x){{throw new Error(x);}}
if(canonicalStamp('ace-trainer')!=='Ace Trainer')fail('ace canonical');
if(canonicalStamp('worlds-2025')!=='Worlds 2025')fail('worlds canonical');
if(canonicalStamp('winner')!=='Winner')fail('winner canonical');
let f=verifiedResidualStampFinishes(cards.mep,'Ace Trainer');
if(JSON.stringify(f)!==JSON.stringify(['Holo']))fail('mep finish');
if(!stampEvidenceFromTCGdex(cards.mep,'Ace Trainer'))fail('mep stamp evidence');
f=verifiedResidualStampFinishes(cards.svp,'Worlds 2025');
if(JSON.stringify(f)!==JSON.stringify(['Normal']))fail('worlds finish');
if(!stampEvidenceFromTCGdex(cards.svp,'Worlds 2025'))fail('worlds stamp evidence');
f=verifiedResidualStampFinishes(cards.svp,'Winner');
if(JSON.stringify(f)!==JSON.stringify(['Reverse Holo']))fail('winner finish');
if(!stampEvidenceFromTCGdex(cards.svp,'Winner'))fail('winner stamp evidence');
for(const [card,stamp] of [[cards.mep,'Worlds 2025'],[cards.svp,'Ace Trainer']])
  if(verifiedResidualStampFinishes(card,stamp).length)fail('wrong stamp leaked');
for(const card of [cards.mep,cards.svp]){{
  const stamp=card.id==='mep-028'?'Ace Trainer':'Worlds 2025';
  for(const wrong of [
    {{...card,id:card.id+'x',tcgdexId:card.id+'x'}},
    {{...card,set:{{id:'wrong'}}}},
    {{...card,localId:card.localId+'x'}},
    {{...card,name:card.name+' wrong'}}
  ]) if(verifiedResidualStampFinishes(wrong,stamp).length)fail('identity guard leaked '+card.id);
}}
const badMep={{...cards.mep,variants_detailed:[{{...cards.mep.variants_detailed[0],thirdParty:{{cardmarket:999999,tcgplayer:681244}}}}]}};
if(verifiedResidualStampFinishes(badMep,'Ace Trainer').length)fail('wrong Cardmarket product leaked');
const badWinner={{...cards.svp,variants_detailed:cards.svp.variants_detailed.map(x=>x.stamp?.[0]==='winner'?{{...x,foil:'cosmos'}}:x)}};
if(verifiedResidualStampFinishes(badWinner,'Winner').length)fail('wrong Winner foil leaked');
process.stdout.write(JSON.stringify({{
  exactStampedIdentities:2,
  exactStampedPrintings:3,
  mepAceTrainer:'Holo',
  svpWorlds2025:'Normal',
  svpWinner:'Reverse Holo',
  wrongIdentityRejected:true,
  wrongProductRejected:true,
  standardRegistryLeak:false
}}));
"""
print(subprocess.check_output(["node","-e",js],text=True).strip())
