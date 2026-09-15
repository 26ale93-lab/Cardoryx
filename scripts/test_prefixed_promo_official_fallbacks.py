#!/usr/bin/env python3
"""Focused regression for official MEP fallbacks and exact Cardmarket products."""

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
  const exactProducts={
    'MEP 089':903672,'MEP 090':903676,'MEP 091':903681,'MEP 094':895609,'MEP 095':895610,
    'MEP 096':895606,'MEP 097':895607,'MEP 098':895608,'MEP 099':895611,'MEP 100':895612
  };
  for(const [code,name] of Object.entries(expected)){
    const rows=await queryManualCardsByPrefixedPromoCode(code);
    assert(rows.length===1,`${code} missing`);
    assert(rows[0].name===name,`${code} wrong name ${rows[0].name}`);
    assert(rows[0]._cardoryxVerifiedPromo===true,`${code} not verified fallback`);
    const cm=rows[0].pricing?.cardmarket;
    if(exactProducts[code]){
      assert(cm?.idProduct===exactProducts[code],`${code} wrong product ${cm?.idProduct}`);
      assert(String(cm?._cardoryxVerified||'').startsWith('2026-09-15'),`${code} wrong snapshot`);
    }else{
      assert(!cm,`${code} ambiguous product must remain fail-closed`);
    }
  }

  const p89=(await queryManualCardsByPrefixedPromoCode('MEP 089'))[0].pricing.cardmarket;
  assert(p89.trend===1.36&&p89.low===1.00&&p89.avg1===2.12&&p89.avg7===1.80&&p89.avg30===2.50,'MEP089 guide mismatch');
  const p90=(await queryManualCardsByPrefixedPromoCode('MEP 090'))[0].pricing.cardmarket;
  assert(p90.trend===2.06&&p90.low===1.00&&p90.avg1===2.92&&p90.avg7===2.30&&p90.avg30===2.97,'MEP090 guide mismatch');
  const p91=(await queryManualCardsByPrefixedPromoCode('MEP 091'))[0].pricing.cardmarket;
  assert(p91.trend===1.57&&p91.low===0.99&&p91.avg1===2.02&&p91.avg7===2.12&&p91.avg30===3.19,'MEP091 guide mismatch');

  for(const code of ['MEP 094','MEP 095']){
    const cm=(await queryManualCardsByPrefixedPromoCode(code))[0].pricing.cardmarket;
    assert(cm.idProduct===exactProducts[code],'exact product missing');
    assert(cm.trend===undefined&&cm.low===undefined&&cm.avg1===undefined&&cm.avg7===undefined&&cm.avg30===undefined,`${code} missing guide fields must not be invented`);
  }
  for(const [code,low] of Object.entries({'MEP 096':1.00,'MEP 097':1.00,'MEP 098':1.00,'MEP 099':5.00,'MEP 100':4.80})){
    const cm=(await queryManualCardsByPrefixedPromoCode(code))[0].pricing.cardmarket;
    assert(cm.low===low,`${code} low mismatch`);
    assert(cm.trend===undefined&&cm.avg1===undefined&&cm.avg7===undefined&&cm.avg30===undefined,`${code} non-low fields must remain unavailable`);
  }

  const d=(await queryManualCardsByPrefixedPromoCode('MEP 091'))[0];
  assert(d.variants?.holo===true,'MEP091 Holo missing');
  const stadium=(await queryManualCardsByPrefixedPromoCode('MEP 092'))[0];
  assert(stadium.category==='Stadio','MEP092 must be Stadio');
  assert(!stadium.pricing,'MEP092 price must remain unavailable');
  assert(Object.keys(stadium.variants||{}).length===0,'MEP092 finish must not be guessed');
  for(const code of ['MEP 093','MEP 101']){
    const x=(await queryManualCardsByPrefixedPromoCode(code))[0];
    assert(!x.pricing,`${code} ambiguous product must remain unavailable`);
  }
  const unknown=await queryManualCardsByPrefixedPromoCode('MEP 102');
  assert(unknown.length===0,'unknown MEP102 must fail closed');
  assert(manualPrefixedPromoCodeParts('091')===null,'naked 091 must remain blocked');
  console.log(JSON.stringify({identities:13,exactProducts:10,ambiguousFailClosed:3,priceSnapshot:'2026-09-15'}));
})().catch(e=>{console.error(e);process.exit(1)});
"""

    script='\n'.join([registry, parser, fallback, resolver, harness])
    result=subprocess.run(['node','-e',script],text=True,capture_output=True)
    if result.returncode:
        raise AssertionError(result.stderr.strip())

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
    print('{"test":"PASS","exactProducts":10,"ambiguous":"MEP092,MEP093,MEP101 fail-closed"}')


if __name__ == '__main__':
    main()
