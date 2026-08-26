# Cardoryx V1.7.0 — Collector Code Scanner

Cambio del metodo di riconoscimento.

## Nome OCR disattivato
Il nome non viene più usato per identificare automaticamente la carta.
Tesseract.js può leggere male font, foil, riflessi e testi stilizzati.

## Flusso
1. Cardoryx legge la zona Numero / Totale set.
2. Verifica il codice con TCGdex.
3. Mostra le carte reali compatibili.
4. Il nome viene preso dal database TCGdex.
5. Se Numero/Set non viene letto, Cardoryx chiede soltanto i due numeri manualmente.

Esempio:
`146 / 159` → TCGdex → `Ricerca di Brock`.

Il vecchio OCR del nome non può più generare stringhe casuali e far scegliere la carta sbagliata.

Database, prezzi, Play! Pokémon, catalogo e backup restano invariati.
