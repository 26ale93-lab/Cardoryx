# Cardoryx

**Scan · Collect · Build · Value**

Cardoryx è una web app mobile-first per catalogare, organizzare e
valorizzare una collezione di carte Pokémon TCG.

## Versione stabile

**Cardoryx V1.0**

Questa è la prima release stabile ufficiale del progetto.

## Funzioni principali

-   📷 Scanner e ricerca carte con identificazione tramite numero
    carta/set e integrazione TCGdex.
-   📚 Catalogo collezione con immagini ufficiali, quantità e gestione
    dei duplicati.
-   🔎 Ricerca, filtri e ordinamento per tipo, stato, finitura,
    condizione, espansione, quantità, data e valore Cardmarket
    crescente/decrescente.
-   🔢 Numero carta completo nel formato `084/086` quando il totale
    ufficiale del set è disponibile.
-   ✨ Gestione di finiture e varianti.
-   🏷️ Stamp / Edition, incluse le edizioni Play! Pokémon supportate.
-   💰 Valutazione Cardmarket della variante salvata, con gestione
    prudente dei casi non verificabili.
-   🛡️ Protezione consigliata e stato Protetta.
-   📊 Categorie Pokémon, Allenatori ed Energie.
-   🃏 Mazzi da gioco e vendita con allocazione delle copie disponibili.
-   📦 Gestione copie Disponibile, Protetta, Vendita e assegnazioni ai
    mazzi.
-   💾 Backup JSON completo e ripristino di catalogo, mazzi e
    preferenze.
-   📄 Esportazione CSV.
-   🧾 PDF Inventario, Lista collezione ed esportazioni per categoria.
-   📱 Interfaccia mobile-first utilizzabile tramite GitHub Pages/PWA.

## Valori Cardmarket

Cardoryx usa i dati Cardmarket disponibili per fornire un **valore
indicativo di mercato**.

Il sistema distingue varianti e finiture quando l'identificazione è
verificabile. Se non esiste una corrispondenza sufficientemente sicura,
Cardoryx non assegna arbitrariamente il prezzo di un'altra variante e
mostra un valore da verificare/non disponibile.

Il valore mostrato non rappresenta necessariamente il ricavo netto
ottenibile dalla vendita.

## Stati e allocazioni

-   **Disponibile** --- copia utilizzabile o assegnabile.
-   **Protetta** --- copia destinata alla collezione personale.
-   **Vendita** --- copia destinata alla vendita.
-   **Mazzo** --- copia riservata a uno specifico mazzo.

Più copie della stessa carta/variante possono essere mostrate in
un'unica scheda mantenendo separata la loro distribuzione.

## Backup

Il **backup JSON completo** è il formato consigliato per conservare e
trasferire i dati di Cardoryx. Prima di modifiche importanti o
aggiornamenti dell'app è consigliato creare un nuovo backup.

## Esportazioni

Cardoryx può generare CSV completo, PDF Inventario con valori, PDF Lista
collezione senza valori, PDF per singola categoria e PDF di tutte le
categorie ordinate per tipo.

## Fonti dati

Cardoryx utilizza **TCGdex** per i dati del catalogo Pokémon TCG e un
indice Cardmarket per la valorizzazione delle carte quando è disponibile
una corrispondenza verificabile.

Cardoryx è un progetto indipendente e non è affiliato, sponsorizzato o
approvato da The Pokémon Company, Nintendo, Creatures Inc., GAME FREAK o
Cardmarket. Pokémon e i relativi marchi appartengono ai rispettivi
proprietari.

## Struttura del progetto

Il progetto è pensato per essere pubblicato tramite **GitHub Pages**. Il
file HTML principale contiene l'interfaccia e la logica dell'app; gli
asset e i dati ausiliari sono mantenuti nelle relative cartelle del
repository.

## Versioning

La prima release stabile rimane **V1.0**.

Per gli aggiornamenti successivi:

-   **V1.0** --- base stabile ufficiale.
-   **V1.1.0** --- primo aggiornamento o gruppo di miglioramenti della
    V1.0.
-   **V1.1.1, V1.1.2, V1.1.3, ...** --- correzioni e perfezionamenti
    successivi dello stesso ciclo.
-   **V1.2.0, V1.3.0, ...** --- nuovi gruppi significativi di
    funzionalità mantenendo la stessa architettura principale.
-   **V2.0** --- riservata a un futuro cambiamento strutturale
    importante dell'app.

------------------------------------------------------------------------

**Cardoryx V1.0**\
*Scan · Collect · Build · Value*
