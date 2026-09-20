#!/usr/bin/env python3
from pathlib import Path

root = Path(__file__).resolve().parents[1]
text = (root / "storage-audit.html").read_text(encoding="utf-8")

required = [
    "mode:'READ_ONLY'",
    "writesPerformed:false",
    "indexedDB.databases",
    "transaction([STATE_STORE,META_STORE],'readonly')",
    "localStorage.getItem",
    "recordDiff:diffRecords",
    "localMatchesMigrationSource",
    "indexedDbMatchesMigrationSource",
    "compactAnalysis",
    "Copia riepilogo compatto",
    "Delta quantità sui record comuni",
    "serialized===undefined?\'__CARDORYX_UNDEFINED__\':serialized",
]
for token in required:
    assert token in text, f"missing required token: {token}"

for forbidden in [
    "localStorage.setItem(",
    "localStorage.removeItem(",
    "localStorage.clear(",
    ".put(",
    ".add(",
    ".delete(",
    ".clear(",
    "readwrite",
    "navigator.storage.persist(",
]:
    assert forbidden not in text, f"forbidden write-capable operation found: {forbidden}"

print("PASS: storage-audit.html is read-only and contains required conflict diagnostics")
