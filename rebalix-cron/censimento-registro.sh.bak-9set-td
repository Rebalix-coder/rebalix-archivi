#!/bin/bash
# Censimento di meta mese del registro ETF (giorno 17, VPS) — decisione Linus 13 ago 2026:
# dimezza la latenza sui nuovi lanci. ingest-etf-registry + (dal 17 ago) i factsheet
# degli OBBLIGAZIONARI ri-archiviati e le metriche obbligazionarie rilette: gli
# emittenti pubblicano il mensile verso il 5-15, il giro del giorno 2 trova ancora
# quello vecchio. I documenti/KID dei neonati arrivano col giro pieno del giorno 2.
# Battito con nome PROPRIO (required nel guardiano: solo «censimento»).
set -u
REPO="$HOME/progetti/rebalix"
LOG="$HOME/backups/rebalix-etf-registry-archivio/_censimento.log"
log() { echo "[$(date "+%Y-%m-%d %H:%M")] $*" >> "$LOG"; }
cd "$REPO"
log "=== censimento meta mese avviato ==="
if node scripts/ingest-etf-registry.mjs --commit >> "$LOG" 2>&1; then OK=true; ERR=0; log "censimento OK"; else OK=false; ERR=1; log "!! censimento FALLITO"; fi
# MOTORE subito dopo il registro (correzione sessione Database ETF, 18 ago): registro
# aggiornato + motore vecchio = tabelle divergenti -> il guardiano di coerenza delle
# 17:30 canta scarti DURI (TER motore != registro). Nel runner mensile il motore e'
# l'ultimo passo apposta; qui lo stesso principio. Modulo proprio nel battito.
MT=false
if [ "$OK" = true ] && timeout 2h node scripts/build-motore-dataset.mjs --commit >> "$LOG" 2>&1; then MT=true; log "motore ricostruito OK"; else ERR=$((ERR+1)); log "!! motore NON ricostruito (registro e motore possono divergere)"; fi
# factsheet freschi degli obbligazionari (solo hash cambiati) + metriche dichiarate
# (duration/rating/scadenze). Non bloccano il battito del censimento: moduli propri.
FS=false; BM=false
if timeout 3h node scripts/archive-etf-documents.mjs --commit --solo-factsheet --solo-obbligazionari >> "$LOG" 2>&1; then FS=true; log "factsheet obbligazionari OK"; else log "!! archivio factsheet obbligazionari FALLITO (non blocca)"; fi
if timeout 1h node scripts/enrich-bond-metrics.mjs --commit >> "$LOG" 2>&1; then BM=true; log "bond-metrics OK"; else log "!! bond-metrics FALLITO (non blocca)"; fi
SECRET=$(grep "^CRON_SECRET=" "$REPO/.env.local" | head -1 | cut -d= -f2- | tr -d "\"" | tr -d "'")
curl -s -m 30 -X POST https://rebalix.com/api/heartbeat -H "Authorization: Bearer $SECRET" -H "Content-Type: application/json" \
  -d "{\"name\":\"etf-registry-censimento\",\"ok\":$OK,\"errors_count\":$ERR,\"metrics\":{\"host\":\"$(hostname)\",\"modules\":{\"censimento\":$OK,\"motore\":$MT,\"factsheet-bond\":$FS,\"bond-metrics\":$BM},\"data_date\":\"$(date +%F)\"}}" >> "$LOG" 2>&1 && log "[heartbeat] inviato"
[ "$OK" = true ]
