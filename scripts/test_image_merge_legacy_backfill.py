#!/usr/bin/env python3
"""Focused audit for Cardoryx language-image merging and legacy backfill.

The script reads index.html and TCGdex catalogue snapshots, exercises the exact
JavaScript helpers with Node, and writes only its diagnostic JSON report.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
OUT = ROOT / "artifacts" / "image_merge_legacy_backfill_report.json"
API = "https://api.tcgdex.net/v2"
POCKET_ID = re.compile(r"^(?:A\d+[a-z]?|P-A)-", re.I)
TARGETS = ("swsh10tg-TG08", "svp-211")


def cli():
    parser = argparse.ArgumentParser()
    parser.add_argument("--index", type=Path, default=INDEX)
    parser.add_argument("--en-cards", type=Path)
    parser.add_argument("--it-cards", type=Path)
    parser.add_argument("--out", type=Path, default=OUT)
    parser.add_argument("--expected-physical", type=int, default=21867)
    parser.add_argument("--expected-lost-before", type=int, default=363)
    parser.add_argument("--expected-runtime-before", type=int, default=1692)
    parser.add_argument("--expected-runtime-after", type=int, default=1329)
    return parser.parse_args()


def get_json(url):
    request = urllib.request.Request(url, headers={"User-Agent": "Cardoryx-Image-Audit/1.0"})
    with urllib.request.urlopen(request, timeout=120) as response:
        return json.load(response)


def load_cards(path, language):
    if path:
        return json.loads(path.read_text(encoding="utf-8"))
    return get_json(f"{API}/{language}/cards")


def sha256(path):
    if not path:
        return None
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def physical(cards):
    return {row["id"]: row for row in cards if row.get("id") and not POCKET_ID.match(row["id"])}


def image(row):
    return str((row or {}).get("image") or "").strip()


def merge_non_destructive(it_cards, en_cards):
    merged = {card_id: dict(row) for card_id, row in it_cards.items()}
    for card_id, incoming in en_cards.items():
        previous = merged.get(card_id)
        if previous is None:
            merged[card_id] = dict(incoming)
            continue
        combined = {**previous, **incoming}
        if image(previous) and not image(incoming):
            combined["image"] = previous["image"]
        merged[card_id] = combined
    return merged


def merge_destructive(it_cards, en_cards):
    merged = {card_id: dict(row) for card_id, row in it_cards.items()}
    merged.update({card_id: dict(row) for card_id, row in en_cards.items()})
    return merged


def extract_function(source, name):
    match = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", source)
    if not match:
        raise AssertionError(f"Missing JavaScript function: {name}")
    start = match.start()
    brace = source.find("{", match.end())
    depth = 0
    quote = None
    escaped = False
    for pos in range(brace, len(source)):
        char = source[pos]
        if quote:
            if escaped:
                escaped = False
            elif char == "\\":
                escaped = True
            elif char == quote:
                quote = None
            continue
        if char in "'\"`":
            quote = char
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                return source[start : pos + 1]
    raise AssertionError(f"Unclosed JavaScript function: {name}")


def run_js_regressions(index_path):
    source = index_path.read_text(encoding="utf-8")
    functions = "\n".join(
        extract_function(source, name)
        for name in ("mergeCardLanguageResult", "backfillOriginalImageFromExactTCGdex")
    )
    tests = r"""
