#!/usr/bin/env python3
"""Focused regression for manual prefixed promo-code lookup (e.g. MEP 091)."""

import subprocess
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


def js_const_object(source, marker, next_marker):
    start = source.index(marker)
    end = source.index(next_marker, start)
    return source[start:end]


def main():
    source = INDEX.read_text(encoding='utf-8')
    registry = js_const_object(source, 'const VERIFIED_MANUAL_PROMO_IDENTITIES', 'function verifiedManualPromoFallback')
    parser = js_declaration(source, 'function manualPrefixedPromoCodeParts')
    fallback = js_declaration(source, 'function verifiedManualPromoFallback')
    resolver = js_declaration(source, 'async function queryManualCardsByPrefixedPromoCode')

    common = r"""
function canonicalPrintedLocalId(v){return String(v||'').toUpperCase().replace(/[^A-Z0-9]/g,'')}
function cardSetId(card){return String(card?.set?.id||'').trim().toLowerCase()}
function assert(ok,message){if(!ok)throw new Error(message)}
"""

    fallback_harness = r"""
async function queryManualCardsByExactLocalId(value){
  if(String(value)!=='91')throw new Error('resolver did not reduce MEP 091 to local number 91');
  return [{id:'sv05-091',name:'Other card',localId:'091',set:{id:'sv05'}}];
}
(async()=>{
  let p=manualPrefixedPromoCodeParts('MEP 091');
  assert(p&&p.prefix==='MEP'&&p.number==='91'&&p.setId==='mep','MEP 091 parser failed');
  p=manualPrefixedPromoCodeParts('svp001');
  assert(p&&p.prefix==='SVP'&&p.number==='1'&&p.setId==='svp','SVP001 parser failed');
  assert(manualPrefixedPromoCodeParts('091')===null,'naked number must stay blocked');
  assert(manualPrefixedPromoCodeParts('M 091')===null,'one-letter prefix must stay blocked');
  const rows=await queryManualCardsByPrefixedPromoCode('MEP 091');
  assert(rows.length===1,'MEP 091 fallback missing');
  assert(rows[0].id==='verified-promo-mep-091','unexpected fallback identity');
  assert(rows[0].name==='Mega Dragonite ex'&&rows[0].localId==='091','wrong verified identity');
  assert(rows[0]._cardoryxLocal===true&&rows[0]._cardoryxVerifiedPromo===true,'fallback not marked verified/local');
  assert(rows[0].variants?.holo===true,'verified Holo finish missing');
  assert(!rows[0].pricing,'fallback must not invent Cardmarket pricing');
  const unknown=await queryManualCardsByPrefixedPromoCode('MEP 092');
  assert(unknown.length===0,'unverified promo code must fail closed');
  console.log(JSON.stringify({fallback:'PASS',result:rows[0].id,price:'none'}));
})().catch(e=>{console.error(e);process.exit(1)});
"""
    script = '\n'.join([registry, parser, fallback, resolver, common, fallback_harness])
    result = subprocess.run(['node', '-e', script], text=True, capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.strip())

    live_harness = r"""
async function queryManualCardsByExactLocalId(){
  return [{id:'mep-091',tcgdexId:'mep-091',name:'Upstream Mega Dragonite ex',localId:'091',set:{id:'mep'}}];
}
(async()=>{
  const rows=await queryManualCardsByPrefixedPromoCode('MEP 091');
  assert(rows.length===1&&rows[0].id==='mep-091','live TCGdex identity must take priority over fallback');
  assert(!rows[0]._cardoryxVerifiedPromo,'fallback leaked over live identity');
  console.log(JSON.stringify({livePriority:'PASS'}));
})().catch(e=>{console.error(e);process.exit(1)});
"""
    live_script = '\n'.join([registry, parser, fallback, resolver, common, live_harness])
    live_result = subprocess.run(['node', '-e', live_script], text=True, capture_output=True)
    if live_result.returncode:
        raise AssertionError(live_result.stderr.strip())

    assert 'if(num&&!total&&!requestedName&&!prefixedPromo)' in source
    assert 'queryManualCardsByPrefixedPromoCode(num)' in source
    assert 'Codice promo completo' in source
    assert 'MEP 091' in source
    assert 'productId' not in registry and 'pricing:' not in registry

    print(result.stdout.strip())
    print(live_result.stdout.strip())
    print('{"test":"PASS","nakedNumber":"blocked","MEP091":"verified-fallback","Cardmarket":"untouched"}')


if __name__ == '__main__':
    main()
