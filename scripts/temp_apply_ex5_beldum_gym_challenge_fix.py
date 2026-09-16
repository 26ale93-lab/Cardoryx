#!/usr/bin/env python3
from pathlib import Path

root=Path(__file__).resolve().parents[1]
index=root/'index.html'
audit=root/'scripts'/'test_card_identity_cardmarket_audit.py'

s=index.read_text(encoding='utf-8')

# 1) Canonical physical stamp label. This only names source evidence; pricing remains exact/fail-closed.
old="""  if(n.includes('gamestop'))return 'GameStop';
  return v||'Altro';
}"""
new="""  if(n.includes('gamestop'))return 'GameStop';
  if(n.includes('gymchallenge'))return 'Gym Challenge';
  return v||'Altro';
}"""
if old not in s: raise SystemExit('canonicalStamp anchor missing')
s=s.replace(old,new,1)

# 2) Exact base override: Beldum standard V1 is 276103. 280585 remains a legitimate stamped product.
old="""  'pl3-7':{setId:'pl3',localId:'007',conflictingProduct:278689,baseProduct:278698},
  // EX Team Magma vs Team Aqua"""
new="""  'pl3-7':{setId:'pl3',localId:'007',conflictingProduct:278689,baseProduct:278698},
  // EX Hidden Legends — Beldum 29/101. TCGdex exposes the Gym Challenge
  // special-print product at top level; V1 product 276103 is the standard
  // Normal/Reverse identity. Product 280585 remains valid only as the exact
  // Gym Challenge stamped printing resolved separately below.
  'ex5-29':{setId:'ex5',localId:'029',conflictingProduct:280585,baseProduct:276103},
  // EX Team Magma vs Team Aqua"""
if old not in s: raise SystemExit('override anchor missing')
s=s.replace(old,new,1)

# 3) Guard the verified base product against leaking to another physical identity.
old="""  const exactMetagrossPl3_7=id==='pl3-7'&&setId==='pl3'&&local==='7'&&name==='metagross';
"""
guard="""  const exactBeldumEx5_29=id==='ex5-29'&&setId==='ex5'&&local==='29'&&name==='beldum';
  if(product===276103&&!exactBeldumEx5_29){
    return {
      kind:'identity-mismatch',
      source:'Cardmarket · EX Hidden Legends Beldum 29/101 V1 product 276103 verificato',
      reason:'Il prodotto 276103 è consentito solo per Beldum ex5-29 / 029'
    };
  }
  const exactMetagrossPl3_7=id==='pl3-7'&&setId==='pl3'&&local==='7'&&name==='metagross';
"""
if old not in s: raise SystemExit('identity guard anchor missing')
s=s.replace(old,guard,1)

# 4) Exact stamped resolver. No generic Gym Challenge price rule.
old="""function verifiedStampPrice(card,variant,stamp){
  const exact=verifiedExactSpecialStampPrice(card,variant,stamp);
  if(exact)return exact;
  const swsh028GameStop=tcgdexExactSwsh028GameStopPrice(card,variant,stamp);
"""
new="""// Exact dynamic evidence for Beldum 29/101 Gym Challenge special print.
// The label Gym Challenge may be recognized from TCGdex evidence globally,
// but Cardmarket pricing is deliberately resolved only for this verified card.
function tcgdexExactEx5BeldumGymChallengePrice(card,variant,stamp){
  const id=String(card?.tcgdexId||card?.id||'').trim().toLowerCase();
  if(id!=='ex5-29' || cardSetId(card)!=='ex5' ||
     exactLocalIdKey(card?.localId||'')!==exactLocalIdKey('029') ||
     normText(card?.name||'')!==normText('Beldum') ||
     canonicalVariant(variant||'Normal')!=='Normal' || canonicalStamp(stamp)!=='Gym Challenge')return null;
  const rows=tcgdexVariantDetails(card).filter(row=>{
    if(Array.isArray(row?.languages)&&row.languages.length&&!row.languages.includes('it'))return false;
    const stamps=(Array.isArray(row?.stamp)?row.stamp:[]).map(normText);
    return stamps.length===1 && stamps[0]==='gymchallenge' &&
      canonicalFinishTypeLabel(row?.type)==='normal' && !canonicalFinishFoilLabel(row?.foil);
  });
  if(rows.length!==1)return null;
  const row=rows[0];
  const productId=Number(row?.thirdParty?.cardmarket||0);
  const cm=row?.pricing?.cardmarket;
  const pricingProductId=Number(cm?.idProduct||cm?.id_product||0);
  if(productId!==280585 || pricingProductId!==280585 || !cm)return null;
  const hasRealPrice=['trend','avg7','avg30','avg','low'].some(k=>Number(cm?.[k])>0);
  if(!hasRealPrice)return null;
  return {...cm,idProduct:280585,source:'TCGdex · Cardmarket · Beldum HL29 Gym Challenge',verified:String(cm?.updated||'')};
}

function verifiedStampPrice(card,variant,stamp){
  const exact=verifiedExactSpecialStampPrice(card,variant,stamp);
  if(exact)return exact;
  const beldumGym=tcgdexExactEx5BeldumGymChallengePrice(card,variant,stamp);
  if(beldumGym)return beldumGym;
  const swsh028GameStop=tcgdexExactSwsh028GameStopPrice(card,variant,stamp);
"""
if old not in s: raise SystemExit('verifiedStampPrice anchor missing')
s=s.replace(old,new,1)
index.write_text(s,encoding='utf-8')