const assert=require('assert');
const checks=[];
function check(name,fn){fn();checks.push(name)}
check('merge_preserves_it_image_when_en_empty',()=>{
  const it={id:'x-1',name:'Nome IT',image:'https://assets/it/x'};
  const en={id:'x-1',name:'Name EN'};
  const value=mergeCardLanguageResult(it,en);
  assert.strictEqual(value.image,it.image);assert.strictEqual(value.name,'Name EN');
});
check('merge_accepts_populated_en_image',()=>{
  const value=mergeCardLanguageResult({id:'x-1',image:'it-url'},{id:'x-1',image:'en-url'});
  assert.strictEqual(value.image,'en-url');
});
check('backfill_exact_tcgdex_id',()=>{
  const card={tcgdexId:'x-1',id:'x-1',image:'',originalImage:'',imageCandidates:[]};
  assert.strictEqual(backfillOriginalImageFromExactTCGdex(card,{id:'x-1',image:'official-url'},'x-1'),true);
  assert.strictEqual(card.originalImage,'official-url');assert.strictEqual(card.image,'');
});
check('backfill_exact_saved_card_id',()=>{
  const card={id:'x-1',image:'',originalImage:'',imageCandidates:[]};
  assert.strictEqual(backfillOriginalImageFromExactTCGdex(card,{id:'x-1',image:'official-url'},'x-1'),true);
});
check('backfill_rejects_identity_mismatch',()=>{
  const card={tcgdexId:'x-1',image:'',originalImage:'',imageCandidates:[]};
  assert.strictEqual(backfillOriginalImageFromExactTCGdex(card,{id:'x-2',image:'official-url'},'x-2'),false);
  assert.strictEqual(card.originalImage,'');
});
for(const [name,card] of [
  ['existing_original_url',{tcgdexId:'x-1',originalImage:'old-url',image:'',imageCandidates:[]}],
  ['personal_url',{tcgdexId:'x-1',originalImage:'',image:'personal-url',imageCandidates:[]}],
  ['data_image',{tcgdexId:'x-1',originalImage:'',image:'data:image/jpeg;base64,AA',imageCandidates:[]}],
  ['image_candidates',{tcgdexId:'x-1',originalImage:'',image:'',imageCandidates:['candidate-url']}]
])check(`backfill_preserves_${name}`,()=>{
  const before=JSON.stringify(card);
  assert.strictEqual(backfillOriginalImageFromExactTCGdex(card,{id:'x-1',image:'official-url'},'x-1'),false);
  assert.strictEqual(JSON.stringify(card),before);
});
check('backfill_rejects_missing_source_image',()=>{
  const card={tcgdexId:'x-1',image:'',originalImage:'',imageCandidates:[]};
  assert.strictEqual(backfillOriginalImageFromExactTCGdex(card,{id:'x-1'},'x-1'),false);
});
process.stdout.write(JSON.stringify({passed:checks.length,checks}));
"""
    script = functions + "\n" + tests
    result = subprocess.run(["node", "-e", script], check=True, capture_output=True, text=True)
    return json.loads(result.stdout)


def main():
    args = cli()
    en_all = load_cards(args.en_cards, "en")
    it_all = load_cards(args.it_cards, "it")
    en = physical(en_all)
    it = physical(it_all)
    destructive = merge_destructive(it, en)
    merged = merge_non_destructive(it, en)
    all_ids = set(en) | set(it)

    lost_before = sum(bool(image(it.get(card_id))) and not image(en.get(card_id)) for card_id in set(it) & set(en))
    lost_after = sum(bool(image(it.get(card_id))) and not image(merged.get(card_id)) for card_id in set(it) & set(en))
    missing_both = sum(not image(it.get(card_id)) and not image(en.get(card_id)) for card_id in all_ids)
    runtime_before = sum(not image(destructive.get(card_id)) for card_id in all_ids)
    runtime_after = sum(not image(merged.get(card_id)) for card_id in all_ids)

    assertions = {
        "physicalIdentities": len(all_ids) == args.expected_physical,
        "itImagesLostBefore": lost_before == args.expected_lost_before,
        "itImagesLostAfter": lost_after == 0,
        "runtimeMissingBefore": runtime_before == args.expected_runtime_before,
        "runtimeMissingAfter": runtime_after == args.expected_runtime_after,
        "runtimeAfterEqualsMissingBoth": runtime_after == missing_both,
    }

    targets = {}
    for card_id in TARGETS:
        en_full = get_json(f"{API}/en/cards/{card_id}")
        it_full = get_json(f"{API}/it/cards/{card_id}")
        targets[card_id] = {
            "enImage": en_full.get("image"),
            "itImage": it_full.get("image"),
            "runtimeImage": merged.get(card_id, {}).get("image"),
            "classification": "SOURCE_MISSING_IMAGE",
        }
        assertions[f"{card_id}RemainsMissing"] = not any(
            (en_full.get("image"), it_full.get("image"), image(merged.get(card_id)))
        )

    js = run_js_regressions(args.index)
    assertions["javascriptRegressions"] = js["passed"] == 10
    failed = [name for name, passed in assertions.items() if not passed]
    report = {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "status": "PASS" if not failed else "FAIL",
        "inputs": {
            "index": str(args.index),
            "indexSha256": sha256(args.index),
            "enCardsSource": f"{API}/en/cards",
            "enCardsInput": args.en_cards.name if args.en_cards else "live",
            "enCardsSha256": sha256(args.en_cards),
            "itCardsSource": f"{API}/it/cards",
            "itCardsInput": args.it_cards.name if args.it_cards else "live",
            "itCardsSha256": sha256(args.it_cards),
        },
        "catalogue": {
            "physicalIdentities": len(all_ids),
            "itImagesLostBefore": lost_before,
            "itImagesLostAfter": lost_after,
            "runtimeMissingBefore": runtime_before,
            "runtimeMissingAfter": runtime_after,
            "missingInBothLanguages": missing_both,
        },
        "targets": targets,
        "javascript": js,
        "assertions": assertions,
        "failed": failed,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "failed": failed, **report["catalogue"]}, ensure_ascii=False))
    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
