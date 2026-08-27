# Cardoryx V2.0 — Cardmarket automatico

Questa versione usa i download pubblici ufficiali Cardmarket.

## File da mettere nel repository
- `index.html`
- `scripts/build_cardmarket_play_index.py`
- `.github/workflows/update-cardmarket-prices.yml`
- cartella `data/`

## Come funziona
1. GitHub Actions scarica il catalogo Pokémon Cardmarket.
2. Scarica il Price Guide Pokémon aggiornato.
3. Collega ogni `idProduct` al relativo prezzo.
4. Costruisce un indice compatto solo per le versioni Play! Pokémon Prize Pack.
5. `index.html` legge `data/cardmarket_play_index.json`.
6. Series 7/8/9 restano prodotti distinti: nessun prezzo viene riciclato tra Series diverse.

## Prima attivazione
Dopo aver caricato i file su GitHub:
Actions → "Aggiorna prezzi Cardmarket" → Run workflow.

Dopo il primo run verrà creato automaticamente:
`data/cardmarket_play_index.json`

Poi l'aggiornamento parte ogni giorno automaticamente.
