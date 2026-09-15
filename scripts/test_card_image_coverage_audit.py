#!/usr/bin/env python3
"""READ-ONLY audit for missing card artwork in Cardoryx / TCGdex.

Known user-reported cases are checked first, then aggregate image coverage is reported.
No production data is modified.
"""
import json
import urllib.request

UA = 'Mozilla/5.0 AppleWebKit/537.36 Chrome/128 Safari/537.36'
BASE = 'https://api.tcgdex.net/v2'

KNOWN = [
    {'name': 'Kleavor', 'localId': 'TG08', 'note': 'Astral Radiance Trainer Gallery TG08/TG30'},
    {'name': 'Gothitelle', 'localId': '211', 'note': 'SVP Black Star Promos 211/225'},
]


def get_json(url, timeout=60):
    req = urllib.request.Request(url, headers={'User-Agent': UA, 'Accept': 'application/json,*/*'})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.load(r)


def head_ok(url, timeout=20):
    req = urllib.request.Request(url, headers={'User-Agent': UA}, method='HEAD')
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return 200 <= r.status < 400
    except Exception:
        return False


def image_candidates(image):
    image = str(image or '').rstrip('/')
    if not image:
        return []
    if image.lower().endswith(('.png', '.jpg', '.jpeg', '.webp')):
        return [image]
    return [image + '/low.webp', image + '/high.webp']


def main():
    lang_rows = {}
    for lang in ('it', 'en'):
        rows = get_json(f'{BASE}/{lang}/cards')
        assert isinstance(rows, list), f'Unexpected TCGdex cards response for {lang}'
        lang_rows[lang] = rows

    known_report = []
    for target in KNOWN:
        entry = {'target': target, 'languages': {}}
        for lang, rows in lang_rows.items():
            matches = [r for r in rows if str(r.get('name', '')).strip().lower() == target['name'].lower()
                       and str(r.get('localId', '')).strip().upper() == target['localId'].upper()]
            detailed = []
            for r in matches:
                image = r.get('image') or ''
                urls = image_candidates(image)
                detailed.append({
                    'id': r.get('id'),
                    'name': r.get('name'),
                    'localId': r.get('localId'),
                    'image': image or None,
                    'candidateUrls': urls,
                    'reachable': [u for u in urls if head_ok(u)],
                })
            entry['languages'][lang] = detailed
        known_report.append(entry)

    coverage = {}
    for lang, rows in lang_rows.items():
        with_image = sum(1 for r in rows if r.get('image'))
        coverage[lang] = {
            'total': len(rows),
            'withImageField': with_image,
            'withoutImageField': len(rows) - with_image,
        }

    print(json.dumps({
        'audit': 'Card image coverage read-only',
        'knownCases': known_report,
        'coverage': coverage,
        'safety': 'No fallback image is accepted automatically. Results are diagnostic only.'
    }, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
