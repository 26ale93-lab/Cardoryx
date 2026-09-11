#!/usr/bin/env python3
from pathlib import Path

index = Path('index.html')
source = index.read_text(encoding='utf-8')

if 'function manualPrefixedPromoCodeParts' in source:
    raise SystemExit('manualPrefixedPromoCodeParts already present')

# 1) UI help: explicitly advertise prefixed promo codes without a set total.
old_help = '<div class="small">Cerca con <b>Numero + Totale set</b>, con <b>Numero + Nome esatto</b>, oppure esplora il catalogo inserendo soltanto il <b>Nome carta</b>.</div>'
new_help = '<div class="small">Cerca con <b>Numero + Totale set</b>, con <b>Numero + Nome esatto</b>, con un <b>codice promo completo</b> (es. MEP 091), oppure esplora il catalogo inserendo soltanto il <b>Nome carta</b>.</div>'
if old_help not in source:
    raise SystemExit('manual search help marker missing')
source = source.replace(old_help, new_help, 1)
source = source.replace('placeholder="146, TG01, SVP001"', 'placeholder="146, TG01, MEP 091, SVP001"', 1)

# 2) Exact prefixed-code parser and resolver. A prefixed code is accepted only
# when its alphabetic prefix resolves to the same TCGdex set id / card id.
marker = 'async function queryManualCardsByExactLocalId(value,allowedIds=null){'
if marker not in source:
    raise SystemExit('queryManualCardsByExactLocalId marker missing')
helper = r'''function manualPrefixedPromoCodeParts(value=''){
  const raw=canonicalPrintedLocalId(value);
  const match=raw.match(/^([A-Z]{2,5})0*(\d{1,3})$/);
  if(!match)return null;
  const prefix=match[1].toUpperCase();
  const number=String(Number(match[2]));
  if(!number || number==='0')return null;
  return {prefix,number,display:`${prefix} ${number.padStart(3,'0')}`,setId:prefix.toLowerCase()};
}

async function queryManualCardsByPrefixedPromoCode(value){
  const code=manualPrefixedPromoCodeParts(value);
  if(!code)return [];
  const cards=await queryManualCardsByExactLocalId(code.number);
  return (cards||[]).filter(card=>{
    const setId=cardSetId(card);
    const id=String(card?.id||card?.tcgdexId||'').trim().toLowerCase();
    return setId===code.setId || id.startsWith(`${code.setId}-`);
  });
}

'''
source = source.replace(marker, helper + marker, 1)

# 3) Preserve the fail-closed rule for naked numbers, but allow a full
# prefixed promo code to take the exact-code route without requiring total/name.
old_preamble = """  const num=canonicalPrintedLocalId(numberInput.value||'');\n  const total=String(setTotalInput.value||'').replace(/\\D/g,'');\n  const requestedName=String(nameInput.value||'').trim();\n"""
new_preamble = old_preamble + "  const prefixedPromo=manualPrefixedPromoCodeParts(num);\n"
if old_preamble not in source:
    raise SystemExit('manual search preamble marker missing')
source = source.replace(old_preamble, new_preamble, 1)

old_block = """  if(num&&!total&&!requestedName){\n    searchMsg.textContent='Il solo numero è troppo ambiguo. Aggiungi Nome carta oppure Totale set.';\n    return;\n  }\n"""
new_block = """  if(num&&!total&&!requestedName&&!prefixedPromo){\n    searchMsg.textContent='Il solo numero è troppo ambiguo. Aggiungi Nome carta, Totale set oppure usa un codice promo completo (es. MEP 091).';\n    return;\n  }\n"""
if old_block not in source:
    raise SystemExit('naked number fail-closed block missing')
source = source.replace(old_block, new_block, 1)

route_marker = """  try{\n    if(requestedName&&!num&&!total){\n"""
route = r'''  try{
    if(prefixedPromo&&!total&&!requestedName){
      searchMsg.textContent=`Verifico codice promo ${prefixedPromo.display}…`;
      const cards=await queryManualCardsByPrefixedPromoCode(num);
      if(!cards.length){
        searchMsg.textContent=`Nessuna carta trovata per il codice ${prefixedPromo.display}. Controlla prefisso e numero.`;
        return;
      }
      if(cards.length===1){
        const card=cards[0];
        searchMsg.textContent=`✓ ${card.name} · ${prefixedPromo.display}`;
        await chooseCard(card);
        return;
      }
      startManualCandidatePagination(
        cards,
        'Codice promo completo',
        `${cards.length} identità condividono il codice ${prefixedPromo.display}. Scegli manualmente.`
      );
      return;
    }

    if(requestedName&&!num&&!total){
'''
if route_marker not in source:
    raise SystemExit('manual search route marker missing')
