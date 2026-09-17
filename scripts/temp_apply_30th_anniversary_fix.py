#!/usr/bin/env python3
from pathlib import Path

p = Path('index.html')
s = p.read_text(encoding='utf-8')

anchor = """// V2.1.29 — startup-safe identity guard for MEE 009–016.\n// IMPORTANT: this helper intentionally does not call codedEnergyInfo() or any\n// constants declared later in the script, so it is safe even during startup.\nfunction isMee30CelebrationEnergy(card){"""
insert = """// V2.1.40 — exact foil-only identity guard for the 30th Anniversary sets.\n// TCGdex does not currently expose finish rows for these cards, while Pokémon's\n// official product documentation states that the 30th Celebration booster cards\n// are holographic. Keep this scoped to the two exact TCGdex set ids only.\nfunction is30thCelebrationSet(card){\n  if(!card)return false;\n  const setId=String(card?.set?.id||card?._cardoryxSetId||card?.setId||'').trim().toLowerCase();\n  return setId==='30th'||setId==='30th-c';\n}\n\n// V2.1.29 — startup-safe identity guard for MEE 009–016.\n// IMPORTANT: this helper intentionally does not call codedEnergyInfo() or any\n// constants declared later in the script, so it is safe even during startup.\nfunction isMee30CelebrationEnergy(card){"""
if anchor not in s:
    raise SystemExit('missing isMee30CelebrationEnergy anchor')
s = s.replace(anchor, insert, 1)

replacements = [
    ("""function stampEvidenceVerified(card,stamp){\n  const st=canonicalStamp(stamp);\n  if(isMee30CelebrationEnergy(card)){\n    if(st==='30° Anniversario')return true;\n    if(st==='Play! Pokémon'||st==='Pokémon Day')return false;\n  }""",
     """function stampEvidenceVerified(card,stamp){\n  const st=canonicalStamp(stamp);\n  if(is30thCelebrationSet(card)||isMee30CelebrationEnergy(card)){\n    if(st==='30° Anniversario')return true;\n    if(st==='Play! Pokémon'||st==='Pokémon Day')return false;\n  }"""),
    ("""function stampExistsForCard(card,stamp){\n  const st=canonicalStamp(stamp);\n  if(isMee30CelebrationEnergy(card)){\n    return st==='30° Anniversario'||st==='Altro';\n  }""",
     """function stampExistsForCard(card,stamp){\n  const st=canonicalStamp(stamp);\n  if(is30thCelebrationSet(card)||isMee30CelebrationEnergy(card)){\n    return st==='30° Anniversario'||st==='Altro';\n  }"""),
    ("""  if(isMee30CelebrationEnergy(card)){\n    sel.value='30° Anniversario';\n    const ps=document.getElementById(edit?'editPlaySeries':'playSeries');\n    if(ps)ps.value='';\n  }""",
     """  if(is30thCelebrationSet(card)||isMee30CelebrationEnergy(card)){\n    sel.value='30° Anniversario';\n    const ps=document.getElementById(edit?'editPlaySeries':'playSeries');\n    if(ps)ps.value='';\n  }"""),
    ("""function migrateFinishStamp(c){\n  if(!c)return c;\n  const old=String(c.variant||'');""",
     """function migrateFinishStamp(c){\n  if(!c)return c;\n  // The two 30th Anniversary sets are foil-only and carry the anniversary edition.\n  // Correct older Cardoryx records that were stored before this exact set rule existed.\n  if(is30thCelebrationSet(c)){\n    c.stamp='30° Anniversario';\n    c.variant='Holo';\n    return c;\n  }\n  const old=String(c.variant||'');"""),
    ("""  // V2.1.31 — 30th Celebration Basic Energies MEE 009–016 are foil-only.\n  // Pokémon explicitly states every 30th Celebration card is foil, including\n  // Basic Energy. Keep the exact edition guard, but expose the real finish.\n  // No database migration and no guessed Cardmarket price are performed here.\n  if(isMee30CelebrationEnergy(card) && stamp==='30° Anniversario'){\n    return new Set(['Holo','Speciale / Altro','Non so']);\n  }""",
     """  // V2.1.40 — the exact 30th / 30th-c sets are foil-only. TCGdex currently\n  // omits per-card finish rows, so the official set rule is the authoritative evidence.\n  // No Cardmarket price is inferred from this finish rule.\n  if(is30thCelebrationSet(card) && stamp==='30° Anniversario'){\n    return new Set(['Holo','Speciale / Altro','Non so']);\n  }\n  // V2.1.31 — 30th Celebration Basic Energies MEE 009–016 are foil-only.\n  // Pokémon explicitly states every 30th Celebration card is foil, including\n  // Basic Energy. Keep the exact edition guard, but expose the real finish.\n  // No guessed Cardmarket price is performed here.\n  if(isMee30CelebrationEnergy(card) && stamp==='30° Anniversario'){\n    return new Set(['Holo','Speciale / Altro','Non so']);\n  }""")
]

for old, new in replacements:
    if old not in s:
        raise SystemExit('missing production patch anchor')
    s = s.replace(old, new, 1)

p.write_text(s, encoding='utf-8')
