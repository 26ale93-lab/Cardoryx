#!/usr/bin/env python3
import json
import subprocess
from pathlib import Path

INDEX=Path(__file__).resolve().parents[1]/"index.html"
source=INDEX.read_text(encoding="utf-8")

def section(start,end):
    a=source.find(start)
    b=source.find(end,a+len(start))
    assert a>=0 and b>a, (start,end)
    return source[a:b]

build=section("function buildPriceRefreshReport(","function renderPriceChanges(")
stable=section("function priceRefreshStableKey(","function priceRefreshSnapshot(")

# Production UI / integration guards.
assert 'id="priceChangesBtn"' in source
assert 'onclick="showPriceChanges()"' in source
assert '📈 Variazioni prezzo' in source
assert 'id="priceChangesPanel"' in source
assert '📚 Vedi carte' not in source.split('<section id="statsView"',1)[1].split('<section id="decksView"',1)[0]
assert "const CARDORYX_PRICE_REFRESH_REPORT_KEY='price-refresh-report';" in source
assert "await idbWritePriceRefreshReport(report)" in source
assert "await idbReadPriceRefreshReport()" in source
assert "buildPriceRefreshReport(before,after,db.length)" in source
assert "Le variazioni con un valore mancante non entrano nei totali monetari." in source
assert ".price-change-stat{background:#f8fafc;border:1px solid #e5e7eb;border-radius:13px;padding:9px;text-align:center;color:#111827}" in source
assert ".price-change-stat strong{display:block;font-size:16px;color:#111827}" in source
assert "background:#fff;color:#111827;cursor:pointer" in source
assert ".price-change-name{font-weight:900;font-size:14px;line-height:1.15;color:#111827}" in source
assert ".price-change-values{font-size:12px;font-weight:800;margin-top:5px;color:#111827}" in source

js=f"""
const assert=require('assert');
function normText(v){{return String(v||'').normalize('NFD').replace(/[\\u0300-\\u036f]/g,'').toLowerCase().replace(/[^a-z0-9]+/g,' ').trim()}}
function canonicalVariant(v){{return String(v||'Normal')}}
function canonicalStamp(v){{return String(v||'None')}}
function normalizedPlaySeries(v){{return String(v||'')}}
{stable}
{build}

const ita={{name:'Pikachu',set:'Set X',localId:'001',variant:'Normal',stamp:'None',playSeries:'',language:'Italiano',condition:'NM'}};
const eng={{...ita,language:'English'}};
assert.notStrictEqual(priceRefreshStableKey(ita),priceRefreshStableKey(eng));

const before=new Map([
 ['up',{{key:'up',name:'A',qty:2,value:1.00}}],
 ['down',{{key:'down',name:'B',qty:3,value:2.00}}],
 ['new',{{key:'new',name:'C',qty:1,value:null}}],
 ['lost',{{key:'lost',name:'D',qty:1,value:5.00}}],
 ['same',{{key:'same',name:'E',qty:1,value:1.00}}],
]);
const after=new Map([
 ['up',{{key:'up',name:'A',qty:2,value:1.20}}],
 ['down',{{key:'down',name:'B',qty:3,value:1.50}}],
 ['new',{{key:'new',name:'C',qty:1,value:0.80}}],
 ['lost',{{key:'lost',name:'D',qty:1,value:null}}],
 ['same',{{key:'same',name:'E',qty:1,value:1.00}}],
]);
const r=buildPriceRefreshReport(before,after,5);
assert.strictEqual(r.checked,5);
assert.strictEqual(r.changes.length,4);
assert.strictEqual(r.up,1);
assert.strictEqual(r.down,1);
assert.strictEqual(r.newCount,1);
assert.strictEqual(r.lost,1);
const by=Object.fromEntries(r.changes.map(x=>[x.key,x]));

assert.strictEqual(by.up.kind,'up');
assert(Math.abs(by.up.delta-0.20)<1e-9);
assert(Math.abs(by.up.percent-20)<1e-9);
assert(Math.abs(by.up.totalDelta-0.40)<1e-9);

assert.strictEqual(by.down.kind,'down');
assert(Math.abs(by.down.delta+0.50)<1e-9);
assert(Math.abs(by.down.percent+25)<1e-9);
assert(Math.abs(by.down.totalDelta+1.50)<1e-9);

assert.strictEqual(by.new.kind,'new');
assert.strictEqual(by.new.delta,null);
assert.strictEqual(by.new.percent,null);
assert.strictEqual(by.new.totalDelta,null);

assert.strictEqual(by.lost.kind,'lost');
assert.strictEqual(by.lost.delta,null);
assert.strictEqual(by.lost.percent,null);
assert.strictEqual(by.lost.totalDelta,null);

assert(!by.same);
assert(Math.abs(r.increaseTotal-0.40)<1e-9);
assert(Math.abs(r.decreaseTotal-1.50)<1e-9);
assert(Math.abs(r.net+1.10)<1e-9);

console.log(JSON.stringify({{
  checked:r.checked,
  changes:r.changes.length,
  up:r.up,
  down:r.down,
  newCount:r.newCount,
  lost:r.lost,
  increaseTotal:r.increaseTotal,
  decreaseTotal:r.decreaseTotal,
  net:r.net,
  languageSeparated:true,
  nullValuesExcludedFromMoneyTotals:true
}}));
"""
out=subprocess.check_output(["node"],input=js,text=True)
print(out.strip())
