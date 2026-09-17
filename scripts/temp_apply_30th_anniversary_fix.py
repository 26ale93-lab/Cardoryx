#!/usr/bin/env python3
from pathlib import Path

p = Path('index.html')
s = p.read_text(encoding='utf-8')

anchor = """// V2.1.29 — startup-safe identity guard for MEE 009–016.\n// IMPORTANT: this helper intentionally does not call codedEnergyInfo() or any\n// constants declared later in the script, so it is safe even during startup.\nfunction isMee30CelebrationEnergy(card){"""
insert = """// V2.1.40 — exact foil-only identity guard for the 30th Anniversary sets.\n// TCGdex does not currently expose finish rows for these cards, while Pokémon's\n// official product documentation states that the 30th Celebration booster cards\n// are holographic. Keep this scoped to the two exact TCGdex set ids only.\nfunction is30thCelebrationSet(card){\n  if(!card)return false;\n  const setId=String(card?.set?.id||card?._cardoryxSetId||card?.setId||'').trim().toLowerCase();\n  return setId==='30th'||setId==='30th-c';\n}\n\n// V2.1.29 — startup-safe identity guard for MEE 009–016.\n// IMPORTANT: this helper intentionally does not call codedEnergyInfo() or any\n// constants declared later in the script, so it is safe even during startup.\nfunction isMee30CelebrationEnergy(card){"""
if anchor not in s:
    raise SystemExit('missing isMee30CelebrationEnergy anchor')
s = s.replace(anchor, insert, 1)

replacements = [
("""function stampEvidenceVerified(card,stamp){\n  const st=canonicalStamp(stamp);\n  if(isMee30CelebrationEnergy(card)){\n    if(st==='30° Anniversario')return true;\n    if(st==='Play! Pokémon'||st==='Pokémon Day')return false;\n  }""",
"""function stampEvidenceVerified(card,stamp){\n  const st=canonicalStamp(stamp);\n  if(is30thCelebrationSet(card)||isMee30CelebrationEnergy(card)){\n    if(st==='30° Anniversario')return true;\n    if(st==='Play! Pokémon'||st==='Pokémon Day')return false;\n  }"""),
("""function stampExistsForCard(card,stamp){\n  const st=canonicalStamp(stamp);\n  if(isMee30CelebrationEnergy(card)){\n    return st==='30° Anniversario'||st==='Altro';\n  }""",
"""function stampExistsForCard(card,stamp){\n  const st=canonicalStamp(stamp);\n  if(is30thCelebrationSet(card)||isMee30CelebrationEnergy(card)){\n    return st==='30° Anniversario'||st==='Altro';\n  }"""),
("""  if(isMee30CelebrationEnergy(card)){\n    sel.value='30° Anniversario';\n    const ps=document.getElementById(edit?'editPlaySeries':'playSeries');\n    if(ps)ps.value='';\n  }""",
"""  if(is30thCelebrationSet(card)||isMee30CelebrationEnergy(card)){\n    sel.value='30° Anniversario';\n    const ps=document.getElementById(edit?'editPlaySeries':'playSeries');\n    if(ps)ps.value='';\n  }"""),
("""function migrateFinishStamp(c){\n  if(!c)return c;\n  const old=String(c.variant||'');""",
"""function migrateFinishStamp(c){\n  if(!c)return c;\n  // The two 30th Anniversary sets are foil-only and carry the anniversary edition.\n  // Correct older Cardoryx records that were stored before this exact set rule existed.\n  if(is30thCelebrationSet(c)){\n    c.stamp='30° Anniversario';\n    c.variant='Holo';\n    return c;\n  }\n  const old=String(c.variant||'');"""),
("""  // V2.1.31 — 30th Celebration Basic Energies MEE 009–016 are foil-only.\n  // Pokémon explicitly states every 30th Celebration card is foil, including\n  // Basic Energy. Keep the exact edition guard, but expose the real finish.\n  // No database migration and no guessed Cardmarket price are performed here.\n  if(isMee30CelebrationEnergy(card) && stamp==='30° Anniversario'){\n    return new Set(['Holo','Speciale / Altro','Non so']);\n  }""",
"""  // V2.1.40 — the exact 30th / 30th-c sets are foil-only. TCGdex currently\n  // omits per-card finish rows, so the official set rule is the authoritative evidence.\n  // No Cardmarket price is inferred from this finish rule.\n  if(is30thCelebrationSet(card) && stamp==='30° Anniversario'){\n    return new Set(['Holo','Speciale / Altro','Non so']);\n  }\n  // V2.1.31 — 30th Celebration Basic Energies MEE 009–016 are foil-only.\n  // Pokémon explicitly states every 30th Celebration card is foil, including\n  // Basic Energy. Keep the exact edition guard, but expose the real finish.\n  // No guessed Cardmarket price is performed here.\n  if(isMee30CelebrationEnergy(card) && stamp==='30° Anniversario'){\n    return new Set(['Holo','Speciale / Altro','Non so']);\n  }""")
]
for old, new in replacements:
    if old not in s:
        raise SystemExit('missing production patch anchor')
    s = s.replace(old, new, 1)
