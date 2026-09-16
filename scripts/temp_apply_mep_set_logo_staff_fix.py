#!/usr/bin/env python3
from pathlib import Path

root=Path(__file__).resolve().parents[1]
index=root/'index.html'
audit=root/'scripts'/'test_card_identity_cardmarket_audit.py'

s=index.read_text(encoding='utf-8')
old="""// Exact live Cardmarket resolver for the verified Scarlet & Violet Promo
// set-logo taxonomy.  Scope is deliberately limited to `svp`: no other set,
// no Worlds/region stamp, no base-card fallback and no cross-stamp price reuse.
function tcgdexExactSvpStampPrice(card,variant,stamp){
  const setId=normText(card?.set?.id||card?._cardoryxSetId||card?.setId||'');
  if(setId!=='svp')return null;
"""
new="""// Exact live Cardmarket resolver for the verified SVP and MEP set-logo
// taxonomy. Scope is deliberately limited to these two promo sets: no other
// set, no Worlds/region stamp, no base-card fallback and no cross-stamp price reuse.
function tcgdexExactSvpStampPrice(card,variant,stamp){
  const setId=normText(card?.set?.id||card?._cardoryxSetId||card?.setId||'');
  if(setId!=='svp'&&setId!=='mep')return null;
"""
if old not in s:
    raise SystemExit('index resolver scope anchor not found')
s=s.replace(old,new,1)
index.write_text(s,encoding='utf-8')

s=audit.read_text(encoding='utf-8')
old="""    # Exact SV Promo set-logo/staff evidence requires live rows even when the
    # identity belongs to the historical sample and is not a shared product.
    # Scope this extra fetch strictly to SVP identities that actually expose
    # the verified `set-logo` taxonomy in the snapshot.
    svp_set_logo_ids = {
        card[\"id\"] for card in cards
        if card[\"id\"].startswith(\"svp-\") and any(
            \"set-logo\" in {str(v or \"\").strip().lower() for v in (row.get(\"stamp\") or [])}
            for row in (card.get(\"variants_detailed\") or [])
        )
    }
    live_targets = ((multi_ids - historical_ids) | shared_identity_ids | svp_set_logo_ids |
"""
new="""    # Exact set-logo/staff evidence requires live rows even when the identity
    # belongs to the historical sample and is not a shared product. Scope this
    # extra fetch strictly to the two promo sets whose taxonomy is verified.
    verified_set_logo_ids = {
        card[\"id\"] for card in cards
        if card[\"id\"].startswith((\"svp-\", \"mep-\")) and any(
            \"set-logo\" in {str(v or \"\").strip().lower() for v in (row.get(\"stamp\") or [])}
            for row in (card.get(\"variants_detailed\") or [])
        )
    }
    live_targets = ((multi_ids - historical_ids) | shared_identity_ids | verified_set_logo_ids |
"""
if old not in s:
    raise SystemExit('audit live target anchor not found')
s=s.replace(old,new,1)
old='''        # Cardoryx production supports an exact dynamic resolver only for the\n        # verified Scarlet & Violet Promo `set-logo` taxonomy.  A plain Set\n        # Stamp row must exclude `staff`; Staff must contain both tokens.  Each\n        # row must carry its own matching Cardmarket product + live Price Guide.\n        live_svp_set_logo_pair = False\n        live_svp_stamp_products = {}\n        if card_id.startswith("svp-"):\n'''
new='''        # Cardoryx production supports an exact dynamic resolver only for the\n        # verified SVP/MEP `set-logo` taxonomy. A plain Set Stamp row must\n        # exclude `staff`; Staff must contain both tokens. Each row must carry\n        # its own matching Cardmarket product + live Price Guide.\n        live_svp_set_logo_pair = False\n        live_svp_stamp_products = {}\n        if card_id.startswith(("svp-", "mep-")):\n'''
if old not in s:
    raise SystemExit('audit stamped classification anchor not found')
s=s.replace(old,new,1)
old='''        elif live_svp_set_logo_pair:\n            classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"\n            reason = ("TCGdex live espone una coppia fisica SV Promo esatta e distinta: `set-logo` e "\n                      "`set-logo + staff`, ciascuna con il proprio productId e Price Guide Cardmarket. "\n                      "Il runtime Cardoryx le risolve separatamente senza fallback tra stamp.")\n            action = "Mantenere il resolver SVP esatto; nessun mapping statico e nessun riuso prezzo fra Set Stamp e Staff."\n'''
new='''        elif live_svp_set_logo_pair:\n            classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"\n            reason = ("TCGdex live espone una coppia fisica promo esatta e distinta: `set-logo` e "\n                      "`set-logo + staff`, ciascuna con il proprio productId e Price Guide Cardmarket. "\n                      "Il runtime Cardoryx le risolve separatamente senza fallback tra stamp.")\n            action = "Mantenere il resolver set-logo esatto; nessun mapping statico e nessun riuso prezzo fra Set Stamp e Staff."\n'''
if old not in s:
    raise SystemExit('audit exact alternate reason anchor not found')
s=s.replace(old,new,1)

insert_before='\ndef main():\n'
if insert_before not in s:
    raise SystemExit('main anchor not found')
