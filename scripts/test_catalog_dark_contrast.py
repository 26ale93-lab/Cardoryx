#!/usr/bin/env python3
from pathlib import Path

source = (Path(__file__).resolve().parents[1] / "index.html").read_text(encoding="utf-8")

required = [
    'html[data-theme="dark"]{color-scheme:dark;',
    '--cx-green:#4ade80;',
    '.catalog-summary{color:var(--cx-muted)}',
    '.price-main{color:var(--cx-green)}',
    '.qty-control{background:var(--cx-panel2);border:1px solid var(--cx-line)}',
    '.qty-control button{background:var(--cx-panel);color:var(--cx-text);border:1px solid var(--cx-line)}',
    '.qty-control strong{color:var(--cx-text)}',
]
for token in required:
    assert token in source, f"Missing dark catalog contrast rule: {token}"

print("PASS: catalog dark-theme contrast rules present")
