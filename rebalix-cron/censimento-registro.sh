#!/bin/bash
# Censimento di meta mese del registro ETF (giorno 17, VPS) — decisione Linus 13 ago 2026:
# dimezza la latenza sui nuovi lanci. SOLO ingest-etf-registry: i documenti/KID dei
# neonati arrivano col giro pieno del giorno 2. Battito con nome PROPRIO.
set -u
REPO="$HOME/progetti/rebalix"
LOG="$HOME/backups/rebalix-etf-registry-archivio/_censimento.log"
log() { echo "[$(date "+%Y-%m-%d %H:%M")] $*" >> "$LOG"; }
cd "$REPO"
log "=== censimento meta mese avviato ==="
if node scripts/ingest-etf-registry.mjs --commit >> "$LOG" 2>&1; then OK=true; ERR=0; log "censimento OK"; else OK=false; ERR=1; log "!! censimento FALLITO"; fi
SECRET=$(grep "^CRON_SECRET=" "$REPO/.env.local" | head -1 | cut -d= -f2- | tr -d "\"" | tr -d "'")
curl -s -m 30 -X POST https://rebalix.com/api/heartbeat -H "Authorization: Bearer $SECRET" -H "Content-Type: application/json" \
  -d "{\"name\":\"etf-registry-censimento\",\"ok\":$OK,\"errors_count\":$ERR,\"metrics\":{\"modules\":{\"censimento\":$OK},\"data_date\":\"$(date +%F)\"}}" >> "$LOG" 2>&1 && log "[heartbeat] inviato"
[ "$OK" = true ]
