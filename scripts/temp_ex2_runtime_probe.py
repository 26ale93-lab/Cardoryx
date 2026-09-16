#!/usr/bin/env python3
from __future__ import annotations
import importlib.util, json, subprocess, sys, urllib.parse, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'
API='https://api.tcgdex.net/v2/en/cards'
IDS=['ex2-2','ex2-12','ex2-22','ex2-45','ex2-1']

def get_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Cardoryx-EX2-Runtime-Probe/1.0'})
    with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)

def load_snapshot(db):
    sys.dont_write_bytecode=True
    spec=importlib.util.spec_from_file_location('vf',ROOT/'scripts'/'test_variant_finish_audit.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    return mod.load_official_database(db)

def compact(card):
    return {
      'id':card.get('id'),'name':card.get('name'),'localId':card.get('localId'),
      'topCardmarket':((card.get('pricing') or {}).get('cardmarket')),
      'variants':[{
        'type':r.get('type'),'subtype':r.get('subtype'),'foil':r.get('foil'),'stamp':r.get('stamp'),
        'thirdParty':r.get('thirdParty'),'pricingCardmarket':((r.get('pricing') or {}).get('cardmarket'))
      } for r in (card.get('variants_detailed') or [])]
    }

def runtime(cards):
    js=r'''
const fs=require('fs'),vm=require('vm');
const source=fs.readFileSync(process.argv[1],'utf8');
const cards=JSON.parse(process.argv[2]);
function section(start,end){const a=source.indexOf(start),b=source.indexOf(end,a+start.length);if(a<0||b<a)throw new Error('missing '+start);return source.slice(a,b)}
const code=[
 section('function normText(','function similarity('),
 section('function canonicalPrintedLocalId(','function extractCollectorCode('),
 section('function normalizedPlaySeries(','function playSeriesLabel('),
 section('function canonicalStamp(','function scanUnit('),
 section('function cardPriceInfo(','function cardUnitPrice(')
].join('\n');
const context={console};vm.createContext(context);vm.runInContext(code+';globalThis.r={resolvedCardmarketPricingForCard,cardmarketValueForCardVariant,cardmarketStatsForCardVariant};',context);
const out={};for(const c of cards){out[c.id]={resolved:context.r.resolvedCardmarketPricingForCard(c),normal:context.r.cardmarketValueForCardVariant(c,'Normal'),holo:context.r.cardmarketValueForCardVariant(c,'Holo'),reverse:context.r.cardmarketValueForCardVariant(c,'Reverse Holo')}}
process.stdout.write(JSON.stringify(out));
'''
    return json.loads(subprocess.check_output(['node','-e',js,str(INDEX),json.dumps(cards)],text=True))

def main():
    if len(sys.argv)!=2:raise SystemExit('usage: temp_ex2_runtime_probe.py <tcgdex-db>')
    cards,_,snapshot=load_snapshot(Path(sys.argv[1]));byid={c['id']:c for c in cards}
    snap={cid:compact(byid[cid]) for cid in IDS}
    live={cid:compact(get_json(f'{API}/{urllib.parse.quote(cid)}')) for cid in IDS}
    live_cards=[get_json(f'{API}/{urllib.parse.quote(cid)}') for cid in IDS]
    report={'snapshot':snapshot,'snapshotRows':snap,'liveRows':live,'currentRuntime':runtime(live_cards)}
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
