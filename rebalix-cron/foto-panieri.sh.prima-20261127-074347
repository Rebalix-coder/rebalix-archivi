#!/bin/bash
# Foto datata e COMPLETA dei panieri (etf_holdings: tutte le posizioni, non solo le top 20
# della history mensile). SOLO LETTURE sul DB; scrive su disco VPS in ~/backups/rebalix-holdings-foto.
# Nata il 21 ago 2026 (decisione Linus: diff entrati/usciti alla revisione MSCI di agosto):
# oggi etf_holdings è UNA riga per ISIN sovrascritta a ogni giro → la foto PRE-revisione va
# conservata prima che il giro del 2/9 la riscriva con quella post-revisione (1 set).
# Uso: foto-panieri.sh [etichetta]   → etf_holdings-<YYYY-MM-DD>[-etichetta].{dump,tsv.gz}
#   .dump  = pg_dump -Fc della sola tabella (ripristinabile in una tabella di lato con pg_restore)
#   .tsv.gz = isin · as_of · n_positions · positions(json) · breakdowns(json): per fare il diff
#             con uno script senza toccare il DB.
set -euo pipefail
set -a; source "$HOME/backups/rebalix-db/.env"; set +a
DEST="$HOME/backups/rebalix-holdings-foto"; mkdir -p "$DEST"
LOG="$DEST/_foto-panieri.log"
OGGI=$(date +%F); ET="${1:-}"; BASE="$DEST/etf_holdings-$OGGI${ET:+-$ET}"
C="host=$PGHOST port=$PGPORT dbname=$PGDATABASE user=$PGUSER password=$PGPASSWORD"
log(){ echo "$(date '+%F %H:%M:%S') $*" | tee -a "$LOG"; }

log "inizio foto panieri → $BASE"
pg_dump "$C" -Fc -t public.etf_holdings -f "$BASE.dump"
printf 'isin\tas_of\tn_positions\tpositions\tbreakdowns\n' > "$BASE.tsv"
psql "$C" -tAc "\\copy (select isin, as_of, n_positions, positions, breakdowns from etf_holdings order by isin) to stdout" >> "$BASE.tsv"
gzip -f "$BASE.tsv"
RIGHE=$(zcat "$BASE.tsv.gz" | wc -l)
ASOF=$(psql "$C" -tAc "select min(as_of)||' → '||max(as_of) from etf_holdings")
log "fatto: $RIGHE righe, as_of $ASOF, $(du -h "$BASE.dump" | cut -f1) dump + $(du -h "$BASE.tsv.gz" | cut -f1) tsv"
md5sum "$BASE.dump" "$BASE.tsv.gz" >> "$DEST/_md5.txt"
# NESSUNA rotazione (decisione Linus 16 set 2026: «conserviamo tutto, può diventare oro un giorno»): le foto complete
# restano per sempre (~60 MB a foto, ~0,7 GB/anno, in B2 col backup). Fino al 16/9 c'era una cancellazione a 24 mesi.