fn=r'''
def runtime_mep_set_logo_staff_regression():
    # Verify all currently audited MEP Set Stamp/Staff product pairs in production JS.
    source = INDEX.read_text(encoding="utf-8")

    def extract_fn(name):
        marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
        if not marker:
            raise AssertionError(f"Missing production function {name}")
        brace = source.find("{", marker.end())
        depth = 0
        quote = None
        esc = False
        for i in range(brace, len(source)):
            ch = source[i]
            if quote:
                if esc:
                    esc = False
                elif ch == "\\":
                    esc = True
                elif ch == quote:
                    quote = None
                continue
            if ch in ("'", '"', "`"):
                quote = ch
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    return source[marker.start():i + 1]
        raise AssertionError(f"Unclosed production function {name}")

    names = (
        "normText", "canonicalStamp", "canonicalVariant", "canonicalFinishTypeLabel",
        "canonicalFinishFoilLabel", "tcgdexVariantDetails", "tcgdexStampedRowFinish",
        "tcgdexExactSvpStampPrice",
    )
    js = "\n".join(extract_fn(name) for name in names)
    ids = (
        "mep-001", "mep-002", "mep-003", "mep-004",
        "mep-014", "mep-015", "mep-016", "mep-017",
        "mep-064", "mep-065", "mep-066", "mep-067",
        "mep-074", "mep-075", "mep-076", "mep-077",
    )
    cache = Path(tempfile.gettempdir()) / "cardoryx_mep_stamp_regression_cache_v1"
    fixtures, errors = {}, {}
    for card_id in ids:
        value, error = live_card(card_id, cache)
        if value:
            fixtures[card_id] = value
        if error:
            errors[card_id] = error
    if errors or set(fixtures) != set(ids):
        raise AssertionError(f"MEP live fixture errors: {errors}; fetched={sorted(fixtures)}")

    harness = r'''
const fixtures=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
function stamps(r){return (Array.isArray(r?.stamp)?r.stamp:[]).map(normText)}
function pid(r){return Number(r?.thirdParty?.cardmarket||0)}
function ppid(r){return Number(r?.pricing?.cardmarket?.idProduct||r?.pricing?.cardmarket?.id_product||0)}
const checked={};
for(const [id,c] of Object.entries(fixtures)){
  const rows=tcgdexVariantDetails(c);
  const setRows=rows.filter(r=>stamps(r).includes('setlogo')&&!stamps(r).includes('staff'));
  const staffRows=rows.filter(r=>stamps(r).includes('setlogo')&&stamps(r).includes('staff'));
  if(setRows.length!==1||staffRows.length!==1)fail(id+' source pair not unique');
  const setRow=setRows[0], staffRow=staffRows[0];
  const setFinish=tcgdexStampedRowFinish(setRow), staffFinish=tcgdexStampedRowFinish(staffRow);
  if(!setFinish||!staffFinish)fail(id+' unsupported physical finish');
  if(!(pid(setRow)>0)||pid(setRow)!==ppid(setRow))fail(id+' invalid Set Stamp product');
  if(!(pid(staffRow)>0)||pid(staffRow)!==ppid(staffRow))fail(id+' invalid Staff product');
  if(pid(setRow)===pid(staffRow))fail(id+' Set Stamp/Staff product collision');
  const setPrice=tcgdexExactSvpStampPrice(c,setFinish,'Set Stamp');
  const staffPrice=tcgdexExactSvpStampPrice(c,staffFinish,'Staff');
  if(!setPrice||Number(setPrice.idProduct)!==pid(setRow))fail(id+' Set Stamp resolver mismatch');
  if(!staffPrice||Number(staffPrice.idProduct)!==pid(staffRow))fail(id+' Staff resolver mismatch');
  checked[id]={setFinish,staffFinish,setPid:pid(setRow),staffPid:pid(staffRow)};
}
const foreign={...fixtures['mep-001'],set:{...(fixtures['mep-001'].set||{}),id:'me01'}};
if(tcgdexExactSvpStampPrice(foreign,'Holo','Set Stamp')!==null)fail('resolver leaked outside verified promo sets');
process.stdout.write(JSON.stringify({checked,count:Object.keys(checked).length,setScopeRejected:true}));
'''
    result = json.loads(subprocess.check_output(
        ["node", "-e", js + "\n" + harness, json.dumps(fixtures)],
        text=True,
    ))
    if result.get("count") != 16 or not result.get("setScopeRejected"):
        raise AssertionError(f"Unexpected MEP runtime result: {result}")
    return result

'''
s=s.replace(insert_before,fn+insert_before,1)
old='''    runtime_regression["svpSetLogoStaff"] = runtime_svp_set_logo_staff_regression()\n'''
new='''    runtime_regression["svpSetLogoStaff"] = runtime_svp_set_logo_staff_regression()\n    runtime_regression["mepSetLogoStaff"] = runtime_mep_set_logo_staff_regression()\n'''
if old not in s:
    raise SystemExit('runtime regression anchor not found')
s=s.replace(old,new,1)
audit.write_text(s,encoding='utf-8')
print('patched index.html and permanent Cardmarket audit for exact MEP set-logo/staff')
