#!/usr/bin/env python3
from pathlib import Path

p = Path('index.html')
s = p.read_text(encoding='utf-8')
marker = 'function tcgdexExactSvpStampPrice(card,variant,stamp)'
if marker in s:
    print('SVP set-logo/staff candidate already applied')
    raise SystemExit(0)

old = """function stampEvidenceFromTCGdex(card,stamp){
  const st=canonicalStamp(stamp);
  const list=tcgdexVariantDetails(card);
  const tokens={
"""
new = """function stampEvidenceFromTCGdex(card,stamp){
  const st=canonicalStamp(stamp);
  const list=tcgdexVariantDetails(card);
  // TCGdex uses the exact `set-logo` taxonomy for set-logo promos.  Staff
  // copies also carry `set-logo`, so a plain Set Stamp must explicitly exclude
  // rows that also carry `staff`.  If this taxonomy is absent, preserve the
  // older lexical aliases below.
  if(st==='Set Stamp'){
    const setLogoRows=list.filter(x=>(Array.isArray(x?.stamp)?x.stamp:[]).map(normText).includes('setlogo'));
    if(setLogoRows.length){
      return setLogoRows.some(x=>!(Array.isArray(x?.stamp)?x.stamp:[]).map(normText).includes('staff'));
    }
  }
  const tokens={
"""
if old not in s:
    raise SystemExit('stampEvidenceFromTCGdex anchor not found')
s = s.replace(old, new, 1)

anchor = """function verifiedStampPrice(card,variant,stamp){
  const exact=verifiedExactSpecialStampPrice(card,variant,stamp);
  if(exact)return exact;
"""
insert = """function tcgdexStampedRowFinish(row){
  const type=canonicalFinishTypeLabel(row?.type);
  const foil=canonicalFinishFoilLabel(row?.foil);
  if(type==='reverse'&&foil==='pokeball')return 'Poké Ball Reverse Holo';
  if(type==='reverse'&&foil==='masterball')return 'Master Ball Reverse Holo';
  if(type==='holo'&&foil==='cosmos')return 'Cosmos Holo';
  if(type==='normal'&&!foil)return 'Normal';
  if(type==='holo'&&!foil)return 'Holo';
  if(type==='reverse'&&!foil)return 'Reverse Holo';
  return '';
}

// Exact live Cardmarket resolver for the verified Scarlet & Violet Promo
// set-logo taxonomy.  Scope is deliberately limited to `svp`: no other set,
// no Worlds/region stamp, no base-card fallback and no cross-stamp price reuse.
function tcgdexExactSvpStampPrice(card,variant,stamp){
  const setId=normText(card?.set?.id||card?._cardoryxSetId||card?.setId||'');
  if(setId!=='svp')return null;
  const st=canonicalStamp(stamp);
  if(st!=='Set Stamp'&&st!=='Staff')return null;
  const target=canonicalVariant(variant||'Normal');
  const rows=tcgdexVariantDetails(card).filter(x=>{
    if(Array.isArray(x?.languages)&&x.languages.length&&!x.languages.includes('it'))return false;
    const stamps=(Array.isArray(x?.stamp)?x.stamp:[]).map(normText);
    const exactStamp=st==='Set Stamp'
      ? stamps.includes('setlogo')&&!stamps.includes('staff')
      : stamps.includes('setlogo')&&stamps.includes('staff');
    return exactStamp&&tcgdexStampedRowFinish(x)===target;
  });
  if(rows.length!==1)return null;
  const row=rows[0];
  const productId=Number(row?.thirdParty?.cardmarket||0);
  const cm=row?.pricing?.cardmarket;
  const pricingProductId=Number(cm?.idProduct||cm?.id_product||0);
  if(!(productId>0)||!cm||pricingProductId!==productId)return null;
  const hasRealPrice=['trend','avg7','avg30','avg','low'].some(k=>Number(cm?.[k])>0);
  if(!hasRealPrice)return null;
  return {...cm,idProduct:productId,source:`TCGdex · Cardmarket · ${st}`,verified:String(cm?.updated||'')};
}

function verifiedStampPrice(card,variant,stamp){
  const exact=verifiedExactSpecialStampPrice(card,variant,stamp);
  if(exact)return exact;
  const tcgdexExact=tcgdexExactSvpStampPrice(card,variant,stamp);
  if(tcgdexExact)return tcgdexExact;
"""
if anchor not in s:
    raise SystemExit('verifiedStampPrice anchor not found')
s = s.replace(anchor, insert, 1)

p.write_text(s, encoding='utf-8')
print('patched index.html')
