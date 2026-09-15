#!/usr/bin/env python3
"""READ-ONLY audit of official MEP 089-101 identities against Cardmarket product catalog/price guide.

This script never writes production data. It only prints candidate rows for manual verification.
"""
import json
import re
import unicodedata
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / 'index.html'
UA = 'Mozilla/5.0 AppleWebKit/537.36 Chrome/128 Safari/537.36'


def get_json(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,*/*'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def norm(v):
    s = unicodedata.normalize('NFKD', str(v or ''))
    s = ''.join(ch for ch in s if not unicodedata.combining(ch)).lower()
    return re.sub(r'[^a-z0-9]+', '', s)


def extract_registry(source):
    start = source.index('const VERIFIED_MANUAL_PROMO_IDENTITIES')
    end = source.index('function verifiedManualPromoFallback', start)
    block = source[start:end]
    rows = []
    pat = re.compile(r"'MEP\s+(0(?:89|90|91|92|93|94|95|96|97|98|99)|100|101)'\s*:\s*\{(.*?)\}(?:,|\n)", re.S)
    for code, body in pat.findall(block):
        m = re.search(r"name:'([^']+)'", body)
        if m:
            rows.append({'code': f'MEP {code}', 'number': code, 'name': m.group(1)})
    return rows


def price_rows(doc):
    if isinstance(doc, dict):
        for v in doc.values():
            if isinstance(v, list) and v and isinstance(v[0], dict) and 'idProduct' in v[0]:
                return v
    return []


def main():
    source = INDEX.read_text(encoding='utf-8')
    identities = extract_registry(source)
    assert len(identities) == 13, f'Expected 13 MEP identities, got {len(identities)}'

    products_doc = get_json('https://downloads.s3.cardmarket.com/productCatalog/productList/products_singles_6.json')
    products = products_doc.get('products', [])
    guide_doc = get_json('https://downloads.s3.cardmarket.com/productCatalog/priceGuide/price_guide_6.json')
    guide = {int(r['idProduct']): r for r in price_rows(guide_doc) if str(r.get('idProduct', '')).isdigit()}

    report = []
    for ident in identities:
        name_key = norm(ident['name'])
        candidates = []
        for p in products:
            pname = p.get('name') or p.get('productName') or ''
            if norm(pname) != name_key:
                continue
            pid = int(p.get('idProduct') or 0)
            row = {
                'idProduct': pid or None,
                'name': pname,
                'number': p.get('number') or p.get('collectorNumber') or p.get('localId'),
                'idExpansion': p.get('idExpansion'),
                'idMetacard': p.get('idMetacard'),
                'expansionName': p.get('expansionName') or p.get('nameExpansion') or p.get('expansion'),
                'priceGuide': guide.get(pid),
            }
            # Ranking hint only; never an automatic match.
            blob = ' '.join(str(v or '') for v in row.values())
            exact_code_hint = norm(ident['number']) in norm(blob)
            mep_hint = 'mep' in norm(blob) or 'blackstarpromo' in norm(blob)
            row['diagnosticHints'] = {'numberMentioned': exact_code_hint, 'mepMentioned': mep_hint}
            candidates.append(row)

        report.append({'identity': ident, 'candidateCount': len(candidates), 'candidates': candidates})

    print(json.dumps({'audit': 'MEP Cardmarket read-only', 'identities': len(report), 'rows': report}, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
