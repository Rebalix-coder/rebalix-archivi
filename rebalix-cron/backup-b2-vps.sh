#!/bin/bash
# Copia remota SETTIMANALE degli archivi su Backblaze B2 (bucket rebalix-archivi) — VPS.
# Gemello dello script del Mac (Fase 3 migrazione, 14 ago 2026): da oggi la VPS è il
# proprietario UNICO del sync B2 (rclone sync CANCELLA dal remoto ciò che manca in
# locale: due macchine sulla stessa destinazione si mangerebbero i file a vicenda).
#
# Credenziali in ~/.config/rebalix/b2-backup.env (mai nel repo, mai in chat).
# Connessione ":b2:" al volo: niente rclone.conf, i segreti restano in UN file.
# DENTRO il giro: tutti gli archivi + i dump DB CIFRATI (age, decisione Fase 4).
# FUORI: .git del clone sparso, i SEGRETI di rebalix-db (.env), i log.
#
# Battito al guardiano (name: b2-backup, con firma host) come gli archiviatori.
set -u
BASE="$HOME/backups"
LOG="$BASE/_backup-b2.log"
ENVFILE="$HOME/.config/rebalix/b2-backup.env"
REPO="$HOME/progetti/rebalix"
log() { echo "[$(date '+%Y-%m-%d %H:%M')] $*" >> "$LOG"; }

# shellcheck disable=SC1090
source "$ENVFILE" || { log "!! env B2 mancante"; exit 1; }
[ -n "${B2_KEY_ID:-}" ] && [ -n "${B2_APPLICATION_KEY:-}" ] && [ -n "${B2_BUCKET:-}" ] || { log "!! chiavi B2 vuote"; exit 1; }

RCLONE=$(command -v rclone || echo /usr/bin/rclone)
DEST=":b2:${B2_BUCKET}/backups"

log "sync verso B2 ($DEST) — inizio (host $(hostname))"
# credenziali via AMBIENTE, mai come argomenti (visibili in ps — lezione 10 ago)
export RCLONE_B2_ACCOUNT="$B2_KEY_ID" RCLONE_B2_KEY="$B2_APPLICATION_KEY"
"$RCLONE" sync "$BASE" "$DEST" \
  --exclude "/.git/**" \
  --exclude "/rebalix-db/.env" \
  --exclude "/rebalix-db/logs/**" \
  --exclude "/_*.log" \
  --fast-list --transfers 4 --checkers 8 \
  --stats-log-level NOTICE --stats 5m \
  --log-file "$LOG" --log-level NOTICE
ESITO=$?

# bilancio dal remoto: quanti file e byte risultano davvero su B2
BILANCIO=$("$RCLONE" size "$DEST" --json 2>/dev/null)
log "sync esito=$ESITO · remoto: $BILANCIO"

# battito al guardiano (stesso impianto degli archiviatori, con firma host)
SECRET=$(grep '^CRON_SECRET=' "$REPO/.env.local" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
if [ -n "$SECRET" ]; then
  OK=$([ "$ESITO" -eq 0 ] && echo true || echo false)
  ERR=$([ "$ESITO" -eq 0 ] && echo 0 || echo 1)
  curl -s -m 30 -X POST "https://rebalix.com/api/heartbeat" \
    -H "Authorization: Bearer $SECRET" -H "Content-Type: application/json" \
    -d "{\"name\":\"b2-backup\",\"ok\":$OK,\"errors_count\":$ERR,\"metrics\":{\"host\":\"$(hostname)\",\"modules\":{\"sync\":$OK},\"remote\":$([ -n "$BILANCIO" ] && echo "$BILANCIO" || echo null),\"data_date\":\"$(date '+%Y-%m-%d')\"}}" >> "$LOG" 2>&1
  log "heartbeat inviato (ok=$OK)"
else
  log "!! CRON_SECRET non trovato — battito saltato"
fi
exit "$ESITO"
