#!/usr/bin/env python3
from __future__ import annotations
import json, re, subprocess, urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'
API='https://api.tcgdex.net/v2/en/cards'

def fetch_card(cid):
    req=urllib.request.Request(f'{API}/{cid}',headers={'User-Agent':'Cardoryx-read-only-audit/1.0'})
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.load(r)

def extract_fn(src,name):
    m=re.search(rf'\bfunction\s+{re.escape(name)}\s*\(',src)
    if not m: raise AssertionError(f'missing function {name}')
    brace=src.find('{',m.start())
    if brace<0: raise AssertionError(f'missing body {name}')
    depth=0; quote=None; esc=False; template_depth=0
    for i in range(brace,len(src)):
        c=src[i]
        if quote:
            if esc: esc=False
            elif c=='\\': esc=True
            elif c==quote: quote=None
            continue
        if c in "'\"`": quote=c; continue
        if c=='{': depth+=1
        elif c=='}':
            depth-=1
            if depth==0: return src[m.start():i+1]
    raise AssertionError(f'unclosed function {name}')

def main():
    src=INDEX.read_text(encoding='utf-8')
    required=['normText','canonicalVariant','canonicalStamp','canonicalFinishTypeLabel','canonicalFinishFoilLabel',
              'tcgdexVariantDetails','stampEvidenceFromTCGdex','tcgdexStampedRowFinish','tcgdexExactSvpStampPrice']
    js='\n'.join(extract_fn(src,n) for n in required)
    fixtures={cid:fetch_card(cid) for cid in ['svp-005','svp-006','svp-007','svp-045','svp-067','svp-101','svp-150']}
    harness=r'''
const fixtures=JSON.parse(process.argv[1]);
function fail(m){throw new Error(m)}
function stamps(r){return (Array.isArray(r?.stamp)?r.stamp:[]).map(normText)}
const checked={};
for(const id of ['svp-005','svp-006','svp-007']){
  const c=fixtures[id], rows=tcgdexVariantDetails(c);
  const setRow=rows.find(r=>stamps(r).includes('setlogo')&&!stamps(r).includes('staff'));
  const staffRow=rows.find(r=>stamps(r).includes('setlogo')&&stamps(r).includes('staff'));
  if(!setRow||!staffRow)fail(id+' missing exact source pair');
  const setFinish=tcgdexStampedRowFinish(setRow), staffFinish=tcgdexStampedRowFinish(staffRow);
  if(!setFinish||!staffFinish)fail(id+' unsupported physical finish');
  const setPrice=tcgdexExactSvpStampPrice(c,setFinish,'Set Stamp');
  const staffPrice=tcgdexExactSvpStampPrice(c,staffFinish,'Staff');
  const setPid=Number(setRow?.thirdParty?.cardmarket||0), staffPid=Number(staffRow?.thirdParty?.cardmarket||0);
  if(!setPrice||Number(setPrice.idProduct)!==setPid)fail(id+' Set Stamp product mismatch');
  if(!staffPrice||Number(staffPrice.idProduct)!==staffPid)fail(id+' Staff product mismatch');
  if(setPid===staffPid)fail(id+' products are not physically distinct');
  if(!stampEvidenceFromTCGdex(c,'Set Stamp'))fail(id+' Set Stamp unavailable');
  if(!stampEvidenceFromTCGdex(c,'Staff'))fail(id+' Staff unavailable');
  const staffOnly={...c,variants_detailed:[staffRow]};
  if(stampEvidenceFromTCGdex(staffOnly,'Set Stamp'))fail(id+' Staff leaked into Set Stamp');
  if(!stampEvidenceFromTCGdex(staffOnly,'Staff'))fail(id+' Staff evidence lost');
  checked[id]={setFinish,staffFinish,setPid,staffPid};
}
for(const id of ['svp-045','svp-150']){
  const c=fixtures[id];
  if(tcgdexExactSvpStampPrice(c,'Holo','Staff')!==null && !tcgdexVariantDetails(c).some(r=>stamps(r).includes('setlogo')&&stamps(r).includes('staff')))fail(id+' non-set-logo Staff was auto-priced');
}
for(const id of ['svp-067','svp-101']){
  const c=fixtures[id];
  for(const finish of ['Normal','Holo','Reverse Holo','Cosmos Holo']){
    if(tcgdexExactSvpStampPrice(c,finish,'Set Stamp')!==null)fail(id+' unexpected Set Stamp price');
    if(tcgdexExactSvpStampPrice(c,finish,'Staff')!==null)fail(id+' unexpected Staff price');
  }
}
const foreign={...fixtures['svp-005'],set:{...(fixtures['svp-005'].set||{}),id:'sv01'}};
if(tcgdexExactSvpStampPrice(foreign,'Holo','Set Stamp')!==null)fail('set scope leaked outside svp');
process.stdout.write(JSON.stringify({checked,failClosed:['svp-045','svp-067','svp-101','svp-150'],setScopeRejected:true}));
'''
    out=json.loads(subprocess.check_output(['node','-e',js+'\n'+harness,json.dumps(fixtures,ensure_ascii=False)],text=True))
    # Binding/order check: verified static stamps retain precedence over dynamic TCGdex evidence.
    needle='const tcgdexExact=tcgdexExactSvpStampPrice(card,variant,stamp);'
    if needle not in src: raise AssertionError('verifiedStampPrice does not consume exact SVP stamp resolver')
    block=extract_fn(src,'verifiedStampPrice')
    if block.find('verifiedExactSpecialStampPrice')>block.find('tcgdexExactSvpStampPrice'):
        raise AssertionError('dynamic SVP resolver precedes existing static exact registry')
    print(json.dumps(out,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
