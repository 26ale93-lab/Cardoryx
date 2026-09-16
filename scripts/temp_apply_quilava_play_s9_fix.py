#!/usr/bin/env python3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
TEST = ROOT / "scripts/test_variant_finish_audit.py"


def replace_once(text, old, new, label):
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


index = INDEX.read_text()

registry_marker = """function verifiedSpecialStampFinishes(card,stamp){
  const id=String(card?.tcgdexId||card?.id||'').trim().toLowerCase();
  const rule=VERIFIED_SPECIAL_STAMP_FINISHES[id];
  if(!rule || cardSetId(card)!==rule.setId ||
     exactLocalIdKey(card?.localId||'')!==exactLocalIdKey(rule.localId) ||
     normText(card?.name||'')!==normText(rule.name||'') ||
     canonicalStamp(stamp)!==canonicalStamp(rule.stamp))return [];
  return Array.isArray(rule.finishes)?rule.finishes.map(canonicalVariant):[];
}


// V2.1.14 — Prize Pack Series 1–9 resolver + exact product refresh.
"""
registry_replacement = """function verifiedSpecialStampFinishes(card,stamp){
  const id=String(card?.tcgdexId||card?.id||'').trim().toLowerCase();
  const rule=VERIFIED_SPECIAL_STAMP_FINISHES[id];
  if(!rule || cardSetId(card)!==rule.setId ||
     exactLocalIdKey(card?.localId||'')!==exactLocalIdKey(rule.localId) ||
     normText(card?.name||'')!==normText(rule.name||'') ||
     canonicalStamp(stamp)!==canonicalStamp(rule.stamp))return [];
  return Array.isArray(rule.finishes)?rule.finishes.map(canonicalVariant):[];
}

// V2.1.43 — exact Play! Pokémon finish-only evidence.
// This registry must never supply a marketplace product or price: it only
// unlocks a physical finish for the exact tcgdexId/set/localId/Series identity.
const VERIFIED_PLAY_SERIES_FINISHES = {
  'sv10-033|9':{
    setId:'sv10',localId:'033',finishes:['Normal'],
    source:'Play! Pokémon Prize Pack Series 9 checklist · DRI 033 · Standard Set / Non-Holo',
    verified:'2026-09-16'
  }
};
function verifiedPlaySeriesFinishes(card,series){
  const id=String(card?.tcgdexId||card?.id||'').trim().toLowerCase();
  const ps=normalizedPlaySeries(series);
  const rule=VERIFIED_PLAY_SERIES_FINISHES[`${id}|${ps}`];
  if(!rule || cardSetId(card)!==rule.setId ||
     exactLocalIdKey(card?.localId||'')!==exactLocalIdKey(rule.localId))return [];
  return Array.isArray(rule.finishes)?rule.finishes.map(canonicalVariant):[];
}


// V2.1.14 — Prize Pack Series 1–9 resolver + exact product refresh.
"""
index = replace_once(index, registry_marker, registry_replacement, "insert exact Play finish registry")

plan_marker = """  if(stamp==='Play! Pokémon'){
    const plan=prizePackFinishPlan(card,series);
    if(plan.authoritative && plan.finishes.length)allowed=new Set(plan.finishes.map(canonicalVariant));
  }

  if(!allowed.size)allowed.add('Non so');
"""
plan_replacement = """  if(stamp==='Play! Pokémon'){
    const plan=prizePackFinishPlan(card,series);
    if(plan.authoritative && plan.finishes.length)allowed=new Set(plan.finishes.map(canonicalVariant));
    // Exact finish evidence is intentionally applied only to UI availability.
    // It does not enter prizePackFinishPlan(), so it cannot manufacture a price.
    const exactPlayFinishes=verifiedPlaySeriesFinishes(card,series);
    if(exactPlayFinishes.length)allowed=new Set(exactPlayFinishes);
  }

  if(!allowed.size)allowed.add('Non so');
"""
index = replace_once(index, plan_marker, plan_replacement, "apply exact Play finish evidence")
INDEX.write_text(index)


test = TEST.read_text()

test = replace_once(
    test,
    '    "sv10-033": {"expected": ["Normal", "Reverse Holo"], "cause": "NEEDS_MORE_EVIDENCE", "playSeries": "9"},',
    '    "sv10-033": {"expected": ["Normal", "Reverse Holo"], "cause": "VERIFIED_PLAY_SERIES_FINISH", "playSeries": "9"},',
    "Quilava regression classification",
)

