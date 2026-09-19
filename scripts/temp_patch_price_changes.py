#!/usr/bin/env python3
from pathlib import Path

p=Path(__file__).resolve().parents[1]/"index.html"
s=p.read_text(encoding="utf-8")

css_anchor=".collection-card h3{font-size:18px;line-height:1.1;margin:2px 0 5px}"
css_insert=""".price-change-panel{margin-top:12px}
.price-change-head{display:flex;align-items:flex-start;justify-content:space-between;gap:10px;margin-bottom:10px}
.price-change-summary{display:grid;grid-template-columns:repeat(3,1fr);gap:7px;margin:10px 0}
.price-change-stat{background:#f8fafc;border:1px solid #e5e7eb;border-radius:13px;padding:9px;text-align:center}
.price-change-stat strong{display:block;font-size:16px}.price-change-stat span{font-size:10px;color:#6b7280}
.price-change-list{display:grid;gap:9px}
.price-change-row{display:grid;grid-template-columns:56px minmax(0,1fr);gap:10px;align-items:center;border:1px solid #e5e7eb;border-radius:15px;padding:9px;background:#fff;cursor:pointer}
.price-change-row img{width:56px;height:78px;object-fit:contain;border-radius:8px;background:#f3f4f6}
.price-change-name{font-weight:900;font-size:14px;line-height:1.15}
.price-change-meta{font-size:10px;color:#6b7280;margin-top:2px}
.price-change-values{font-size:12px;font-weight:800;margin-top:5px}
.price-change-delta{font-size:12px;font-weight:900;margin-top:3px}
.price-change-up .price-change-delta{color:#15803d}
.price-change-down .price-change-delta{color:#b42318}
.price-change-new .price-change-delta{color:#2563eb}
.price-change-lost .price-change-delta{color:#6b7280}
"""+css_anchor
assert css_anchor in s
s=s.replace(css_anchor,css_insert,1)

html_old="""<div class="value-actions"><button class="btn green" type="button" onclick="refreshAllPrices()">↻ Aggiorna valori</button><button class="btn alt" type="button" onclick="showView('catalog')">📚 Vedi carte</button></div>
      <div id="priceRefreshStatus" class="footer-note"></div>
    </div>

    <div class="category-hero">"""
html_new="""<div class="value-actions"><button class="btn green" type="button" onclick="refreshAllPrices()">↻ Aggiorna valori</button><button id="priceChangesBtn" class="btn alt" type="button" onclick="showPriceChanges()">📈 Variazioni prezzo</button></div>
      <div id="priceRefreshStatus" class="footer-note"></div>
    </div>

    <div id="priceChangesPanel" class="card price-change-panel hidden">
      <div class="price-change-head">
        <div><div class="section-title">Variazioni ultimo aggiornamento</div><div id="priceChangesMeta" class="small">Aggiorna i valori per confrontare i prezzi Cardmarket.</div></div>
        <button class="btn alt" type="button" onclick="hidePriceChanges()">Chiudi</button>
      </div>
      <div id="priceChangesSummary"></div>
      <div id="priceChangesList" class="price-change-list"></div>
    </div>

    <div class="category-hero">"""
assert html_old in s
s=s.replace(html_old,html_new,1)

