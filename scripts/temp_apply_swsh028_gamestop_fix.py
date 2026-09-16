#!/usr/bin/env python3
from pathlib import Path

root=Path(__file__).resolve().parents[1]
index=root/'index.html'; audit=root/'scripts'/'test_card_identity_cardmarket_audit.py'

s=index.read_text(encoding='utf-8')
anchor="""function verifiedStampPrice(card,variant,stamp){
  const exact=verifiedExactSpecialStampPrice(card,variant,stamp);
  if(exact)return exact;
  const tcgdexExact=tcgdexExactSvpStampPrice(card,variant,stamp);
"""
insert="""// Exact dynamic evidence for one verified Sword & Shield promo printing.
// This is deliberately not a generic GameStop rule: it applies only to
// Duraludon SWSH028 and never falls back to EB Games or the base Cosmos Holo.
function tcgdexExactSwsh028GameStopPrice(card,variant,stamp){
  const id=String(card?.tcgdexId||card?.id||'').trim().toLowerCase();
  if(id!=='swshp-swsh028' || cardSetId(card)!=='swshp' ||
     exactLocalIdKey(card?.localId||'')!==exactLocalIdKey('SWSH028') ||
     normText(card?.name||'')!==normText('Duraludon') ||
     canonicalVariant(variant||'Normal')!=='Holo' || canonicalStamp(stamp)!=='GameStop')return null;
  const rows=tcgdexVariantDetails(card).filter(row=>{
    if(Array.isArray(row?.languages)&&row.languages.length&&!row.languages.includes('it'))return false;
    const stamps=(Array.isArray(row?.stamp)?row.stamp:[]).map(normText);
    return stamps.length===1 && stamps[0]==='gamestop' &&
      canonicalFinishTypeLabel(row?.type)==='holo' && !canonicalFinishFoilLabel(row?.foil);
  });
  if(rows.length!==1)return null;
  const row=rows[0];
  const productId=Number(row?.thirdParty?.cardmarket||0);
  const cm=row?.pricing?.cardmarket;
  const pricingProductId=Number(cm?.idProduct||cm?.id_product||0);
  if(productId!==742039 || pricingProductId!==742039 || !cm)return null;
  const hasRealPrice=['trend','avg7','avg30','avg','low'].some(k=>Number(cm?.[k])>0);
  if(!hasRealPrice)return null;
  return {...cm,idProduct:742039,source:'TCGdex · Cardmarket · Duraludon SWSH028 GameStop',verified:String(cm?.updated||'')};
}

function verifiedStampPrice(card,variant,stamp){
  const exact=verifiedExactSpecialStampPrice(card,variant,stamp);
  if(exact)return exact;
  const swsh028GameStop=tcgdexExactSwsh028GameStopPrice(card,variant,stamp);
  if(swsh028GameStop)return swsh028GameStop;
  const tcgdexExact=tcgdexExactSvpStampPrice(card,variant,stamp);
"""
if anchor not in s: raise SystemExit('verifiedStampPrice anchor missing')
s=s.replace(anchor,insert,1)
index.write_text(s,encoding='utf-8')

s=audit.read_text(encoding='utf-8')
# Add exact live evidence next to existing promo evidence.
anchor="""        classification, priority, confidence = \"SAFE\", None, \"HIGH\"
"""
evidence="""        live_swsh028_gamestop = False
        live_swsh028_gamestop_pid = None
        if card_id == \"swshp-SWSH028\":
            exact_rows = []
            for row in live_card_detail.get(\"variants_detailed\") or []:
                stamp_tokens = [str(v or \"\").strip().lower() for v in (row.get(\"stamp\") or [])]
                row_pid = cm_id(row)
                pricing_cm = ((row.get(\"pricing\") or {}).get(\"cardmarket\") or {})
                try:
                    pricing_pid = int(pricing_cm.get(\"idProduct\") or pricing_cm.get(\"id_product\"))
                except (TypeError, ValueError):
                    pricing_pid = None
                usable = any(isinstance(pricing_cm.get(k), (int, float)) and pricing_cm.get(k) > 0
                             for k in (\"trend\", \"avg7\", \"avg30\", \"avg\", \"low\"))
                if (stamp_tokens == [\"gamestop\"] and str(row.get(\"type\") or \"\").lower() == \"holo\" and
                        not row.get(\"foil\") and row_pid == 742039 and pricing_pid == 742039 and usable):
                    exact_rows.append(row)
            if len(exact_rows) == 1:
                live_swsh028_gamestop = True
                live_swsh028_gamestop_pid = 742039

        classification, priority, confidence = \"SAFE\", None, \"HIGH\"
"""
if anchor not in s: raise SystemExit('classification anchor missing')
s=s.replace(anchor,evidence,1)
anchor="""        elif live_svp_set_logo_pair:
            classification, priority, confidence = \"EXACT_ALTERNATE_PRODUCT\", \"P2\", \"HIGH\"
"""
replacement="""        elif live_swsh028_gamestop:
            classification, priority, confidence = \"EXACT_ALTERNATE_PRODUCT\", \"P2\", \"HIGH\"
            reason = (\"TCGdex live espone la stampa GameStop esatta di Duraludon SWSH028 con productId \"
                      \"Cardmarket 742039 e Price Guide sulla stessa riga fisica. Il runtime la risolve \"
                      \"solo per identità, finitura e stamp esatti.\")
            action = \"Mantenere il resolver esatto SWSH028 GameStop; EB Games e gli altri promo restano fail-closed.\"
        elif live_svp_set_logo_pair:
            classification, priority, confidence = \"EXACT_ALTERNATE_PRODUCT\", \"P2\", \"HIGH\"
"""
if anchor not in s: raise SystemExit('classification branch anchor missing')
s=s.replace(anchor,replacement,1)
anchor='''            \"liveExactSvpSetLogoStaffPair\": live_svp_set_logo_pair,\n            \"liveExactSvpStampProducts\": live_svp_stamp_products,\n'''
replacement='''            \"liveExactSvpSetLogoStaffPair\": live_svp_set_logo_pair,\n            \"liveExactSvpStampProducts\": live_svp_stamp_products,\n            \"liveExactSwsh028GameStop\": live_swsh028_gamestop,\n            \"liveExactSwsh028GameStopProductId\": live_swsh028_gamestop_pid,\n'''
if anchor not in s: raise SystemExit('case fields anchor missing')
s=s.replace(anchor,replacement,1)