test = replace_once(
    test,
    '        "NEEDS_MORE_EVIDENCE": "La stampa Play!/Prize Pack esiste come prodotto separato, ma i dati locali non ne provano con precisione la finitura; mantenere il fail-closed.",\n        "VERIFIED_REVERSE_STANDARD":',
    '        "NEEDS_MORE_EVIDENCE": "La stampa Play!/Prize Pack esiste come prodotto separato, ma i dati locali non ne provano con precisione la finitura; mantenere il fail-closed.",\n        "VERIFIED_PLAY_SERIES_FINISH": "Checklist Prize Pack Series 9 e identità DRI 033 confermano la ristampa Play! come Standard Set / Non-Holo; la regola resta circoscritta a sv10-033 + Series 9.",\n        "VERIFIED_REVERSE_STANDARD":',
    "Quilava cause text",
)

test = replace_once(
    test,
    '        "NEEDS_MORE_EVIDENCE": "Non automatizzare Play! Series 9 finché product ID e finish fisica non sono entrambi dimostrati.",\n        "VERIFIED_REVERSE_STANDARD":',
    '        "NEEDS_MORE_EVIDENCE": "Non automatizzare Play! Series 9 finché product ID e finish fisica non sono entrambi dimostrati.",\n        "VERIFIED_PLAY_SERIES_FINISH": "Abilitare esclusivamente Normal per sv10-033 + Play! Pokémon + Series 9; nessun product ID o prezzo viene introdotto da questa evidenza finish-only.",\n        "VERIFIED_REVERSE_STANDARD":',
    "Quilava fix text",
)

test = replace_once(
    test,
    '        "SOURCE_DATA": 0, "SPECIAL_PRINTING": 1, "CARDMARKET_IDENTITY": 4,\n        "ALREADY_FIXED": 28, "NEEDS_MORE_EVIDENCE": 1, "VERIFIED_REVERSE_STANDARD": 5,',
    '        "SOURCE_DATA": 0, "SPECIAL_PRINTING": 1, "CARDMARKET_IDENTITY": 4,\n        "ALREADY_FIXED": 28, "NEEDS_MORE_EVIDENCE": 0, "VERIFIED_PLAY_SERIES_FINISH": 1, "VERIFIED_REVERSE_STANDARD": 5,',
    "regression expected counts",
)

test = replace_once(
    test,
    '            "SPECIAL_PRINTING", "CARDMARKET_IDENTITY", "ALREADY_FIXED", "NEEDS_MORE_EVIDENCE",\n            "VERIFIED_REVERSE_STANDARD")},',
    '            "SPECIAL_PRINTING", "CARDMARKET_IDENTITY", "ALREADY_FIXED", "NEEDS_MORE_EVIDENCE",\n            "VERIFIED_PLAY_SERIES_FINISH", "VERIFIED_REVERSE_STANDARD")},',
    "regression report classification keys",
)

helper_marker = """\ndef main():
    ap = argparse.ArgumentParser()
"""
helper_code = r'''\ndef run_quilava_play_finish_runtime(source):
    registry = extract_js_object(source, "VERIFIED_PLAY_SERIES_FINISHES")
    expected = {
        "sv10-033|9": {
            "setId": "sv10", "localId": "033", "finishes": ["Normal"],
            "source": "Play! Pokémon Prize Pack Series 9 checklist · DRI 033 · Standard Set / Non-Holo",
            "verified": "2026-09-16",
        }
    }
    if registry != expected:
        raise AssertionError("Exact Quilava Play Series 9 finish registry changed unexpectedly")

    names = ("normText", "canonicalVariant", "exactLocalIdKey", "cardSetId",
             "normalizedPlaySeries", "verifiedPlaySeriesFinishes")
    functions = "\n".join(extract_js_function(source, name) for name in names)
    js = "const VERIFIED_PLAY_SERIES_FINISHES=" + json.dumps(registry, ensure_ascii=False) + ";\n" + functions + r'''
