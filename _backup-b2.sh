#!/bin/bash
# Copia remota SETTIMANALE degli archivi su Backblaze B2 (bucket rebalix-archivi).
# Terza gamba del backup: Mac (vivo) + Time Machine T9 (locale) + GitHub (notturno,
# compresso) + B2 (questo — il magazzino di prospettiva, deciso con Linus 10 ago 2026).
#
# Credenziali in ~/.config/rebalix/b2-backup.env (mai nel repo, mai in chat).
# Connessione ":b2:" al volo: niente rclone.conf, i segreti restano in UN file.
# FUORI dal giro: rebalix/ (dump DB con dati utente — decisione aperta, semmai
# cifrati), rebalix-cestino/, .git/, log. I symlink rclone li ignora da sé.
#
# Battito al guardiano (name: b2-backup) come gli archiviatori: se il giro
# smette di girare o fallisce, email dall'archiver-health quotidiano.
set -u
BASE="$HOME/backups"
LOG="$BASE/_backup-b2.log"
ENVFILE="$HOME/.config/rebalix/b2-backup.env"
REPO="$HOME/progetti/rebalix"
log() { echo "[$(date '+%Y-%m-%d %H:%M')] $*" >> "$LOG"; }

# shellcheck disable=SC1090
source "$ENVFILE" || { log "!! env B2 mancante"; exit 1; }
[ -n "${B2_KEY_ID:-}" ] && [ -n "${B2_APPLICATION_KEY:-}" ] && [ -n "${B2_BUCKET:-}" ] || { log "!! chiavi B2 vuote"; exit 1; }

RCLONE="/opt/homebrew/bin/rclone"
DEST=":b2:${B2_BUCKET}/backups"

log "sync verso B2 ($DEST) — inizio"
# credenziali via AMBIENTE, mai come argomenti: gli argomenti sono visibili
# nella lista processi (ps/pgrep) — lezione del 10 ago, chiave finita in chat
export RCLONE_B2_ACCOUNT="$B2_KEY_ID" RCLONE_B2_KEY="$B2_APPLICATION_KEY"
"$RCLONE" sync "$BASE" "$DEST" \
  --exclude "/.git/**" \
  --exclude "/rebalix/**" \
  --exclude "/rebalix-cestino/**" \
  --exclude "/_*.log" \
  --fast-list --transfers 4 --checkers 8 \
  --stats-log-level NOTICE --stats 5m \
  --log-file "$LOG" --log-level NOTICE
ESITO=$?

# bilancio dal remoto: quanti file e byte risultano davvero su B2
BILANCIO=$("$RCLONE" size "$DEST" --json 2>/dev/null)
log "sync esito=$ESITO · remoto: $BILANCIO"

# battito al guardiano (stesso impianto degli archiviatori)
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
