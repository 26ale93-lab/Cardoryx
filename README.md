# Cardoryx V1.5.3 — Prize Pack Series + Dettagli + Energie

Basata sulla V1.5.2.

## Play! Pokémon
Aggiunto un campo separato `Prize Pack Series` quando Stamp / Edizione = Play! Pokémon.

Valori disponibili:
- Series 1–9
- Da identificare

Il motore prezzi ora usa:
`set + numero + finitura + stamp + Prize Pack Series`

Se la serie non è indicata, Cardoryx non assegna un prezzo standard e mostra che la Prize Pack Series va identificata.

### Zoroark-ex di N 098/159
Inseriti riferimenti Cardmarket verificati per:
- Holo + Play! Pokémon + Series 7
- Holo + Play! Pokémon + Series 8
- Holo + Play! Pokémon + Series 9

## Dettagli carta
Il pannello Dettagli e i Consigli usano ora lo stesso motore `cardPriceInfo()` del Catalogo/Home.

## Energie
Corretto il raggruppamento:
- Energia base → Energie Base
- altre energie, come Energia Rocciosa → Energie Speciali

## Backup
CSV e backup mantengono anche la Prize Pack Series.
