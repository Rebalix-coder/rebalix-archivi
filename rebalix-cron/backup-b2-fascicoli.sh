#!/bin/bash
# Backup GIORNALIERO di ~/fascicoli su B2 con conservazione delle versioni (16 ott 2026, GO Linus).
# I fascicoli sono il repository delle prove (verbali, grezzi conservati, fotografie «prima», strumenti): fino a oggi NON erano
# in nessun backup. rclone sync + --backup-dir: ogni file sovrascritto o cancellato sulla VPS viene SPOSTATO nella cartella delle
# versioni datata (mai perso); le versioni si conservano per RETENTION_GIORNI dall'ARCHIVIAZIONE. In più il bucket B2 non ha
# regole di ciclo di vita: conserva tutte le versioni dei file (rclone --b2-versions). Battito «b2-fascicoli» al guardiano
# (ok/errore); un backup non eseguito = battito assente = segnalazione del guardiano (voce attesa giornaliera).
# LIMITE (auditor 16/10): il backup conserva gli STATI acquisiti alle 23:55, non ogni esecuzione: un file creato e sovrascritto
# nella stessa giornata non è recuperabile da qui → gli strumenti devono scrivere con nome univoco (data/ora) e mai sovrascrivere.
set -u
SRC="$HOME/fascicoli"
BASE="$HOME/backups"
LOG="$BASE/_backup-b2-fascicoli.log"
ENVFILE="$HOME/.config/rebalix/b2-backup.env"
REPO="$HOME/progetti/rebalix"
RETENTION_GIORNI=365
log() { echo "[$(date '+%Y-%m-%d %H:%M:%S%z')] $*" >> "$LOG"; }

source "$ENVFILE" || { log "!! env B2 mancante"; exit 1; }
[ -n "${B2_KEY_ID:-}" ] && [ -n "${B2_APPLICATION_KEY:-}" ] && [ -n "${B2_BUCKET:-}" ] || { log "!! chiavi B2 vuote"; exit 1; }
[ -d "$SRC" ] || { log "!! sorgente $SRC assente"; exit 1; }

RCLONE=$(command -v rclone || echo /usr/bin/rclone)
DEST=":b2:${B2_BUCKET}/fascicoli"
VERSIONI=":b2:${B2_BUCKET}/fascicoli-versioni/$(date +%Y-%m-%d_%H%M%S)"
export RCLONE_B2_ACCOUNT="$B2_KEY_ID" RCLONE_B2_KEY="$B2_APPLICATION_KEY"

N_LOCALI=$(find "$SRC" -type f | wc -l)
log "sync $SRC -> $DEST (versioni in $VERSIONI) - inizio - file locali $N_LOCALI"
"$RCLONE" sync "$SRC" "$DEST" \
  --backup-dir "$VERSIONI" \
  --fast-list --transfers 4 --checkers 8 \
  --stats-log-level NOTICE --stats 5m \
  --log-file "$LOG" --log-level NOTICE
ESITO=$?

# versioni piu vecchie della conservazione dichiarata: la retention decorre dall'ARCHIVIAZIONE della versione (data nel
# nome della cartella), NON dalla data di modifica del file (rclone --min-age userebbe quella: un file con mtime vecchio
# appena entrato nelle versioni sarebbe cancellato subito — rettifica auditor 16/10). Si eliminano intere cartelle datate.
LIMITE=$(date -d "-${RETENTION_GIORNI} days" +%Y-%m-%d)
for d in $("$RCLONE" lsf ":b2:${B2_BUCKET}/fascicoli-versioni" --dirs-only 2>/dev/null | tr -d /); do
  g=${d:0:10}
  case "$g" in [0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]) ;; *) continue ;; esac
  if [[ "$g" < "$LIMITE" ]]; then log "versioni: elimino la cartella $d (archiviata prima del $LIMITE)"; "$RCLONE" purge ":b2:${B2_BUCKET}/fascicoli-versioni/$d" --log-file "$LOG" --log-level NOTICE 2>/dev/null; fi
done

BILANCIO=$("$RCLONE" size "$DEST" --json 2>/dev/null)
N_REMOTI=$(echo "$BILANCIO" | grep -o '"count":[0-9]*' | cut -d: -f2)
log "sync esito=$ESITO - locali $N_LOCALI - remoti ${N_REMOTI:-?} - remoto: $BILANCIO"
# conteggio riconciliato: locali = remoti, altrimenti errore dichiarato
if [ "$ESITO" -eq 0 ] && [ -n "${N_REMOTI:-}" ] && [ "$N_REMOTI" -ne "$N_LOCALI" ]; then log "!! conteggio NON riconciliato (locali $N_LOCALI, remoti $N_REMOTI)"; ESITO=3; fi

SECRET=$(grep '^CRON_SECRET=' "$REPO/.env.local" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
if [ -n "$SECRET" ]; then
  OK=$([ "$ESITO" -eq 0 ] && echo true || echo false)
  ERR=$([ "$ESITO" -eq 0 ] && echo 0 || echo 1)
  curl -s -m 30 -X POST "https://rebalix.com/api/heartbeat" \
    -H "Authorization: Bearer $SECRET" -H "Content-Type: application/json" \
    -d "{\"name\":\"b2-fascicoli\",\"ok\":$OK,\"errors_count\":$ERR,\"metrics\":{\"host\":\"$(hostname)\",\"modules\":{\"sync\":$OK},\"file_locali\":$N_LOCALI,\"file_remoti\":${N_REMOTI:-0},\"retention_giorni\":$RETENTION_GIORNI,\"esito\":$ESITO}}" >/dev/null
  log "heartbeat b2-fascicoli inviato (ok=$OK)"
else
  log "!! CRON_SECRET non trovato - battito saltato"
fi
exit "$ESITO"