function fail(msg){throw new Error(msg);}
const exact={tcgdexId:'sv10-033',id:'sv10-033',set:{id:'sv10'},localId:'33',name:'Quilava di Armonio'};
const ok=verifiedPlaySeriesFinishes(exact,'9');
if(JSON.stringify(ok)!==JSON.stringify(['Normal']))fail('Exact Quilava Series 9 finish did not resolve to Normal');
for(const probe of [
  [exact,'8'],
  [{...exact,tcgdexId:'sv10-034',id:'sv10-034'},'9'],
  [{...exact,set:{id:'sv09'}},'9'],
  [{...exact,localId:'034'},'9']
]){
  if(verifiedPlaySeriesFinishes(probe[0],probe[1]).length)fail('Exact guard leaked');
}
console.log(JSON.stringify({exactSeries9:ok,series8:verifiedPlaySeriesFinishes(exact,'8'),wrongIdentityRejected:true}));
'''
    runtime = json.loads(subprocess.check_output(["node", "-e", js], text=True))
    integration = "const exactPlayFinishes=verifiedPlaySeriesFinishes(card,series);"
    if integration not in source:
        raise AssertionError("documentedVariantsForCard does not consume exact Play finish evidence")
    if "verifiedPlaySeriesFinishes" in extract_js_function(source, "prizePackFinishPlan"):
        raise AssertionError("Finish-only Quilava evidence leaked into Prize Pack price planning")
    runtime["pricePlanUntouched"] = True
    runtime["finishOnlyEvidence"] = True
    return runtime


def main():
    ap = argparse.ArgumentParser()
'''
test = replace_once(test, helper_marker, helper_code, "insert Quilava production runtime")

test = replace_once(
    test,
    '    ap.add_argument("--numel-ditto-only", action="store_true",\n                    help="Run the production-JS Numel Ditto P0 checks plus the binding 39-card regression set only")\n    args = ap.parse_args()',
    '    ap.add_argument("--numel-ditto-only", action="store_true",\n                    help="Run the production-JS Numel Ditto P0 checks plus the binding 39-card regression set only")\n    ap.add_argument("--quilava-play-only", action="store_true",\n                    help="Run exact Quilava Play Series 9 finish checks plus the binding 39-card regression set only")\n    args = ap.parse_args()',
    "add Quilava focused CLI",
)

test = replace_once(
    test,
    '        "VERIFIED_NORMAL_FINISHES", "verifiedNormalFinish",\n        "VERIFIED_REVERSE_FINISHES", "verifiedReverseFinish",',
    '        "VERIFIED_NORMAL_FINISHES", "verifiedNormalFinish",\n        "VERIFIED_REVERSE_FINISHES", "verifiedReverseFinish",\n        "VERIFIED_PLAY_SERIES_FINISHES", "verifiedPlaySeriesFinishes",',
    "required exact Play finish logic",
)

test = replace_once(
    test,
    '        "playAuto": extract_js_object(source, "PLAY_AUTO_CATALOG"),\n        "reverseConflict":',
    '        "playAuto": extract_js_object(source, "PLAY_AUTO_CATALOG"),\n        "playFinish": extract_js_object(source, "VERIFIED_PLAY_SERIES_FINISHES"),\n        "reverseConflict":',
    "extract exact Play finish registry",
)

focused_marker = """    if args.numel_ditto_only:
        real_world_regression = real_world_regression_audit(registries, play_index, set(), args.workers)
"""
focused_insert = """    if args.quilava_play_only:
        quilava_runtime = run_quilava_play_finish_runtime(source)
        real_world_regression = real_world_regression_audit(registries, play_index, set(), args.workers)
        report = {
            "audit": "Quilava Play Series 9 exact finish-only regression",
            "quilavaRuntime": quilava_runtime,
            "realWorldRegression": real_world_regression,
            "safety": {
                "readOnlyAudit": True, "retailModified": False, "cardmarketDataModified": False,
                "priceMappingModified": False, "scannerModified": False,
                "storageSchemaModified": False, "deckModified": False,
            },
        }
        output = ROOT / args.output
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\\n")
        print(json.dumps({
            "output": str(output), "quilavaRuntime": quilava_runtime,
            "realWorldRegression": {k: real_world_regression[k] for k in (
                "bindingDatasetSize", "recordsRecovered", "classificationBreakdown",
                "finishMatrixMatchesExpectation", "finishMatrixAnomalies", "fullyResolvedCases",
                "pipelineDataLossCases")},
        }, ensure_ascii=False, indent=2))
        return

    if args.numel_ditto_only:
        real_world_regression = real_world_regression_audit(registries, play_index, set(), args.workers)
"""
test = replace_once(test, focused_marker, focused_insert, "add Quilava focused test mode")

TEST.write_text(test)
print("Patched index.html and scripts/test_variant_finish_audit.py")
