#!/usr/bin/env python3
import subprocess
from pathlib import Path

INDEX=Path(__file__).resolve().parents[1]/"index.html"
source=INDEX.read_text(encoding="utf-8")

def section(start,end):
    a=source.find(start)
    b=source.find(end,a+len(start))
    assert a>=0 and b>a, (start,end)
    return source[a:b]

canonical_variant=section("function canonicalVariant(","function canonicalFinishTypeLabel(")
canonical_stamp=section("function canonicalStamp(","function stampBadgeHTML(")
alloc=section("const CARDORYX_ALLOCATION_STATUSES=","function allocationInputsHtml(")
catalog=section("function syncCatalogAllocationFilterOptions(","function renderCatalog(")
status_model=section("const CARDORYX_PRIMARY_STATUSES=","// Storage V1")

catalog_html=source.split('<section id="catalogView"',1)[1].split('<section id="statsView"',1)[0]
for item in [
    'id="stampFilter"',
    'value="Poké Ball Reverse Holo"',
    'value="Master Ball Reverse Holo"',
    'value="Ditto Peelable"',
    'Tutti gli stamp / edizioni',
]:
    assert item in catalog_html, item
assert '<option>Pokémon Day Stamp</option>' not in catalog_html
assert '<option>Play! Pokémon Stamp</option>' not in catalog_html


scanner_html=source.split('<div class="label">Stato</div><select id="status"',1)[1].split('</select>',1)[0]
quick_status_html=source.split('<select id="quickStatus">',1)[1].split('</select>',1)[0]
edit_status_html=source.split('<select id="editStatus">',1)[1].split('</select>',1)[0]
for block in [scanner_html,quick_status_html,edit_status_html]:
    assert 'Disponibile' in block
    assert 'Protetta' in block
    assert 'Vendita' in block
    assert 'Mazzo 1' not in block
    assert 'Mazzo 2' not in block
assert "const CARDORYX_ALLOCATION_STATUSES=[...CARDORYX_PRIMARY_STATUSES];" in source
assert "p.status=canonicalPrimaryStatus(p.status);" in source

