#!/usr/bin/env python3
from pathlib import Path
import json
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SOURCE = (ROOT / "index.html").read_text(encoding="utf-8")


def extract_fn(name):
    marker = re.search(rf"\bfunction\s+{re.escape(name)}\s*\(", SOURCE)
    if not marker:
        raise AssertionError(f"Missing production function {name}")
    brace = SOURCE.find("{", marker.end())
    depth = 0
    quote = None
    esc = False
    for i in range(brace, len(SOURCE)):
        ch = SOURCE[i]
        if quote:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
            continue
        if ch in "'\"\`":
            quote = ch
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return SOURCE[marker.start():i + 1]
    raise AssertionError(f"Unterminated function {name}")


for group, stat_id in (
    ("pokemon", "deckPokemonStat"),
    ("trainer", "deckTrainerStat"),
    ("energy", "deckEnergyStat"),
):
    assert f'id="{stat_id}"' in SOURCE
    assert f"setDeckEntriesFilter('{group}')" in SOURCE

assert ".deck-stat.active" in SOURCE
assert "const visibleEntries=(d.entries||[]).filter(e=>" in SOURCE
assert "deckEntryGroup(c)===deckEntriesFilter" in SOURCE
assert "Nessuna carta di questa categoria nel mazzo." in SOURCE
assert SOURCE.count("deckEntriesFilter='';") >= 2

js = "\n".join(extract_fn(n) for n in (
    "deckEntryGroup", "updateDeckEntryFilterUi", "setDeckEntriesFilter"
))
js += r"""
let deckEntriesFilter='';
let renders=0,scrolls=0;
const elements={};
function makeEl(){
  return {
    classes:new Set(),attrs:{},
    classList:{toggle(name,on){if(on)this.owner.classes.add(name);else this.owner.classes.delete(name);}},
    setAttribute(name,value){this.attrs[name]=String(value);},
    scrollIntoView(){scrolls++;}
  };
}
for(const id of ['deckPokemonStat','deckTrainerStat','deckEnergyStat','deckEntries']){
  const el=makeEl();el.classList.owner=el;elements[id]=el;
}
function ui(id){return elements[id]||null;}
function renderDeckBuilder(){renders++;updateDeckEntryFilterUi();}

const out={groups:[
  deckEntryGroup({category:'Pokémon'}),
  deckEntryGroup({category:'Allenatore'}),
  deckEntryGroup({category:'Energia'}),
  deckEntryGroup({category:'Altro'})
]};
setDeckEntriesFilter('pokemon');
out.afterPokemon={filter:deckEntriesFilter,renders,scrolls,pressed:elements.deckPokemonStat.attrs['aria-pressed'],active:elements.deckPokemonStat.classes.has('active')};
setDeckEntriesFilter('pokemon');
out.afterToggleOff={filter:deckEntriesFilter,renders,scrolls,pressed:elements.deckPokemonStat.attrs['aria-pressed'],active:elements.deckPokemonStat.classes.has('active')};
setDeckEntriesFilter('trainer');
out.afterTrainer={filter:deckEntriesFilter,pokemonPressed:elements.deckPokemonStat.attrs['aria-pressed'],trainerPressed:elements.deckTrainerStat.attrs['aria-pressed']};
console.log(JSON.stringify(out));
"""
out=json.loads(subprocess.check_output(["node","-e",js],text=True))
assert out["groups"] == ["pokemon","trainer","energy",""], out
assert out["afterPokemon"] == {"filter":"pokemon","renders":1,"scrolls":1,"pressed":"true","active":True}, out
assert out["afterToggleOff"] == {"filter":"","renders":2,"scrolls":2,"pressed":"false","active":False}, out
assert out["afterTrainer"] == {"filter":"trainer","pokemonPressed":"false","trainerPressed":"true"}, out
print(json.dumps({"status":"PASS","deckCategoryFilter":out},ensure_ascii=False,indent=2))
