# Cardoryx V1.4.2 — Home Fix

Correzione della V1.4.1.

## Corretto
- Ripristinata la funzione `renderHomeDashboard()` accidentalmente rimossa nella V1.4.1.
- La Home torna a leggere il database locale già esistente.
- Ripristinati totale carte, set, Holo/Reverse, protette, valore collezione, carta più preziosa, ultime aggiunte e categorie.
- Mantenuto il sistema valore della V1.4.1.
- Mantenute Poké Ball Reverse Holo e Master Ball Reverse Holo.
- Corretto anche il salvataggio della migrazione delle vecchie denominazioni variante.
- Aggiornata la cache PWA alla V1.4.2.

## Dati
La patch non cancella e non reinizializza `cardoryx_db`.
Le carte già salvate nel browser restano nel database locale.
