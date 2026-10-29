#!/bin/bash
# esegui-commit-lotto-giro.sh (rev. 3, 28 ott 2026: campo reale raw->>'paginaEmittente'; comando nella sessione del supervisore con trap sui segnali esterni → uscita 9) — COMMIT di UN lotto del GIRO DOCUMENTALE AUTOMATICO da sorgenti conservate (REV. 2, 28 ott 2026; riesame
# dell'auditor sulla rev. 1: residui dopo l'uscita normale = esito incerto; revalidazione a blocchi di 200 con riconciliazione; attese
# pubbliche dal comportamento effettivo della pagina per classe: classi non pubbliche = 404 atteso, factsheet in anomalia definitiva =
# rimando alla pagina del fondo, invalidazione = solo href).
# Generalizza il copione «esegui-commit-lotto-ridotto.sh» rev. 3 del 25/10 (PASS). TUTTO arriva dal runner per variabili d'ambiente;
# l'autorizzazione (file di GO) è verificata dal runner PRIMA di chiamare questo copione. Un lancio = un lotto.
#   REBALIX_SEMAFORO=1 LOTTO=<lotto.json> APPROVATA=<anteprima verificata .json> SORGENTI=<cartella della prova> W=<cartella di lavoro>
#   ATTESO=<sha di main> SHA_LOTTO=<sha256 del lotto> SHA_APPROVATA=<sha256 dell'anteprima> [REPO ARCH NODE ENV_DB ENV_LOCAL COLLAUDO SITO
#   ORA_LIMITE=HHMM SENTINELLA_PASSO ATTESA_TERM ATTESA_REVALIDATE BLOCCO_REVALIDATE=200] [OFFLINE_REGISTRO OFFLINE_SORGENTI: SOLO banco]
# Uscite: 0 = scritto, riscontrato, revalidato e collaudato · 2 = precondizioni (nulla scritto) · 7 = il comando si è fermato PRIMA di
# scrivere (verificato: nulla scritto) · 8 = STATO PARZIALE o verifiche dopo non superate (tabella per voce; nessun rilancio) · 9 = esito
# INCERTO (processi residui dopo il comando, arresto al limite incompleto, fotografia dopo impossibile): nessun COMMIT successivo.
set -u
[ "${REBALIX_SEMAFORO:-}" = 1 ] || { echo "ARRESTO: non sotto con-semaforo (REBALIX_SEMAFORO≠1)"; exit 2; }
: "${LOTTO:?LOTTO}" "${APPROVATA:?APPROVATA}" "${SORGENTI:?SORGENTI}" "${W:?W}" "${ATTESO:?ATTESO}" "${SHA_LOTTO:?SHA_LOTTO}" "${SHA_APPROVATA:?SHA_APPROVATA}"
REPO=${REPO:-/home/rebalix/progetti/rebalix}; ARCH=${ARCH:-/home/rebalix/backups/rebalix-docs-archivio}; NODE=${NODE:-/usr/bin/node}
ENV_DB=${ENV_DB:-/home/rebalix/backups/rebalix-db/.env}; ENV_LOCAL=${ENV_LOCAL:-$REPO/.env.local}
COLLAUDO=${COLLAUDO:-$(dirname "$0")/collaudo-pagina-documenti.py}; COLLAUDO=$(cd "$(dirname "$COLLAUDO")" 2>/dev/null && pwd)/$(basename "$COLLAUDO"); SITO=${SITO:-https://rebalix.com}; ORA_LIMITE=${ORA_LIMITE:-1700}; BLOCCO_REVALIDATE=${BLOCCO_REVALIDATE:-200}
OFFLINE_FLAGS=(); [ -n "${OFFLINE_REGISTRO:-}" ] && [ -n "${OFFLINE_SORGENTI:-}" ] && OFFLINE_FLAGS=(--registro-json "$OFFLINE_REGISTRO" --sorgenti-locali "$OFFLINE_SORGENTI")
mkdir -p "$W/copie-di-lavoro"; E=$W/esito.txt
log(){ echo "[$(date '+%F %T')] $*" | tee -a "$E"; }
hhmm(){ date +%H%M; }
log "COMMIT lotto $(basename "$LOTTO") · inizio · cartella $W · limite operativo $ORA_LIMITE${OFFLINE_FLAGS:+ · MODALITÀ OFFLINE DI PROVA (mai in produzione)}"
# ── precondizioni
HEAD=$(git -C "$REPO" rev-parse HEAD); [ "$HEAD" = "$ATTESO" ] || { log "ARRESTO (2): repo a $HEAD, atteso $ATTESO"; exit 2; }
[ -f "$LOTTO" ] && [ -f "$APPROVATA" ] && [ -d "$SORGENTI" ] || { log "ARRESTO (2): manca il lotto, l'anteprima approvata o la cartella delle sorgenti"; exit 2; }
SJ=$(sha256sum "$LOTTO" | cut -d' ' -f1); SA=$(sha256sum "$APPROVATA" | cut -d' ' -f1)
[ "$SJ" = "$SHA_LOTTO" ] || { log "ARRESTO (2): impronta del lotto $SJ ≠ attesa $SHA_LOTTO"; exit 2; }
[ "$SA" = "$SHA_APPROVATA" ] || { log "ARRESTO (2): impronta dell'anteprima approvata $SA ≠ attesa $SHA_APPROVATA"; exit 2; }
[ "$(hhmm)" -lt "$ORA_LIMITE" ] || { log "ARRESTO (2): avvio alle $(hhmm) oltre il limite operativo $ORA_LIMITE"; exit 2; }
python3 - "$LOTTO" "$APPROVATA" "$W" <<'EOF' || { log "ARRESTO (2): lotto e anteprima approvata non coerenti (dettaglio in $W/attese.txt)"; exit 2; }
import json,sys
J,A,W=sys.argv[1:4]; j=json.load(open(J)); a=json.load(open(A)); voci=j['voci']; righe=a['righe']
COL={'kid_it':'kid_url','kid_en':'kid_url_en','factsheet_it':'factsheet_url','factsheet_en':'factsheet_url_en','prospetto_it':'prospectus_url','prospetto_en':'prospectus_url_en'}
kv={(v['isin'],v['tipo'],v['url']) for v in voci}; kr={(r['isin'],r['tipo'],r['url']) for r in righe}
err=[]
if a.get('commit') is not False: err.append('anteprima approvata non è di una PROVA')
if kv!=kr: err.append(f'chiavi diverse: solo nel lotto {len(kv-kr)}, solo nell’anteprima {len(kr-kv)}')
nv=[r for r in righe if r['verdetto']!='verificato']
if nv: err.append(f'{len(nv)} righe non «verificato» nell’anteprima approvata')
with open(f'{W}/attese.txt','w') as f:
    f.write(f"voci {len(voci)}\nrighe_approvate {len(righe)}\n")
    for v in voci: f.write(f"voce\t{v['isin']}\t{v['tipo']}\t{v['sha256_attesa']}\t{v['sorgente_locale']}\n")
    for r in righe:
        al=r.get('azione_lingua') if isinstance(r.get('azione_lingua'),dict) else None
        if al and al.get('azione') in ('scrivi','invalida') and isinstance(al.get('patch'),dict):
            f.write(f"lingua\t{r['isin']}\t{r['tipo']}\t{al['azione']}\t{json.dumps(al['patch'],sort_keys=True)}\n")
        if r.get('azione_url')=='da scrivere' and r['tipo'] in COL: f.write(f"url\t{r['isin']}\t{COL[r['tipo']]}\t{r['url']}\n")
    for e in err: f.write(f"ERRORE\t{e}\n")
sys.exit(1 if err else 0)
EOF
NV=$(awk '$1=="voci"{print $2}' "$W/attese.txt"); NL=$(grep -c '^lingua' "$W/attese.txt"); NU=$(grep -c '^url' "$W/attese.txt")
log "precondizioni OK: HEAD $HEAD · lotto $SJ · approvata $SA · voci $NV · lingue da scrivere/invalidare $NL · URL da scrivere $NU"
# ── foto PRIMA (registro: 6 colonne URL + 10 di lingua/provenienza; classe: pubblica?, pagina dell'emittente, anomalia del factsheet)
set -a; source "$ENV_DB"; set +a
ISINS=$(awk -F'\t' '$1=="voce"{print $2}' "$W/attese.txt" | grep . | sort -u); IN=$(echo "$ISINS" | grep . | sed "s/.*/'&'/" | paste -sd, -); echo "ISIN del lotto ($(echo "$ISINS" | grep -c .)): $IN" >> "$W/attese.txt"
COLS_URL="kid_url, kid_url_en, factsheet_url, factsheet_url_en, prospectus_url, prospectus_url_en"
COLS_LINGUA="kid_lang, kid_lang_fonte, kid_lang_sha256, kid_lang_url, kid_lang_verificata_il, factsheet_lang, factsheet_lang_fonte, factsheet_lang_sha256, factsheet_lang_url, factsheet_lang_verificata_il"
SOTTRAI=$(echo "$COLS_URL, $COLS_LINGUA" | sed "s/, / - '/g; s/^/- '/; s/$/'/")
foto_archivio(){ awk -F'\t' '$1=="voce"{print $2"\t"$3}' "$W/attese.txt" | sort -u | while IFS=$'\t' read -r i t; do for f in "$ARCH/$i/$t"/*.pdf; do [ -f "$f" ] && echo -e "$i\t$t\t$(basename "$f")\t$(sha256sum "$f" | cut -d' ' -f1)"; done; done; }
foto_db(){ psql -X -At -F'|' -v ON_ERROR_STOP=1 <<SQL
SELECT 'riga', isin, $COLS_URL, $COLS_LINGUA FROM public.etf_registry WHERE isin IN ($IN) ORDER BY isin;
SELECT 'classe', isin, (coalesce(is_etf,false) OR coalesce(product_type,'') ~* '^(ETC|ETP|ETN)$')::int, coalesce(raw->>'paginaEmittente',''), coalesce(raw->'docNote'->'factsheet'->>'stato','') FROM public.etf_registry WHERE isin IN ($IN) ORDER BY isin;
SELECT 'impronta ALTRE righe', count(*), md5(string_agg(concat_ws('|', isin, $COLS_URL, $COLS_LINGUA), E'\n' ORDER BY isin)) FROM public.etf_registry WHERE isin NOT IN ($IN);
SELECT 'impronta colonne NON autorizzate delle righe del lotto', md5(string_agg((to_jsonb(t) $SOTTRAI)::text, E'\n' ORDER BY isin)) FROM public.etf_registry t WHERE isin IN ($IN);
SELECT 'righe etf_registry', count(*) FROM public.etf_registry;
SQL
}
foto_archivio > "$W/foto-archivio-prima.tsv"; P0=$(find "$ARCH" -name '*.pdf' | wc -l | tr -d ' '); touch "$ARCH/_controlli.jsonl"; cp "$ARCH/_controlli.jsonl" "$W/_controlli.prima.jsonl"; C0=$(wc -l < "$W/_controlli.prima.jsonl" | tr -d ' '); S0=$(sha256sum "$W/_controlli.prima.jsonl" | cut -d' ' -f1)
foto_db > "$W/foto-db-prima.txt" 2> "$W/foto-db-prima.err" || { log "ARRESTO (2): fotografia del registro prima fallita: $(head -c 300 "$W/foto-db-prima.err" | tr '\n' ' ')"; exit 2; }
touch "$W/marca-prima"; sleep 1
GIA=$(awk -F'\t' 'NR==FNR{if($1=="voce")a[$4]=1;next} ($4 in a){n++} END{print n+0}' "$W/attese.txt" "$W/foto-archivio-prima.tsv")
log "foto PRIMA: archivio $P0 PDF (per le associazioni del lotto: $(wc -l < "$W/foto-archivio-prima.tsv" | tr -d ' ') versioni; impronte attese già presenti: $GIA, attese 0) · _controlli $C0 righe ($S0) · registro fotografato ($(grep -c '^classe|' "$W/foto-db-prima.txt") classi, pubbliche $(awk -F'|' '$1=="classe" && $3=="1"' "$W/foto-db-prima.txt" | wc -l | tr -d ' '))"
[ "$GIA" = 0 ] || { log "ARRESTO (2): $GIA impronte del lotto già presenti in archivio: lo stato non è quello dell'anteprima approvata"; exit 2; }
# ── COMMIT (gruppo di processi proprio MA nella stessa sessione del supervisore, rev. 3: `set -m`, non setsid, così il runner lo vede
#    per gruppo/sessione/marcatore REBALIX_LANCIO; sentinella al limite operativo; residui dopo l'uscita = esito incerto; un segnale esterno
#    (TERM/INT/HUP dal supervisore) ferma il gruppo del comando, riconteggia ed esce 9: mai «ESITO: ok»)
cd "$REPO" || exit 2
PG=""; vivi(){ [ -n "$PG" ] || return 0; ps -eo pgid= -o pid= -o stat= -o args= | awk -v g="$PG" '$1==g && $3 !~ /^Z/ {print $2": "$4" "$5}'; }
arresto_esterno(){ log "ARRESTO ESTERNO (segnale $1) durante il COMMIT: SIGTERM al gruppo ${PG:-?}, attesa ${ATTESA_TERM:-30} s, poi SIGKILL"
  if [ -n "$PG" ]; then kill -TERM -- "-$PG" 2>/dev/null; for i in $(seq 1 "${ATTESA_TERM:-30}"); do [ -z "$(vivi)" ] && break; sleep 1; done; [ -n "$(vivi)" ] && { kill -KILL -- "-$PG" 2>/dev/null; sleep 1; }; fi
  log "ESITO INCERTO (9): COMMIT interrotto da un segnale esterno ($1); residui del gruppo del comando: $(vivi | wc -l | tr -d ' ') — verificare a mano, NESSUN COMMIT successivo"; exit 9; }
trap 'arresto_esterno TERM' TERM; trap 'arresto_esterno INT' INT; trap 'arresto_esterno HUP' HUP
set -m
"$NODE" scripts/lotto-documenti-mirato.mjs --file "$LOTTO" --anteprima "$W/anteprima-fresca.tsv" --anteprima-approvata "$APPROVATA" --sorgenti-conservate "$SORGENTI" --archivio "$ARCH" --scarica-in "$W/copie-di-lavoro" ${OFFLINE_FLAGS[@]+"${OFFLINE_FLAGS[@]}"} --commit > "$W/commit.out" 2>&1 &
PID=$!; PG=$PID; set +m
INTERROTTO=0; RESIDUI=0
while kill -0 "$PID" 2>/dev/null; do
  if [ "$(hhmm)" -ge "$ORA_LIMITE" ]; then
    log "LIMITE RAGGIUNTO ($(hhmm) ≥ $ORA_LIMITE): SIGTERM al gruppo $PG, attesa fino a ${ATTESA_TERM:-30} s"; kill -TERM -- "-$PG" 2>/dev/null; INTERROTTO=1
    for i in $(seq 1 "${ATTESA_TERM:-30}"); do [ -z "$(vivi)" ] && break; sleep 1; done
    [ -n "$(vivi)" ] && { log "restano vivi: $(vivi | tr '\n' ';') → SIGKILL al gruppo"; kill -KILL -- "-$PG" 2>/dev/null; sleep 2; }
    break
  fi
  sleep "${SENTINELLA_PASSO:-10}"
done
wait "$PID" 2>/dev/null; RC=$?
if [ -n "$(vivi)" ]; then
  RESIDUI=1; log "ANOMALIA: processi del gruppo del comando ancora vivi dopo l'uscita $RC: $(vivi | tr '\n' ';') → SIGTERM, attesa ${ATTESA_TERM:-30} s, poi SIGKILL"
  kill -TERM -- "-$PG" 2>/dev/null; for i in $(seq 1 "${ATTESA_TERM:-30}"); do [ -z "$(vivi)" ] && break; sleep 1; done
  [ -n "$(vivi)" ] && { kill -KILL -- "-$PG" 2>/dev/null; sleep 2; }
  log "residui dopo l'arresto forzato: $(vivi | wc -l | tr -d ' ')"
fi
[ "$INTERROTTO" = 1 ] && [ -n "$(vivi)" ] && { RESIDUI=1; log "ANOMALIA: arresto al limite INCOMPLETO: $(vivi | tr '\n' ';')"; }
trap - TERM INT HUP
cat "$W/commit.out" | tee -a "$E" > /dev/null; log "comando terminato con uscita $RC (interrotto al limite: $INTERROTTO; residui: $RESIDUI)"
# ── foto DOPO e stato per voce
foto_archivio > "$W/foto-archivio-dopo.tsv"; P1=$(find "$ARCH" -name '*.pdf' | wc -l | tr -d ' '); cp "$ARCH/_controlli.jsonl" "$W/_controlli.dopo.jsonl"; C1=$(wc -l < "$W/_controlli.dopo.jsonl" | tr -d ' ')
foto_db > "$W/foto-db-dopo.txt" 2> "$W/foto-db-dopo.err" || { log "ESITO INCERTO (9): fotografia del registro dopo fallita ($(head -c 200 "$W/foto-db-dopo.err" | tr '\n' ' ')): verificare a mano, NON rilanciare"; exit 9; }
find "$ARCH" -name '*.pdf' -newer "$W/marca-prima" | sort > "$W/pdf-nuovi-o-toccati.txt"
python3 - "$W" "$ARCH" "$RC" "$INTERROTTO" "$C0" <<'EOF' > "$W/stato-per-voce.tsv"; VERD=$?
import sys,json
W,ARCH,RC,INT,C0=sys.argv[1:6]; RC=int(RC); INT=int(INT); C0=int(C0)
voci=[l.rstrip('\n').split('\t') for l in open(f'{W}/attese.txt') if l.startswith('voce\t')]
ling={(l.split('\t')[1],l.split('\t')[2]):json.loads(l.rstrip('\n').split('\t')[4]) for l in open(f'{W}/attese.txt') if l.startswith('lingua\t')}
urls={(l.split('\t')[1],l.split('\t')[2]):l.rstrip('\n').split('\t')[3] for l in open(f'{W}/attese.txt') if l.startswith('url\t')}
prima={(a,b,c):d for a,b,c,d in (l.rstrip('\n').split('\t') for l in open(f'{W}/foto-archivio-prima.tsv') if l.strip())}
dopo={(a,b,c):d for a,b,c,d in (l.rstrip('\n').split('\t') for l in open(f'{W}/foto-archivio-dopo.tsv') if l.strip())}
ctrl=[json.loads(l) for l in open(f'{W}/_controlli.dopo.jsonl') if l.strip()][C0:]
COLS=['riga','isin','kid_url','kid_url_en','factsheet_url','factsheet_url_en','prospectus_url','prospectus_url_en','kid_lang','kid_lang_fonte','kid_lang_sha256','kid_lang_url','kid_lang_verificata_il','factsheet_lang','factsheet_lang_fonte','factsheet_lang_sha256','factsheet_lang_url','factsheet_lang_verificata_il']
dbp={l.split('|')[1]:l.rstrip('\n').split('|') for l in open(f'{W}/foto-db-prima.txt') if l.startswith('riga|')}
dbd={l.split('|')[1]:l.rstrip('\n').split('|') for l in open(f'{W}/foto-db-dopo.txt') if l.startswith('riga|')}
print('isin\ttipo\tarchiviato\tcontrollo\tlingua\turl\tstato\triprendere_da')
tot=len(voci); arch=0; con=0; lin_ok=0; lin_att=len(ling); url_ok=0; url_att=len(urls); completi=0; parziali=0
reg_viol=[]
for isin in sorted(set(dbp)|set(dbd)):
    p=dbp.get(isin); d=dbd.get(isin)
    if p is None or d is None: reg_viol.append((isin,'riga comparsa/scomparsa nella fotografia')); continue
    amm={}
    for (i,t),patch in ling.items():
        if i==isin:
            for k,v in patch.items(): amm[k]=('*' if k.endswith('_verificata_il') else ('' if v is None else str(v)))
    for (i,c),u in urls.items():
        if i==isin: amm[c]=u
    for ci,c in enumerate(COLS):
        pv=p[ci] if ci<len(p) else ''; dv=d[ci] if ci<len(d) else ''
        if pv==dv: continue
        if c in amm and (amm[c]=='*' and dv or amm[c]==dv): continue
        reg_viol.append((isin,f'{c}: «{pv[:40]}» → «{dv[:40]}» NON autorizzata'))
arch_viol=[]
for k,v in prima.items():
    if k not in dopo: arch_viol.append((k,'file preesistente scomparso'))
    elif dopo[k]!=v: arch_viol.append((k,f'impronta cambiata {v[:12]} → {dopo[k][:12]}'))
COLDI={'kid_it':'kid_url','kid_en':'kid_url_en','factsheet_it':'factsheet_url','factsheet_en':'factsheet_url_en','prospetto_it':'prospectus_url','prospetto_en':'prospectus_url_en'}
for _,isin,tipo,sha,src in voci:
    a=[k for k,v in dopo.items() if k[0]==isin and k[1]==tipo and k not in prima]
    arch_ok=any(dopo[k]==sha for k in a); arch+=arch_ok
    c_ok=any(c.get('isin')==isin and c.get('tipo')==tipo and c.get('sha256')==sha for c in ctrl); con+=c_ok
    stato_l='n/p'; stato_u='n/p'; d=dbd.get(isin,[]); p=dbp.get(isin,[])
    if (isin,tipo) in ling:
        patch=ling[(isin,tipo)]; ok=True
        for k,v in patch.items():
            if k not in COLS: continue
            dv=d[COLS.index(k)] if len(d)>COLS.index(k) else ''
            if k.endswith('_verificata_il'): ok = ok and bool(dv)
            else: ok = ok and (dv==('' if v is None else str(v)))
        if ok: stato_l='scritta e verificata'; lin_ok+=1
        elif d==p: stato_l='NON scritta: riga invariata'
        else: stato_l='CAMBIATA MA DIVERSA DALLA PATCH: verificare'
    col=COLDI.get(tipo); u=urls.get((isin,col)) if col else None
    if u:
        dv=d[COLS.index(col)] if len(d)>COLS.index(col) else ''
        if dv==u: stato_u='scritto e verificato'; url_ok+=1
        elif (p[COLS.index(col)] if len(p)>COLS.index(col) else '')==dv: stato_u='NON scritto: colonna invariata'
        else: stato_u='DIVERSO DALL’ATTESO: verificare'
    reg_ok = stato_l in ('n/p','scritta e verificata') and stato_u in ('n/p','scritto e verificato')
    if arch_ok and c_ok and reg_ok: stato='completo'; completi+=1; rip='-'
    elif arch_ok and c_ok: stato='PARZIALE (registro)'; parziali+=1; rip='registro (lingua/url)'
    elif arch_ok and not c_ok: stato='PARZIALE'; parziali+=1; rip='riga di controllo'
    elif not arch_ok and not c_ok: stato='non eseguito'; rip='tutto'
    else: stato='PARZIALE'; parziali+=1; rip='archiviazione'
    print(f'{isin}\t{tipo}\t{int(arch_ok)}\t{int(c_ok)}\t{stato_l}\t{stato_u}\t{stato}\t{rip}')
extra=[(k,v) for k,v in dopo.items() if k not in prima and not any(v==s and k[0]==i and k[1]==t for _,i,t,s,_ in voci)]
print(f'#RIEPILOGO\tvoci {tot}\tarchiviate {arch}\tcontrolli {con}\tlingue {lin_ok}/{lin_att}\turl {url_ok}/{url_att}\tcomplete {completi}\tparziali {parziali}\tnon eseguite {max(tot-arch-parziali,0)}\tnuovi file fuori attesa {len(extra)}\tregistro non autorizzato {len(reg_viol)}\tarchivio preesistente alterato {len(arch_viol)}')
for k,v in extra: print(f'#FUORI_ATTESA\t{k[0]}\t{k[1]}\t{k[2]}\t{v}')
for i,m in reg_viol: print(f'#REGISTRO_NON_AUTORIZZATO\t{i}\t{m}')
for k,m in arch_viol: print(f'#ARCHIVIO_PREESISTENTE_ALTERATO\t{k[0]}\t{k[1]}\t{k[2]}\t{m}')
ok = (RC==0 and INT==0 and arch==tot and con==tot and completi==tot and len(extra)==0 and len(ctrl)==tot and not reg_viol and not arch_viol and lin_ok==lin_att and url_ok==url_att)
nulla = (arch==0 and con==0 and len(ctrl)==0 and len(extra)==0 and dbp==dbd and not arch_viol)
sys.exit(0 if ok else (7 if nulla else 8))
EOF
R_=$(grep '^#RIEPILOGO' "$W/stato-per-voce.tsv" | cut -f2- | tr '\t' ' '); log "stato per voce: $R_"
ERR=0
v(){ grep "^$2|" "$1" | cut -d'|' -f2-; }
[ "$(v "$W/foto-db-prima.txt" 'impronta ALTRE righe')" = "$(v "$W/foto-db-dopo.txt" 'impronta ALTRE righe')" ] || { log "SCARTO: colonne URL/lingua di ALTRE righe cambiate"; ERR=1; }
[ "$(v "$W/foto-db-prima.txt" 'impronta colonne NON autorizzate delle righe del lotto')" = "$(v "$W/foto-db-dopo.txt" 'impronta colonne NON autorizzate delle righe del lotto')" ] || { log "SCARTO: colonne NON autorizzate delle righe del lotto cambiate"; ERR=1; }
[ "$(v "$W/foto-db-prima.txt" 'righe etf_registry')" = "$(v "$W/foto-db-dopo.txt" 'righe etf_registry')" ] || { log "SCARTO: numero di righe del registro cambiato"; ERR=1; }
[ "$( { [ "$C0" -gt 0 ] && head -n "$C0" "$W/_controlli.dopo.jsonl"; :; } | sha256sum | cut -d' ' -f1)" = "$S0" ] || { log "SCARTO: righe di controllo preesistenti cambiate"; ERR=1; }
NT=$(wc -l < "$W/pdf-nuovi-o-toccati.txt" | tr -d ' ')
if [ "$RESIDUI" = 1 ]; then log "ESITO INCERTO (9): processi residui dopo il comando (o arresto incompleto): archivio ${P0}→$P1 PDF, controlli ${C0}→$C1, stato per voce in $W/stato-per-voce.tsv — verificare a mano, NESSUN COMMIT successIVO"; exit 9; fi
if [ "$VERD" = 7 ]; then
  [ "$P1" = "$P0" ] && [ "$C1" = "$C0" ] && [ "$NT" = 0 ] && [ $ERR = 0 ] && { log "ESITO: il comando si è FERMATO PRIMA DI SCRIVERE (uscita $RC): archivio ($P1 PDF), controlli ($C1) e registro invariati · uscita 7"; exit 7; }
  log "ESITO INCERTO (9): il comando non ha scritto per voce ma qualcosa è cambiato (PDF ${P0}→$P1, controlli ${C0}→$C1, file toccati $NT, scarti $ERR): verificare a mano"; exit 9
fi
[ "$P1" = $((P0 + NV)) ] || { log "SCARTO: PDF nell'archivio $P0 → $P1 (attesi +$NV)"; ERR=1; }
[ "$NT" = "$NV" ] || { log "SCARTO: file nuovi/toccati nell'archivio $NT (attesi $NV)"; ERR=1; }
[ "$C1" = $((C0 + NV)) ] || { log "SCARTO: righe di controllo $C0 → $C1 (attese +$NV)"; ERR=1; }
grep -q "ESITO: ok" "$W/commit.out" || { log "SCARTO: manca «ESITO: ok» nel comando"; ERR=1; }
if [ "$VERD" != 0 ] || [ $ERR != 0 ]; then log "ESITO: STATO PARZIALE o verifiche NON superate (uscita 8): tabella in $W/stato-per-voce.tsv («riprendere da» per voce) · nessun rilancio automatico"; exit 8; fi
log "verifiche DOPO OK: +$NV PDF come versioni nuove (impronte = attese, nessun file fuori attesa), +$NV controlli (preesistenti intatti), registro: altre righe e colonne non autorizzate invariate, lingue $NL e URL $NU come da anteprima"
# ── revalidazione A BLOCCHI e collaudo pubblico: classi con scrittura sul registro; le classi NON pubbliche (404 atteso) non si revalidano
LS_TUTTE=$( { awk -F'\t' '$5=="scritta e verificata"{print $1}' "$W/stato-per-voce.tsv"; awk -F'\t' '$6=="scritto e verificato"{print $1}' "$W/stato-per-voce.tsv"; } | grep . | sort -u)
LS=$(for i in $LS_TUTTE; do [ "$(grep "^classe|$i|" "$W/foto-db-dopo.txt" | cut -d'|' -f3)" = 1 ] && echo "$i"; done); NLS=$(echo "$LS" | grep -c . || true)
LNP=$(for i in $LS_TUTTE; do [ "$(grep "^classe|$i|" "$W/foto-db-dopo.txt" | cut -d'|' -f3)" = 1 ] || echo "$i"; done); NNP=$(echo "$LNP" | grep -c . || true)
[ "$NNP" = 0 ] || log "classi NON pubbliche con scrittura sul registro: $NNP ($(echo $LNP | tr '\n' ' ')): nessuna scheda, 404 atteso (si verifica), nessuna revalidazione"
if [ "$NLS" = 0 ] && [ "$NNP" = 0 ]; then log "nessuna scrittura sul registro in questo lotto: nessuna pagina pubblica cambia → revalidazione e collaudo non necessari"; log "ESITO: ok · lotto scritto e riscontrato (solo archivio e controlli) · uscita 0"; exit 0; fi
if [ "$NLS" -gt 0 ]; then
  SEG=$(grep '^CRON_SECRET=' "$ENV_LOCAL" | cut -d= -f2- | tr -d '"' | tr -d "'"); [ -n "$SEG" ] || { log "ESITO (8): scritto, ma CRON_SECRET non trovato: revalidazione non eseguita"; exit 8; }
  echo "$LS" | grep . | split -l "$BLOCCO_REVALIDATE" - "$W/revalidate-blocco-"; TOT_REV=0; KOB=0; NB=0
  for B in "$W"/revalidate-blocco-*; do NB=$((NB+1)); n=$(grep -c . "$B"); HR=$(curl -s -m 120 -o "$B.json" -w '%{http_code}' -X POST -H "Authorization: Bearer $SEG" "$SITO/api/revalidate?scope=schede&isins=$(paste -sd, - < "$B")")
    python3 - "$B.json" "$n" "$HR" <<'EOF' > "$B.verifica" 2>&1 || { KOB=$((KOB+1)); log "revalidate blocco $NB ($n ISIN): NON conforme → $(head -c 200 "$B.verifica")"; continue; }
import json,sys
f,n,hr=sys.argv[1],int(sys.argv[2]),sys.argv[3]
try: j=json.load(open(f))
except Exception as e: print(f'corpo non JSON ({e})'); sys.exit(1)
ok = (hr=='200' and isinstance(j,dict) and j.get('ok') is True and isinstance(j.get('isin'), int) and not isinstance(j.get('isin'), bool) and j.get('isin') == n
      and isinstance(j.get('scartati'), list) and len(j['scartati']) == 0 and j.get('troppi') is False and j.get('schede_letterali') == 6*n)
print(f"HTTP {hr} ok={j.get('ok')!r} isin={j.get('isin')!r}/{n} schede_letterali={j.get('schede_letterali')!r}/{6*n} scartati={j.get('scartati')!r} troppi={j.get('troppi')!r} → {'conforme' if ok else 'NON conforme'}")
sys.exit(0 if ok else 1)
EOF
    TOT_REV=$((TOT_REV+n)); log "revalidate blocco $NB ($n ISIN): $(cat "$B.verifica")"; done
  [ "$KOB" = 0 ] && [ "$TOT_REV" = "$NLS" ] || { log "ESITO (8): scritto, revalidazione NON confermata ($KOB blocchi non conformi su $NB; riconciliati $TOT_REV/$NLS ISIN): nessun collaudo"; exit 8; }
  log "revalidate riconciliata: $NB blocchi (≤ $BLOCCO_REVALIDATE), $TOT_REV/$NLS ISIN con corpo conforme"
  sleep "${ATTESA_REVALIDATE:-20}"
fi
# ── attese pubbliche per classe dal comportamento effettivo della pagina: href = URL del documento, o PAGINA DEL FONDO per il factsheet in
#    anomalia definitiva; lingua scritta → «PDF in <lingua>»; invalidata → solo href; classe non pubblica → 404
mkdir -p "$W/letture"; KO=0
python3 - "$W" <<'EOF'
import json,sys
W=sys.argv[1]; COL={'kid_it':'kid_url','kid_en':'kid_url_en','factsheet_it':'factsheet_url','factsheet_en':'factsheet_url_en','prospetto_it':'prospectus_url','prospetto_en':'prospectus_url_en'}
ANOM=('anomalia: il collegamento non serve un PDF','anomalia: il collegamento non si apre fuori dal sito dell’emittente')
ling={(l.split('\t')[1],l.split('\t')[2]):(l.split('\t')[3],json.loads(l.rstrip('\n').split('\t')[4])) for l in open(f'{W}/attese.txt') if l.startswith('lingua\t')}
COLS=['riga','isin','kid_url','kid_url_en','factsheet_url','factsheet_url_en','prospectus_url','prospectus_url_en']
dbd={l.split('|')[1]:l.rstrip('\n').split('|') for l in open(f'{W}/foto-db-dopo.txt') if l.startswith('riga|')}
classi={l.split('|')[1]:l.rstrip('\n').split('|') for l in open(f'{W}/foto-db-dopo.txt') if l.startswith('classe|')}
per_isin={}
for l in open(f'{W}/stato-per-voce.tsv'):
    if l.startswith('#') or l.startswith('isin\t'): continue
    isin,tipo,_,_,sl,su,_,_=l.rstrip('\n').split('\t')
    if sl!='scritta e verificata' and su!='scritto e verificato': continue
    col=COL.get(tipo); url=dbd.get(isin,[''])[COLS.index(col)] if col and col in COLS else ''
    c=classi.get(isin,['','','1','','']); pubblica=(c[2]=='1'); pagina=c[3]; anom=c[4]
    via=tipo.startswith('factsheet') and anom in ANOM and bool(pagina)
    att={'tipo':tipo,'href':pagina if via else url,'lingua':None,'invalidata':False,'via_pagina':via}
    if sl=='scritta e verificata':
        az,patch=ling[(isin,tipo)]
        if az=='scrivi': att['lingua']=patch.get('kid_lang') or patch.get('factsheet_lang')
        else: att['invalidata']=True
    per_isin.setdefault(isin,{'pubblica':pubblica,'voci':[]})['voci'].append(att)
for isin,a in per_isin.items(): json.dump(a,open(f'{W}/letture/attese-{isin}.json','w'))
EOF
for isin in $LS $LNP; do for l in it en; do u="$SITO/$l/etf/$isin"; curl -s -m 60 -o /dev/null "$u"; code=$(curl -s -m 60 -o "$W/letture/$l-$isin.html" -w '%{http_code}' "$u"); python3 "$COLLAUDO" --html "$W/letture/$l-$isin.html" --lang "$l" --http "$code" --attese "$W/letture/attese-$isin.json" > "$W/letture/$l-$isin.collaudo" 2>&1 || { KO=$((KO+1)); log "collaudo $l $isin NON superato: $(tr '\n' ' ' < "$W/letture/$l-$isin.collaudo" | cut -c1-200)"; }; done; done
[ $KO = 0 ] || { log "ESITO (8): scritto, collaudo pubblico NON superato su $KO letture: nessun rilancio"; exit 8; }
log "collaudo pubblico superato $(( (NLS+NNP)*2 ))/$(( (NLS+NNP)*2 )) ($NLS classi pubbliche + $NNP non pubbliche × IT/EN)"; log "ESITO: ok · lotto scritto, riscontrato, revalidato e collaudato · uscita 0"; exit 0
