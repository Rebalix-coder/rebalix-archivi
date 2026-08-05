#!/usr/bin/env python3
"""Runner mensile del registro ETF (etf_registry) — benchmark dichiarati dagli emittenti.

Lancia `node scripts/ingest-etf-registry.mjs --commit` dal repo: il lavoro vero
(fetch dei 9 emittenti automatici, sanity, upsert, soft-delist con soglia,
snapshot in questo archivio) vive TUTTO nello script node — qui solo il contorno
operativo: stato anti-doppioni, log, battito al guardiano.

NOTA UBS: il fetcher UBS legge l'Excel «esteso» scaricato a mano col browser
(cancello Akamai). Se in ~/Downloads c'è un file fresco viene ingerito, altrimenti
viene SALTATO senza errore: l'aggiornamento UBS resta parte del giro-browser
mensile manuale (vedi memoria progetto serie-indici).

Uso: python3 _archiver.py [--dry-run] [--force]
Cadenza: launchd il giorno 2 del mese alle 07:45 (RunAtLoad recupera i mesi col
Mac spento; _state.json evita i doppi giri nello stesso mese).
"""
import os, re, sys, json, datetime, subprocess, urllib.request

os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")

ARCHIVE = os.path.expanduser("~/backups/rebalix-etf-registry-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
NODE = "/usr/local/bin/node"
STATE = os.path.join(ARCHIVE, "_state.json")

DRY = "--dry-run" in sys.argv
FORCE = "--force" in sys.argv
TODAY = datetime.date.today()
YM = f"{TODAY:%Y-%m}"


def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M}  {msg}"
    print(line)
    if not DRY:
        with open(os.path.join(ARCHIVE, "_archiver.log"), "a") as f:
            f.write(line + "\n")


