#!/usr/bin/env python3
"""Focused offline regression for explicit special-stamp finish availability."""

import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"


def js_declaration(source, marker):
    start = source.index(marker)
    if marker.startswith("function "):
        paren = source.index("(", start)
        paren_depth = 0
        quote = None
        escape = False
        brace = None
        for pos in range(paren, len(source)):
            ch = source[pos]
            if quote:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == quote:
                    quote = None
                continue
            if ch in ("'", '"', "`"):
                quote = ch
            elif ch == "(":
                paren_depth += 1
            elif ch == ")":
                paren_depth -= 1
                if paren_depth == 0:
                    brace = source.index("{", pos)
                    break
        if brace is None:
            raise AssertionError(f"Function body not found: {marker}")
    else:
        brace = source.index("{", start)
    depth = 0
    quote = None
    escape = False
    for pos in range(brace, len(source)):
        ch = source[pos]
        if quote:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in ("'", '"', "`"):
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = pos + 1
                while end < len(source) and source[end] in " \t\r\n;":
                    end += 1
                return source[start:end]
    raise AssertionError(f"Unclosed JavaScript declaration: {marker}")


def main():
    source = INDEX.read_text(encoding="utf-8")
    ranges = [
        ("function canonicalStamp", "function stampBadgeHTML"),
        ("function stampEvidenceFromTCGdex", "function cachedOfficialPlaySeries"),
        ("function stampExistsForCard", "function syncStampAvailability"),
        ("function tcgdexVariantDetails", "function recommendedVariantFromTCGdex"),
        ("function addDetailedFinishes", "function addModernStandardStructure"),
        ("const VERIFIED_SPECIAL_STAMP_FINISHES", "// V2.1.14 — Prize Pack Series"),
        ("function documentedVariantsForCard", "function syncVariantAvailability"),
        ("function syncVariantAvailability", "// Prezzi Cardmarket verificati manualmente"),
    ]
    actual = "\n".join(source[source.index(start):source.index(end, source.index(start))]
                       for start, end in ranges)
    harness = r"""
function normText(v){return String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,'')}
function normalizedPlaySeries(v){return String(v||'')}
function canonicalVariant(v){return v==='Normale'?'Normal':String(v||'Normal')}
function canonicalFinishTypeLabel(v){return normText(v)}
function canonicalFinishFoilLabel(v){return normText(v)}
function cardSetId(card){return String(card?._cardoryxSetId||card?.set?.id||'').trim().toLowerCase()}
function exactLocalIdKey(v){return String(v||'').replace(/^0+/,'')||'0'}
function isMee30CelebrationEnergy(){return false}
function isMeePrizePackEnergy(){return false}
function stampEvidenceVerified(){return false}
function isModernParallelEra(){return false}
function addModernStandardStructure(){return false}
function addCoarseStandardFinishes(){return false}
function addMarketplaceStandardFinishes(){return false}
function rarityForcesStandardHolo(){return false}
function verifiedNormalFinish(){return false}
function verifiedReverseFinish(){return false}
function verifiedVariantPrice(){return null}
function verifiedStampPrice(){return null}
function verifiedPlaySeriesPrice(){return null}
function prizePackFinishPlan(){return {finishes:[],authoritative:false}}
function assert(ok,message){if(!ok)throw new Error(message)}
function finishes(card,stamp,series=''){return [...documentedVariantsForCard(card,stamp,series)].sort()}
function exactOnly(actual,expected,label){
  const physical=actual.filter(x=>!['Speciale / Altro','Non so'].includes(x)).sort();
  assert(JSON.stringify(physical)===JSON.stringify([...expected].sort()),label+': '+JSON.stringify(physical));
}

const pikachu={
  id:'sv05-051',tcgdexId:'sv05-051',name:'Pikachu',localId:'051',set:{id:'sv05',name:'Temporal Forces'},
  variants_detailed:[
    {type:'normal'},
    {type:'reverse'},
    {type:'holo',foil:'cosmos'},
    {type:'holo',stamp:['pokemon-day'],thirdParty:{cardmarket:870424}}
  ]
};
assert(stampExistsForCard(pikachu,'Pokémon Day'),'Pokémon Day stamp was not recognized');
exactOnly(finishes(pikachu,'Pokémon Day'),['Holo'],'Pikachu Pokémon Day');
assert(!finishes(pikachu,'Pokémon Day').includes('Normal'),'Base Normal leaked into Pokémon Day');
assert(!finishes(pikachu,'Pokémon Day').includes('Reverse Holo'),'Base Reverse leaked into Pokémon Day');
assert(!finishes(pikachu,'Pokémon Day').includes('Cosmos Holo'),'Base Cosmos leaked into Pokémon Day');
exactOnly(finishes({...pikachu,id:'sv05-052',tcgdexId:'sv05-052',variants_detailed:pikachu.variants_detailed.slice(0,3)},'Pokémon Day'),[],'Wrong identity');
exactOnly(finishes({...pikachu,set:{id:'sv04'}},'Pokémon Day'),[],'Wrong set');
exactOnly(finishes({...pikachu,localId:'052'},'Pokémon Day'),[],'Wrong local id');
exactOnly(finishes({...pikachu,name:'Raichu'},'Pokémon Day'),[],'Wrong name');
exactOnly(finishes(pikachu,'GameStop'),[],'Wrong stamp');

for(const [label,stamp,row,expected] of [
  ['Pokémon Center','Pokémon Center',{type:'normal',stamp:['pokemon-center']},'Normal'],
  ['Staff','Staff',{type:'holo',stamp:['national-championships','staff']},'Holo'],
  ['Pre-release','Pre-release',{type:'normal',stamp:['pre-release']},'Normal'],
  ['GameStop','GameStop',{type:'normal',stamp:['gamestop']},'Normal']
]){
  exactOnly(finishes({id:'probe',variants_detailed:[row]},stamp),[],label+' remains audit-only');
}
exactOnly(finishes({id:'play-probe',variants_detailed:[{type:'holo',stamp:['player-rewards-program']}]},'Play! Pokémon'),['Holo'],'Play path');
exactOnly(finishes({id:'de-only',variants_detailed:[{type:'normal'},{type:'normal',stamp:['pokemon-day'],languages:['de']}]},'Pokémon Day'),[],'Language guard');

function makeSelect(values,selected){
  const options=values.map(value=>({value,disabled:false,setAttribute(){}}));
  return {options,value:selected,get selectedOptions(){return options.filter(o=>o.value===this.value)}};
}
const ui={
  stamp:makeSelect(['None','Pokémon Day'],'Pokémon Day'),
  playSeries:makeSelect([''],''),
  variant:makeSelect(['Normal','Holo','Reverse Holo','Cosmos Holo','Poké Ball Reverse Holo','Master Ball Reverse Holo','Speciale / Altro','Non so'],'Non so'),
  editStamp:makeSelect(['None','Pokémon Day'],'Pokémon Day'),
  editPlaySeries:makeSelect([''],''),
  editVariant:makeSelect(['Normal','Holo','Reverse Holo','Cosmos Holo','Speciale / Altro','Non so'],'Non so')
};
globalThis.document={getElementById:id=>ui[id]||null};
syncVariantAvailability(pikachu,false);
assert(ui.variant.options.find(o=>o.value==='Holo').disabled===false,'Holo remains disabled');
assert(ui.variant.options.find(o=>o.value==='Normal').disabled===true,'Normal unexpectedly enabled');
syncVariantAvailability(pikachu,true);
assert(ui.editVariant.options.find(o=>o.value==='Holo').disabled===false,'Edit path keeps Holo disabled');

console.log(JSON.stringify({
  pikachuPokemonDay:'Holo',
  blocked:['Normal','Reverse Holo','Cosmos Holo','Poké Ball Reverse Holo','Master Ball Reverse Holo'],
  relatedExplicitRows:'audit-only; no generalized fix',
  playPrizePack:'unchanged-pass',
  scannerConfirmation:'Holo enabled',
  edit:'Holo enabled'
}));
"""
    result = subprocess.run(["node", "-e", actual + "\n" + harness], text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.strip())
    print(result.stdout.strip())
    print(json.dumps({"index": str(INDEX), "test": "PASS"}))


if __name__ == "__main__":
    main()
