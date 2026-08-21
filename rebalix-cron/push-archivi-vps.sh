#!/bin/bash
# Push quotidiano archivi VPS → GitHub rebalix-archivi (doppio pusher col Mac,
# percorsi disgiunti). Liturgia: commit → pull --rebase → push; sparse checkout
# limitato alle cartelle di cui QUESTA macchina è proprietaria.
set -u
cd "$HOME/backups" || exit 1
LOG="$HOME/backups/_push-archivi.log"
log() { echo "[$(date "+%Y-%m-%d %H:%M")] $*" >> "$LOG"; }
DIRS="rebalix-xtrackers-archivio rebalix-c3m-archivio rebalix-lifestrategy-archivio rebalix-replica-archivio rebalix-broker-zero-archivio rebalix-cron rebalix-etf-registry-archivio rebalix-docs-archivio rebalix-msci-archivio rebalix-bond-lifecycle"
git add -A -- $DIRS >> "$LOG" 2>&1
if ! git diff --cached --quiet; then
  git commit -q -m "Snapshot archivi $(date "+%Y-%m-%d") (VPS)" >> "$LOG" 2>&1
  log "commit dello snapshot"
fi
if ! git pull --rebase -X theirs -q origin main >> "$LOG" 2>&1; then
  git rebase --abort >> "$LOG" 2>&1
  log "!! pull --rebase FALLITO — push saltato (riprovera domani)"
  exit 1
fi
if git push -q origin main >> "$LOG" 2>&1; then
  log "push OK"; ESITO=0
else
  log "!! push FALLITO (restera nel prossimo giro)"; ESITO=1
fi
# battito al guardiano (21 ago 2026: i push erano MUTI — 4 giorni di fallimenti invisibili)
SECRET=$(grep '^CRON_SECRET=' "$HOME/progetti/rebalix/.env.local" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
if [ -n "$SECRET" ]; then
  OKB=$([ "$ESITO" -eq 0 ] && echo true || echo false)
  ERRB=$([ "$ESITO" -eq 0 ] && echo 0 || echo 1)
  curl -s -m 30 -X POST "https://rebalix.com/api/heartbeat" \
    -H "Authorization: Bearer $SECRET" -H "Content-Type: application/json" \
    -d "{\"name\":\"archivi-push-vps\",\"ok\":$OKB,\"errors_count\":$ERRB,\"metrics\":{\"host\":\"$(hostname)\",\"modules\":{\"push\":$OKB},\"data_date\":\"$(date +%F)\"}}" >/dev/null 2>&1
fi
exit "$ESITO"
