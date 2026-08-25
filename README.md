# Cardoryx V1.4.9 — Varianti intelligenti + Backup completo

Basata sulla V1.4.7 Unified Price Engine.

Il Backup JSON completo include carte, quantità, stato, condizione, variante, note, ID TCGdex, riferimenti immagine, dati pricing Cardmarket/TCGdex, snapshot del valore unitario/totale, fonte e data valore, totale collezione, mazzi e preferenze Scanner rapido.

Il ripristino supporta sia il nuovo formato completo sia i vecchi backup composti dal solo array delle carte.

Il CSV completo include anche ID TCGdex, note, valore unitario e totale, fonte, variante verificata, data aggiornamento, trend/minimo/media 7gg/media 30gg Cardmarket e immagine.


## V1.4.9
- Preselezione automatica della variante quando TCGdex indica una sola stampa disponibile (Normal/Holo/Reverse).
- Supporto UI per Pokémon Day Stamp e Play! Pokémon Stamp.
- Preparazione al campo TCGdex variants_detailed: stamp/foil vengono usati quando disponibili.
- Il prezzo delle varianti speciali resta separato: nessun moltiplicatore inventato.
- Backup/CSV continuano a salvare la stringa variante e quindi preservano anche le nuove varianti.