refresh_old="""async function refreshAllPrices(){
  const st=document.getElementById('priceRefreshStatus');let ok=0,done=0,noPrice=0;
  if(st)st.textContent='Associo le carte a TCGdex e aggiorno Cardmarket…';
  for(const c of db){done++;const got=await refreshPriceForRecord(c);if(got)ok++;else noPrice++;if(st)st.textContent=`Controllo ${done}/${db.length} · prezzi trovati ${ok}…`}
  if(!await persist()){if(st)st.textContent='Aggiornamento non salvato.';return}renderCatalog();renderStats();if(st)st.textContent=`Completato: ${ok} con prezzo · ${noPrice} senza prezzo su ${db.length}.`;
}"""
refresh_new=r"""let lastPriceRefreshReport=null;
function priceRefreshStableKey(c){
  return [
    normText(c?.name||''),normText(c?.set?.name||c?.set||''),String(c?.localId||'').trim().toLowerCase(),
    canonicalVariant(c?.variant||'Normal'),canonicalStamp(c?.stamp||'None'),
    normalizedPlaySeries(c?.playSeries||''),String(c?.condition||'NM').trim().toUpperCase()
  ].join('|||');
}
function priceRefreshSnapshot(){
  const out=new Map();
  for(const c of db||[]){
    const key=priceRefreshStableKey(c),qty=Math.max(1,Number(c?.qty)||1),value=cardPriceInfo(c).value;
    let row=out.get(key);
    if(!row){
      row={key,name:c?.name||'Carta',set:c?.set?.name||c?.set||'',localId:c?.localId||'',
        variant:canonicalVariant(c?.variant||'Normal'),stamp:canonicalStamp(c?.stamp||'None'),
        condition:c?.condition||'NM',qty:0,value:value==null?null:Number(value),recordKey:recordKey(c)};
      out.set(key,row);
    }
    row.qty+=qty;
    if(row.value==null && value!=null)row.value=Number(value);
  }
  return out;
}
function buildPriceRefreshReport(before,after){
  const changes=[];
  let totalBefore=0,totalAfter=0;
  for(const row of before.values())if(row.value!=null)totalBefore+=row.value*row.qty;
  for(const row of after.values())if(row.value!=null)totalAfter+=row.value*row.qty;
  for(const [key,newRow] of after){
    const oldRow=before.get(key);if(!oldRow)continue;
    const beforeValue=oldRow.value,afterValue=newRow.value,qty=newRow.qty;
    let kind='',delta=null,percent=null,totalDelta=null;
    if(beforeValue!=null&&afterValue!=null){
      delta=afterValue-beforeValue;
      if(Math.abs(delta)<0.000001)continue;
      kind=delta>0?'up':'down';
      percent=beforeValue>0?(delta/beforeValue)*100:null;
      totalDelta=delta*qty;
    }else if(beforeValue==null&&afterValue!=null){
      kind='new';totalDelta=afterValue*qty;
    }else if(beforeValue!=null&&afterValue==null){
      kind='lost';totalDelta=null;
    }else continue;
    changes.push({...newRow,beforeValue,afterValue,kind,delta,percent,totalDelta});
  }
  changes.sort((a,b)=>{
    const av=Math.abs(Number(a.totalDelta)||0),bv=Math.abs(Number(b.totalDelta)||0);
    if(bv!==av)return bv-av;
    return String(a.name).localeCompare(String(b.name),'it');
  });
  return {
    at:new Date().toISOString(),changes,totalBefore,totalAfter,net:totalAfter-totalBefore,
    up:changes.filter(x=>x.kind==='up').length,down:changes.filter(x=>x.kind==='down').length,
    newCount:changes.filter(x=>x.kind==='new').length,lost:changes.filter(x=>x.kind==='lost').length
  };
}
function renderPriceChanges(){
  const report=lastPriceRefreshReport,meta=document.getElementById('priceChangesMeta'),
    summary=document.getElementById('priceChangesSummary'),list=document.getElementById('priceChangesList'),
    btn=document.getElementById('priceChangesBtn');
  if(btn)btn.textContent=report?`📈 Variazioni (${report.changes.length})`:'📈 Variazioni prezzo';
  if(!meta||!summary||!list)return;
  if(!report){
    meta.textContent='Aggiorna i valori per confrontare i prezzi Cardmarket.';
    summary.innerHTML='';list.innerHTML='<div class="small">Nessun aggiornamento eseguito in questa sessione.</div>';return;
  }
  const when=new Date(report.at);
  meta.textContent=`Ultimo aggiornamento: ${when.toLocaleString('it-IT')} · confronto sul valore unitario Cardmarket.`;
  summary.innerHTML=`<div class="price-change-summary">
    <div class="price-change-stat"><strong>↑ ${report.up}</strong><span>AUMENTI</span></div>
    <div class="price-change-stat"><strong>↓ ${report.down}</strong><span>DIMINUZIONI</span></div>
    <div class="price-change-stat"><strong>${report.newCount+report.lost}</strong><span>NUOVI / PERSI</span></div>
  </div><div class="small">Impatto netto sull'ultimo aggiornamento: <b>${report.net>=0?'+':''}${euro(report.net)}</b>.</div>`;
  if(!report.changes.length){
    list.innerHTML='<div class="catalog-empty"><b>Nessuna variazione di prezzo</b><div class="small" style="margin-top:5px">I valori Cardmarket sono rimasti invariati rispetto a prima dell’aggiornamento.</div></div>';return;
  }
  list.innerHTML=report.changes.map(x=>{
    const current=[...db].find(c=>recordKey(c)===x.recordKey)||[...db].find(c=>priceRefreshStableKey(c)===x.key);
    const img=current?cardImageSrc(current,'low'):'';
    const values=x.kind==='new'?`Nuovo valore: ${euro(x.afterValue)}`
      :x.kind==='lost'?`Prima: ${euro(x.beforeValue)} · ora non disponibile`
      :`${euro(x.beforeValue)} → ${euro(x.afterValue)}`;
    const delta=x.kind==='new'?`Nuovo valore Cardmarket`
      :x.kind==='lost'?`Quotazione affidabile non disponibile`
      :`${x.delta>0?'↑ +':'↓ '}${euro(x.delta)} / copia${x.percent!=null?` · ${x.percent>0?'+':''}${x.percent.toFixed(1)}%`:''}${x.qty>1?` · impatto ${x.totalDelta>=0?'+':''}${euro(x.totalDelta)}`:''}`;
    const cls=x.kind==='up'?'price-change-up':x.kind==='down'?'price-change-down':x.kind==='new'?'price-change-new':'price-change-lost';
    const safe=current?encodeURIComponent(recordKey(current)):'';
    return `<div class="price-change-row ${cls}" ${safe?`onclick="openCardDetail('${safe}')"`:''}>
      <div>${img?`<img src="${esc(img)}" onerror="this.style.visibility='hidden'">`:'<div style="width:56px;height:78px"></div>'}</div>
      <div><div class="price-change-name">${esc(x.name)}</div><div class="price-change-meta">${esc(x.set||'Set sconosciuto')} · N° ${esc(x.localId||'—')} · ${esc(x.variant)} · ${esc(x.condition)}${x.qty>1?` · ×${x.qty}`:''}</div>
      <div class="price-change-values">${values}</div><div class="price-change-delta">${delta}</div></div>
    </div>`;
  }).join('');
}
function showPriceChanges(){
  const panel=document.getElementById('priceChangesPanel');if(!panel)return;
  renderPriceChanges();panel.classList.remove('hidden');
  setTimeout(()=>panel.scrollIntoView({behavior:'smooth',block:'start'}),20);
}
function hidePriceChanges(){document.getElementById('priceChangesPanel')?.classList.add('hidden')}
async function refreshAllPrices(){
  const st=document.getElementById('priceRefreshStatus');let ok=0,done=0,noPrice=0;
  const before=priceRefreshSnapshot();
  if(st)st.textContent='Associo le carte a TCGdex e aggiorno Cardmarket…';
  for(const c of db){done++;const got=await refreshPriceForRecord(c);if(got)ok++;else noPrice++;if(st)st.textContent=`Controllo ${done}/${db.length} · prezzi trovati ${ok}…`}
  const after=priceRefreshSnapshot();
  const report=buildPriceRefreshReport(before,after);
  if(!await persist()){if(st)st.textContent='Aggiornamento non salvato.';return}
  lastPriceRefreshReport=report;
  renderCatalog();renderStats();renderPriceChanges();
  if(st)st.textContent=`Completato: ${ok} con prezzo · ${noPrice} senza prezzo su ${db.length} · ${report.changes.length} variazioni.`;
}"""
assert refresh_old in s
s=s.replace(refresh_old,refresh_new,1)

stats_old="""function renderStats(){
  const cv=document.getElementById('collectionValue'),ci=document.getElementById('collectionValueInfo');if(cv)cv.textContent=euro(collectionMarketValue());if(ci)ci.textContent=`${pricedCopies()} carte valorizzate su ${catalogCopyCount()} · trend Cardmarket disponibile.`;"""
stats_new="""function renderStats(){
  const cv=document.getElementById('collectionValue'),ci=document.getElementById('collectionValueInfo');if(cv)cv.textContent=euro(collectionMarketValue());if(ci)ci.textContent=`${pricedCopies()} carte valorizzate su ${catalogCopyCount()} · trend Cardmarket disponibile.`;
  renderPriceChanges();"""
assert stats_old in s
s=s.replace(stats_old,stats_new,1)

p.write_text(s,encoding="utf-8")
print("patched")
