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