p.write_text(s, encoding='utf-8')

Path('scripts/test_30th_anniversary_finish_stamp.py').write_text(r'''#!/usr/bin/env python3
from pathlib import Path
import json, re, subprocess
ROOT=Path(__file__).resolve().parents[1]
SOURCE=(ROOT/'index.html').read_text(encoding='utf-8')
def extract_fn(name):
    m=re.search(rf"\bfunction\s+{re.escape(name)}\s*\(",SOURCE)
    if not m: raise AssertionError(f"Missing production function {name}")
    brace=SOURCE.find('{',m.end()); depth=0; quote=None; esc=False
    for i in range(brace,len(SOURCE)):
        ch=SOURCE[i]
        if quote:
            if esc: esc=False
            elif ch=='\\': esc=True
            elif ch==quote: quote=None
            continue
        if ch in "'\"`": quote=ch
        elif ch=='{': depth+=1
        elif ch=='}':
            depth-=1
            if depth==0:return SOURCE[m.start():i+1]
    raise AssertionError(f"Unterminated function {name}")
names=['is30thCelebrationSet','stampEvidenceVerified','stampExistsForCard','syncStampAvailability','documentedVariantsForCard','migrateFinishStamp']
js='\n'.join(extract_fn(n) for n in names)+r'''
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
function makeSelect(){const options=['None','30° Anniversario','Altro','Play! Pokémon','Pokémon Day'].map(value=>({value,disabled:false}));const sel={options,value:'None'};Object.defineProperty(sel,'selectedOptions',{get(){return [options.find(o=>o.value===sel.value)||options[0]];}});return sel;}
const scanStamp=makeSelect(),editStamp=makeSelect(),scanPlay={value:'9'},editPlay={value:'9'},scanInfo={textContent:''},editInfo={textContent:''};
global.document={getElementById(id){return {stamp:scanStamp,editStamp,playSeries:scanPlay,editPlaySeries:editPlay,stampAvailabilityInfo:scanInfo,editStampAvailabilityInfo:editInfo}[id]||null;}};
const main={id:'30th-001',tcgdexId:'30th-001',name:'Exeggcute',localId:'001',set:{id:'30th',name:'30th Celebration'},variant:'Normal',stamp:'None'};
const classic={id:'30th-c-001',tcgdexId:'30th-c-001',name:'Classic test',localId:'001',set:{id:'30th-c',name:'30th Classic Collection'},variant:'Normal',stamp:'None'};
const control={id:'me01-001',tcgdexId:'me01-001',name:'Control',localId:'001',set:{id:'me01',name:'Mega Evolution'},variant:'Normal',stamp:'None'};
const r={};
r.identities=[is30thCelebrationSet(main),is30thCelebrationSet(classic),is30thCelebrationSet(control)];
r.stamps=[stampExistsForCard(main,'30° Anniversario'),stampExistsForCard(main,'None'),stampExistsForCard(main,'Play! Pokémon'),stampExistsForCard(classic,'30° Anniversario'),stampExistsForCard(control,'30° Anniversario')];
syncStampAvailability(main,false,false);syncStampAvailability(classic,true,false);r.auto=[scanStamp.value,scanPlay.value,editStamp.value,editPlay.value];
r.finishes=[...documentedVariantsForCard(main,'30° Anniversario')];r.classicFinishes=[...documentedVariantsForCard(classic,'30° Anniversario')];
const a=migrateFinishStamp(JSON.parse(JSON.stringify(main))),b=migrateFinishStamp(JSON.parse(JSON.stringify(classic))),c=migrateFinishStamp(JSON.parse(JSON.stringify(control)));
r.migrated=[a.variant,a.stamp,b.variant,b.stamp,c.variant,c.stamp];console.log(JSON.stringify(r));
'''
out=json.loads(subprocess.check_output(['node','-e',js],text=True))
assert out['identities']==[True,True,False],out
assert out['stamps']==[True,False,False,True,False],out
assert out['auto']==['30° Anniversario','','30° Anniversario',''],out
assert out['finishes']==['Holo','Speciale / Altro','Non so'],out
assert out['classicFinishes']==['Holo','Speciale / Altro','Non so'],out
assert out['migrated']==['Holo','30° Anniversario','Holo','30° Anniversario','Normal','None'],out
print(json.dumps({'status':'PASS','regression':out},ensure_ascii=False,indent=2))
''',encoding='utf-8')
