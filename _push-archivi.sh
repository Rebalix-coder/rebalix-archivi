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
if ! git pull --rebase -X theirs -q origin main >> "$LOG" 2>&1; then
  git rebase --abort >> "$LOG" 2>&1
  log "!! pull --rebase FALLITO — push saltato (riproverà domani)"
  exit 1
fi
if git push -q origin main >> "$LOG" 2>&1; then
  log "push OK"; ESITO=0
else
  log "!! push FALLITO (resterà nel prossimo giro)"; ESITO=1
fi
# battito al guardiano (21 ago 2026: i push erano MUTI — 4 giorni di fallimenti invisibili)
SECRET=$(grep '^CRON_SECRET=' "$HOME/progetti/rebalix/.env.local" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
if [ -n "$SECRET" ]; then
  OKB=$([ "$ESITO" -eq 0 ] && echo true || echo false)
  ERRB=$([ "$ESITO" -eq 0 ] && echo 0 || echo 1)
  curl -s -m 30 -X POST "https://rebalix.com/api/heartbeat" \
    -H "Authorization: Bearer $SECRET" -H "Content-Type: application/json" \
    -d "{\"name\":\"archivi-push-mac\",\"ok\":$OKB,\"errors_count\":$ERRB,\"metrics\":{\"host\":\"$(hostname)\",\"modules\":{\"push\":$OKB},\"data_date\":\"$(date +%F)\"}}" >/dev/null 2>&1
fi
exit "$ESITO"
