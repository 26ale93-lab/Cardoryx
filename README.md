# Cardoryx V1.5.4 — Hotfix Home, Salvataggi e Play! Pokémon

## Correzioni
- Ripristinata `renderHomeDashboard()`: era assente nella V1.5.3 e causava il crash della Home.
- Il crash della Home interrompeva anche `persist()` durante Modifica carta, per questo il popup poteva non chiudersi.
- Il salvataggio da Scanner ora scrive realmente nel database:
  - Finitura
  - Stamp / Edizione
  - eventuale Prize Pack Series
- Il riconoscimento dei duplicati distingue anche Stamp e Prize Pack Series.
- Salvataggio Modifica carta reso più robusto: chiude il popup prima del rendering.
- `persist()` salva comunque i dati anche se una sezione dell'interfaccia dovesse avere un errore.
- Migliorato il riconoscimento delle Energie Speciali.

## Prize Pack Series
La serie NON è obbligatoria.

Il logo Play! Pokémon stampato sulla carta non contiene il numero della Prize Pack Series, quindi dalla sola carta spesso non è possibile sapere se è Series 7, 8, 9 ecc.

Puoi lasciare:
`Non so / lascia automatico`

Cardoryx conserva comunque correttamente:
`Finitura + Play! Pokémon`.

La serie va compilata solo quando è stata identificata con certezza tramite la specifica ristampa/database Cardmarket.
