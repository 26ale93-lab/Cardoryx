# Cardoryx V1.8.0 — Dynamic Play Price Resolver

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


## V1.7.6 — Play! Prize Pack Resolver
Corretto il resolver del catalogo Play! Pokémon: i nomi set normalizzati (spazi/accenti rimossi) ora corrispondono alle chiavi leggibili del catalogo. Esempio verificato: Ricerca di Brock 146/159, Avventure Insieme, Prize Pack Series 9 → trend Cardmarket 0,16 €.


## V1.7.6 — Resolver set recenti / fallback IT+EN
- Ricerca manuale Numero/Totale interroga sia TCGdex IT sia EN.
- Cerca prima per localId e valida il totale set, evitando la scansione pesante di tutti i set.
- Hydration della carta con fallback EN per espansioni recenti non ancora complete nel catalogo IT.
- Correzione mirata al caso Riolu 076/132 (Megaevoluzione) e casi analoghi.


## V1.8.0 — Dynamic Play Price Resolver
- aggiunto Riolu Megaevoluzione 076/132 nel catalogo Play! Pokémon Prize Pack Series 9;
- prezzo Cardmarket verificato: da 1,30 €, trend 2,39 € al 26/08/2026;
- il selettore Prize Pack ora limita le Series quando la carta è già presente nel catalogo verificato;
- Riolu 076/132 consente quindi Series 9 e non serie incompatibili;
- per carte non ancora catalogate il menu resta libero, così non vengono inventate compatibilità.


## V1.7.8 — Ricerca senza foto
- Il blocco Numero carta + Totale set è sempre visibile nello Scanner.
- La ricerca funziona anche senza aver scattato una foto.
- Il resolver Numero/Totale e il Play Variant Validator restano invariati.


## V1.8.0 — stabilizzazione prezzi Play!

- Le carte Play! con più versioni Cardmarket e senza trend univoco mostrano ora un **intervallo reale di offerte** invece di un generico “Valore da verificare”.
- Aggiunto il prezzo verificato di **Energia Fighting Rocciosa 087/094 — Equilibrio Perfetto — Prize Pack Series 9, Versione 1**.
- Il valore della collezione non usa automaticamente il punto medio di un intervallo: evita di gonfiare o abbassare la collezione con una stima arbitraria.
- Scanner e ricerca Numero carta + Totale set restano invariati.


## V1.8.0 — Dynamic Play Price Resolver
- Il prezzo Play!/Prize Pack non dipende più soltanto dal catalogo locale.
- Quando manca un valore, l’app tenta una ricerca live su Cardmarket per Series + set + numero.
- Gestisce V1/V2 usando la finitura selezionata quando possibile.
- Memorizza il risultato sulla carta per usarlo nel catalogo anche dopo il salvataggio.
- “Aggiorna valori” tenta anche di aggiornare le carte Play! già salvate.
- Se esistono più versioni e la finitura non basta a distinguerle, mostra un intervallo senza inventare un prezzo unico.
