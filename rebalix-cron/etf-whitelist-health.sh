#!/bin/sh
# Guardiano freschezza etf_whitelist — chiama l'endpoint prod (email admin se quote
# scadute/in scadenza). Il segreto vive SOLO in .env.local del repo (unica fonte).
SECRET=$(grep '^CRON_SECRET=' /Users/ale/progetti/rebalix/.env.local | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
if [ -z "$SECRET" ]; then echo "$(date '+%F %T') CRON_SECRET non trovato in .env.local"; exit 1; fi
echo "$(date '+%F %T') check…"
curl -s -m 60 -H "Authorization: Bearer $SECRET" "https://rebalix.com/api/cron/etf-whitelist-health"
echo ""
