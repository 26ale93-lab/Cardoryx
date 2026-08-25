# Cardoryx V1.5.2 — Fix Finitura + Stamp + Prezzi

Correzione della V1.5.1.

## Corretto
- La Finitura non contiene più Play! Pokémon / Pokémon Day: questi rimangono solo in Stamp / Edizione.
- Salvataggio Modifica carta: Finitura e Stamp vengono persistiti separatamente.
- Le vecchie carte che avevano lo stamp dentro la variante vengono migrate.
- Il motore prezzi usa ora la combinazione `set + numero + finitura + stamp`.
- Una carta con stamp non eredita più automaticamente il prezzo della carta normale.

## Anita WHT 084 — Play! Pokémon Prize Pack Series Nine
Prezzi Cardmarket verificati il 25/08/2026:
- Normal + Play! Pokémon: trend 0,81 €; minimo 0,40 €; media 7 gg 0,85 €.
- Cosmos Holo + Play! Pokémon: trend 2,36 €; minimo 1,47 €; media 7 gg 2,88 €.

Le carte Allenatore foil della Prize Pack Series Nine usano Cosmos Holofoil.

## Backup
Backup JSON e CSV continuano a includere separatamente Finitura e Stamp / Edizione.
