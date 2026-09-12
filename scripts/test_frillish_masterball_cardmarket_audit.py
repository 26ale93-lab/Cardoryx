#!/usr/bin/env python3
"""READ-ONLY audit for Frillish 044/086 Master Ball Reverse Cardmarket runtime mapping."""
import json
import re
import urllib.request
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
INDEX=ROOT/'index.html'


def get_json(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Cardoryx-audit/1.0'})
    with urllib.request.urlopen(req,timeout=20) as r:
        return json.load(r)


def main():
    src=INDEX.read_text(encoding='utf-8')
    print('INDEX_LEN',len(src))
    for marker in ['870424','407919','398524','VERIFIED','Cardmarket','cardmarket','productId','Master Ball']:
        print('\n=== MARKER',marker,'===')
        for m in list(re.finditer(re.escape(marker),src,re.I))[:12]:
            a=max(0,m.start()-700); b=min(len(src),m.end()+1200)
            print(src[a:b].replace('\n','\\n'))
            print('---')

    # Probe TCGdex search endpoints conservatively.
    urls=[
      'https://api.tcgdex.net/v2/it/cards?name=Frillish',
      'https://api.tcgdex.net/v2/en/cards?name=Frillish',
      'https://api.tcgdex.net/v2/it/cards?localId=44',
    ]
    for u in urls:
        print('\nURL',u)
        try:
            data=get_json(u)
            if isinstance(data,list):
                rows=[x for x in data if str(x.get('name','')).lower()=='frillish']
                print(json.dumps(rows[:30],ensure_ascii=False)[:12000])
            else:
                print(json.dumps(data,ensure_ascii=False)[:12000])
        except Exception as e:
            print('ERR',repr(e))

    # Candidate details guessed from returned/search IDs if available by scanning search response isn't enough here.

if __name__=='__main__':
    main()
