from pathlib import Path

index=Path('index.html')
src=index.read_text()
marker='function cardmarketValueForCardVariant(card,variant){'
if src.count(marker)!=1:
    raise SystemExit(f'cardmarketValue marker count={src.count(marker)}')
insert=r'''const VERIFIED_DUAL_BASE_CARDMARKET_PRODUCTS={
  'sv05-041':{setId:'sv05',localId:'41',name:'Feraligatr',normal:761970,holo:760671,reverse:760671},
  'sv08-065':{setId:'sv08',localId:'65',name:'Tapu Koko',normal:799718,holo:794346,reverse:794346}
};
function verifiedDualBaseCardmarketVariant(card,variant){
  const id=String(card?.tcgdexId||card?.id||'').trim().toLowerCase();
  const rule=VERIFIED_DUAL_BASE_CARDMARKET_PRODUCTS[id];
  if(!rule)return null;
  const setId=String(card?.set?.id||card?._cardoryxSetId||'').trim().toLowerCase();
  const localRaw=String(card?.localId||'').trim().toLowerCase();
  const local=localRaw.match(/^\d+$/)?String(Number(localRaw)):localRaw.replace(/[^a-z0-9]+/g,'');
  if(setId!==rule.setId||local!==rule.localId||normText(card?.name||'')!==normText(rule.name))return null;
  const v=canonicalVariant(variant||'Normal');
  const type=v==='Normal'?'normal':v==='Holo'?'holo':v==='Reverse Holo'?'reverse':'';
  if(!type)return {handled:true,matched:false,kind:'needs-exact-variant'};
  const expected=Number(rule[type]||0);
  const rows=tcgdexVariantDetails(card).filter(row=>{
    if(String(row?.type||'').trim().toLowerCase()!==type)return false;
    if(row?.stamp&&(Array.isArray(row.stamp)?row.stamp.length:String(row.stamp).trim()))return false;
    if(row?.foil&&(Array.isArray(row.foil)?row.foil.length:String(row.foil).trim()))return false;
    const size=String(row?.size||'standard').trim().toLowerCase();
    if(size&&size!=='standard')return false;
    const rowPid=Number(row?.thirdParty?.cardmarket||row?.pricing?.cardmarket?.idProduct||row?.pricing?.cardmarket?.id_product||0);
    return rowPid===expected;
  });
  if(rows.length!==1)return {handled:true,matched:false,kind:'needs-exact-variant'};
  const pricing=rows[0]?.pricing?.cardmarket||null;
  const pricingPid=Number(pricing?.idProduct||pricing?.id_product||0);
  if(!pricing||pricingPid!==expected)return {handled:true,matched:false,kind:'base-product-price-unavailable'};
  const keys=type==='reverse'?['trend-holo','avg7-holo','avg30-holo','avg-holo','low-holo']:['trend','avg7','avg30','avg','low'];
  if(!keys.some(key=>Number(pricing?.[key]||0)>0))return {handled:true,matched:false,kind:'base-product-price-unavailable'};
  return {handled:true,matched:true,productId:expected,pricing,finish:v,
    source:`Cardmarket · prodotto fisico esatto ${expected}`};
}
'''
src=src.replace(marker,insert+marker,1)

old=marker+"\n  const mcd2019=verifiedMcdonalds2019CardmarketVariant(card,variant);"
new=marker+"\n  const dualBase=verifiedDualBaseCardmarketVariant(card,variant);\n  if(dualBase?.handled){\n    if(!dualBase.matched)return {value:0,kind:dualBase.kind||'needs-exact-variant'};\n    const p=dualBase.pricing||{};\n    const reverse=canonicalVariant(variant||'Normal')==='Reverse Holo';\n    const keys=reverse?['trend-holo','avg7-holo','avg30-holo','avg-holo','low-holo']:['trend','avg7','avg30','avg','low'];\n    const value=keys.map(k=>Number(p[k]||0)).find(x=>Number.isFinite(x)&&x>0)||0;\n    return {value,kind:'exact-dual-base-cardmarket',exact:true,productId:dualBase.productId,source:dualBase.source};\n  }\n  const mcd2019=verifiedMcdonalds2019CardmarketVariant(card,variant);"
if old not in src:
    raise SystemExit('cardmarketValue insertion point missing')
src=src.replace(old,new,1)

