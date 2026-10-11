#!/usr/bin/env python3
from pathlib import Path
import argparse
import concurrent.futures
import hashlib
import json
import re
import subprocess
import tempfile
import urllib.request
from collections import Counter
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / 'index.html').read_text(encoding='utf-8')
TCGDEX_API = 'https://api.tcgdex.net/v2/en'
CM_BASE = 'https://downloads.s3.cardmarket.com/productCatalog'


def extract_fn(name):
    marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", SOURCE)
    if not marker:
        raise AssertionError(f"Missing production function {name}")
    brace = SOURCE.find('{', marker.end())
    depth = 0
    quote = None
    esc = False
    for i in range(brace, len(SOURCE)):
        ch = SOURCE[i]
        if quote:
            if esc:
                esc = False
            elif ch == '\\':
                esc = True
            elif ch == quote:
                quote = None
            continue
        if ch in "'\"\`":
            quote = ch
        elif ch == '{':
            depth += 1
        elif ch == '}':
            depth -= 1
            if depth == 0:
                return SOURCE[marker.start():i + 1]
    raise AssertionError(f"Unterminated function {name}")


def run_production_regression():
    names = [
        'is30thCelebrationSet',
        'stampEvidenceVerified',
        'stampExistsForCard',
        'syncStampAvailability',
        'documentedVariantsForCard',
        'migrateFinishStamp',
    ]
    js = '\n'.join(extract_fn(n) for n in names)
    js += r'''
function canonicalStamp(v){return String(v||'');}
function canonicalVariant(v){return String(v||'Normal');}
function normalizedPlaySeries(){return '';}
function isMee30CelebrationEnergy(){return false;}
function isVerifiedMcdonalds2021AnniversarySet(){return false;}
function tcgdexExactMfbPokeballRow(){return null;}
function tcgdexExactMcdonaldsStampRow(){return null;}
function tcgdexMcdonalds2021AnniversaryRows(){return null;}
function tcgdexExactSwshp25thStandardRow(){return null;}
function tcgdexExactSwshpSetLogoRow(){return null;}
function verifiedPrimaryWorldsStamp(){return '';}
function verifiedMepStampRule(){return false;}
function tcgdexExactMepStampRow(){return null;}
function cachedOfficialPlaySeries(){return [];}
function playAutoMatch(){return null;}
function stampEvidenceFromTCGdex(){return false;}
const VERIFIED_STAMP_PRICES={};
function normText(v){return String(v||'').toLowerCase().replace(/[^a-z0-9]+/g,'');}
function syncPlaySeriesVisibility(){}
function syncEditPlaySeriesVisibility(){}
function makeSelect(){
  const options=['None','30° Anniversario','Altro','Play! Pokémon','Pokémon Day'].map(value=>({value,disabled:false}));
  const sel={options,value:'None'};
  Object.defineProperty(sel,'selectedOptions',{get(){return [options.find(o=>o.value===sel.value)||options[0]];}});
  return sel;
}
const scanStamp=makeSelect(),editStamp=makeSelect();
const scanPlay={value:'9'},editPlay={value:'9'};
const scanInfo={textContent:''},editInfo={textContent:''};
global.document={getElementById(id){return {
  stamp:scanStamp,
  editStamp:editStamp,
  playSeries:scanPlay,
  editPlaySeries:editPlay,
  stampAvailabilityInfo:scanInfo,
  editStampAvailabilityInfo:editInfo
}[id]||null;}};

const main={id:'30th-001',tcgdexId:'30th-001',name:'Exeggcute',localId:'001',set:{id:'30th',name:'30th Celebration'},variant:'Normal',stamp:'None'};
const classic={id:'30th-c-001',tcgdexId:'30th-c-001',name:'Classic test',localId:'001',set:{id:'30th-c',name:'30th Classic Collection'},variant:'Normal',stamp:'None'};
const control={id:'me01-001',tcgdexId:'me01-001',name:'Control',localId:'001',set:{id:'me01',name:'Mega Evolution'},variant:'Normal',stamp:'None'};

const r={};
r.identities=[is30thCelebrationSet(main),is30thCelebrationSet(classic),is30thCelebrationSet(control)];
r.stamps=[
  stampExistsForCard(main,'30° Anniversario'),
  stampExistsForCard(main,'None'),
  stampExistsForCard(main,'Play! Pokémon'),
  stampExistsForCard(classic,'30° Anniversario'),
  stampExistsForCard(control,'30° Anniversario')
];
syncStampAvailability(main,false,false);
syncStampAvailability(classic,true,false);
r.auto=[scanStamp.value,scanPlay.value,editStamp.value,editPlay.value];
r.finishes=[...documentedVariantsForCard(main,'30° Anniversario')];
r.classicFinishes=[...documentedVariantsForCard(classic,'30° Anniversario')];
const a=migrateFinishStamp(JSON.parse(JSON.stringify(main)));
const b=migrateFinishStamp(JSON.parse(JSON.stringify(classic)));
const c=migrateFinishStamp(JSON.parse(JSON.stringify(control)));
r.migrated=[a.variant,a.stamp,b.variant,b.stamp,c.variant,c.stamp];
console.log(JSON.stringify(r));
'''
    out = json.loads(subprocess.check_output(['node', '-e', js], text=True))
    assert out['identities'] == [True, True, False], out
    assert out['stamps'] == [True, False, False, True, False], out
    assert out['auto'] == ['30° Anniversario', '', '30° Anniversario', ''], out
    assert out['finishes'] == ['Holo', 'Speciale / Altro', 'Non so'], out
    assert out['classicFinishes'] == ['Holo', 'Speciale / Altro', 'Non so'], out
    assert out['migrated'] == ['Holo', '30° Anniversario', 'Holo', '30° Anniversario', 'Normal', 'None'], out
    return out


