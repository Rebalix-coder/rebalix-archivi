# Archivio documenti white list (D.L. 138/2011)

Documenti fiscali ORIGINALI degli emittenti, da cui sono estratte le quote in `etf_whitelist`.

## Perché esiste
Scoperto il 21 luglio 2026 raccogliendo gli storici: **gli emittenti cancellano i documenti
vecchi**. BlackRock e SPDR ne tengono ~3 semestri; l'H1-2025 di entrambi non è più scaricabile
da nessuna parte — nemmeno dagli archivi del web. Invesco invece conserva dal 2019.

Prima salvavamo solo i NUMERI nel database. Questo archivio conserva la FONTE: è l'unica prova
di provenienza, e per i semestri già cancellati dagli emittenti è irripetibile.

## Come si popola
Automaticamente: `scripts/ingest-etf-whitelist.mjs` copia qui ogni file ingerito
(`emittente_ANNO-Hn.ext`). Non sovrascrive: se il semestre c'è già, lo dice e basta.

## Dove vivono le copie (aggiornato 22 lug 2026)
Questa cartella è un collegamento: i file veri stanno in `~/Documents/Rebalix-archivi/whitelist-docs`
→ **sincronizzati su iCloud** + coperti da **Time Machine** (SSD TM_T9). Funziona perché
l'ingestione è sempre INTERATTIVA (il terminale ha il permesso su Documenti).

## ⚠️ Perché gli archivi LifeStrategy/Xtrackers NON stanno qui
Provato il 21 lug, rotto il 22: macOS protegge ~/Documents e i processi **launchd** (gli
archiviatori automatici) ricevono `PermissionError` attraversando il collegamento — 16 errori
nel run delle 10:30, guardiano scattato. Riportati in `~/backups/` (percorso non protetto);
lì li copre Time Machine, orario e versionato. **Regola: mai spostare in Documenti dati
scritti da launchd — e collaudare nel contesto VERO (`launchctl kickstart`), non dal
terminale, che ha permessi diversi.**

## Contenuto
Nomi: `emittente_ANNO-Hn.xlsx|pdf` — es. `invesco_2021-H1.xlsx`.
Amundi H1-2025 è il file «Totali» (include anche i fondi comuni); `amundi_2026-H1.pdf` è il
documento dell'area investitori qualificati.

## Audit di coerenza (dal 28 lug 2026)
`node scripts/ingest-etf-whitelist.mjs --audit` confronta questo archivio col DB nei due sensi
(documento senza ingest, ingest senza documento, cali di righe >40%, semestri bucati) e gira
da solo in coda a ogni ingest. Nato dal buco Amundi H1-2026: PDF archiviato il 21/7, ingest
mai partito, scoperto per caso una settimana dopo. I buchi di fonte noti (JPM, Vanguard) sono
censiti nello script (`BUCHI_NOTI`) e non allarmano.