stats='function cardmarketStatsForCardVariant(card,variant){'
old=stats+"\n  const mcd2019=verifiedMcdonalds2019CardmarketVariant(card,variant);"
new=stats+"\n  const dualBase=verifiedDualBaseCardmarketVariant(card,variant);\n  if(dualBase?.handled){\n    if(!dualBase.matched)return {low:null,trend:null,avg7:null,avg30:null};\n    const p=dualBase.pricing||{};\n    const reverse=canonicalVariant(variant||'Normal')==='Reverse Holo';\n    return reverse\n      ?{low:p['low-holo']??null,trend:p['trend-holo']??null,avg7:p['avg7-holo']??null,avg30:p['avg30-holo']??null}\n      :{low:p.low??null,trend:p.trend??null,avg7:p.avg7??null,avg30:p.avg30??null};\n  }\n  const mcd2019=verifiedMcdonalds2019CardmarketVariant(card,variant);"
if old not in src:
    raise SystemExit('cardmarketStats insertion point missing')
src=src.replace(old,new,1)
index.write_text(src)

audit=Path('scripts/test_card_identity_cardmarket_audit.py')
s=audit.read_text()
const_marker='MCDONALDS_2021_EXACT_PAIRS = {'
if s.count(const_marker)!=1:
    raise SystemExit('audit constant marker missing')
pyconst='''VERIFIED_DUAL_BASE_CARDMARKET_PRODUCTS = {\n    "sv05-041": {"setId": "sv05", "localId": "041", "name": "Feraligatr", "expansion": 5589, "metacard": 430014, "normal": 761970, "holo": 760671, "reverse": 760671},\n    "sv08-065": {"setId": "sv08", "localId": "065", "name": "Tapu Koko", "expansion": 5879, "metacard": 441182, "normal": 799718, "holo": 794346, "reverse": 794346},\n}\n'''
s=s.replace(const_marker,pyconst+const_marker,1)

old='''    live_targets = ((multi_ids - historical_ids) | shared_identity_ids | verified_set_logo_ids | {"swshp-SWSH028", "ex5-29"} |\n                    set(CONFIRMED_BASE_PRODUCT_CONFLICTS) |\n                    {"sm12-29", "sm12-54", "sm12-237"} | PROTECTED_REVERSE)'''
new='''    live_targets = ((multi_ids - historical_ids) | shared_identity_ids | verified_set_logo_ids | {"swshp-SWSH028", "ex5-29"} |\n                    set(CONFIRMED_BASE_PRODUCT_CONFLICTS) | set(VERIFIED_DUAL_BASE_CARDMARKET_PRODUCTS) |\n                    {"sm12-29", "sm12-54", "sm12-237"} | PROTECTED_REVERSE)'''
if old not in s:
    raise SystemExit('live_targets marker missing')
s=s.replace(old,new,1)

