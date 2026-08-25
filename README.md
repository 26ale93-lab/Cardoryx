# Cardoryx V3.2

Hotfix OCR ottimizzato per iPhone/Safari.

- OCR eseguito solo su due piccole zone della carta
- elaborazione sequenziale per ridurre il picco di memoria
- priorità al codice numero/totale set (es. 055/159)
- fallback manuale se OCR non riesce
- mantiene catalogo, backup, PWA e funzioni V3.1


## V3.3 — Candidate Selection Fix
- I pulsanti "È questa" non contengono più i dati completi della carta.
- Ogni candidato riceve un ID interno sicuro (`cand_0`, `cand_1`, ...).
- Accenti, apostrofi, abilità e testo italiano non possono più rompere il click.
- La carta selezionata deve corrispondere esattamente al pulsante premuto.
- Cache PWA aggiornata a `cardoryx-v3.3.0`.


## V3.4 — Kilowattrel fix + OCR name cleanup
- Correzione reale di `chooseCard`: ora accetta direttamente l'oggetto candidato.
- Il pulsante "È questa" di Kilowattrel usa esattamente lo stesso percorso degli altri candidati.
- OCR nome più stretto: esclude FASE/PS e numeri laterali.
- Se più carte condividono lo stesso codice (es. 055/159), Cardoryx non assegna più un falso "PIÙ PROBABILE" senza un nome affidabile.
- Cache aggiornata a `cardoryx-v3.4.0`.


## V3.5 — Smart Name Normalization
- Il nome OCR non deve più essere perfetto.
- Esempio: `7 Kilowattrel di Kissara ra 204` viene confrontato con i candidati `055/159`.
- Se il nome ufficiale `Kilowattrel di Kissara` è contenuto nel testo OCR, Cardoryx lo normalizza automaticamente.
- Se numero/totale + nome ufficiale identificano una sola carta, Cardoryx la apre direttamente in Conferma.
- OCR palesemente inutili vengono ignorati invece di sporcare il campo Nome.
- Rimane sempre disponibile la selezione manuale dei candidati.
- Cache PWA: `cardoryx-v3.5.0`.


## V3.6 — Guida condizioni
- Condizioni semplificate: NM, EX, GD, PL, PO.
- Pulsante `?` accanto a Condizione.
- Guida rapida integrata nell'app con descrizione di ogni stato.
- Suggerimento per le carte appena aperte e ben conservate.
- Mantiene tutte le correzioni V3.5 sul riconoscimento OCR e sulla selezione intelligente.
- Cache PWA: `cardoryx-v3.6.0`.


## V3.7 — Catalog + Save Fix
- Corretto conflitto Safari con `window.status`: lo stato viene letto dal select `#status`.
- Corretto Catalogo vuoto.
- Corretto conteggio Disponibili / Protette / Mazzi.
- Salva si disattiva subito per impedire doppi tap.
- Se la stessa carta/variante/stato/condizione esiste già, non aumenta più automaticamente la quantità.
- Aggiunti Modifica quantità ed Elimina nel Catalogo.
- Migrazione una tantum: se il catalogo pre-V3.7 contiene un solo record gonfiato dai test, viene riportato a quantità 1.
- Cache PWA: `cardoryx-v3.7.0`.


## V4.0 — Stable UI + Duplicati
- Ricostruita la barra inferiore a 5 sezioni usando lo stesso sistema `showView` per tutte.
- Impostazioni ora è una vera schermata nativa dell'app.
- Backup CSV/JSON e Import spostati esclusivamente in Impostazioni.
- Reset catalogo protetto da seconda conferma.
- Duplicato: se stessa carta + variante + stato + condizione esiste già, Cardoryx chiede se aggiungere un'altra copia; confermando aumenta `×1 → ×2`.
- Modifica carta completa: quantità, variante, stato e condizione.
- Tap sull'immagine nel Catalogo apre la carta ingrandita.
- Tap su una categoria apre il Catalogo già filtrato.
- Archivio canonico `cardoryx_db`.
- Cache PWA `cardoryx-v4.0.0`.


## V4.1 — Catalogo ridisegnato + fix quantità
- Corretto il bug che impediva di salvare una nuova quantità dalla finestra Modifica.
- Catalogo ridisegnato con schede più pulite e leggibili.
- Immagine più grande e cliccabile per lo zoom.
- Badge per tipo, variante, condizione e stato.
- Quantità modificabile direttamente con `−` e `+`.
- Modifica completa ed Elimina restano disponibili.
- Riepilogo delle schede e del numero totale di carte visibili.
- Cache PWA `cardoryx-v4.1.0`.


## V4.2 — Categorie redesign
- Nuova schermata Categorie a schede visive.
- Ogni categoria mostra icona, nome e conteggio.
- Colori distinti per tipo/categoria.
- Tap sulla scheda apre il Catalogo già filtrato.
- Layout responsive: 2 colonne su iPhone, 3 su schermi più larghi.
- Cache PWA `cardoryx-v4.2.0`.
