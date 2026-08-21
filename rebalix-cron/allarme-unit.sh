#!/bin/bash
# Allarme IMMEDIATO di unit fallita (21 ago 2026, richiesta Linus «avvisato senza chiedere»).
# Agganciato via OnFailure=rebalix-allarme@%n.service a tutte le unit rebalix-*:
# qualunque job esca male -> email entro il minuto, via Resend, SENZA aspettare la
# sonda delle 14. Tema chiaro come tutte le email Rebalix.
set -u
UNIT="${1:?unit mancante}"
REPO="$HOME/progetti/rebalix"
KEY=$(grep '^RESEND_API_KEY=' "$REPO/.env.local" | head -1 | cut -d= -f2- | tr -d '"' | tr -d "'")
[ -z "$KEY" ] && exit 0   # niente chiave = niente mail, ma non fallire l'allarme stesso

QUANDO=$(date '+%d/%m %H:%M')
DETTAGLIO=$(journalctl -u "$UNIT" -n 12 --no-pager -q 2>/dev/null | tail -8 | sed 's/</\&lt;/g' | sed 's/$/<br\/>/' | tr -d '\n')
RISULTATO=$(systemctl show "$UNIT" -p Result --value 2>/dev/null)

HTML="<p>🔴 <strong>${UNIT}</strong> è uscita male su <strong>rebalix-vps</strong> alle ${QUANDO} (esito: ${RISULTATO}).</p>\
<p style=\"color:#666\">Ultime righe del journal:</p>\
<p style=\"font-family:monospace;font-size:12px;background:#f5f5f5;padding:8px\">${DETTAGLIO}</p>\
<p style=\"color:#666\"><small>Cosa fare: <code>ssh rebalix-vps</code> → <code>journalctl -u ${UNIT}</code>; log del job in ~/backups. Questo allarme parte al fallimento, senza aspettare la sonda delle 14. Runbook: docs/piano-migrazione-ionos.md §9.</small></p>"

curl -s -m 20 -X POST "https://api.resend.com/emails" \
  -H "Authorization: Bearer $KEY" -H "Content-Type: application/json" \
  -d "{\"from\":\"Rebalix Guardiani <guardiani@rebalix.com>\",\"to\":[\"linuspc@outlook.it\"],\"subject\":\"🔴 VPS: ${UNIT} fallita (${QUANDO})\",\"html\":\"${HTML//\"/\\\"}\"}" >/dev/null 2>&1
exit 0
