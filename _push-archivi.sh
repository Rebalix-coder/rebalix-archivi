#!/bin/bash
# Push notturno degli archivi documentali su GitHub (rebalix-archivi).
# Best-effort sul mirror della white list: ~/Documents è protetta da TCC e da
# launchd la lettura può fallire — in quel caso si tiene il mirror precedente
# (i documenti white list cambiano ~2 volte l'anno, il refresh vero avviene
# durante l'ingest interattivo).
set -u
cd "$HOME/backups" || exit 1
LOG="$HOME/backups/_push-archivi.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M')] $*" >> "$LOG"; }

rsync -a --delete "$HOME/Documents/Rebalix-archivi/whitelist-docs/" _whitelist-docs-mirror/ 2>/dev/null \
  || log "mirror white list saltato (TCC?), tengo il precedente"

git add -A >> "$LOG" 2>&1
if git diff --cached --quiet; then
  log "nessuna modifica, niente commit"
  exit 0
fi
git commit -q -m "Snapshot archivi $(date '+%Y-%m-%d')" >> "$LOG" 2>&1
if git push -q origin main >> "$LOG" 2>&1; then
  log "push OK"
else
  log "!! push FALLITO (resterà nel prossimo giro)"
  exit 1
fi