js=f"""
const assert=require('assert');
let decks=[];
function esc(v){{return String(v??'')}}
const fakeSelect={{value:'',innerHTML:''}};
function ui(id){{return id==='status'?fakeStatus:id==='editStatus'?fakeEditStatus:null}}
const fakeStatus={{value:'Disponibile'}};
const fakeEditStatus={{
  value:'',innerHTML:'',children:[],
  appendChild(el){{this.children.push(el);this.value=el.value}}
}};
const document={{
  createElement(){{return {{value:'',textContent:'',disabled:false}}}},
  getElementById(id){{return id==='statusFilter'?fakeSelect:ui(id)}}
}};

function deckTypeLabel(d){{return d?.type==='sale'?'Vendita':'Gioco'}}
function deckRecordKey(c){{return [c.id||'',c.variant||'Normale',c.status||'Disponibile',c.condition||'NM'].join('|||')}}
function normText(v){{return String(v||'').normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim()}}
{canonical_variant}
{canonical_stamp}
{status_model}
{alloc}
{catalog}

assert.strictEqual(canonicalVariant('Normale'),'Normal');
assert.strictEqual(canonicalVariant('Normal'),'Normal');
assert.strictEqual(canonicalVariant('Poké Ball Reverse Holo'),'Poké Ball Reverse Holo');
assert.strictEqual(canonicalVariant('Master Ball Reverse Holo'),'Master Ball Reverse Holo');
assert.strictEqual(canonicalVariant('Ditto rimovibile'),'Ditto Peelable');
assert.strictEqual(canonicalStamp('Pokémon Day'),'Pokémon Day');
assert.strictEqual(canonicalStamp('Worlds 2024'),'Worlds 2024');

assert.deepStrictEqual(CARDORYX_PRIMARY_STATUSES,['Disponibile','Protetta','Vendita']);
fakeStatus.value='Mazzo 1';
assert.strictEqual(selectedStatus(),'Disponibile');
fakeStatus.value='Protetta';
assert.strictEqual(selectedStatus(),'Protetta');
syncEditStatusOptions('Mazzo 2');
assert.strictEqual(fakeEditStatus.value,'Mazzo 2');
assert.strictEqual(fakeEditStatus.children.length,1);
assert.strictEqual(fakeEditStatus.children[0].disabled,true);
assert.strictEqual(fakeEditStatus.children[0].textContent,'Mazzo 2 (legacy)');
syncEditStatusOptions('Vendita');
assert.strictEqual(fakeEditStatus.value,'Vendita');

const available={{id:'c1',variant:'Normal',status:'Disponibile',condition:'NM',qty:3}};
const full={{id:'c2',variant:'Poké Ball Reverse Holo',status:'Disponibile',condition:'NM',qty:2}};
const protectedCard={{id:'c3',variant:'Master Ball Reverse Holo',status:'Protetta',condition:'NM',qty:1}};
const saleCard={{id:'c4',variant:'Ditto Peelable',status:'Vendita',condition:'EX',qty:1}};
const legacy={{id:'c5',variant:'Normal',status:'Mazzo 1',condition:'NM',qty:1}};
decks=[
  {{id:'deckA',name:'Erba',type:'game',entries:[
    {{cardKey:deckRecordKey(available),qty:2}},
    {{cardKey:deckRecordKey(full),qty:2}}
  ]}}
];
const gAvailable={{records:[available]}};
const gFull={{records:[full]}};
const gProtected={{records:[protectedCard]}};
const gSale={{records:[saleCard]}};
const gLegacy={{records:[legacy]}};

assert.strictEqual(catalogAllocationMatches(gAvailable,'available'),true);
assert.strictEqual(catalogAllocationMatches(gAvailable,'deck:any'),true);
assert.strictEqual(catalogAllocationMatches(gAvailable,'deck:deckA'),true);
assert.strictEqual(catalogAllocationMatches(gFull,'available'),false);
assert.strictEqual(catalogAllocationMatches(gFull,'deck:any'),true);
assert.strictEqual(catalogAllocationMatches(gProtected,'protected'),true);
assert.strictEqual(catalogAllocationMatches(gSale,'sale'),true);
assert.strictEqual(catalogAllocationMatches(gLegacy,'deck:any'),true);
assert.strictEqual(catalogAllocationMatches(gLegacy,'available'),false);

assert.strictEqual(gAvailable.records.some(r=>canonicalVariant(r.variant||'Normal')===canonicalVariant('Normale')),true);
assert.strictEqual(gFull.records.some(r=>canonicalVariant(r.variant||'Normal')===canonicalVariant('Poké Ball Reverse Holo')),true);
assert.strictEqual(gProtected.records.some(r=>canonicalVariant(r.variant||'Normal')===canonicalVariant('Master Ball Reverse Holo')),true);
assert.strictEqual(gSale.records.some(r=>canonicalVariant(r.variant||'Normal')===canonicalVariant('Ditto Peelable')),true);

syncCatalogAllocationFilterOptions();
assert(fakeSelect.innerHTML.includes('Tutte le allocazioni'));
assert(fakeSelect.innerHTML.includes('In un mazzo'));
assert(fakeSelect.innerHTML.includes('deck:deckA'));
assert(fakeSelect.innerHTML.includes('Gioco · Erba'));

console.log(JSON.stringify({{
  normalCanonical:true,
  ballFinishes:true,
  stampSeparated:true,
  partialDeckAvailable:true,
  fullDeckUnavailable:true,
  dynamicDeckFilter:true,
  legacyDeckCompatible:true,
  scannerUsesCurrentStatuses:true,
  legacyQuickStatusFallsBackSafely:true
}}));
"""
out=subprocess.check_output(["node"],input=js,text=True)
print(out.strip())
