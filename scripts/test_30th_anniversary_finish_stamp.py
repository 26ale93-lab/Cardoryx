#!/usr/bin/env python3
from pathlib import Path
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'index.html').read_text(encoding='utf-8')


def extract_fn(name):
    marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", SOURCE)
    if not marker:
        raise AssertionError(f"Missing production function {name}")
    brace = SOURCE.find('{', marker.end())
    depth = 0
    quote = None
    esc = False
    for i in range(brace, len(SOURCE)):
        ch = SOURCE[i]
        if quote:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == quote:
                quote = None
            continue
        if ch in "'\"`":
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return SOURCE[marker.start():i + 1]
    raise AssertionError(f"Unterminated function {name}")


names = [
    'is30thCelebrationSet',
    'stampEvidenceVerified',
    'stampExistsForCard',
    'syncStampAvailability',
    'documentedVariantsForCard',
    'migrateFinishStamp',
]
js = '\n'.join(extract_fn(n) for n in names)
js += r'''
function canonicalStamp(v){return String(v||'');}
function canonicalVariant(v){return String(v||'Normal');}
function normalizedPlaySeries(){return '';}
function isMee30CelebrationEnergy(){return false;}
function cachedOfficialPlaySeries(){return [];}
function playAutoMatch(){return null;}
function stampEvidenceFromTCGdex(){return false;}
const VERIFIED_STAMP_PRICES={};
function normText(v){return String(v||'').toLowerCase().replace(/[^a-z0-9]+/g,'');}
function syncPlaySeriesVisibility(){}
function syncEditPlaySeriesVisibility(){}
function makeSelect(){
  const options=['None','30° Anniversario','Altro','Play! Pokémon','Pokémon Day'].map(value=>({value,disabled:false}));
  const sel={options,value:'None'};
  Object.defineProperty(sel,'selectedOptions',{get(){return [options.find(o=>o.value===sel.value)||options[0]];}});
  return sel;
}
const scanStamp=makeSelect(),editStamp=makeSelect();
const scanPlay={value:'9'},editPlay={value:'9'};
const scanInfo={textContent:''},editInfo={textContent:''};
global.document={getElementById(id){return {
  stamp:scanStamp,
  editStamp:editStamp,
  playSeries:scanPlay,
  editPlaySeries:editPlay,
  stampAvailabilityInfo:scanInfo,
  editStampAvailabilityInfo:editInfo
}[id]||null;}};

const main={id:'30th-001',tcgdexId:'30th-001',name:'Exeggcute',localId:'001',set:{id:'30th',name:'30th Celebration'},variant:'Normal',stamp:'None'};
const classic={id:'30th-c-001',tcgdexId:'30th-c-001',name:'Classic test',localId:'001',set:{id:'30th-c',name:'30th Classic Collection'},variant:'Normal',stamp:'None'};
const control={id:'me01-001',tcgdexId:'me01-001',name:'Control',localId:'001',set:{id:'me01',name:'Mega Evolution'},variant:'Normal',stamp:'None'};

const r={};
r.identities=[is30thCelebrationSet(main),is30thCelebrationSet(classic),is30thCelebrationSet(control)];
r.stamps=[
  stampExistsForCard(main,'30° Anniversario'),
  stampExistsForCard(main,'None'),
  stampExistsForCard(main,'Play! Pokémon'),
  stampExistsForCard(classic,'30° Anniversario'),
  stampExistsForCard(control,'30° Anniversario')
];
syncStampAvailability(main,false,false);
syncStampAvailability(classic,true,false);
r.auto=[scanStamp.value,scanPlay.value,editStamp.value,editPlay.value];
r.finishes=[...documentedVariantsForCard(main,'30° Anniversario')];
r.classicFinishes=[...documentedVariantsForCard(classic,'30° Anniversario')];
const a=migrateFinishStamp(JSON.parse(JSON.stringify(main)));
const b=migrateFinishStamp(JSON.parse(JSON.stringify(classic)));
const c=migrateFinishStamp(JSON.parse(JSON.stringify(control)));
r.migrated=[a.variant,a.stamp,b.variant,b.stamp,c.variant,c.stamp];
console.log(JSON.stringify(r));
'''

out = json.loads(subprocess.check_output(['node', '-e', js], text=True))
assert out['identities'] == [True, True, False], out
assert out['stamps'] == [True, False, False, True, False], out
assert out['auto'] == ['30° Anniversario', '', '30° Anniversario', ''], out
assert out['finishes'] == ['Holo', 'Speciale / Altro', 'Non so'], out
assert out['classicFinishes'] == ['Holo', 'Speciale / Altro', 'Non so'], out
assert out['migrated'] == ['Holo', '30° Anniversario', 'Holo', '30° Anniversario', 'Normal', 'None'], out
print(json.dumps({'status': 'PASS', 'regression': out}, ensure_ascii=False, indent=2))
