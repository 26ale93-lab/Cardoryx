#!/usr/bin/env python3
"""Focused regression for official MEP fallback identities and MEP091 Cardmarket price."""

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
    raise AssertionError(marker)


def main():
    source = INDEX.read_text(encoding='utf-8')
    reg_start = source.index('const VERIFIED_MANUAL_PROMO_IDENTITIES')
    reg_end = source.index('function verifiedManualPromoFallback', reg_start)
    registry = source[reg_start:reg_end]
    parser = js_declaration(source, 'function manualPrefixedPromoCodeParts')
    fallback = js_declaration(source, 'function verifiedManualPromoFallback')
    resolver = js_declaration(source, 'async function queryManualCardsByPrefixedPromoCode')

    harness = r"""
function canonicalPrintedLocalId(v){return String(v||'').toUpperCase().replace(/[^A-Z0-9]/g,'')}
function cardSetId(card){return String(card?.set?.id||'').trim().toLowerCase()}
function assert(ok,msg){if(!ok)throw new Error(msg)}
async function queryManualCardsByExactLocalId(){return []}
(async()=>{
  const expected={
    'MEP 089':'Mega Zeraora ex','MEP 090':'Mega Darkrai ex','MEP 091':'Mega Dragonite ex',
    'MEP 092':'Resort Paradiso','MEP 093':'Pikachu','MEP 094':'Exeggutor di Alola',
    'MEP 095':'Lucario','MEP 096':'Moltres','MEP 097':'Articuno','MEP 098':'Zapdos',
    'MEP 099':'Greninja ex','MEP 100':'Sylveon ex','MEP 101':'Nidorina'
  };
  for(const [code,name] of Object.entries(expected)){
    const rows=await queryManualCardsByPrefixedPromoCode(code);
    assert(rows.length===1,`${code} missing`);
    assert(rows[0].name===name,`${code} wrong name ${rows[0].name}`);
    assert(rows[0]._cardoryxVerifiedPromo===true,`${code} not verified fallback`);
  }
  const d=(await queryManualCardsByPrefixedPromoCode('MEP 091'))[0];
  assert(d.variants?.holo===true,'MEP091 Holo missing');
  assert(d.pricing?.cardmarket?.trend===2.04,'MEP091 trend mismatch');
  assert(d.pricing?.cardmarket?.low===1.33,'MEP091 low mismatch');
  assert(d.pricing?.cardmarket?.avg1===1.76,'MEP091 avg1 mismatch');
  assert(d.pricing?.cardmarket?.avg7===2.37,'MEP091 avg7 mismatch');
  assert(d.pricing?.cardmarket?.avg30===3.39,'MEP091 avg30 mismatch');
  assert(String(d.pricing?.cardmarket?._cardoryxSourceUrl||'').includes('Mega-Dragonite-ex-MEP091'),'MEP091 exact Cardmarket source missing');
  const stadium=(await queryManualCardsByPrefixedPromoCode('MEP 092'))[0];
  assert(stadium.category==='Stadio','MEP092 must be Stadio');
  assert(!stadium.pricing,'MEP092 price must not be invented');
  assert(Object.keys(stadium.variants||{}).length===0,'MEP092 finish must not be guessed');
  const unknown=await queryManualCardsByPrefixedPromoCode('MEP 102');
  assert(unknown.length===0,'unknown MEP102 must fail closed');
  assert(manualPrefixedPromoCodeParts('091')===null,'naked 091 must remain blocked');
  console.log(JSON.stringify({identities:13,MEP091Price:'PASS',unknown:'fail-closed'}));
})().catch(e=>{console.error(e);process.exit(1)});
"""

    script='\n'.join([registry, parser, fallback, resolver, harness])
    result=subprocess.run(['node','-e',script],text=True,capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.strip())

    # A future live TCGdex result must continue to beat local fallback.
    live_harness = r"""
function canonicalPrintedLocalId(v){return String(v||'').toUpperCase().replace(/[^A-Z0-9]/g,'')}
function cardSetId(card){return String(card?.set?.id||'').trim().toLowerCase()}
function assert(ok,msg){if(!ok)throw new Error(msg)}
async function queryManualCardsByExactLocalId(){return [{id:'mep-091',name:'Mega Dragonite ex',localId:'091',set:{id:'mep'},image:'https://example.invalid/live'}]}
(async()=>{
  const rows=await queryManualCardsByPrefixedPromoCode('MEP 091');
  assert(rows.length===1&&rows[0].id==='mep-091','live TCGdex must win');
  assert(!rows[0]._cardoryxVerifiedPromo,'fallback leaked over live result');
  console.log(JSON.stringify({livePriority:'PASS'}));
})().catch(e=>{console.error(e);process.exit(1)});
"""
    live_script='\n'.join([registry, parser, fallback, resolver, live_harness])
    live=subprocess.run(['node','-e',live_script],text=True,capture_output=True)
    if live.returncode:
        raise AssertionError(live.stderr.strip())

    print(result.stdout.strip())
    print(live.stdout.strip())
    print('{"test":"PASS","Cardmarket":"MEP091 exact snapshot only","image":"not guessed"}')


if __name__ == '__main__':
    main()
