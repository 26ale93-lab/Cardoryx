# Cardoryx V1.4.3 — Price Fallback

Basata sulla V1.4.2 con Home funzionante.

## Correzione valore nello Scanner
- Mantiene il valore Cardmarket come dato informativo, senza consigli di acquisto.
- Per Holo preferisce i campi Cardmarket Holo.
- Per Reverse Holo / Poké Ball Reverse Holo / Master Ball Reverse Holo:
  1. usa un eventuale prezzo Reverse specifico se presente;
  2. altrimenti usa il prezzo foil/holo Cardmarket disponibile;
  3. altrimenti usa trend/media/prezzo Cardmarket standard come riferimento.
- Se non esiste alcun dato Cardmarket, mostra chiaramente che il prezzo non è disponibile.
- Non modifica né cancella il database locale.
- Home V1.4.2 mantenuta.

Nota: il riferimento di fallback non viene presentato come prezzo esatto della variante Poké Ball/Master Ball.
