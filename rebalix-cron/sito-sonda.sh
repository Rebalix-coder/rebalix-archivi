#!/bin/bash
# sito-sonda.sh — VEDETTA ESTERNA (20 ago 2026, dopo il 2° crollo DB in 4 giorni:
# «stasera l'ha scoperto Linus, non il sistema»). Ogni 5 minuti misura, DA FUORI:
#   (a) una query da 1 riga sul DB Supabase (la causa)   (b) una scheda del sito (l'utente).
# 3 fallimenti CONSECUTIVI di uno dei due → mail d'allarme a Linus via Resend
# (stesso mittente delle mail del guardiano). Mentre resta giù: al massimo una mail
# l'ora. Al rientro: una mail di «rientrato» e contatori a zero.
# Stato in /home/rebalix/cache/sito-sonda.stato (righe: fallimenti_db fallimenti_sito ultimo_allarme_epoch)
set -u
ENV=/home/rebalix/progetti/rebalix/.env.local
URL=$(grep '^NEXT_PUBLIC_SUPABASE_URL' "$ENV" | cut -d= -f2- | tr -d '"' | tr -d "'")
KEY=$(grep '^SUPABASE_SERVICE_ROLE_KEY' "$ENV" | cut -d= -f2- | tr -d '"' | tr -d "'")
RESEND=$(grep '^RESEND_API_KEY' "$ENV" | cut -d= -f2- | tr -d '"' | tr -d "'")
DEST=$(grep '^NEXT_PUBLIC_ADMIN_EMAIL' "$ENV" | cut -d= -f2- | tr -d '"' | tr -d "'"); DEST=${DEST:-linuspc@gmail.com}
STATO=/home/rebalix/cache/sito-sonda.stato
LOG=/home/rebalix/cache/sito-sonda.log
read -r F_DB F_SITO ULTIMO 2>/dev/null < "$STATO" || { F_DB=0; F_SITO=0; ULTIMO=0; }
ADESSO=$(date +%s)

misura() { local c; c=$(curl -s -o /dev/null -m 10 -w '%{http_code}' "$@" 2>/dev/null); echo "${c:-000}"; }
DB=$(misura -H "apikey: $KEY" -H "Authorization: Bearer $KEY" "$URL/rest/v1/etf_registry?select=isin&limit=1")
SITO=$(misura "https://rebalix.com/it/etf/IE00B4L5Y983")

[ "$DB" = "200" ] && NUOVO_DB=0 || NUOVO_DB=$((F_DB + 1))
[ "$SITO" = "200" ] && NUOVO_SITO=0 || NUOVO_SITO=$((F_SITO + 1))

manda() { # $1 = oggetto, $2 = corpo
  curl -s -m 20 -X POST https://api.resend.com/emails \
    -H "Authorization: Bearer $RESEND" -H 'Content-Type: application/json' \
    -d "$(python3 -c "import json,sys;print(json.dumps({'from':'Rebalix Cron <noreply@rebalix.com>','to':['$DEST'],'subject':sys.argv[1],'text':sys.argv[2]}))" "$1" "$2")" >/dev/null
}

GIU_PRIMA=$([ "$F_DB" -ge 3 ] || [ "$F_SITO" -ge 3 ] && echo 1 || echo 0)
GIU_ADESSO=$([ "$NUOVO_DB" -ge 3 ] || [ "$NUOVO_SITO" -ge 3 ] && echo 1 || echo 0)

if [ "$GIU_ADESSO" = 1 ] && [ $((ADESSO - ULTIMO)) -ge 3600 ]; then
  manda "🔴 Rebalix: DB o sito non rispondono (vedetta VPS)" \
"La vedetta esterna sulla VPS vede da >15 minuti:
- query DB Supabase: HTTP $DB (fallimenti consecutivi: $NUOVO_DB)
- scheda rebalix.com: HTTP $SITO (fallimenti consecutivi: $NUOVO_SITO)

Cosa fare: dashboard Supabase -> il progetto -> Restart project se il DB e' muto.
Il CSV minuto-per-minuto e' in ~/cache/supabase-metriche.csv sulla VPS.
Questa mail arriva al massimo una volta l'ora finche' dura."
  ULTIMO=$ADESSO
  echo "$(date -u +%FT%TZ) ALLARME db=$DB sito=$SITO" >> "$LOG"
elif [ "$GIU_PRIMA" = 1 ] && [ "$GIU_ADESSO" = 0 ]; then
  manda "🟢 Rebalix: rientrato (vedetta VPS)" "DB e sito rispondono di nuovo (db=$DB, sito=$SITO). Nessuna azione."
  ULTIMO=0
  echo "$(date -u +%FT%TZ) RIENTRO db=$DB sito=$SITO" >> "$LOG"
fi
echo "$NUOVO_DB $NUOVO_SITO $ULTIMO" > "$STATO"