fixture_marker='    fixtures["tyranitar"] = {'
dual_fixture='''    fixtures["dualBase"] = [\n        {\n            "id":"sv05-041","tcgdexId":"sv05-041","name":"Feraligatr","localId":"041","set":{"id":"sv05","name":"Temporal Forces"},\n            "variants":{"normal":True,"holo":True,"reverse":True},\n            "variants_detailed":[\n                {"type":"holo","size":"standard","thirdParty":{"cardmarket":760671},"pricing":{"cardmarket":{"idProduct":760671,"trend":0.10,"low":0.02,"avg7":0.12,"avg30":0.14,"avg":0.14,"trend-holo":0.19,"low-holo":0.02,"avg7-holo":0.19,"avg30-holo":0.28,"avg-holo":0.26}}},\n                {"type":"reverse","size":"standard","thirdParty":{"cardmarket":760671},"pricing":{"cardmarket":{"idProduct":760671,"trend":0.10,"low":0.02,"avg7":0.12,"avg30":0.14,"avg":0.14,"trend-holo":0.19,"low-holo":0.02,"avg7-holo":0.19,"avg30-holo":0.28,"avg-holo":0.26}}},\n                {"type":"normal","size":"standard","thirdParty":{"cardmarket":761970},"pricing":{"cardmarket":{"idProduct":761970,"trend":0.84,"low":0.02,"avg7":0.81,"avg30":0.52,"avg":0.69}}},\n                {"type":"normal","size":"standard","stamp":["player-rewards-program"]}\n            ],\n            "pricing":{"cardmarket":{"idProduct":760671,"trend":0.10,"low":0.02,"avg7":0.12,"avg30":0.14,"avg":0.14,"trend-holo":0.19,"low-holo":0.02,"avg7-holo":0.19,"avg30-holo":0.28,"avg-holo":0.26}},\n            "expected":{"normal":[0.84,761970],"holo":[0.10,760671],"reverse":[0.19,760671]}\n        },\n        {\n            "id":"sv08-065","tcgdexId":"sv08-065","name":"Tapu Koko","localId":"065","set":{"id":"sv08","name":"Surging Sparks"},\n            "variants":{"normal":True,"holo":True,"reverse":True},\n            "variants_detailed":[\n                {"type":"holo","size":"standard","thirdParty":{"cardmarket":794346},"pricing":{"cardmarket":{"idProduct":794346,"trend":0.07,"low":0.02,"avg7":0.06,"avg30":0.05,"avg":0.05,"trend-holo":0.24,"low-holo":0.02,"avg7-holo":0.23,"avg30-holo":0.16,"avg-holo":0.13}}},\n                {"type":"reverse","size":"standard","thirdParty":{"cardmarket":794346},"pricing":{"cardmarket":{"idProduct":794346,"trend":0.07,"low":0.02,"avg7":0.06,"avg30":0.05,"avg":0.05,"trend-holo":0.24,"low-holo":0.02,"avg7-holo":0.23,"avg30-holo":0.16,"avg-holo":0.13}}},\n                {"type":"normal","size":"standard","thirdParty":{"cardmarket":799718},"pricing":{"cardmarket":{"idProduct":799718,"trend":0.02,"low":0.02,"avg7":1.55,"avg30":2.48,"avg":1.12}}},\n                {"type":"normal","size":"standard","stamp":["player-rewards-program"]}\n            ],\n            "pricing":{"cardmarket":{"idProduct":794346,"trend":0.07,"low":0.02,"avg7":0.06,"avg30":0.05,"avg":0.05,"trend-holo":0.24,"low-holo":0.02,"avg7-holo":0.23,"avg30-holo":0.16,"avg-holo":0.13}},\n            "expected":{"normal":[0.02,799718],"holo":[0.07,794346],"reverse":[0.24,794346]}\n        },\n    ]\n'''
if fixture_marker not in s:
    raise SystemExit('fixture marker missing')
s=s.replace(fixture_marker,dual_fixture+fixture_marker,1)

global_marker='  verifiedBaseCardmarketProductOverride,resolvedCardmarketPricingForCard,\n'
if global_marker not in s:
    raise SystemExit('runtime global marker missing')
s=s.replace(global_marker,'  verifiedDualBaseCardmarketVariant,verifiedBaseCardmarketProductOverride,resolvedCardmarketPricingForCard,\n',1)

harness_marker='const tyr=fixtures.tyranitar;'
dual_assert=r'''for(const card of fixtures.dualBase){
  const normal=r.cardmarketValueForCardVariant(card,'Normal');
  const holo=r.cardmarketValueForCardVariant(card,'Holo');
  const reverse=r.cardmarketValueForCardVariant(card,'Reverse Holo');
  assert.deepStrictEqual(JSON.parse(JSON.stringify([normal.value,normal.productId])),card.expected.normal);
  assert.deepStrictEqual(JSON.parse(JSON.stringify([holo.value,holo.productId])),card.expected.holo);
  assert.deepStrictEqual(JSON.parse(JSON.stringify([reverse.value,reverse.productId])),card.expected.reverse);
  assert.strictEqual(normal.kind,'exact-dual-base-cardmarket');
  assert.strictEqual(holo.kind,'exact-dual-base-cardmarket');
  assert.strictEqual(reverse.kind,'exact-dual-base-cardmarket');
  assert.strictEqual(r.verifiedDualBaseCardmarketVariant({...card,set:{id:'wrong'}},'Normal'),null);
  assert.strictEqual(r.verifiedDualBaseCardmarketVariant({...card,localId:'999'},'Normal'),null);
  assert.strictEqual(r.verifiedDualBaseCardmarketVariant({...card,name:card.name+' wrong'},'Normal'),null);
  const stampedOnly={...card,variants_detailed:card.variants_detailed.filter(x=>Array.isArray(x.stamp)&&x.stamp.includes('player-rewards-program'))};
  const noLeak=r.verifiedDualBaseCardmarketVariant(stampedOnly,'Normal');
  assert.strictEqual(noLeak?.handled,true);
  assert.strictEqual(noLeak?.matched,false);
  const ns=r.cardmarketStatsForCardVariant(card,'Normal');
  const hs=r.cardmarketStatsForCardVariant(card,'Holo');
  const rs=r.cardmarketStatsForCardVariant(card,'Reverse Holo');
  assert.strictEqual(ns.trend,card.expected.normal[0]);
  assert.strictEqual(hs.trend,card.expected.holo[0]);
  assert.strictEqual(rs.trend,card.expected.reverse[0]);
}
'''
if harness_marker not in s:
    raise SystemExit('harness marker missing')
