# Cardoryx V1.7.2 — Resolver Numero/Totale Fix

Questa versione corregge il vero problema della V1.7.1.

## Causa del bug
Cardoryx provava a filtrare i set TCGdex usando una query `sets?cardCount.official=...`.
La documentazione TCGdex indica che la ricerca dei set non supporta quel filtro lato API.

## Correzione
1. Cardoryx scarica una sola volta l'elenco completo dei set.
2. Filtra localmente `cardCount.official`.
3. Per ogni set compatibile interroga direttamente:
   `/sets/{setId}/{localId}`
4. Verifica di nuovo numero e totale stampato.
5. Se l'API italiana non restituisce la carta, prova anche l'endpoint inglese.
6. Scanner automatico e inserimento manuale usano ESATTAMENTE lo stesso resolver.

## Esempio di test
`146 / 159` deve risolvere direttamente `Ricerca di Brock`.

Se esiste una sola corrispondenza, Cardoryx apre subito la Conferma.
Se esistono più corrispondenze reali, mostra solo quelle.

Il nome OCR resta fuori dal processo di identificazione.