def fetch_json(url, timeout=90):
    req = urllib.request.Request(url, headers={'User-Agent': 'Cardoryx-30th-Price-Audit/1.0'})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return json.load(response)


def download_cm(filename):
    destination = Path(tempfile.gettempdir()) / filename
    section = 'productList' if filename.startswith('products_') else 'priceGuide'
    req = urllib.request.Request(
        f'{CM_BASE}/{section}/{filename}',
        headers={'User-Agent': 'Cardoryx-30th-Price-Audit/1.0'},
    )
    with urllib.request.urlopen(req, timeout=300) as response, destination.open('wb') as handle:
        while True:
            chunk = response.read(1024 * 1024)
            if not chunk:
                break
            handle.write(chunk)
    return destination


def rows(root, keys):
    if isinstance(root, list):
        return root
    if isinstance(root, dict):
        for key in keys:
            value = root.get(key)
            if isinstance(value, list):
                return value
    return []


def sha256(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def normalize_token(value):
    return re.sub(r'[^a-z0-9]+', '', str(value or '').lower())


def card_name(card):
    value = card.get('name')
    if isinstance(value, dict):
        return value.get('en') or value.get('it') or next(iter(value.values()), '')
    return str(value or '')


def set_card_ids(set_id):
    data = fetch_json(f'{TCGDEX_API}/sets/{set_id}')
    found = []
    for item in data.get('cards') or []:
        if isinstance(item, dict) and item.get('id'):
            found.append(str(item['id']))
        elif isinstance(item, str):
            found.append(item)
    if not found:
        raise RuntimeError(f'No cards returned for TCGdex set {set_id}')
    return found


def cm_product_id(card):
    cm = ((card.get('pricing') or {}).get('cardmarket') or {})
    try:
        value = int(cm.get('idProduct') or cm.get('id_product') or 0)
    except (TypeError, ValueError):
        value = 0
    return value or None


def detailed_rows(card):
    value = card.get('variants_detailed')
    return value if isinstance(value, list) else []


def row_cm_product_id(row):
    try:
        return int(((row.get('thirdParty') or {}).get('cardmarket')) or 0) or None
    except (TypeError, ValueError):
        return None


def row_price_product_id(row):
    cm = ((row.get('pricing') or {}).get('cardmarket') or {})
    try:
        return int(cm.get('idProduct') or cm.get('id_product') or 0) or None
    except (TypeError, ValueError):
        return None


def is_30th_stamp_row(row):
    stamps = row.get('stamp') or []
    if isinstance(stamps, str):
        stamps = [stamps]
    tokens = [normalize_token(x) for x in stamps]
    return any(('30' in x and ('anniv' in x or 'celebr' in x)) or x in {'30th', '30anniversary'} for x in tokens)


def price_payload(price):
    if not price:
        return None
    keys = ('low', 'trend', 'avg', 'avg1', 'avg7', 'avg30',
            'low-holo', 'trend-holo', 'avg-holo', 'avg1-holo', 'avg7-holo', 'avg30-holo')
    return {k: price.get(k) for k in keys if k in price}


def positive(price, key):
    try:
        return float((price or {}).get(key) or 0) > 0
    except (TypeError, ValueError):
        return False


def price_classification(price):
    if not price:
        return 'EXACT_PRODUCT_MISSING_PRICE_GUIDE'
    standard_trend = positive(price, 'trend')
    holo_trend = positive(price, 'trend-holo')
    standard_low = positive(price, 'low')
    holo_low = positive(price, 'low-holo')
    if standard_trend and holo_trend:
        return 'BOTH_TREND_SLOTS_PRESENT_REVIEW_REQUIRED'
    if standard_trend:
        return 'STANDARD_TREND_AVAILABLE'
    if holo_trend:
        return 'HOLO_TREND_AVAILABLE_REVIEW_REQUIRED'
    if standard_low or holo_low:
        return 'LOW_ONLY_NO_TREND'
    return 'NO_USABLE_PRICE'


def norm_name(value):
    value = str(value or '').split(' [', 1)[0]
    return normalize_token(value)


def norm_number(value):
    return normalize_token(value).lstrip('0') or '0'


def number_matches(product_number, local_id):
    pn = norm_number(product_number)
    ln = norm_number(local_id)
    return pn == ln or (ln.isdigit() and pn.endswith(ln))


def discover_30th_catalogue(cards_by_set, products):
    by_name = {}
    for product in products.values():
        by_name.setdefault(norm_name(product.get('name')), []).append(product)

    expansion_counts = Counter()
    exact_candidates = {}
    for card in cards_by_set.get('30th', []):
        candidates = [
            p for p in by_name.get(norm_name(card_name(card)), [])
            if number_matches(p.get('number'), card.get('localId'))
        ]
        exact_candidates[card.get('id')] = candidates
        for p in candidates:
            if p.get('idExpansion') is not None:
                expansion_counts[int(p['idExpansion'])] += 1

    dominant_expansion = expansion_counts.most_common(1)[0][0] if expansion_counts else None
    dominant_matches = expansion_counts.get(dominant_expansion, 0) if dominant_expansion else 0
    return {
        'byName': by_name,
        'exactCandidates': exact_candidates,
        'dominantExpansionId': dominant_expansion,
        'dominantExpansionMatches': dominant_matches,
        'expansionCountsTop10': expansion_counts.most_common(10),
    }


def audit_intrinsic_30th(card, products, prices, discovery):
    set_id = ((card.get('set') or {}).get('id') if isinstance(card.get('set'), dict) else None)
    pid = cm_product_id(card)
    evidence = 'tcgdex-top-level'
    candidates = []

    if not pid:
        dominant = discovery.get('dominantExpansionId')
        by_name = discovery.get('byName') or {}
        if set_id == '30th':
            candidates = [
                p for p in discovery.get('exactCandidates', {}).get(card.get('id'), [])
                if dominant is not None and int(p.get('idExpansion') or -1) == int(dominant)
            ]
        elif set_id == '30th-c':
            candidates = [
                p for p in by_name.get(norm_name(card_name(card)), [])
                if dominant is not None and int(p.get('idExpansion') or -1) == int(dominant)
            ]
        if len(candidates) == 1:
            pid = int(candidates[0]['idProduct'])
            evidence = 'official-cardmarket-catalogue-candidate'
        else:
            evidence = 'unresolved'

    product = products.get(pid) if pid else None
    price = prices.get(pid) if pid else None
    if not pid:
        classification = 'CATALOGUE_MAPPING_AMBIGUOUS_OR_MISSING'
    elif not product:
        classification = 'PRODUCT_NOT_IN_CARDMARKET_CATALOGUE'
    else:
        base = price_classification(price)
        classification = base if evidence == 'tcgdex-top-level' else f'CATALOGUE_CANDIDATE_{base}'

    candidate_preview = [
        {
            'idProduct': p.get('idProduct'),
            'idExpansion': p.get('idExpansion'),
            'idMetacard': p.get('idMetacard'),
            'name': p.get('name'),
            'number': p.get('number'),
        }
        for p in candidates[:8]
    ]
    return {
        'scope': 'intrinsic_30th_set',
        'tcgdexId': card.get('id'),
        'name': card_name(card),
        'setId': set_id,
        'localId': card.get('localId'),
        'cardmarketProductId': pid,
        'mappingEvidence': evidence,
        'cardmarketProductName': (product or {}).get('name'),
        'cardmarketProductNumber': (product or {}).get('number'),
        'cardmarketExpansionId': (product or {}).get('idExpansion'),
        'classification': classification,
        'candidateCount': len(candidates),
        'candidatePreview': candidate_preview,
        'priceGuide': price_payload(price),
    }


def audit_mee_30th(card, products, prices):
    exact = []
    for row in detailed_rows(card):
        if not is_30th_stamp_row(row):
            continue
        pid = row_cm_product_id(row)
        ppid = row_price_product_id(row)
        if pid and ppid == pid:
            exact.append((pid, row))
    if len(exact) != 1:
        return {
            'scope': 'mee_009_016_30th_stamp',
            'tcgdexId': card.get('id'),
            'name': card_name(card),
            'localId': card.get('localId'),
            'classification': 'NO_UNIQUE_EXACT_30TH_STAMP_PRODUCT_EVIDENCE',
            'exactStampedRowsFound': len(exact),
            'topLevelCardmarketProductId': cm_product_id(card),
        }
    pid, row = exact[0]
    product = products.get(pid)
    price = prices.get(pid)
    classification = price_classification(price) if product else 'PRODUCT_NOT_IN_CARDMARKET_CATALOGUE'
    return {
        'scope': 'mee_009_016_30th_stamp',
        'tcgdexId': card.get('id'),
        'name': card_name(card),
        'localId': card.get('localId'),
        'cardmarketProductId': pid,
        'cardmarketProductName': (product or {}).get('name'),
        'classification': classification,
        'priceGuide': price_payload(price),
    }


def run_price_audit(report_path):
    products_path = download_cm('products_singles_6.json')
    prices_path = download_cm('price_guide_6.json')
    products_root = json.loads(products_path.read_text(encoding='utf-8'))
    prices_root = json.loads(prices_path.read_text(encoding='utf-8'))
    products = {int(x['idProduct']): x for x in rows(products_root, ('products',)) if x.get('idProduct')}
    prices = {int(x['idProduct']): x for x in rows(prices_root, ('priceGuides', 'priceGuide')) if x.get('idProduct')}

    catalogue_gengar = [
        {
            'idProduct': p.get('idProduct'),
            'idExpansion': p.get('idExpansion'),
            'idMetacard': p.get('idMetacard'),
            'name': p.get('name'),
            'number': p.get('number'),
        }
        for p in products.values()
        if norm_name(p.get('name')) == norm_name('Gengar ex')
    ]
    catalogue_30c = [
        {
            'idProduct': p.get('idProduct'),
            'idExpansion': p.get('idExpansion'),
            'name': p.get('name'),
            'number': p.get('number'),
        }
        for p in products.values()
        if '30c' in normalize_token(p.get('number'))
    ]

    set_ids = {'30th': set_card_ids('30th'), '30th-c': set_card_ids('30th-c')}
    mee_all = set_card_ids('mee')
    mee_ids = []
    for card_id in mee_all:
        m = re.search(r'(\\d+)$', card_id)
        if m and 9 <= int(m.group(1)) <= 16:
            mee_ids.append(card_id)
    target_ids = sorted(set(set_ids['30th'] + set_ids['30th-c'] + mee_ids))

    cards = {}
    errors = {}
    def load(card_id):
        return card_id, fetch_json(f'{TCGDEX_API}/cards/{card_id}')
    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:
        futures = {pool.submit(load, card_id): card_id for card_id in target_ids}
        for future in concurrent.futures.as_completed(futures):
            card_id = futures[future]
            try:
                cid, card = future.result()
                cards[cid] = card
            except Exception as exc:
                errors[card_id] = f'{type(exc).__name__}: {exc}'

    cards_by_set = {
        set_id: [cards[cid] for cid in set_ids[set_id] if cid in cards]
        for set_id in ('30th', '30th-c')
    }
    discovery = discover_30th_catalogue(cards_by_set, products)

    results = []
    for set_id in ('30th', '30th-c'):
        for card in cards_by_set[set_id]:
            results.append(audit_intrinsic_30th(card, products, prices, discovery))
    for card_id in mee_ids:
        card = cards.get(card_id)
        if card:
            results.append(audit_mee_30th(card, products, prices))

    counts = Counter(x['classification'] for x in results)
    scope_counts = {}
    for scope in ('intrinsic_30th_set', 'mee_009_016_30th_stamp'):
        scope_counts[scope] = dict(Counter(x['classification'] for x in results if x['scope'] == scope))

    gengar = next((x for x in results if x.get('tcgdexId') == '30th-090'), None)
    report = {
        'generatedAt': datetime.now(timezone.utc).isoformat(),
        'mode': 'READ_ONLY_DIAGNOSTIC',
        'sources': {
            'tcgdexApi': TCGDEX_API,
            'cardmarketProductCatalogue': {'file': products_path.name, 'sha256': sha256(products_path)},
            'cardmarketPriceGuide': {'file': prices_path.name, 'sha256': sha256(prices_path)},
        },
        'safety': {
            'productionFilesWritten': False,
            'cardmarketIndexWritten': False,
            'retailPricesWritten': False,
            'priceEstimationOrSubstitution': False,
            'policy': 'No generic/base price is reused for a 30th Anniversary printing. Missing exact evidence remains unavailable.',
        },
        'coverage': {
            'set30thExpected': len(set_ids['30th']),
            'set30thClassicExpected': len(set_ids['30th-c']),
            'meeExpected': len(mee_ids),
            'targetIds': len(target_ids),
            'cardsFetched': len(cards),
            'fetchErrors': errors,
            'rowsAudited': len(results),
        },
        'catalogueProbe': {
            'productRowsTotal': len(products),
            'priceGuideRowsTotal': len(prices),
            'gengarExExactNameRows': catalogue_gengar[:25],
            'numbersContaining30CCount': len(catalogue_30c),
            'numbersContaining30CSample': catalogue_30c[:25],
            'meeSetIdsCount': len(mee_all),
            'meeSetIdsSample': mee_all[:25],
        },
        'catalogueDiscovery': {
            'dominantExpansionId': discovery.get('dominantExpansionId'),
            'dominantExpansionMatches': discovery.get('dominantExpansionMatches'),
            'expansionCountsTop10': discovery.get('expansionCountsTop10'),
            'note': 'Audit-only inference from exact Cardmarket catalogue name + printed-number matches across TCGdex 30th main-set identities. Not a production mapping rule.',
        },
        'classificationTotals': dict(counts),
        'classificationByScope': scope_counts,
        'gengar30th090': gengar,
        'results': sorted(results, key=lambda x: (x['scope'], str(x.get('tcgdexId') or ''))),
        'interpretation': {
            'STANDARD_TREND_AVAILABLE': 'Exact product has a non-zero standard trend in the official downloadable Cardmarket Price Guide; candidate for a future exact resolver after production-field semantics are verified.',
            'HOLO_TREND_AVAILABLE_REVIEW_REQUIRED': 'Only the holo trend slot is populated; do not integrate without proving that slot matches the live dedicated product page.',
            'BOTH_TREND_SLOTS_PRESENT_REVIEW_REQUIRED': 'Both trend families are populated; manual/official semantic verification required.',
            'LOW_ONLY_NO_TREND': 'Exact product has offers/minimum data but no trend; Cardoryx must not invent a market value from the minimum.',
            'NO_USABLE_PRICE': 'Exact product exists but the downloadable guide has no usable market fields.',
            'NO_UNIQUE_EXACT_30TH_STAMP_PRODUCT_EVIDENCE': 'The 30th stamp inside MEE is not proven by one unique physical row; fail closed.',
        },
    }

    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--price-audit', action='store_true', help='Run read-only live 30th Anniversary Cardmarket coverage audit.')
    parser.add_argument('--report', default='artifacts/30th_cardmarket_price_audit_report.json')
    args = parser.parse_args()

    regression = run_production_regression()
    output = {'status': 'PASS', 'regression': regression}
    if args.price_audit:
        report = run_price_audit(ROOT / args.report)
        output['priceAuditSummary'] = {
            'coverage': report['coverage'],
            'classificationTotals': report['classificationTotals'],
            'classificationByScope': report['classificationByScope'],
            'catalogueProbe': report['catalogueProbe'],
            'catalogueDiscovery': report['catalogueDiscovery'],
            'gengar30th090': report['gengar30th090'],
            'report': args.report,
        }
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
