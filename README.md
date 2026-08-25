# Cardoryx V1.4.7 — Unified Price Engine

Basata sulla V1.4.5 / Scanner Price Fix.

## Correzione principale
Poké Ball Reverse Holo e Master Ball Reverse Holo non devono usare automaticamente il prezzo standard della carta.

Cardoryx ora ha un registro estendibile di prezzi variante verificati su Cardmarket.

### Okidogi — Evoluzioni Prismatiche 057
Dati verificati il 25/08/2026:

- Normal: trend 0,13 € · minimo 0,02 € · media 7 gg 0,11 €
- Poké Ball Reverse Holo: trend 0,42 € · minimo 0,05 € · media 7 gg 0,42 €
- Master Ball Reverse Holo: trend 6,61 € · minimo 1,99 € · media 7 gg 6,87 €

Quando esiste un prezzo specifico verificato, Cardoryx lo mostra come tale.
Quando non esiste, un eventuale prezzo TCGdex/Cardmarket viene indicato esplicitamente come riferimento generico, non come prezzo certo della variante.

## Modifica carta
Corretto anche il vero menu Variante nella finestra Modifica:
- Normale
- Holo
- Reverse Holo
- 🔴 Poké Ball Reverse Holo
- 🟣 Master Ball Reverse Holo
- Cosmos Holo
- Speciale / Altro
- Non so

## Nota
Il registro è volutamente prudente: nuovi prezzi specifici possono essere aggiunti solo dopo verifica della corrispondente pagina Cardmarket, evitando di attribuire valori errati a Master Ball/Poké Ball.


## V1.4.7 — Unified Price Engine
- Unificato il calcolo prezzi tra Home, Catalogo, Scanner, Dettagli e totale collezione.
- Le varianti con prezzo Cardmarket verificato usano lo stesso valore in ogni schermata.
- Okidogi 057 Master Ball Reverse Holo: trend verificato 6,61 € in tutte le viste.
- Il fallback TCGdex/Cardmarket resta attivo solo quando non esiste un prezzo variante verificato.