# Permanent audit/regression changes.
s=audit.read_text(encoding='utf-8')

old='''    "pl3-7": {"setId": "pl3", "localId": "007", "conflictingProduct": 278689, "baseProduct": 278698},\n'''
new='''    "pl3-7": {"setId": "pl3", "localId": "007", "conflictingProduct": 278689, "baseProduct": 278698},\n    "ex5-29": {"setId": "ex5", "localId": "029", "conflictingProduct": 280585, "baseProduct": 276103},\n'''
if old not in s: raise SystemExit('EXPECTED_BASE_OVERRIDES anchor missing')
s=s.replace(old,new,1)

# Add runtime regression before the SWSH028 regression.
anchor='''def runtime_swsh028_gamestop_regression():\n'''
fn=r'''def runtime_ex5_beldum_gym_challenge_regression():
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
    card,error=live_card("ex5-29", Path(tempfile.gettempdir())/"cardoryx_ex5_beldum_gym_v1")
    if error or not card: raise AssertionError(f"Beldum ex5-29 live fixture unavailable: {error}")
    rows=card.get("variants_detailed") or []
    base=[r for r in rows if not (r.get("stamp") or []) and cm_id(r)==276103 and int(((r.get("pricing") or {}).get("cardmarket") or {}).get("idProduct") or 0)==276103]
    gym=[r for r in rows if [str(x).lower() for x in (r.get("stamp") or [])]==["gym-challenge"] and cm_id(r)==280585 and int(((r.get("pricing") or {}).get("cardmarket") or {}).get("idProduct") or 0)==280585]
    if len(base)!=1 or len(gym)!=1: raise AssertionError(f"Unexpected Beldum product rows base={len(base)} gym={len(gym)}")
    base_cm=(base[0].get("pricing") or {}).get("cardmarket") or {}
    if not any(isinstance(base_cm.get(k),(int,float)) and base_cm.get(k)>0 for k in ("trend","avg7","avg30","avg","low")):
        raise AssertionError("Beldum base V1 has no real Cardmarket price")
    names=("normText","canonicalStamp","canonicalVariant","canonicalFinishTypeLabel","canonicalFinishFoilLabel",
           "cardSetId","canonicalPrintedLocalId","printedLocalIdParts","exactLocalIdKey","tcgdexVariantDetails",
           "tcgdexExactEx5BeldumGymChallengePrice")
    js="\n".join(extract_fn(n) for n in names)
    harness=r'''