def send_heartbeat(ok, errori, modules):
    if DRY:
        log(f"[heartbeat] (dry) ok={ok} moduli={modules}")
        return
    try:
        secret = None
        with open(os.path.join(REPO, ".env.local")) as f:
            for line in f:
                if line.startswith("CRON_SECRET="):
                    secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        if not secret:
            log("!! [heartbeat] CRON_SECRET non trovato — salto")
            return
        payload = json.dumps({"name": "etf-registry", "ok": ok, "errors_count": errori,
                              "metrics": {"modules": modules, "data_date": f"{TODAY}"}}).encode()
        req = urllib.request.Request("https://rebalix.com/api/heartbeat", data=payload, method="POST",
                                     headers={"Authorization": f"Bearer {secret}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            log(f"[heartbeat] inviato ({r.status})")
    except Exception as e:
        log(f"!! [heartbeat] invio fallito (non blocca): {e}")


def main():
    # stato: un solo giro per mese (RunAtLoad può svegliarci più volte)
    state = {}
    if os.path.exists(STATE):
        with open(STATE) as f:
            state = json.load(f)
    if state.get("last_ym") == YM and not FORCE and not DRY:
        log(f"già girato per {YM}, esco (usa --force per rifare)")
        return

    cmd = [NODE, "scripts/ingest-etf-registry.mjs"] + ([] if DRY else ["--commit"])
    log(f"lancio: {' '.join(cmd)}")
    try:
        p = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=1800)
    except subprocess.TimeoutExpired:
        log("!! TIMEOUT (30 min)")
        send_heartbeat(False, 1, {"timeout": False})
        sys.exit(1)

    out = (p.stdout or "") + "\n" + (p.stderr or "")
    for line in out.strip().splitlines()[-25:]:
        log(f"  | {line}")

    # moduli per il guardiano: '  <emittente>: N righe …' = ok; 'FALLITO' = ko; 'SALTATO' = omesso
    modules = {}
    for m in re.finditer(r"^\s{2}(\w[\w&]*): (\d+) righe", out, re.M):
        modules[m.group(1)] = True
    for m in re.finditer(r"^\s{2}✗ (\w[\w&]*):", out, re.M):
        modules[m.group(1)] = False
    falliti = sum(1 for v in modules.values() if not v)
    ok = p.returncode == 0 and falliti == 0 and len(modules) > 0

    if ok and not DRY:
        with open(STATE, "w") as f:
            json.dump({"last_ym": YM, "at": f"{datetime.datetime.now():%Y-%m-%d %H:%M}"}, f)
    log(f"esito: exit={p.returncode}, emittenti ok={sum(1 for v in modules.values() if v)}/{len(modules)}")

    # Costi di transazione dai KID (trimestrale di fatto: lo script salta le righe
    # con estrazione più fresca di 80 giorni). NON-fatale: un problema qui non deve
    # oscurare il giro principale — finisce nel battito come modulo dedicato.
    if not DRY:
        try:
            k = subprocess.run([NODE, "scripts/enrich-kid-costs.mjs", "--commit"],
                               cwd=REPO, capture_output=True, text=True, timeout=3600)
            for line in (k.stdout or "").strip().splitlines()[-4:]:
                log(f"  |kid| {line}")
            modules["kid-costs"] = k.returncode == 0
        except Exception as e:
            log(f"!! kid-costs fallito (non blocca): {e}")
            modules["kid-costs"] = False

    # Borse di quotazione da FIRDS/ESMA (3.188 ISIN x ~0,6s ≈ 35-40 min). NON-fatale
    # come kid-costs. --only-missing NO: il senso del giro mensile è proprio rivedere
    # gli stati (un listing puo' passare a Terminated), quindi si ripassa tutto.
    if not DRY:
        try:
            l = subprocess.run([NODE, "scripts/enrich-etf-listings.mjs", "--commit"],
                               cwd=REPO, capture_output=True, text=True, timeout=5400)
            for line in (l.stdout or "").strip().splitlines()[-3:]:
                log(f"  |listings| {line}")
            modules["listings"] = l.returncode == 0
        except Exception as e:
            log(f"!! listings fallito (non blocca): {e}")
            modules["listings"] = False

    # Serie storiche + COMPOSIZIONI (NAV, total-return, benchmark, holdings) per i
    # 4 emittenti industrializzati. E' il modulo LUNGO (~3-4h coi ritmi di cortesia):
    # timeout largo, non-fatale, e riprende da solo se interrotto (salta i gia'
    # fatti in giornata). Le pagine mostrano sempre la data di rilevazione.
    if not DRY:
        try:
            sr = subprocess.run([NODE, "scripts/ingest-etf-series.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=6*3600)
            for line in (sr.stdout or "").strip().splitlines()[-4:]:
                log(f"  |series| {line}")
            modules["series"] = sr.returncode == 0
        except Exception as e:
            log(f"!! series fallito (non blocca): {e}")
            modules["series"] = False

    # Listini ufficiali delle borse (ticker+valuta per linea; primo modulo Xetra).
    # PRIMA dei ticker derivati: cio' che scrive la borsa non va sovrascritto.
    if not DRY:
        try:
            v = subprocess.run([NODE, "scripts/enrich-venue-listings.mjs", "--commit"],
                               cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (v.stdout or "").strip().splitlines()[-2:]:
                log(f"  |venues| {line}")
            modules["venues"] = v.returncode == 0
        except Exception as e:
            log(f"!! venues fallito (non blocca): {e}")
            modules["venues"] = False

    # Ticker per borsa (whitelist + emittenti + OpenFIGI con taratura). Dopo listings:
    # aggiorna le righe che il modulo precedente ha appena creato/rivisto.
    if not DRY:
        try:
            t = subprocess.run([NODE, "scripts/enrich-etf-tickers.mjs", "--commit"],
                               cwd=REPO, capture_output=True, text=True, timeout=5400)
            for line in (t.stdout or "").strip().splitlines()[-3:]:
                log(f"  |tickers| {line}")
            modules["tickers"] = t.returncode == 0
        except Exception as e:
            log(f"!! tickers fallito (non blocca): {e}")
            modules["tickers"] = False

    # Documenti ufficiali (prospetto+factsheet): aggancia i fondi nuovi e vigila
    # sugli schemi-URL. Gli URL emittente sono stabili e aggiornati sul posto.
    if not DRY:
        try:
            dd = subprocess.run([NODE, "scripts/enrich-etf-documents.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=1200)
            for line in (dd.stdout or "").strip().splitlines()[-2:]:
                log(f"  |documents| {line}")
            modules["documents"] = dd.returncode == 0
        except Exception as e:
            log(f"!! documents fallito (non blocca): {e}")
            modules["documents"] = False

    # Archivio storico dei PDF (KID/prospetto/factsheet): gli emittenti aggiornano
    # sul posto e la versione di ieri sparisce dal mondo — noi la teniamo. Dedup
    # per hash: si salva solo ciò che è cambiato. «La storia è valore» (Linus).
    if not DRY:
        try:
            da = subprocess.run([NODE, "scripts/archive-etf-documents.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=3*3600)
            for line in (da.stdout or "").strip().splitlines()[-2:]:
                log(f"  |doc-archive| {line}")
            modules["doc-archive"] = da.returncode == 0
        except Exception as e:
            log(f"!! doc-archive fallito (non blocca): {e}")
            modules["doc-archive"] = False

    send_heartbeat(ok, falliti + (0 if p.returncode == 0 else 1), modules)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
