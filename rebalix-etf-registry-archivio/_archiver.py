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

    send_heartbeat(ok, falliti + (0 if p.returncode == 0 else 1), modules)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
