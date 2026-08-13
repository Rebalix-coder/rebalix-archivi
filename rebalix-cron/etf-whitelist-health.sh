#!/bin/sh
# Guardiano freschezza etf_whitelist — chiama l endpoint prod (email admin se quote scadute).
SECRET=$(grep "^CRON_SECRET=" $HOME/progetti/rebalix/.env.local | head -1 | cut -d= -f2- | tr -d "\"" | tr -d "'")
if [ -z "$SECRET" ]; then echo "$(date "+%F %T") CRON_SECRET non trovato"; exit 1; fi
echo "$(date "+%F %T") check…"
curl -s -m 60 -H "Authorization: Bearer $SECRET" "https://rebalix.com/api/cron/etf-whitelist-health"
echo ""