# Permanent runtime regression.
main_anchor='\ndef main():\n'
fn=r'''
def runtime_swsh028_gamestop_regression():
    source = INDEX.read_text(encoding="utf-8")
    def extract_fn(name):
        marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
        if not marker: raise AssertionError(f"Missing production function {name}")
        brace=source.find("{", marker.end()); depth=0; quote=None; esc=False
        for i in range(brace,len(source)):
            ch=source[i]
            if quote:
                if esc: esc=False
                elif ch=="\\": esc=True
                elif ch==quote: quote=None
                continue
            if ch in ("'", '"', "`"): quote=ch
            elif ch=="{": depth+=1
            elif ch=="}":
                depth-=1
                if depth==0:return source[marker.start():i+1]
        raise AssertionError(f"Unclosed production function {name}")
    card,error=live_card("swshp-SWSH028", Path(tempfile.gettempdir())/"cardoryx_swsh028_gamestop_v1")
    if error or not card: raise AssertionError(f"SWSH028 live fixture unavailable: {error}")
    names=("normText","canonicalStamp","canonicalVariant","canonicalFinishTypeLabel","canonicalFinishFoilLabel",
           "cardSetId","exactLocalIdKey","tcgdexVariantDetails","tcgdexExactSwsh028GameStopPrice")
    js="\n".join(extract_fn(n) for n in names)
    harness=r'''
const c=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
const ok=tcgdexExactSwsh028GameStopPrice(c,'Holo','GameStop');
if(!ok||Number(ok.idProduct)!==742039)fail('exact GameStop product not resolved');
if(!Number(ok.low)>0 && !Number(ok.trend)>0)fail('no real price');
for(const [v,s] of [['Normal','GameStop'],['Holo','EB Games'],['Holo','None']]){
  if(tcgdexExactSwsh028GameStopPrice(c,v,s)!==null)fail('wrong finish/stamp accepted '+v+' '+s);
}
for(const mutated of [
  {...c,id:'swshp-SWSH029',tcgdexId:'swshp-SWSH029'},
  {...c,localId:'SWSH029'},
  {...c,name:'Duraludon wrong'},
  {...c,set:{...(c.set||{}),id:'swshp-other'}},
]) if(tcgdexExactSwsh028GameStopPrice(mutated,'Holo','GameStop')!==null)fail('wrong identity accepted');
const wrongPid={...c,variants_detailed:(c.variants_detailed||[]).map(r=>(r.stamp||[]).includes('gamestop')?{...r,thirdParty:{...(r.thirdParty||{}),cardmarket:742040}}:r)};
if(tcgdexExactSwsh028GameStopPrice(wrongPid,'Holo','GameStop')!==null)fail('wrong product accepted');
process.stdout.write(JSON.stringify({productId:ok.idProduct,trend:ok.trend,low:ok.low,exact:true}));
'''
    return json.loads(subprocess.check_output(["node","-e",js+"\n"+harness,json.dumps(card)],text=True))

'''
if main_anchor not in s: raise SystemExit('main anchor missing')
s=s.replace(main_anchor,fn+main_anchor,1)
anchor='''    runtime_regression[\"mepSetLogoStaff\"] = runtime_mep_set_logo_staff_regression()\n'''
replacement='''    runtime_regression[\"mepSetLogoStaff\"] = runtime_mep_set_logo_staff_regression()\n    runtime_regression[\"swsh028GameStop\"] = runtime_swsh028_gamestop_regression()\n'''
if anchor not in s: raise SystemExit('runtime anchor missing')
s=s.replace(anchor,replacement,1)
audit.write_text(s,encoding='utf-8')
print('patched exact SWSH028 GameStop runtime and audit')
