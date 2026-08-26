# Cardoryx V1.7.1 — Scanner Unico

La V1.7.0 aveva troppi percorsi sovrapposti. Questa versione ne mantiene uno solo.

## Flusso
1. Scatta/carica foto.
2. Premi una sola volta `Riconosci carta`.
3. Cardoryx legge Numero / Totale set.
4. Verifica direttamente con TCGdex.
5. Se trova una sola carta, passa direttamente alla Conferma.
6. Se ci sono più corrispondenze, mostra soltanto i candidati reali.
7. Se non riesce, compare un unico fallback con due campi numerici.

Non esistono più tre ricerche successive automatiche.
Il nome OCR non viene usato per avviare altre ricerche.

Esempio: `146 / 159` → TCGdex → Ricerca di Brock → Conferma.

Database, prezzi, Play! Pokémon, backup e catalogo restano invariati.
