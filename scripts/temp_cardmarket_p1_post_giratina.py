#!/usr/bin/env python3
from pathlib import Path

path = Path('scripts/test_card_identity_cardmarket_audit.py')
text = path.read_text(encoding='utf-8')
needle = '    over, under = [], []\n'
insert = r'''    import re as _re
    excluded_prefixes = ('base', 'gym', 'neo')
    excluded_exact = {
        'sv09-055','me01-073','ex8-16','sv05-041','sv10.5b-065','swshp-SWSH055',
        'pl3-70','sv10.5b-027','sv10.5b-014','swsh11-201'
    }
    def _nm(v):
        return _re.sub(r'[^a-z0-9]+','',str(v or '').lower())
    ranked=[]
    for c in p1:
        cid=str(c.get('tcgdexId') or '')
        if cid.startswith(excluded_prefixes) or cid in excluded_exact:
            continue
        pid=c.get('currentProductId')
        cat=(c.get('cardmarketProductCatalog') or {}).get(str(pid)) or {}
        pname=str(cat.get('name') or '')
        base_name=pname.split(' [',1)[0].strip()
        card_name=str(c.get('name') or '')
        n_card=_nm(card_name)
        n_prod=_nm(base_name)
        mismatch=bool(n_card and n_prod and n_card not in n_prod and n_prod not in n_card)
        ranked.append({
            'tcgdexId':cid,'setId':c.get('setId'),'localId':c.get('localId'),'name':card_name,
            'currentProductId':pid,'currentProductName':pname,'nameMismatch':mismatch,
            'shared':c.get('sharedProductWithTcgdexIds') or [],
            'baseRows':c.get('baseRowProductIdsAccordingToTcgdex') or [],
            'allProductIds':c.get('allProductIds') or [],
            'alternateProducts':{
                str(apid):(c.get('cardmarketProductCatalog') or {}).get(str(apid))
                for apid in (c.get('alternateProductIds') or [])
            },
            'currentValue':c.get('currentCardoryxValue'),
            'reason':c.get('reason'),
        })
    ranked.sort(key=lambda x:(not x['nameMismatch'], -len(x['shared']), x['tcgdexId']))
    print('P1_POST_GIRATINA_COUNT ' + str(len(ranked)))
    print('P1_NAME_MISMATCH ' + json.dumps([x for x in ranked if x['nameMismatch']], ensure_ascii=False, sort_keys=True))
    print('P1_RANKED_TOP40 ' + json.dumps(ranked[:40], ensure_ascii=False, sort_keys=True))

    over, under = [], []
'''
if needle not in text:
    raise SystemExit('audit anchor missing')
path.write_text(text.replace(needle, insert, 1), encoding='utf-8')
print('post-Giratina P1 diagnostic injection applied')
