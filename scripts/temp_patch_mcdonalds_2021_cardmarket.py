#!/usr/bin/env python3
from pathlib import Path
import json

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'
AUDIT=ROOT/'scripts/test_card_identity_cardmarket_audit.py'

# Explicit official Cardmarket pairs. No product-id arithmetic is used.
ROWS=[
(1,'Bulbasaur',538778,(0.66,0.51,0.46,0.44,0.02),538783,(3.71,3.75,3.36,3.38,0.49)),
(2,'Chikorita',538788,(0.28,0.31,0.28,0.28,0.02),538793,(1.67,1.66,1.83,1.95,0.10)),
(3,'Treecko',538798,(0.21,0.22,0.24,0.25,0.02),538803,(2.77,3.73,3.14,3.04,0.70)),
(4,'Turtwig',538808,(0.20,0.27,0.25,0.25,0.02),538813,(1.64,1.67,1.58,1.55,0.19)),
(5,'Snivy',538818,(0.20,0.21,0.22,0.25,0.02),538823,(1.55,1.60,1.27,1.21,0.02)),
(6,'Chespin',538828,(0.24,0.21,0.19,0.20,0.02),538833,(1.22,1.44,1.09,0.93,0.02)),
(7,'Rowlet',538838,(0.18,0.20,0.19,0.20,0.02),538843,(1.22,1.40,1.17,1.16,0.05)),
(8,'Grookey',538848,(0.15,0.19,0.19,0.24,0.02),538853,(0.89,1.05,0.95,1.00,0.02)),
(9,'Charmander',538858,(0.74,0.51,0.48,0.46,0.02),538863,(4.22,3.81,3.66,3.75,0.40)),
(10,'Cyndaquil',538868,(0.22,0.27,0.24,0.24,0.02),538873,(1.62,1.67,1.73,1.91,0.30)),
(11,'Torchic',538878,(0.23,0.20,0.22,0.26,0.02),538883,(1.19,1.44,1.45,1.49,0.20)),
(12,'Chimchar',538888,(0.25,0.23,0.22,0.23,0.02),538893,(1.37,1.25,1.13,1.20,0.05)),
(13,'Tepig',538898,(0.21,0.28,0.23,0.23,0.02),538903,(1.09,1.11,1.12,1.18,0.15)),
(14,'Fennekin',538908,(0.18,0.19,0.18,0.21,0.02),538913,(1.09,1.18,1.15,1.16,0.10)),
(15,'Litten',538918,(0.23,0.24,0.23,0.22,0.02),538923,(1.15,1.31,1.31,1.29,0.02)),
(16,'Scorbunny',538928,(0.24,0.27,0.24,0.24,0.02),538933,(1.04,1.21,1.19,1.28,0.02)),
(17,'Squirtle',538938,(0.20,0.39,0.46,0.46,0.02),538943,(4.34,4.74,4.18,4.04,0.49)),
(18,'Totodile',538948,(0.35,0.27,0.27,0.32,0.02),538953,(1.87,1.90,1.86,2.09,0.30)),
(19,'Mudkip',538958,(0.35,0.31,0.32,0.33,0.02),538963,(1.62,2.12,2.02,1.88,0.20)),
(20,'Piplup',538968,(0.28,0.27,0.24,0.24,0.02),538973,(2.77,2.74,2.31,2.14,0.30)),
(21,'Oshawott',538978,(0.18,0.23,0.21,0.22,0.02),538983,(1.86,2.07,1.67,1.62,0.20)),
(22,'Froakie',538988,(0.26,0.24,0.24,0.26,0.02),538993,(1.10,1.33,1.20,1.28,0.15)),
(23,'Popplio',538998,(0.23,0.25,0.24,0.28,0.02),539003,(3.90,2.41,3.67,4.06,0.40)),
(24,'Sobble',539008,(0.21,0.22,0.19,0.21,0.02),539013,(2.64,3.39,2.84,2.82,0.20)),
(25,'Pikachu',539018,(2.03,1.79,1.86,1.91,0.10),539023,(16.09,15.30,17.49,16.87,1.00)),
]

def js_entry(num,name,np,ns,hp,hs):
    def p(pid,s):
        t,a7,a30,a,low=s
        return f"{{idProduct:{pid},trend:{t},avg7:{a7},avg30:{a30},avg:{a},low:{low}}}"
    return f"  '2021swsh-{num}':{{localId:'{num}',name:{json.dumps(name)},normal:{p(np,ns)},holo:{p(hp,hs)}}},"

