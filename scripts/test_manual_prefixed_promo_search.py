#!/usr/bin/env python3
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

    harness = r"""
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
"""
    result = subprocess.run(['node', '-e', parser + '\n' + resolver + '\n' + harness], text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.strip())

    assert 'if(num&&!total&&!requestedName&&!prefixedPromo)' in source
    assert 'queryManualCardsByPrefixedPromoCode(num)' in source
    assert 'Codice promo completo' in source
    assert 'MEP 091' in source

    req = urllib.request.Request(
        'https://api.tcgdex.net/v2/it/cards/mep-091',
        headers={'User-Agent': 'Cardoryx-regression/1.0'},
    )
    with urllib.request.urlopen(req, timeout=20) as response:
        live = json.load(response)
    assert str(live.get('id', '')).lower() == 'mep-091', live
    assert str(live.get('localId', '')).lstrip('0') == '91', live

    print(result.stdout.strip())
    print(json.dumps({
        'test': 'PASS',
        'liveId': live.get('id'),
        'liveName': live.get('name'),
        'liveLocalId': live.get('localId'),
    }))


if __name__ == '__main__':
    main()
