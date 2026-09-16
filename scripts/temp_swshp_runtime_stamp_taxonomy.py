#!/usr/bin/env python3
from __future__ import annotations
import json,re,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]; INDEX=ROOT/'index.html'; OUT=ROOT/'artifacts'/'swshp_runtime_stamp_taxonomy_report.json'

def extract_fn(src,name):
 m=re.search(rf'\bfunction\s+{re.escape(name)}\s*\(',src)
 if not m: raise SystemExit(f'missing {name}')
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
 raise SystemExit(f'unclosed {name}')

def main():
 src=INDEX.read_text(encoding='utf-8')
 names=['normText','canonicalStamp']
 js='\n'.join(extract_fn(src,n) for n in names)
 vals=['eb-games','EB Games','gamestop','GameStop','25th-celebration','25th Celebration','worlds-2022','Worlds 2022','staff','Staff','Set Stamp']
 harness="const xs=JSON.parse(process.argv[1]);process.stdout.write(JSON.stringify(Object.fromEntries(xs.map(x=>[x,canonicalStamp(x)]))))"
 out=json.loads(subprocess.check_output(['node','-e',js+'\n'+harness,json.dumps(vals)],text=True))
 report={'canonicalStamp':out,'sourceSnippets':{n:extract_fn(src,n) for n in names}}
 OUT.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps(report,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
