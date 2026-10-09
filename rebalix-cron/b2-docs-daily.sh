#!/bin/bash
# b2-docs-daily.sh — copia QUOTIDIANA dei documenti nuovi su B2 (piano archivio 29/9, passo 5; acceso 8/10).
# SOLO rclone copy: aggiunge, MAI cancella — il sync del lunedì (backup-b2-vps.sh) resta l'unico
# riconciliatore. Finestra di esposizione dei documenti nuovi: < 24 h. Battito name=b2-docs.
set -u
ENVFILE="$HOME/.config/rebalix/b2-backup.env"
LOG="$HOME/logs/b2-docs/run-$(date +%Y%m%d-%H%M%S).log"
mkdir -p "$(dirname "$LOG")"
exec >> "$LOG" 2>&1
echo "=== b2-docs $(date -Iseconds) ==="
set -a; source "$ENVFILE"; set +a
[ -n "${B2_KEY_ID:-}" ] && [ -n "${B2_APPLICATION_KEY:-}" ] && [ -n "${B2_BUCKET:-}" ] || { echo "!! chiavi B2 vuote"; exit 1; }
export RCLONE_B2_ACCOUNT="$B2_KEY_ID" RCLONE_B2_KEY="$B2_APPLICATION_KEY"
SRC="$HOME/backups/rebalix-docs-archivio"
DEST=":b2:${B2_BUCKET}/backups/rebalix-docs-archivio"
if rclone copy "$SRC" "$DEST" --transfers 8 --stats-one-line --stats 0 -v 2>&1 | grep -E "Copied|Transferred:" | tail -4; then OK=true; ERR=0; else OK=false; ERR=1; fi
NUOVI=$(grep -c "Copied (new)" "$LOG" || true)
echo "esito: ok=$OK · file nuovi copiati: ${NUOVI:-0}"
SECRET=$(grep "^CRON_SECRET=" "$HOME/progetti/rebalix/.env.local" | head -1 | cut -d= -f2- | tr -d "\042\047")
curl -s --max-time 30 -X POST "https://rebalix.com/api/heartbeat" \
  -H "Authorization: Bearer ${SECRET}" -H "Content-Type: application/json" \
  -d "{\"name\":\"b2-docs\",\"ok\":${OK},\"errors_count\":${ERR},\"metrics\":{\"host\":\"$(hostname)\",\"modules\":{\"copy\":${OK}},\"nuovi\":${NUOVI:-0},\"data_date\":\"$(date +%F)\"}}" \
  && echo "" && echo "[heartbeat] inviato (ok=${OK})" || echo "[heartbeat] invio fallito (non blocca)"
ls -t "$HOME/logs/b2-docs"/run-*.log 2>/dev/null | tail -n +31 | xargs rm -f 2>/dev/null
echo "=== fine $(date -Iseconds) ==="
[ "$OK" = true ]
