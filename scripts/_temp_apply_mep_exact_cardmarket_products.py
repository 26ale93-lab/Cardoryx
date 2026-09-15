#!/usr/bin/env python3
"""Temporary surgical patcher for exact MEP 089-101 Cardmarket products.

Production contract:
- only exact, audited MEP identities with a unique Cardmarket product get a mapping;
- MEP 092, 093 and 101 remain fail-closed;
- missing Price Guide fields remain absent/undefined, never estimated;
- no retail, storage, scanner/OCR, deck or workflow-production logic is touched.
"""
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
TEST = ROOT / "scripts/test_prefixed_promo_official_fallbacks.py"
REPORT = ROOT / "artifacts/mep_exact_cardmarket_products_report.json"

PRODUCTS = {
    "MEP 089": dict(productId=903672, trend=1.36, low=1.00, avg1=2.12, avg7=1.80, avg30=2.50,
                    name="Mega Zeraora ex", slug="Mega-Zeraora-ex-MEP089"),
    "MEP 090": dict(productId=903676, trend=2.06, low=1.00, avg1=2.92, avg7=2.30, avg30=2.97,
                    name="Mega Darkrai ex", slug="Mega-Darkrai-ex-MEP090"),
    "MEP 091": dict(productId=903681, trend=1.57, low=0.99, avg1=2.02, avg7=2.12, avg30=3.19,
                    name="Mega Dragonite ex", slug="Mega-Dragonite-ex-MEP091"),
    "MEP 094": dict(productId=895609, name="Exeggutor di Alola", slug="Alolan-Exeggutor-MEP094"),
    "MEP 095": dict(productId=895610, name="Lucario", slug="Lucario-MEP095"),
    "MEP 096": dict(productId=895606, low=1.00, name="Moltres", slug="Moltres-MEP096"),
    "MEP 097": dict(productId=895607, low=1.00, name="Articuno", slug="Articuno-MEP097"),
    "MEP 098": dict(productId=895608, low=1.00, name="Zapdos", slug="Zapdos-MEP098"),
    "MEP 099": dict(productId=895611, low=5.00, name="Greninja ex", slug="Greninja-ex-MEP099"),
    "MEP 100": dict(productId=895612, low=4.80, name="Sylveon ex", slug="Sylveon-ex-MEP100"),
}

IDENTITIES = {
    "MEP 089": ("Mega Zeraora ex", "089", "Pokemon", "Holo", "Mega Forces Tin foil promo"),
    "MEP 090": ("Mega Darkrai ex", "090", "Pokemon", "Holo", "Mega Forces Tin foil promo"),
    "MEP 091": ("Mega Dragonite ex", "091", "Pokemon", "Holo", "Mega Forces Tin foil promo"),
    "MEP 094": ("Exeggutor di Alola", "094", "Pokemon", "", ""),
    "MEP 095": ("Lucario", "095", "Pokemon", "", ""),
    "MEP 096": ("Moltres", "096", "Pokemon", "", ""),
    "MEP 097": ("Articuno", "097", "Pokemon", "", ""),
    "MEP 098": ("Zapdos", "098", "Pokemon", "", ""),
    "MEP 099": ("Greninja ex", "099", "Pokemon", "", ""),
    "MEP 100": ("Sylveon ex", "100", "Pokemon", "", ""),
}

OFFICIAL = "https://www.pokemon.com/it/play-pokemon/info/entrata-in-vigore-delle-carte-promozionali-del-gcc-pokemon"
CM_BASE = "https://www.cardmarket.com/en/Pokemon/Products/Singles/MEP-Black-Star-Promos/"
PRICE_GUIDE = "https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json"
CATALOG = "https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json"
PRICE_SNAPSHOT = "2026-09-15T02:48:12+0200"
CATALOG_SNAPSHOT = "2026-09-15T12:48:15+0200"
PRICE_SHA = "5acedfc9bda0b7b59b1cab4538135941e55d3cb34381a38ec5d3b1f8841d43ca"
CATALOG_SHA = "244b5abf51d5f6b4586aee0a7acec61cd7977c64ab67314b28ed74664712bff0"


def js_num(v):
    return format(v, ".2f") if isinstance(v, float) else str(v)


