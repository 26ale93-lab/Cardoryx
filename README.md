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


## V4.3 — Catalogo Pro
- Nuovi filtri: variante e condizione.
- Ordinamento per nome, recenti, quantità ed espansione.
- Pulsante Pulisci filtri.
- Scheda Dettagli carta con immagine, dati e note personali.
- Le note vengono salvate nel catalogo e sono ricercabili.
- Statistiche rapide: schede uniche, copie totali, holo/speciali, NM.
- Mantiene categorie visuali V4.2, duplicati e quantità.
- Cache PWA `cardoryx-v4.3.0`.


## V4.4 — Note persistenti + scorrimento automatico
- Corrette le note personali: ora vengono salvate direttamente nel database locale e restano associate alla specifica scheda/variante.
- Chiave record stabile basata su carta + variante + stato + condizione, usata anche da Modifica, Quantità ed Elimina.
- Dopo `È questa` Cardoryx scorre automaticamente alla sezione Conferma con variante, stato, condizione e Salva.
- Il pulsante candidato mostra `È questa ↓` per rendere evidente lo spostamento.
- Cache PWA `cardoryx-v4.4.0`.


## V4.5 — Scanner Pro
- Foto ridimensionata automaticamente prima dell'OCR per ridurre memoria su iPhone.
- OCR su due sole aree: nome e numero/set.
- Le due zone vengono processate una alla volta, non in parallelo.
- Lettura più tollerante di codici come 055/159.
- Barra di avanzamento e messaggi di stato.
- Guida visiva sulla foto per nome e numero/set.
- Massimo 6 candidati mostrati.
- Fallback manuale se l'OCR non è affidabile.
- Cache PWA `cardoryx-v4.5.0`.


## V4.6 — Scanner Cascade
- Ricerca automatica a cascata: Numero/Set → Nome + Set → Nome.
- Se Numero/Set non trova la carta, Cardoryx passa automaticamente a Nome + Set.
- Se resta una sola corrispondenza, apre direttamente la conferma.
- Mostra visivamente quale strategia di ricerca sta usando.
- Mantiene il ridimensionamento OCR e l'elaborazione leggera della V4.5.
- Massimo 6 candidati.
- Cache PWA `cardoryx-v4.6.0`.


V4.7 Name-First: scanner ranking priority changed to Name > Set > Number. Collector code is fallback only when no usable name is available.


## V4.8 — Ricerca numerica normalizzata
- `14`, `014` e altre forme con zeri iniziali sono trattate come lo stesso numero.
- `94` e `094` sono trattati come lo stesso totale set.
- La ricerca solo numero/set prova automaticamente tutte le varianti del `localId`.
- Prima di filtrare per totale set, Cardoryx recupera i dettagli completi dei candidati.
- Se numero/set non trova nulla, il messaggio suggerisce Nome + Set.
- Mantiene il ranking Name-first della V4.7.
- Cache PWA `cardoryx-v4.8.0`.


## V4.9.1 — Strict Set Hotfix
- Ripristinato il JavaScript rotto nella V4.9.
- Con Nome vuoto, Numero + Totale Set sono filtri obbligatori.
- 14/94 equivale a 014/094.
- Le carte con stesso numero ma totale set diverso vengono escluse.
- Nessun allargamento automatico della ricerca numerica se Nome è vuoto.
- Cache PWA `cardoryx-v4.9.1`.


## V5.0 — Motore ricerca deterministico
- Corretto il bug che impediva la ricerca solo Numero + Totale Set.
- Nome = identità primaria della carta.
- Totale Set = filtro reale, non semplice punteggio.
- Numero = conferma finale.
- Senza nome, Numero + Totale Set vengono cercati come coppia esatta.
- Ricerca del codice stampato: individua prima i set con `cardCount.official`, poi cerca la carta dentro il set.
- Fallback alla ricerca `localId`.
- Una sola corrispondenza esatta apre direttamente Conferma.
- Cache PWA `cardoryx-v5.0.0`.


## V5.1 — Ricerca libera + Browser set
- Solo Numero: mostra tutte le carte con quel numero nei diversi set.
- Solo Totale Set: mostra i set compatibili.
- Ogni set ha il pulsante `Vedi set completo`.
- Il set completo viene caricato a blocchi di 12 carte con `Carica altre`.
- Numero + Totale Set mantiene la ricerca precisa V5.0.
- Nome resta prioritario quando presente.
- Cache PWA `cardoryx-v5.1.0`.


## V5.2 — Zoom immagini
- Tocca l'immagine di una carta nei risultati per aprirla a schermo quasi intero.
- Funziona anche nel browser del set.
- Prova automaticamente l'immagine `high.webp`, con fallback alla versione già caricata.
- Chiusura con X o tocco fuori dall'immagine.
- Cache PWA `cardoryx-v5.2.0`.


## V5.3 — Zoom Catalogo
- Zoom attivo anche sulle carte già salvate nel Catalogo.
- Zoom attivo anche nella scheda Dettagli della carta posseduta.
- Tocco sull'immagine: apre a schermo grande.
- Tocco in qualsiasi area esterna alla carta: chiude.
- Tocco direttamente sulla carta ingrandita: resta aperta.
- Cache PWA `cardoryx-v5.3.0`.


## V5.4 — Scansione Rapida
- Nuovo interruttore `Scansione rapida`.
- Predefiniti persistenti per Variante, Condizione e Stato.
- Dopo Salva passa automaticamente alla foto successiva della coda.
- Se la modalità rapida è attiva, avvia automaticamente l'OCR sulla carta successiva.
- Indicatore della coda e del numero di carte rimanenti.
- Gestione duplicati invariata: chiede prima di aumentare la quantità.
- Cache PWA `cardoryx-v5.4.0`.


## V5.5 — Scanner continuo
- Nuova modalità `Scanner continuo` pensata per catalogare fisicamente una carta alla volta.
- Flusso: Scatta carta → OCR → scegli/conferma → Salva → riapertura fotocamera → carta successiva.
- Usa gli stessi predefiniti di Variante, Condizione e Stato della scansione rapida.
- Il salvataggio di un duplicato mantiene la richiesta di conferma.
- Pulsante `Ferma` per terminare la sessione.
- La riapertura della fotocamera avviene dopo il salvataggio; su iOS il comportamento finale dipende dalle regole di Safari/PWA per l'apertura del selettore fotocamera.
- Cache PWA `cardoryx-v5.5.0`.


## V5.6 — OCR nome assistito
- Il nome viene letto con due passaggi OCR su una zona stretta.
- Un passaggio usa l'immagine normale, uno usa una versione ad alto contrasto.
- Cardoryx sceglie automaticamente la lettura OCR più pulita.
- Se numero + totale set producono un piccolo gruppo di candidati, il nome OCR viene confrontato con i nomi ufficiali.
- Un OCR rumoroso viene normalizzato al nome ufficiale quando il match è abbastanza forte.
- Se numero + totale set identificano una sola carta, il nome ufficiale viene usato direttamente.
- Scanner continuo invariato.
- Cache PWA `cardoryx-v5.6.0`.