s=s.replace(harness_marker,dual_assert+harness_marker,1)

classification_marker='        classification, priority, confidence = "SAFE", None, "HIGH"\n'
dual_eval='''        live_dual_base_pair = False\n        if card_id in VERIFIED_DUAL_BASE_CARDMARKET_PRODUCTS:\n            rule = VERIFIED_DUAL_BASE_CARDMARKET_PRODUCTS[card_id]\n            expected = {"normal": rule["normal"], "holo": rule["holo"], "reverse": rule["reverse"]}\n            exact_rows = {}\n            for finish, expected_pid in expected.items():\n                matches = []\n                for row in live_card_detail.get("variants_detailed") or []:\n                    if str(row.get("type") or "").strip().lower() != finish:\n                        continue\n                    if row.get("stamp") or row.get("foil") or row.get("firstEdition"):\n                        continue\n                    if str(row.get("size") or "standard").strip().lower() not in {"", "standard"}:\n                        continue\n                    row_pid = cm_id(row)\n                    pricing_cm = ((row.get("pricing") or {}).get("cardmarket") or {})\n                    try:\n                        pricing_pid = int(pricing_cm.get("idProduct") or pricing_cm.get("id_product"))\n                    except (TypeError, ValueError):\n                        pricing_pid = None\n                    keys = ("trend-holo", "avg7-holo", "avg30-holo", "avg-holo", "low-holo") if finish == "reverse" else ("trend", "avg7", "avg30", "avg", "low")\n                    usable = any(isinstance(pricing_cm.get(k), (int, float)) and pricing_cm.get(k) > 0 for k in keys)\n                    if row_pid == expected_pid and pricing_pid == expected_pid and usable:\n                        matches.append(row)\n                exact_rows[finish] = matches\n            pn, ph = products.get(rule["normal"]), products.get(rule["holo"])\n            gn, gh = prices.get(rule["normal"]), prices.get(rule["holo"])\n            same_identity = bool(\n                pn and ph and pn.get("idExpansion") == rule["expansion"] and ph.get("idExpansion") == rule["expansion"] and\n                pn.get("idMetacard") == rule["metacard"] and ph.get("idMetacard") == rule["metacard"] and\n                pn.get("name") == ph.get("name") and str(pn.get("name") or "").split(" [", 1)[0] == rule["name"]\n            )\n            guides_ok = bool(gn and gh and int(gn.get("idProduct") or 0) == rule["normal"] and int(gh.get("idProduct") or 0) == rule["holo"])\n            live_dual_base_pair = bool(\n                current_pid == rule["holo"] and rule["normal"] != rule["holo"] and\n                all(len(exact_rows[k]) == 1 for k in ("normal", "holo", "reverse")) and same_identity and guides_ok\n            )\n\n'''
if classification_marker not in s:
    raise SystemExit('classification marker missing')
s=s.replace(classification_marker,dual_eval+classification_marker,1)

before='''        elif live_exact_base_evidence and not snapshot_exact_alternate_product:\n'''
dual_class='''        elif live_dual_base_pair:\n            classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"\n            rule = VERIFIED_DUAL_BASE_CARDMARKET_PRODUCTS[card_id]\n            resolved_pid = rule["holo"]\n            resolved_value = (prices.get(rule["holo"]) or {}).get("trend")\n            reason = ("TCGdex live espone Normal e Holo/Reverse come prodotti Cardmarket fisicamente distinti; "\n                      "il catalogo ufficiale conferma stesso set, stesso metacard e stesso nome. Il runtime "\n                      "seleziona il productId esclusivamente dalla finitura esatta e non usa la stampa Player Rewards senza productId.")\n            action = "Mantenere il resolver esatto limitato a questa identità; nessuna generalizzazione ad altre carte o tassonomie."\n'''+before
if before not in s:
    raise SystemExit('classification insertion point missing')
s=s.replace(before,dual_class,1)
audit.write_text(s)

Path('.github/workflows/temp-fix-cardmarket-dual-base.yml').unlink()
Path('scripts/temp_fix_dual_base.py').unlink()
