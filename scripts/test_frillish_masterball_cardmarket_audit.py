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
    for marker in ['VERIFIED_EXACT_CARDMARKET_PRICE_GUIDES','cardmarketValueForCardVariant','cardmarketStatsForCardVariant','isBallReverseVariant']:
        print('\n=== MARKER',marker,'===')
        m=re.search(re.escape(marker),src,re.I)
        if m:
            a=max(0,m.start()-1200); b=min(len(src),m.end()+5000)
            print(src[a:b].replace('\n','\\n'))

    urls=[
      'https://api.tcgdex.net/v2/it/cards/sv10.5w-044',
      'https://api.tcgdex.net/v2/en/cards/sv10.5w-044',
    ]
    for u in urls:
        print('\nDETAIL',u)
        try:
            data=get_json(u)
            print(json.dumps(data,ensure_ascii=False)[:30000])
        except Exception as e:
            print('ERR',repr(e))

if __name__=='__main__':
    main()
