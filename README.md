# Cardoryx V1.5.5 — Valutazione sicura Play! Pokémon

Basata sulla V1.5.4 stabile.

## Nuova logica valore
Cardoryx distingue:
1. `Valorizzata` — prezzo specifico disponibile.
2. `Valore da verificare` — soprattutto Play! Pokémon con più possibili ristampe/serie.
3. `Valore non disponibile` — nessuna quotazione specifica disponibile.

Una carta senza prezzo NON vale 0 € e NON riceve automaticamente il prezzo della versione normale.

## Totale collezione
Le carte senza prezzo specifico vengono escluse dal totale numerico.
La Home mostra anche quante carte restano da valutare, comprese le Play! da verificare.

Esempio:
`125,40 € + 4 carte da valutare (3 Play! da verificare)`

## Scanner
Se una Play! Pokémon non ha una corrispondenza di prezzo specifica:
- mostra `Valore da verificare`;
- non applica il prezzo standard;
- permette comunque di salvare la carta.

## Prize Pack Series
Rimane opzionale. Il logo Play! Pokémon non indica da solo il numero della serie.

## Backup
Il backup salva anche il numero di carte senza prezzo e delle Play! da verificare.
