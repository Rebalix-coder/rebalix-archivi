#!/bin/bash
# supabase-metriche.sh — campiona l'endpoint Prometheus del progetto Supabase (fuori dal DB:
# l'esportatore gira a lato) e appende UNA riga CSV al minuto. Nato il 19 ago 2026 sera dopo il
# secondo crollo del DB in 4 giorni: la dashboard Supabase richiede il login di Linus, questo no.
# Campi: ts, mem_avail_mb, mem_total_mb, swap_used_mb, oom_kill, load1, disk_io_s (nvme0n1 cumul.),
#        pgrst_pool_waiting, pgrst_pool_timeouts, pgb_client_waiting, backends, pg_restarts, cpu_idle_s
set -u
ENV=/home/rebalix/progetti/rebalix/.env.local
URL=$(grep '^NEXT_PUBLIC_SUPABASE_URL' "$ENV" | cut -d= -f2- | tr -d '"' | tr -d "'")
KEY=$(grep '^SUPABASE_SERVICE_ROLE_KEY' "$ENV" | cut -d= -f2- | tr -d '"' | tr -d "'")
OUT=/home/rebalix/cache/supabase-metriche.csv
TMP=$(mktemp)
[ -f "$OUT" ] || echo "ts,mem_avail_mb,mem_total_mb,swap_used_mb,oom_kill,load1,disk_io_s,pgrst_pool_waiting,pgrst_pool_timeouts,pgb_client_waiting,backends,pg_restarts,cpu_idle_s,http" > "$OUT"
code=$(curl -s -m 20 -u "service_role:$KEY" "$URL/customer/v1/privileged/metrics" -o "$TMP" -w '%{http_code}')
g() { grep -E "^$1(\{[^}]*\})? " "$TMP" | head -1 | awk '{print $NF}'; }
gl() { grep -E "^$1\{[^}]*$2[^}]*\} " "$TMP" | head -1 | awk '{print $NF}'; }
sum() { grep -E "^$1(\{[^}]*\})? " "$TMP" | awk '{s+=$NF} END {print s+0}'; }
mt=$(g node_memory_MemTotal_bytes); ma=$(g node_memory_MemAvailable_bytes)
st=$(g node_memory_SwapTotal_bytes); sf=$(g node_memory_SwapFree_bytes)
oom=$(g node_vmstat_oom_kill); l1=$(g node_load1)
io=$(gl node_disk_io_time_seconds_total 'device="nvme0n1"')
pw=$(g pgrst_db_pool_waiting); pt=$(g pgrst_db_pool_timeouts_total)
cw=$(sum pgbouncer_pools_client_waiting_connections)
be=$(sum pg_stat_database_num_backends); pr=$(g postgresql_restarts_total)
ci=$(grep -E '^node_cpu_seconds_total\{[^}]*mode="idle"' "$TMP" | awk '{s+=$NF} END {print s+0}')
f() { awk -v v="${1:-}" -v d="${2:-1}" 'BEGIN { if (v=="") print ""; else printf "%.1f", v/d }'; }
echo "$(date -u +%Y-%m-%dT%H:%M:%SZ),$(f "$ma" 1e6),$(f "$mt" 1e6),$(awk -v t="${st:-0}" -v f="${sf:-0}" 'BEGIN{printf "%.1f",(t-f)/1e6}'),${oom:-},${l1:-},${io:-},${pw:-},${pt:-},${cw:-},${be:-},${pr:-},${ci:-},$code" >> "$OUT"
rm -f "$TMP"
# tiene 45 giorni (~65k righe)
if [ "$(wc -l < "$OUT")" -gt 70000 ]; then { head -1 "$OUT"; tail -n 64800 "$OUT"; } > "$OUT.new" && mv "$OUT.new" "$OUT"; fi
