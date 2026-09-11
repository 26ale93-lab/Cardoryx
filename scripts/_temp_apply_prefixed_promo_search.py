#!/usr/bin/env python3
from pathlib import Path

index = Path('index.html')
source = index.read_text(encoding='utf-8')

if 'function manualPrefixedPromoCodeParts' in source:
    raise SystemExit('manualPrefixedPromoCodeParts already present')

old_help = '<div class="small">Cerca con <b>Numero + Totale set</b>, con <b>Numero + Nome esatto</b>, oppure esplora il catalogo inserendo soltanto il <b>Nome carta</b>.</div>'
new_help = '<div class="small">Cerca con <b>Numero + Totale set</b>, con <b>Numero + Nome esatto</b>, con un <b>codice promo completo</b> (es. MEP 091), oppure esplora il catalogo inserendo soltanto il <b>Nome carta</b>.</div>'
if old_help not in source:
    raise SystemExit('manual search help marker missing')
source = source.replace(old_help, new_help, 1)
source = source.replace('placeholder="146, TG01, SVP001"', 'placeholder="146, TG01, MEP 091, SVP001"', 1)

marker = 'async function queryManualCardsByExactLocalId(value,allowedIds=null){'
if marker not in source:
    raise SystemExit('queryManualCardsByExactLocalId marker missing')
helper = r'''function manualPrefixedPromoCodeParts(value=''){
  const raw=canonicalPrintedLocalId(value);
  const match=raw.match(/^([A-Z]{2,5})0*(\d{1,3})$/);
  if(!match)return null;
  const prefix=match[1].toUpperCase();
  const number=String(Number(match[2]));
  if(!number || number==='0')return null;
  return {prefix,number,display:`${prefix} ${number.padStart(3,'0')}`,setId:prefix.toLowerCase()};
}

// Exact externally verified promo identities used only when TCGdex has not yet
// published the card. No Cardmarket price is attached and no prefix-wide rule is inferred.
const VERIFIED_MANUAL_PROMO_IDENTITIES = {
  'MEP 091':{
    name:'Mega Dragonite ex',localId:'091',setId:'mep',setName:'Promozioni MEP',finish:'Holo',
    source:'Pokémon ufficiale · MEP 091; finitura Holo verificata da catalogo promo indipendente',
    sourceUrl:'https://www.pokemon.com/it/play-pokemon/info/entrata-in-vigore-delle-carte-promozionali-del-gcc-pokemon',
    verified:'2026-09-11'
  }
};
function verifiedManualPromoFallback(code){
  const key=String(code?.display||'').trim().toUpperCase();
  const row=VERIFIED_MANUAL_PROMO_IDENTITIES[key];
  if(!row || row.setId!==code?.setId || String(Number(row.localId))!==String(Number(code?.number)))return null;
  return {
    id:`verified-promo-${row.setId}-${row.localId}`,
    tcgdexId:'',name:row.name,localId:row.localId,number:row.localId,
    category:'Pokemon',rarity:'Promo',variants:{holo:true},
    variants_detailed:[{type:'holo',languages:['it']}],
    set:{id:row.setId,name:row.setName},
    _cardoryxLocal:true,_cardoryxVerifiedPromo:true,_printedCode:key,
    _verifiedPromoSource:row.source,_verifiedPromoSourceUrl:row.sourceUrl,_verifiedPromoAt:row.verified
  };
}

async function queryManualCardsByPrefixedPromoCode(value){
  const code=manualPrefixedPromoCodeParts(value);
  if(!code)return [];
  const cards=await queryManualCardsByExactLocalId(code.number);
  const live=(cards||[]).filter(card=>{
    const setId=cardSetId(card);
    const id=String(card?.id||card?.tcgdexId||'').trim().toLowerCase();
    return setId===code.setId || id.startsWith(`${code.setId}-`);
  });
  if(live.length)return live;
  const fallback=verifiedManualPromoFallback(code);
  return fallback?[fallback]:[];
}

'''
source = source.replace(marker, helper + marker, 1)

old_preamble = """  const num=canonicalPrintedLocalId(numberInput.value||'');\n  const total=String(setTotalInput.value||'').replace(/\\D/g,'');\n  const requestedName=String(nameInput.value||'').trim();\n"""
new_preamble = old_preamble + "  const prefixedPromo=manualPrefixedPromoCodeParts(num);\n"
if old_preamble not in source:
    raise SystemExit('manual search preamble marker missing')
source = source.replace(old_preamble, new_preamble, 1)

old_block = """  if(num&&!total&&!requestedName){\n    searchMsg.textContent='Il solo numero è troppo ambiguo. Aggiungi Nome carta oppure Totale set.';\n    return;\n  }\n"""
new_block = """  if(num&&!total&&!requestedName&&!prefixedPromo){\n    searchMsg.textContent='Il solo numero è troppo ambiguo. Aggiungi Nome carta, Totale set oppure usa un codice promo completo (es. MEP 091).';\n    return;\n  }\n"""
if old_block not in source:
    raise SystemExit('naked number fail-closed block missing')
source = source.replace(old_block, new_block, 1)

route_marker = """  try{\n    if(requestedName&&!num&&!total){\n"""
route = r'''  try{
    if(prefixedPromo&&!total&&!requestedName){
      searchMsg.textContent=`Verifico codice promo ${prefixedPromo.display}…`;
      const cards=await queryManualCardsByPrefixedPromoCode(num);
      if(!cards.length){
        searchMsg.textContent=`Nessuna carta trovata per il codice ${prefixedPromo.display}. Controlla prefisso e numero.`;
        return;
      }
      if(cards.length===1){
        const card=cards[0];
        searchMsg.textContent=`✓ ${card.name} · ${prefixedPromo.display}`;
        await chooseCard(card);
        return;
      }
      startManualCandidatePagination(
        cards,
        'Codice promo completo',
        `${cards.length} identità condividono il codice ${prefixedPromo.display}. Scegli manualmente.`
      );
      return;
    }

    if(requestedName&&!num&&!total){
'''
if route_marker not in source:
    raise SystemExit('manual search route marker missing')
source = source.replace(route_marker, route, 1)

index.write_text(source, encoding='utf-8')
print('Patch prepared')