s=INDEX.read_text(encoding='utf-8')
anchor='function cardmarketValueForCardVariant(card,variant){\n'
if anchor not in s: raise SystemExit('cardmarket value anchor missing')
registry="""// McDonald's Collection 2021 — exact official Cardmarket Normal/Holo pairs.\n// Each pair was verified in expansion 3738 against the same exact metacard.\n// Do not infer IDs arithmetically and do not generalize the 25th-celebration stamp.\nconst VERIFIED_MCDONALDS_2021_CARDMARKET_PRODUCTS={\n"""+'\n'.join(js_entry(*r) for r in ROWS)+"\n};\n"+r"""
function verifiedMcdonalds2021CardmarketVariant(card,variant){
  const id=String(card?.tcgdexId||card?.id||'').trim();
  const rule=VERIFIED_MCDONALDS_2021_CARDMARKET_PRODUCTS[id];
  if(!rule)return null;
  const setId=String(card?.set?.id||card?.setId||'').trim();
  const local=exactLocalIdKey(card?.localId||card?.local_id||'');
  const name=normText(card?.name||'');
  if(setId!=='2021swsh'||local!==rule.localId||name!==normText(rule.name)){
    return {handled:true,matched:false,kind:'identity-mismatch'};
  }
  const v=canonicalVariant(variant||'Normal');
  if(v!=='Normal'&&v!=='Holo')return {handled:true,matched:false,kind:'needs-exact-variant'};
  const pricing=v==='Holo'?rule.holo:rule.normal;
  return {handled:true,matched:true,variant:v,pricing,productId:pricing.idProduct,
    source:"Cardmarket · McDonald's Collection 2021 · prodotto esatto per finitura"};
}
"""
s=s.replace(anchor,registry+anchor,1)
old=anchor+"  const baseOverride=verifiedBaseCardmarketProductOverride(card);\n"
new=anchor+"  const mcd=verifiedMcdonalds2021CardmarketVariant(card,variant);\n  if(mcd?.handled){\n    if(!mcd.matched)return {value:0,kind:mcd.kind||'needs-exact-variant'};\n    const value=Number(mcd.pricing?.trend||0);\n    return {value:Number.isFinite(value)&&value>0?value:0,kind:'exact-mcdonalds-2021',productId:mcd.productId,source:mcd.source};\n  }\n  const baseOverride=verifiedBaseCardmarketProductOverride(card);\n"
if old not in s: raise SystemExit('cardmarket value insertion anchor missing')
s=s.replace(old,new,1)
stats_anchor='function cardmarketStatsForCardVariant(card,variant){\n'
stats_old=stats_anchor+"  const baseOverride=verifiedBaseCardmarketProductOverride(card);\n"
stats_new=stats_anchor+"  const mcd=verifiedMcdonalds2021CardmarketVariant(card,variant);\n  if(mcd?.handled){\n    if(!mcd.matched)return {low:null,trend:null,avg7:null,avg30:null};\n    const p=mcd.pricing||{};\n    return {low:p.low??null,trend:p.trend??null,avg7:p.avg7??null,avg30:p.avg30??null};\n  }\n  const baseOverride=verifiedBaseCardmarketProductOverride(card);\n"
if stats_old not in s: raise SystemExit('cardmarket stats insertion anchor missing')
s=s.replace(stats_old,stats_new,1)
INDEX.write_text(s,encoding='utf-8')

s=AUDIT.read_text(encoding='utf-8')
const_anchor='PROTECTED_REVERSE = '
idx=s.find(const_anchor)
if idx<0: raise SystemExit('audit constants anchor missing')
const_lines=['MCDONALDS_2021_EXACT_PAIRS = {']
for num,name,np,ns,hp,hs in ROWS:
    const_lines.append(f'    "2021swsh-{num}": {{"localId": "{num}", "name": {json.dumps(name)}, "normal": {np}, "holo": {hp}}},')
const_lines.append('}\n')
s=s[:idx]+'\n'.join(const_lines)+s[idx:]

class_anchor='        elif live_ex5_beldum_gym_pair:\n'
condition='''        elif card_id in MCDONALDS_2021_EXACT_PAIRS:
            rule = MCDONALDS_2021_EXACT_PAIRS[card_id]
            pn, ph = products.get(rule["normal"]), products.get(rule["holo"])
            gn, gh = prices.get(rule["normal"]), prices.get(rule["holo"])
            same_meta = bool(pn and ph and pn.get("idExpansion") == 3738 and ph.get("idExpansion") == 3738 and
                             pn.get("idMetacard") == ph.get("idMetacard") and pn.get("idMetacard") is not None)
            exact_names = bool(pn and ph and str(pn.get("name") or "").split(" [",1)[0] == rule["name"] and
                               str(ph.get("name") or "").split(" [",1)[0] == rule["name"])
            priced = bool(gn and gh and isinstance(gn.get("trend"),(int,float)) and gn.get("trend") > 0 and
                          isinstance(gh.get("trend"),(int,float)) and gh.get("trend") > 0)
            if same_meta and exact_names and priced:
                classification, priority, confidence = "EXACT_ALTERNATE_PRODUCT", "P2", "HIGH"
                resolved_pid = rule["normal"]
                resolved_value = gn.get("trend")
                reason = ("McDonald's Collection 2021 ha prodotti Cardmarket Normal/Holo distinti, verificati "
                          "sullo stesso metacard ufficiale; Cardoryx li risolve per identità e finitura esatte.")
                action = "Mantenere la tabella esatta 25 carte; nessuna formula productId e nessun fallback tra finiture."
            else:
                classification, priority, confidence = "P1_AMBIGUOUS_PRODUCT", "P1", "LOW"
                reason = "La coppia McDonald's 2021 non supera più i controlli catalogo/metacard/prezzo ufficiali."
                action = "Fail-closed e nuova verifica del catalogo Cardmarket."
'''
if class_anchor not in s: raise SystemExit('audit classification anchor missing')
s=s.replace(class_anchor,condition+class_anchor,1)
AUDIT.write_text(s,encoding='utf-8')
print('McDonalds 2021 exact 25-pair patch applied')