const c=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
if(canonicalStamp('gym-challenge')!=='Gym Challenge')fail('taxonomy not canonicalized');
const ok=tcgdexExactEx5BeldumGymChallengePrice(c,'Normal','Gym Challenge');
if(!ok||Number(ok.idProduct)!==280585)fail('exact Gym Challenge product not resolved');
for(const [v,s] of [['Reverse Holo','Gym Challenge'],['Normal','None'],['Normal','GameStop']]){
  if(tcgdexExactEx5BeldumGymChallengePrice(c,v,s)!==null)fail('wrong finish/stamp accepted '+v+' '+s);
}
for(const mutated of [
  {...c,id:'ex5-30',tcgdexId:'ex5-30'},
  {...c,localId:'030'},
  {...c,name:'Beldum wrong'},
  {...c,set:{...(c.set||{}),id:'ex5-other'}},
]) if(tcgdexExactEx5BeldumGymChallengePrice(mutated,'Normal','Gym Challenge')!==null)fail('wrong identity accepted');
const wrongPid={...c,variants_detailed:(c.variants_detailed||[]).map(r=>(r.stamp||[]).includes('gym-challenge')?{...r,thirdParty:{...(r.thirdParty||{}),cardmarket:280586}}:r)};
if(tcgdexExactEx5BeldumGymChallengePrice(wrongPid,'Normal','Gym Challenge')!==null)fail('wrong product accepted');
process.stdout.write(JSON.stringify({baseProductId:276103,gymProductId:ok.idProduct,baseTrend:Number(process.argv[2]),gymTrend:Number(ok.trend||0),exact:true}));
'''
    return json.loads(subprocess.check_output(["node","-e",js+"\n"+harness,json.dumps(card),str(base_cm.get("trend") or 0)],text=True))


'''
if anchor not in s: raise SystemExit('runtime function anchor missing')
s=s.replace(anchor,fn+anchor,1)

old='''    runtime_regression["swsh028GameStop"] = runtime_swsh028_gamestop_regression()\n'''
new='''    runtime_regression["ex5BeldumGymChallenge"] = runtime_ex5_beldum_gym_challenge_regression()\n    runtime_regression["swsh028GameStop"] = runtime_swsh028_gamestop_regression()\n'''
if old not in s: raise SystemExit('runtime registration anchor missing')
s=s.replace(old,new,1)

# Live evidence: one V1 row plus one exact Gym Challenge row.
anchor='''        live_swsh028_gamestop = False\n'''
evidence='''        live_ex5_beldum_gym_pair = False\n        live_ex5_beldum_products = None\n        if card_id == "ex5-29":\n            base_rows = []\n            gym_rows = []\n            for row in live_card_detail.get("variants_detailed") or []:\n                stamp_tokens = [str(v or "").strip().lower() for v in (row.get("stamp") or [])]\n                row_pid = cm_id(row)\n                pricing_cm = ((row.get("pricing") or {}).get("cardmarket") or {})\n                try:\n                    pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))\n                except (TypeError, ValueError):\n                    pricing_pid = None\n                usable = any(isinstance(pricing_cm.get(k), (int, float)) and pricing_cm.get(k) > 0\n                             for k in ("trend", "avg7", "avg30", "avg", "low"))\n                if not stamp_tokens and row_pid == 276103 and pricing_pid == 276103 and usable:\n                    base_rows.append(row)\n                if (stamp_tokens == ["gym-challenge"] and str(row.get("type") or "").lower() == "normal" and\n                        not row.get("foil") and row_pid == 280585 and pricing_pid == 280585 and usable):\n                    gym_rows.append(row)\n            if len(base_rows) == 1 and len(gym_rows) == 1:\n                live_ex5_beldum_gym_pair = True\n                live_ex5_beldum_products = {"base": 276103, "gymChallenge": 280585}\n\n        live_swsh028_gamestop = False\n'''
if anchor not in s: raise SystemExit('live evidence anchor missing')
s=s.replace(anchor,evidence,1)

anchor='''        elif live_swsh028_gamestop:\n'''
branch='''        elif live_ex5_beldum_gym_pair:\n            classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"\n            reason = ("Beldum EX Hidden Legends 29/101 ha V1 base Cardmarket 276103 e una stampa Gym Challenge "\n                      "fisicamente distinta 280585, entrambe verificate sulla stessa identità live. Il runtime "\n                      "separa base Normal/Reverse dallo stamp Gym Challenge senza fallback.")\n            action = "Mantenere override base ex5-29 e resolver esatto Gym Challenge; nessuna regola generale per altri set."\n        elif live_swsh028_gamestop:\n'''
if anchor not in s: raise SystemExit('classification branch anchor missing')
s=s.replace(anchor,branch,1)

old='''            "liveExactSwsh028GameStop": live_swsh028_gamestop,\n'''
new='''            "liveExactEx5BeldumGymChallenge": live_ex5_beldum_gym_pair,\n            "liveExactEx5BeldumProducts": live_ex5_beldum_products,\n            "liveExactSwsh028GameStop": live_swsh028_gamestop,\n'''
if old not in s: raise SystemExit('case fields anchor missing')
s=s.replace(old,new,1)

audit.write_text(s,encoding='utf-8')
print('patched exact EX Hidden Legends Beldum Gym Challenge support')
