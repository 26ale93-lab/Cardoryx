# Cardoryx V1.0 — Stable

Cardoryx è una web app/PWA per catalogare, organizzare e valorizzare una collezione di carte Pokémon.

## Stato

**Versione stabile:** V1.0

Questa versione è la baseline ufficiale del progetto. Le versioni successive dovranno partire da questa base stabile.

## Funzioni principali

- Scanner fotografico da fotocamera o rullino
- OCR per nome, numero e totale set
- Ricerca intelligente con priorità Numero/Set e fallback sul nome
- Scanner rapido e scanner continuo
- Catalogo personale con quantità
- Gestione duplicati
- Stato carta: Disponibile / Protetta / Nei mazzi
- Condizione carta
- Variante: Normale / Holo / Reverse e altre varianti supportate
- Note personali
- Modifica ed eliminazione delle carte
- Zoom immagini
- Ritaglio e raddrizzamento della foto personale
- Categorie e filtri
- Energie Base MEE 001–008 con immagini dedicate
- Backup JSON
- Importazione JSON
- Esportazione CSV
- Valori Cardmarket tramite dati TCGdex
- Aggiornamento prezzi
- Valore totale della collezione
- Carta più preziosa
- Home Dashboard con statistiche rapide
- Ultime carte aggiunte
- Categorie rapide cliccabili
- Supporto PWA con manifest e service worker

## Home Dashboard

La Home mostra:

- valore totale indicativo della collezione
- numero totale di carte
- numero di set
- numero di Holo/Reverse
- numero di carte protette
- accessi rapidi a Scanner, Catalogo e Cerca
- carta più preziosa
- ultime carte aggiunte
- categorie principali della collezione

## Valore delle carte

Cardoryx usa i dati prezzo disponibili tramite TCGdex/Cardmarket.

Quando disponibili, i valori sono associati alla carta tramite il relativo ID TCGdex. Per le carte già salvate senza ID, Cardoryx prova a migrare automaticamente il record usando nome, numero e set.

Se non esiste un prezzo attendibile, Cardoryx mostra **Valore non disponibile**.

## Energie Base MEE

Sono supportate le Energie Base MEE:

- 001 Erba
- 002 Fuoco
- 003 Acqua
- 004 Lampo
- 005 Psico
- 006 Lotta
- 007 Oscurità
- 008 Metallo

## Installazione su GitHub Pages

Caricare nella root del repository questi 8 file:

- `index.html`
- `manifest.webmanifest`
- `sw.js`
- `README.md`
- `cardoryx-logo.png`
- `apple-touch-icon.png`
- `icon-192.png`
- `icon-512.png`

Dopo l'upload, attendere l'aggiornamento di GitHub Pages e ricaricare la pagina.

Su iPhone, se una versione precedente resta in cache, chiudere e riaprire Safari/PWA oppure effettuare un nuovo refresh della pagina.

## Backup consigliato

Prima di modificare il codice o caricare una nuova versione:

1. aprire Cardoryx;
2. entrare in Impostazioni;
3. creare un **Backup JSON**;
4. conservarlo prima di aggiornare l'app.

## Versionamento

Da questa release:

- `V1.0` = prima versione stabile
- `V1.1`, `V1.2`, ecc. = miglioramenti compatibili
- `V2.0` = eventuale evoluzione strutturale importante

---

Cardoryx — Scan · Collect · Build · Value
