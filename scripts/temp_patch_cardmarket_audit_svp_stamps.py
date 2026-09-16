#!/usr/bin/env python3
from pathlib import Path

p=Path('scripts/test_card_identity_cardmarket_audit.py')
s=p.read_text(encoding='utf-8')
marker='def runtime_svp_set_logo_staff_regression():'
if marker in s:
    print('permanent SVP regression already applied')
    raise SystemExit(0)

# Add strict live pair evidence immediately after the existing exact-base gate.
old='''        live_exact_base_evidence = bool(
            live_pid and current_pid == live_pid and live_base_rows and
            live_usable_price and not live_explicit_rows
        )

        classification, priority, confidence = "SAFE", None, "HIGH"
'''
new='''        live_exact_base_evidence = bool(
            live_pid and current_pid == live_pid and live_base_rows and
            live_usable_price and not live_explicit_rows
        )

        # Cardoryx production supports an exact dynamic resolver only for the
        # verified Scarlet & Violet Promo `set-logo` taxonomy.  A plain Set
        # Stamp row must exclude `staff`; Staff must contain both tokens.  Each
        # row must carry its own matching Cardmarket product + live Price Guide.
        live_svp_set_logo_pair = False
        live_svp_stamp_products = {}
        if card_id.startswith("svp-"):
            def exact_svp_stamp_rows(require_staff):
                exact = []
                for row in live_card_detail.get("variants_detailed") or []:
                    stamp_tokens = {str(v or "").strip().lower() for v in (row.get("stamp") or [])}
                    if "set-logo" not in stamp_tokens:
                        continue
                    if ("staff" in stamp_tokens) != require_staff:
                        continue
                    languages = row.get("languages")
                    if isinstance(languages, list) and languages and "it" not in languages:
                        continue
                    row_type = str(row.get("type") or "").strip().lower()
                    row_foil = str(row.get("foil") or "").strip().lower()
                    supported_finish = (
                        (row_type in {"normal", "holo", "reverse"} and not row_foil) or
                        (row_type == "holo" and row_foil == "cosmos") or
                        (row_type == "reverse" and row_foil in {"pokeball", "masterball"})
                    )
                    if not supported_finish:
                        continue
                    row_pid = cm_id(row)
                    pricing_cm = ((row.get("pricing") or {}).get("cardmarket") or {})
                    try:
                        pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))
                    except (TypeError, ValueError):
                        pricing_pid = None
                    usable = any(
                        isinstance(pricing_cm.get(key), (int, float)) and pricing_cm.get(key) > 0
                        for key in ("trend", "avg7", "avg30", "avg", "low")
                    )
                    if row_pid and pricing_pid == row_pid and usable:
                        exact.append((row, row_pid))
                return exact

            svp_set_rows = exact_svp_stamp_rows(False)
            svp_staff_rows = exact_svp_stamp_rows(True)
            if (len(svp_set_rows) == 1 and len(svp_staff_rows) == 1 and
                    svp_set_rows[0][1] != svp_staff_rows[0][1]):
                live_svp_set_logo_pair = True
                live_svp_stamp_products = {
                    "setStamp": svp_set_rows[0][1],
                    "staff": svp_staff_rows[0][1],
                }

        classification, priority, confidence = "SAFE", None, "HIGH"
'''
if old not in s:
    raise SystemExit('live exact base anchor not found')
s=s.replace(old,new,1)

old='''        elif card_id in PROTECTED_REVERSE:
            classification, priority = "SOURCE_CONFLICT", "P0_PROTECTED"
            reason, action = "Conflitto Reverse Cardmarket noto e già protetto con identità/prodotto esatti.", "Mantenere il fail-closed esistente."
        elif live_exact_base_evidence:
'''
new='''        elif card_id in PROTECTED_REVERSE:
            classification, priority = "SOURCE_CONFLICT", "P0_PROTECTED"
            reason, action = "Conflitto Reverse Cardmarket noto e già protetto con identità/prodotto esatti.", "Mantenere il fail-closed esistente."
        elif live_svp_set_logo_pair:
            classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"
            reason = ("TCGdex live espone una coppia fisica SV Promo esatta e distinta: `set-logo` e "
                      "`set-logo + staff`, ciascuna con il proprio productId e Price Guide Cardmarket. "
                      "Il runtime Cardoryx le risolve separatamente senza fallback tra stamp.")
            action = "Mantenere il resolver SVP esatto; nessun mapping statico e nessun riuso prezzo fra Set Stamp e Staff."
        elif live_exact_base_evidence:
'''
if old not in s:
    raise SystemExit('classification anchor not found')
s=s.replace(old,new,1)

old='''            "liveExactBaseEvidence": live_exact_base_evidence,
            "liveExactBaseProductId": live_pid if live_exact_base_evidence else None,
            "liveExactBasePriceAvailable": live_usable_price,
            "liveExplicitVariantUsesSameProduct": bool(live_explicit_rows),
'''
new='''            "liveExactBaseEvidence": live_exact_base_evidence,
            "liveExactBaseProductId": live_pid if live_exact_base_evidence else None,
            "liveExactBasePriceAvailable": live_usable_price,
            "liveExplicitVariantUsesSameProduct": bool(live_explicit_rows),
            "liveExactSvpSetLogoStaffPair": live_svp_set_logo_pair,
            "liveExactSvpStampProducts": live_svp_stamp_products,
'''
if old not in s:
    raise SystemExit('case fields anchor not found')
s=s.replace(old,new,1)

