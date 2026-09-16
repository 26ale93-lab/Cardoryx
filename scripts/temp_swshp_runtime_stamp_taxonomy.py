#!/usr/bin/env python3
from __future__ import annotations
import json,re,subprocess,urllib.request
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; INDEX=ROOT/'index.html'; OUT=ROOT/'artifacts'/'swshp_runtime_stamp_taxonomy_report.json'

def extract_fn(src,name):
 m=re.search(rf'\bfunction\s+{re.escape(name)}\s*\(',src)
 if not m:return None
 b=src.find('{',m.end()); depth=0; quote=None; esc=False
 for i in range(b,len(src)):
  ch=src[i]
  if quote:
   if esc: esc=False
   elif ch=='\\': esc=True
   elif ch==quote: quote=None
   continue
  if ch in ("'",'"','`'): quote=ch
  elif ch=='{': depth+=1
  elif ch=='}':
   depth-=1
   if depth==0:return src[m.start():i+1]
 return None

def live_card(cid):
 req=urllib.request.Request(f'https://api.tcgdex.net/v2/en/cards/{cid}',headers={'User-Agent':'Cardoryx-SWSHP-Taxonomy-Audit/1.2'})
 with urllib.request.urlopen(req,timeout=20) as r:return json.loads(r.read().decode('utf-8'))

def main():
 src=INDEX.read_text(encoding='utf-8')
 exec_names=['normText','canonicalStamp','tcgdexVariantDetails','stampEvidenceFromTCGdex']
 js='\n'.join(extract_fn(src,n) for n in exec_names)
 vals=['eb-games','EB Games','gamestop','GameStop','25th-celebration','25th Celebration','worlds-2022','Worlds 2022','staff','Staff','Set Stamp']
 canon_harness="const xs=JSON.parse(process.argv[1]);process.stdout.write(JSON.stringify(Object.fromEntries(xs.map(x=>[x,canonicalStamp(x)]))))"
 canon=json.loads(subprocess.check_output(['node','-e',js+'\n'+canon_harness,json.dumps(vals)],text=True))
 card=live_card('swshp-SWSH028')
 evidence_harness=r'''
const c=JSON.parse(process.argv[1]);
process.stdout.write(JSON.stringify({
  gameStop:stampEvidenceFromTCGdex(c,'GameStop'),
  ebGames:stampEvidenceFromTCGdex(c,'EB Games'),
  staff:stampEvidenceFromTCGdex(c,'Staff'),
  rows:tcgdexVariantDetails(c).map(r=>({stamp:r.stamp,pid:r?.thirdParty?.cardmarket,pricingPid:r?.pricing?.cardmarket?.idProduct,trend:r?.pricing?.cardmarket?.trend,low:r?.pricing?.cardmarket?.low}))
}));
'''
 evidence=json.loads(subprocess.check_output(['node','-e',js+'\n'+evidence_harness,json.dumps(card)],text=True))
 inspect_names=exec_names+['verifiedStampPrice','verifiedExactSpecialStampPrice','tcgdexExactSvpStampPrice','tcgdexMarketplaceVariant','staticProductToPrice']
 snippets={n:extract_fn(src,n) for n in inspect_names if extract_fn(src,n)}
 report={'canonicalStamp':canon,'swshpSWSH028Evidence':evidence,'sourceSnippets':snippets}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
