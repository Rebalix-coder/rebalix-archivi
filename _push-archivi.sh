#!/bin/bash
# Push notturno degli archivi documentali su GitHub (rebalix-archivi).
# Dal 13 ago 2026 il repo ha DUE pusher (Mac + VPS rebalix-vps, percorsi disgiunti):
# liturgia commit → pull --rebase → push, come la cura anti-retrocessione degli
# archiviatori. Il rebase non può confliggere finché ogni macchina scrive SOLO
# nelle proprie cartelle (gli archivi migrati sulla VPS sul Mac restano congelati
# e si aggiornano da soli col pull).
# Best-effort sul mirror della white list: ~/Documents è protetta da TCC e da
# launchd la lettura può fallire — in quel caso si tiene il mirror precedente.
set -u
cd "$HOME/backups" || exit 1
LOG="$HOME/backups/_push-archivi.log"
log() { echo "[$(date '+%Y-%m-%d %H:%M')] $*" >> "$LOG"; }

rsync -a --delete "$HOME/Documents/Rebalix-archivi/whitelist-docs/" _whitelist-docs-mirror/ 2>/dev/null \
  || log "mirror white list saltato (TCC?), tengo il precedente"

git add -A >> "$LOG" 2>&1
if ! git diff --cached --quiet; then
  git commit -q -m "Snapshot archivi $(date '+%Y-%m-%d') (Mac)" >> "$LOG" 2>&1
  log "commit dello snapshot"
fi
if ! git pull --rebase -q origin main >> "$LOG" 2>&1; then
  git rebase --abort >> "$LOG" 2>&1
  log "!! pull --rebase FALLITO — push saltato (riproverà domani)"
  exit 1
fi
if git push -q origin main >> "$LOG" 2>&1; then
  log "push OK"
else
  log "!! push FALLITO (resterà nel prossimo giro)"
  exit 1
fi