# Add a permanent production-JS runtime regression before main().  It uses live
# TCGdex rows, so no price is invented or frozen in the test.
anchor='''def main():
'''
fn=r'''def runtime_svp_set_logo_staff_regression():
    """Verify exact live SVP Set Stamp/Staff product separation in production JS."""
    source = INDEX.read_text(encoding="utf-8")

    def extract_fn(name):
        marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
        if not marker:
            raise AssertionError(f"Missing production function {name}")
        brace = source.find("{", marker.start())
        depth = 0
        quote = None
        escape = False
        for i in range(brace, len(source)):
            ch = source[i]
            if quote:
                if escape:
                    escape = False
                elif ch == "\\":
                    escape = True
                elif ch == quote:
                    quote = None
                continue
            if ch in "'\"`":
                quote = ch
                continue
            if ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return source[marker.start():i + 1]
        raise AssertionError(f"Unclosed production function {name}")

    cache = Path(tempfile.gettempdir()) / "cardoryx_svp_stamp_regression_cache_v1"
    fixtures, errors = {}, {}
    for card_id in ("svp-005", "svp-006", "svp-007", "svp-045", "svp-067", "svp-101", "svp-150"):
        value, error = live_card(card_id, cache)
        if value:
            fixtures[card_id] = value
        if error:
            errors[card_id] = error
    if errors or len(fixtures) != 7:
        raise AssertionError(f"SVP live regression unavailable: {errors}")

    names = (
        "normText", "canonicalVariant", "canonicalStamp", "canonicalFinishTypeLabel",
        "canonicalFinishFoilLabel", "tcgdexVariantDetails", "stampEvidenceFromTCGdex",
        "tcgdexStampedRowFinish", "tcgdexExactSvpStampPrice",
    )
    js = "\n".join(extract_fn(name) for name in names)
    harness = r'''
const fixtures=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
function stamps(r){return (Array.isArray(r?.stamp)?r.stamp:[]).map(normText)}
const checked={};
for(const id of ['svp-005','svp-006','svp-007']){
  const c=fixtures[id], rows=tcgdexVariantDetails(c);
  const setRow=rows.find(r=>stamps(r).includes('setlogo')&&!stamps(r).includes('staff'));
  const staffRow=rows.find(r=>stamps(r).includes('setlogo')&&stamps(r).includes('staff'));
  if(!setRow||!staffRow)fail(id+' missing exact source pair');
  const setFinish=tcgdexStampedRowFinish(setRow), staffFinish=tcgdexStampedRowFinish(staffRow);
  if(!setFinish||!staffFinish)fail(id+' unsupported physical finish');
  const setPrice=tcgdexExactSvpStampPrice(c,setFinish,'Set Stamp');
  const staffPrice=tcgdexExactSvpStampPrice(c,staffFinish,'Staff');
  const setPid=Number(setRow?.thirdParty?.cardmarket||0), staffPid=Number(staffRow?.thirdParty?.cardmarket||0);
  if(!setPrice||Number(setPrice.idProduct)!==setPid)fail(id+' Set Stamp product mismatch');
  if(!staffPrice||Number(staffPrice.idProduct)!==staffPid)fail(id+' Staff product mismatch');
  if(setPid===staffPid)fail(id+' products are not distinct');
  if(!stampEvidenceFromTCGdex(c,'Set Stamp')||!stampEvidenceFromTCGdex(c,'Staff'))fail(id+' stamp evidence missing');
  const staffOnly={...c,variants_detailed:[staffRow]};
  if(stampEvidenceFromTCGdex(staffOnly,'Set Stamp'))fail(id+' Staff leaked into Set Stamp');
  checked[id]={setFinish,staffFinish,setPid,staffPid};
}
for(const id of ['svp-045','svp-067','svp-101','svp-150']){
  const c=fixtures[id];
  for(const finish of ['Normal','Holo','Reverse Holo','Cosmos Holo']){
    if(tcgdexExactSvpStampPrice(c,finish,'Set Stamp')!==null)fail(id+' unexpected Set Stamp auto-price');
    if(tcgdexExactSvpStampPrice(c,finish,'Staff')!==null)fail(id+' unexpected Staff auto-price');
  }
}
const foreign={...fixtures['svp-005'],set:{...(fixtures['svp-005'].set||{}),id:'sv01'}};
if(tcgdexExactSvpStampPrice(foreign,'Holo','Set Stamp')!==null)fail('resolver leaked outside svp');
process.stdout.write(JSON.stringify({checked,failClosed:['svp-045','svp-067','svp-101','svp-150'],setScopeRejected:true}));
'''
    result = json.loads(subprocess.check_output(
        ["node", "-e", js + "\n" + harness, json.dumps(fixtures, ensure_ascii=False)], text=True
    ))
    verified = extract_fn("verifiedStampPrice")
    if "tcgdexExactSvpStampPrice(card,variant,stamp)" not in verified:
        raise AssertionError("verifiedStampPrice does not consume exact SVP stamp evidence")
    if verified.find("verifiedExactSpecialStampPrice") > verified.find("tcgdexExactSvpStampPrice"):
        raise AssertionError("dynamic SVP resolver precedes existing exact static registry")
    return result


'''
if anchor not in s:
    raise SystemExit('main anchor not found')
s=s.replace(anchor,fn+anchor,1)

old='''    runtime_regression = runtime_cardmarket_regression()
    if args.runtime_only:
'''
new='''    runtime_regression = runtime_cardmarket_regression()
    runtime_regression["svpSetLogoStaff"] = runtime_svp_set_logo_staff_regression()
    if args.runtime_only:
'''
if old not in s:
    raise SystemExit('runtime main anchor not found')
s=s.replace(old,new,1)

p.write_text(s,encoding='utf-8')
print('patched permanent Cardmarket audit')
