#!/bin/bash
# Push quotidiano archivi VPS → GitHub rebalix-archivi (doppio pusher col Mac,
# percorsi disgiunti). Liturgia: commit → pull --rebase → push; sparse checkout
# limitato alle cartelle di cui QUESTA macchina è proprietaria.
set -u
cd "$HOME/backups" || exit 1
LOG="$HOME/backups/_push-archivi.log"
log() { echo "[$(date "+%Y-%m-%d %H:%M")] $*" >> "$LOG"; }
DIRS="rebalix-xtrackers-archivio rebalix-c3m-archivio rebalix-lifestrategy-archivio rebalix-replica-archivio rebalix-broker-zero-archivio rebalix-cron rebalix-etf-registry-archivio rebalix-docs-archivio rebalix-msci-archivio"
git add -A -- $DIRS >> "$LOG" 2>&1
if ! git diff --cached --quiet; then
  git commit -q -m "Snapshot archivi $(date "+%Y-%m-%d") (VPS)" >> "$LOG" 2>&1
  log "commit dello snapshot"
fi
if ! git pull --rebase -q origin main >> "$LOG" 2>&1; then
  git rebase --abort >> "$LOG" 2>&1
  log "!! pull --rebase FALLITO — push saltato (riprovera domani)"
  exit 1
fi
if git push -q origin main >> "$LOG" 2>&1; then
  log "push OK"
else
  log "!! push FALLITO (restera nel prossimo giro)"
  exit 1
fi
