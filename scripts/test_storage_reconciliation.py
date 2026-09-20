#!/usr/bin/env python3
import json
import re
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "index.html").read_text(encoding="utf-8")

def extract_function(name):
    marker = f"function {name}("
    start = SOURCE.find(marker)
    if start < 0:
        raise AssertionError(f"Missing function {name}")
    brace = SOURCE.find("{", start)
    depth = 0
    quote = None
    escaped = False
    for i in range(brace, len(SOURCE)):
        ch = SOURCE[i]
        if quote:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in ("'", '"', "`"):
            quote = ch
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return SOURCE[start:i+1]
    raise AssertionError(f"Unclosed function {name}")

required = [
    "collectionTotals",
    "storageFingerprint",
    "verifiedIndexedStateRow",
    "verifiedMigrationMarker",
    "verifiedIndexedState",
    "sameMigrationPayload",
    "migrationPayloadMatchesMarker",
    "storageMigrationReconciliation",
]
js = "\n".join(extract_function(name) for name in required)

js += r'''
const CARDORYX_IDB_MIGRATION_KEY='localstorage-to-indexeddb';
const CARDORYX_IDB_MIGRATION_VERSION=1;
function row(key,value){
  const out={key,value,fingerprint:storageFingerprint(value)};
  if(key==='collection')out.totals=collectionTotals(value);
  else out.count=value.length;
  return out;
}
function markerFor(collection,decks){
  const totals=collectionTotals(collection);
  return {
    key:CARDORYX_IDB_MIGRATION_KEY,version:CARDORYX_IDB_MIGRATION_VERSION,status:'complete',
    records:totals.records,total:totals.total,decks:decks.length,
    sourceCollectionFingerprint:storageFingerprint(collection),
    sourceDecksFingerprint:storageFingerprint(decks),
    verifiedAt:'fixture'
  };
}
function state(collection,decks,marker){
  return {collectionRow:row('collection',collection),decksRow:row('decks',decks),collection,decks,marker};
}
const baseCollection=[{id:'a',qty:1}];
const baseDecks=[];
const marker=markerFor(baseCollection,baseDecks);

const same=storageMigrationReconciliation(
  baseCollection,baseDecks,state(baseCollection,baseDecks,marker)
);
if(same!=='same')throw new Error('same -> '+same);

const idbNewCollection=[{id:'a',qty:2}];
const idbNew=storageMigrationReconciliation(
  baseCollection,baseDecks,state(idbNewCollection,baseDecks,marker)
);
if(idbNew!=='use-indexeddb')throw new Error('idb-new -> '+idbNew);

const localNewCollection=[{id:'a',qty:1},{id:'b',qty:1}];
const localNew=storageMigrationReconciliation(
  localNewCollection,baseDecks,state(baseCollection,baseDecks,marker)
);
if(localNew!=='promote-local')throw new Error('local-new -> '+localNew);

const bothNew=storageMigrationReconciliation(
  localNewCollection,baseDecks,state(idbNewCollection,baseDecks,marker)
);
if(bothNew!=='conflict')throw new Error('both-new -> '+bothNew);

const invalid=storageMigrationReconciliation(
  baseCollection,baseDecks,state(baseCollection,baseDecks,{})
);
if(invalid!=='invalid')throw new Error('invalid -> '+invalid);

process.stdout.write(JSON.stringify({same,idbNew,localNew,bothNew,invalid}));
'''
result = json.loads(subprocess.check_output(["node", "-e", js], text=True))

assert result == {
    "same": "same",
    "idbNew": "use-indexeddb",
    "localNew": "promote-local",
    "bothNew": "conflict",
    "invalid": "invalid",
}, result

# Production integration guards.
assert "if(reconciliation==='promote-local')" in SOURCE
assert "await idbWriteState(localCollection,localDecks);" in SOURCE
assert "const promotedMarker=migrationMarkerFor(localCollection,localDecks);" in SOURCE
assert "Fallback recuperato e verificato · IndexedDB riattivato" in SOURCE
assert "Conflitto reale tra localStorage e IndexedDB" in SOURCE
assert "sameMigrationPayload(localCollection,localDecks,promoted.collection,promoted.decks)" in SOURCE
assert "const localCollection=loadDB();" in SOURCE
assert "localStorage.getItem(DECK_KEY)" in SOURCE
assert "const localCollection=db,localDecks=decks;" not in SOURCE

print(json.dumps({"status":"PASS","scenarios":result},ensure_ascii=False))
