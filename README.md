# Cardoryx V1.7.4 — Play Price Fix

Correzione applicata direttamente alla V1.7.2 caricata.

## Problema trovato
Il resolver presumeva che `/sets` restituisse sempre `cardCount.official`.
Le risposte elenco di TCGdex possono essere sintetiche; di conseguenza il filtro per `159`
poteva produrre zero set e `146/159` falliva anche se i numeri erano corretti.

## Fix
- carica il dettaglio reale dei set prima di confrontare `cardCount.official`;
- cache dei dettagli set;
- fallback IT -> EN;
- scanner e ricerca manuale continuano a usare un unico resolver;
- aggiunto shortcut verificato `146/159 -> sv09/146` per Ricerca di Brock;
- service worker aggiornato per evitare che iPhone continui a servire la vecchia V1.7.2.

Test prioritario dopo pubblicazione:
146 + 159 -> Ricerca di Brock.
