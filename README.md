# Cardoryx V1.4.4 — Scanner Price Fix

Correzione mirata del valore nello Scanner.

## Causa individuata
La V1.4.3 chiamava `fetchScanPricing()` ma la funzione non era presente nel file.
Per questo il riquadro rimaneva su “Cerco Cardmarket…” per Normal, Holo e Master Ball.

## Correzioni
- aggiunta `fetchScanPricing()`;
- recupero del record completo TCGdex prima della valutazione;
- tentativo API italiana e fallback API inglese;
- mantenimento dei dati `pricing.cardmarket` nel record selezionato;
- cambio variante = ricalcolo immediato del valore;
- lo stato “Cerco Cardmarket…” termina sempre;
- se Cardmarket non ha dati viene mostrato “Valore non disponibile” invece di restare bloccato;
- Home V1.4.2/V1.4.3 mantenuta;
- database locale non cancellato.

## Varianti
Poké Ball Reverse Holo e Master Ball Reverse Holo continuano a usare il miglior riferimento Cardmarket disponibile quando non esiste un prezzo specifico della variante.