def replacement_for(code):
    p = PRODUCTS[code]
    name, local_id, category, finish, note = IDENTITIES[code]
    source = f"Pokémon ufficiale · {code}" + (f"; {note}" if note else "")
    cm_fields = [f"productId:{p['productId']}"]
    for key in ("trend", "low", "avg1", "avg7", "avg30"):
        if key in p:
            cm_fields.append(f"{key}:{js_num(p[key])}")
    cm_fields.extend([
        f"source:'Cardmarket · {p['name']} {code.replace(' ', '')} · product {p['productId']}'",
        f"sourceUrl:'{CM_BASE}{p['slug']}'",
        f"priceGuideUrl:'{PRICE_GUIDE}'",
        f"verified:'{PRICE_SNAPSHOT}'",
    ])
    base = (
        f"name:'{name}',localId:'{local_id}',setId:'mep',setName:'Promozioni MEP',"
        f"category:'{category}',finish:'{finish}',source:'{source}',sourceUrl:'{OFFICIAL}',verified:'2026-09-11'"
    )
    return f"  '{code}':{{{base},cardmarket:{{{','.join(cm_fields)}}}}},"


def replace_registry_entry(src, code, replacement):
    # Entries are either one-line or, for the old MEP091, a small multiline block.
    if code == "MEP 091":
        pattern = r"^  'MEP 091':\{.*?^  \},$"
        out, n = re.subn(pattern, replacement, src, count=1, flags=re.M | re.S)
    else:
        pattern = rf"^  '{re.escape(code)}':\{{.*\}},$"
        out, n = re.subn(pattern, replacement, src, count=1, flags=re.M)
    if n != 1:
        raise SystemExit(f"expected exactly one registry entry for {code}, found {n}")
    return out


def patch_index():
    src = INDEX.read_text(encoding="utf-8")
    for code in PRODUCTS:
        src = replace_registry_entry(src, code, replacement_for(code))

    old = """  const cm=row.cardmarket?{\n    trend:row.cardmarket.trend,low:row.cardmarket.low,avg1:row.cardmarket.avg1,avg7:row.cardmarket.avg7,avg30:row.cardmarket.avg30,\n    _cardoryxSource:row.cardmarket.source,_cardoryxSourceUrl:row.cardmarket.sourceUrl,_cardoryxVerified:row.cardmarket.verified\n  }:null;"""
    new = """  const cm=row.cardmarket?{\n    idProduct:row.cardmarket.productId,\n    trend:row.cardmarket.trend,low:row.cardmarket.low,avg1:row.cardmarket.avg1,avg7:row.cardmarket.avg7,avg30:row.cardmarket.avg30,\n    _cardoryxSource:row.cardmarket.source,_cardoryxSourceUrl:row.cardmarket.sourceUrl,_cardoryxPriceGuideUrl:row.cardmarket.priceGuideUrl,_cardoryxVerified:row.cardmarket.verified\n  }:null;"""
    if old not in src:
        if new not in src:
            raise SystemExit("verifiedManualPromoFallback Cardmarket constructor marker not found")
    else:
        src = src.replace(old, new, 1)
    INDEX.write_text(src, encoding="utf-8")


def write_test():
    TEST.write_text(r'''#!/usr/bin/env python3
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
''', encoding='utf-8')


def write_report():
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "auditDate": "2026-09-15",
        "catalogSnapshot": {"createdAt": CATALOG_SNAPSHOT, "sha256": CATALOG_SHA, "url": CATALOG},
        "priceGuideSnapshot": {"createdAt": PRICE_SNAPSHOT, "sha256": PRICE_SHA, "url": PRICE_GUIDE},
        "exactProducts": {
            code: {k: v for k, v in row.items() if k not in ("slug", "name")}
            | {"name": row["name"], "sourceUrl": CM_BASE + row["slug"]}
            for code, row in PRODUCTS.items()
        },
        "ambiguousFailClosed": {
            "MEP 092": [903686, 905263],
            "MEP 093": [894884, 894885],
            "MEP 101": [895604, 895605],
        },
        "rules": [
            "No price is estimated for missing Price Guide fields.",
            "MEP 092, 093 and 101 receive no Cardmarket product or price.",
            "Only exact audited MEP identities are mapped.",
        ],
    }
    REPORT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main():
    patch_index()
    write_test()
    write_report()
    print(json.dumps({"patched": True, "exactProducts": 10, "ambiguousFailClosed": 3}))


if __name__ == "__main__":
    main()
