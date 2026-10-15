# Rassegna HN

Rassegna quotidiana di [Hacker News](https://news.ycombinator.com): le storie più votate e discusse delle ultime 24 ore, la reazione della community, i tool da provare. Pubblicata ogni mattina su GitHub Pages.

## Come funziona
1. `scripts/hn_daily.py` raccoglie le storie dall'API ufficiale di Hacker News e da [Algolia HN Search](https://hn.algolia.com/api), seleziona le più rilevanti e scarica i commenti.
2. Un modello linguistico (Claude) legge l'articolo quando è raggiungibile e un campione di commenti, e produce sintesi, argomenti pro e contro, commenti migliori e tool citati. Quando l'articolo non è leggibile la notizia è ricostruita dai commenti ed è segnalata.
3. `scripts/assemble.py` verifica l'output: le citazioni devono corrispondere parola per parola ai commenti originali, i link dei tool devono comparire nei dati.
4. `scripts/publish.py` aggiorna `data/` e `feed.xml`; la GitHub Action `email.yml` invia l'edizione per email.

## Avvertenze
- Contenuti generati automaticamente a partire da fonti pubbliche: possono contenere errori. Le affermazioni sono attribuite alle fonti (articolo o commentatori) e non rappresentano opinioni dell'autore del repository.
- Le citazioni sono brevi estratti dei commenti, con autore e link all'originale. Titoli, articoli e commenti appartengono ai rispettivi autori.
- Progetto personale, non affiliato a Hacker News, Y Combinator o alle aziende citate.
- Per correzioni o rimozioni apri una issue.