source = source.replace(route_marker, route, 1)

index.write_text(source, encoding='utf-8')

# 4) Focused regression test. Keep this as the permanent test for future edits.
test = Path('scripts/test_manual_prefixed_promo_search.py')
test.write_text(r'''#!/usr/bin/env python3
"""Focused regression for manual prefixed promo-code lookup (e.g. MEP 091)."""

import json
import subprocess
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'index.html'


def js_declaration(source, marker):
    start = source.index(marker)
    paren = source.index('(', start)
    paren_depth = 0
    quote = None
    escape = False
    brace = None
    for pos in range(paren, len(source)):
        ch = source[pos]
        if quote:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in ("'", '"', '`'):
            quote = ch
        elif ch == '(':
            paren_depth += 1
        elif ch == ')':
            paren_depth -= 1
            if paren_depth == 0:
                brace = source.index('{', pos)
                break
    if brace is None:
        raise AssertionError(f'Function body not found: {marker}')
    depth = 0
    quote = None
    escape = False
    for pos in range(brace, len(source)):
        ch = source[pos]
        if quote:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == quote:
                quote = None
            continue
        if ch in ("'", '"', '`'):
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return source[start:pos + 1]
    raise AssertionError(f'Unclosed JavaScript declaration: {marker}')


def main():
    source = INDEX.read_text(encoding='utf-8')
    parser = js_declaration(source, 'function manualPrefixedPromoCodeParts')
    resolver = js_declaration(source, 'async function queryManualCardsByPrefixedPromoCode')

    harness = r'''
function canonicalPrintedLocalId(v){return String(v||'').toUpperCase().replace(/[^A-Z0-9]/g,'')}
function cardSetId(card){return String(card?.set?.id||'').trim().toLowerCase()}
async function queryManualCardsByExactLocalId(value){
  if(String(value)!=='91')throw new Error('resolver did not reduce MEP 091 to local number 91');
  return [
    {id:'sv05-091',name:'Other card',localId:'091',set:{id:'sv05'}},
    {id:'mep-091',name:'Mega Dragonite ex',localId:'091',set:{id:'mep'}}
  ];
}
function assert(ok,message){if(!ok)throw new Error(message)}
(async()=>{
  let p=manualPrefixedPromoCodeParts('MEP 091');
  assert(p&&p.prefix==='MEP'&&p.number==='91'&&p.setId==='mep','MEP 091 parser failed');
  p=manualPrefixedPromoCodeParts('svp001');
  assert(p&&p.prefix==='SVP'&&p.number==='1'&&p.setId==='svp','SVP001 parser failed');
  assert(manualPrefixedPromoCodeParts('091')===null,'naked number must stay blocked');
  assert(manualPrefixedPromoCodeParts('M 091')===null,'one-letter prefix must stay blocked');
  const rows=await queryManualCardsByPrefixedPromoCode('MEP 091');
  assert(rows.length===1&&rows[0].id==='mep-091','prefixed resolver did not isolate MEP set');
  console.log(JSON.stringify({parser:'PASS',resolver:'PASS',result:rows[0].id}));
})().catch(e=>{console.error(e);process.exit(1)});
'''
    result = subprocess.run(['node', '-e', parser + '\n' + resolver + '\n' + harness], text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.strip())

    # Structural guards for the UI route: naked numbers remain fail-closed and
    # prefixed codes have their own exact lookup path.
    assert 'if(num&&!total&&!requestedName&&!prefixedPromo)' in source
    assert 'queryManualCardsByPrefixedPromoCode(num)' in source
    assert 'Codice promo completo' in source
    assert 'MEP 091' in source

    # Live upstream check for the concrete regression case. If TCGdex stops
    # publishing this exact identity, fail closed rather than pretending support.
    req = urllib.request.Request('https://api.tcgdex.net/v2/it/cards/mep-091', headers={'User-Agent':'Cardoryx-regression/1.0'})
    with urllib.request.urlopen(req, timeout=20) as response:
        live = json.load(response)
    assert str(live.get('id','')).lower() == 'mep-091', live
    assert str(live.get('localId','')).lstrip('0') == '91', live

    print(result.stdout.strip())
    print(json.dumps({'test':'PASS','liveId':live.get('id'),'liveName':live.get('name'),'liveLocalId':live.get('localId')}))


if __name__ == '__main__':
    main()
''', encoding='utf-8')

print('Patch prepared')
