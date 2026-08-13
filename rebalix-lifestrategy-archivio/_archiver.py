#!/usr/bin/env python3
"""Archiviatore automatico Vanguard LifeStrategy.
- Scarica il report trimestrale dall'URL stabile (Vanguard lo sovrascrive).
- Legge la DATA dentro il PDF: archivia solo se è un trimestre NUOVO (robusto ai ritardi).
- Quando archivia il report, scarica anche i 13 factsheet dei sottostanti (Livello B).
- Naming coerente con l'archivio esistente: {anno}/{Mese}.pdf
Uso: python3 archive_lifestrategy.py [--dry-run]
"""
import os, re, sys, json, glob, time, urllib.request, tempfile, datetime, subprocess, shutil
import pdfplumber

# launchd parte con PATH minimale (/usr/bin:/bin:...): senza /usr/local/bin lo shebang
# «#!/usr/bin/env node» di vercel non trova node e il deploy muore con exit 127.
os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")

ARCHIVE = os.path.expanduser("~/backups/rebalix-lifestrategy-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
GIT = shutil.which("git") or "/usr/bin/git"
VERCEL = shutil.which("vercel") or "/usr/local/bin/vercel"
# i moduli dati versionati che i generatori rigenerano (gli unici file che il deploy auto committa)
DATA_FILES = ["lib/blog/ls-aum.ts", "lib/blog/ls-holdings.ts", "lib/blog/ls-holdings-uk.ts",
              "lib/blog/ls-lookthrough.ts", "lib/blog/ls-tax.ts", "lib/blog/ls-distributions.ts",
              "lib/blog/ls-bondstats.ts",  # ← mancava: il Q2-2026 restò rigenerato ma mai committato
              "lib/blog/ls-changes.ts"]   # registro variazioni panieri (trimestrale)
NEWSLETTER = "https://www.it.vanguard/content/dam/intl/europe/documents/it/lifestrategy-etf-newsletter-it-pro.pdf"
MONTHS = {"marzo":("Marzo","03"),"giugno":("Giugno","06"),"settembre":("Settembre","09"),"dicembre":("Dicembre","12")}

FACTSHEETS = {
 "all-world":"FTSE_All-World_UCITS_ETF_USD_Accumulating_9679_EU_INT_EN.pdf",
 "developed-world":"FTSE_Developed_World_UCITS_ETF_USD_Accumulating_9675_EU_INT_EN.pdf",
 "north-america":"FTSE_North_America_UCITS_ETF_USD_Accumulating_9680_EU_INT_EN.pdf",
 "emerging":"FTSE_Emerging_Markets_UCITS_ETF_USD_Distributing_9507_EU_INT_EN.pdf",
 "dev-europe":"FTSE_Developed_Europe_UCITS_ETF_EUR_Distributing_9520_EU_INT_EN.pdf",
 "japan":"FTSE_Japan_UCITS_ETF_USD_Accumulating_9674_EU_INT_EN.pdf",
 "asia-pac":"FTSE_Developed_Asia_Pacific_ex_Japan_UCITS_ETF_USD_Distributing_9522_EU_INT_EN.pdf",
 "sp500":"SandP_500_UCITS_ETF_USD_Accumulating_9694_EU_INT_EN.pdf",
 "global-agg":"Global_Aggregate_Bond_UCITS_ETF_EUR_Hedged_Accumulating_9443_EU_INT_EN.pdf",
 "usd-treasury":"USD_Treasury_Bond_UCITS_ETF_EUR_Hedged_Accumulating_9518_EU_INT_EN.pdf",
 "eur-govt":"EUR_Eurozone_Government_Bond_UCITS_ETF_EUR_Accumulating_9591_EU_INT_EN.pdf",
 "usd-corp":"USD_Corporate_Bond_UCITS_ETF_EUR_Hedged_Accumulating_9516_EU_INT_EN.pdf",
 "eur-corp":"EUR_Corporate_Bond_UCITS_ETF_EUR_Distributing_9659_EU_INT_EN.pdf",
 "uk-gilt":"U.K._Gilt_UCITS_ETF_EUR_Hedged_Accumulating_9519_EU_INT_EN.pdf",
}
FS_BASE = "https://fund-docs.vanguard.com/"

# documenti fiscali/cedole (URL stabili, aggiornati periodicamente da Vanguard)
EXTRA_DOCS = {
 "tax-italy-reduced-rate.xlsx": "https://fund-docs.vanguard.com/ETFsVF_IRRP.xlsx",
 "distribution-schedule.pdf": "https://fund-docs.vanguard.com/etf-distribution-schedule-vam.pdf",
}

DRY = "--dry-run" in sys.argv

def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M}  {msg}"
    print(line)
    if not DRY:
        with open(os.path.join(ARCHIVE, "_archiver.log"), "a") as f:
            f.write(line + "\n")

def fetch(url, dest, min_size=50_000):
    if DRY:
        log(f"[dry] scaricherei {url}  ->  {dest}")
        return True
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if len(data) < min_size:
        log(f"!! scarto sospetto ({len(data)}B) da {url} — salto")
        return False
    with open(dest, "wb") as f:
        f.write(data)
    return True

def quarter_of(pdf_path):
    with pdfplumber.open(pdf_path) as pdf:
        txt = "\n".join((pg.extract_text() or "") for pg in pdf.pages[:1])
    m = re.search(r"(31|30) (marzo|giugno|settembre|dicembre) (20\d\d)", txt)
    if not m:
        return None
    mese_it, mm = MONTHS[m.group(2)]
    return {"anno": m.group(3), "mese": mese_it, "mm": mm, "label": f"{m.group(3)}-{mm}"}

def capture_lookthrough():
    """Cattura mensile del look-through granulare GraphQL (auto-dedup). Isolata: un errore qui
    non deve bloccare l'archiviazione del report. Accumula la storia (l'API dà solo la foto corrente)."""
    if DRY:
        log("[dry] eseguirei la cattura look-through GraphQL"); return
    try:
        cap = subprocess.run([sys.executable, os.path.join(ARCHIVE, "_scripts", "capture_lookthrough.py")],
                             capture_output=True, text=True, timeout=240)
        for line in (cap.stdout + cap.stderr).splitlines():
            if line.strip(): log(line.strip())
        if cap.returncode != 0:
            log("!! cattura look-through: exit non-zero (fonte GraphQL da verificare)")
    except Exception as e:
        log(f"!! cattura look-through fallita: {e}")

def refresh_extra_docs():
    """Controlla e ri-scarica i documenti EXTRA_DOCS (fisco IRRP semestrale + calendario cedole)
    OGNI run, indipendentemente dal trimestre: hanno una cadenza propria (il fisco si aggiorna
    2 volte l'anno, il report trimestrale 4) e prima erano scaricati SOLO quando veniva rilevato
    un nuovo trimestre — potendo restare silenziosamente vecchi per mesi se i due calendari non
    si allineano per caso. Sovrascrive solo se il contenuto è davvero cambiato (niente log/churn
    inutile); scrive nell'ultima cartella factsheets/* esistente (quella che gen_tax_module.py
    già legge col glob più recente)."""
    dirs = sorted(glob.glob(os.path.join(ARCHIVE, "factsheets", "*")))
    if not dirs:
        log("!! [fiscal] nessuna cartella factsheets — salto (serve almeno un trimestre già archiviato)")
        return
    fs_dir = dirs[-1]
    for dest_name, url in EXTRA_DOCS.items():
        dest = os.path.join(fs_dir, dest_name)
        if DRY:
            log(f"[dry] [fiscal] controllerei {dest_name}"); continue
        tmp = tempfile.NamedTemporaryFile(delete=False).name
        try:
            if not fetch(url, tmp, min_size=10_000):
                continue
            changed = not os.path.exists(dest) or open(tmp, "rb").read() != open(dest, "rb").read()
            if changed:
                os.replace(tmp, dest)
                log(f"[fiscal] {dest_name} AGGIORNATO ({os.path.relpath(fs_dir, ARCHIVE)})")
            else:
                os.remove(tmp)
        except Exception as e:
            log(f"!! [fiscal] {dest_name}: {e}")

def regen(script):
    """Rigenera un modulo dati versionato del sito (ls-aum / ls-holdings / ls-lookthrough).
    Isolata: un errore qui non blocca l'archiviazione. Tiene vivi i grafici del blog.
    Ritorna True se il generatore è uscito con successo (usato dal battito del guardiano)."""
    if DRY:
        log(f"[dry] rigenererei via {script}"); return True
    try:
        g = subprocess.run([sys.executable, os.path.join(ARCHIVE, "_scripts", script)],
                           capture_output=True, text=True, timeout=240)  # parse_ls apre 14 PDF con pdfplumber
        for line in (g.stdout + g.stderr).splitlines():
            if line.strip(): log(line.strip())
        return g.returncode == 0
    except Exception as e:
        log(f"!! rigenerazione {script} fallita: {e}")
        return False

# ── Guardiano (dead-man's switch): battito a fine run verso l'endpoint Rebalix.
LS_GEN_TO_MODULE = {  # script -> chiave modulo attesa dal guardiano (lib/archiver-health)
    "parse_ls.py": "parse_ls", "gen_aum_module.py": "aum", "gen_holdings_module.py": "holdings",
    "gen_holdings_uk_module.py": "holdings_uk", "gen_lookthrough_module.py": "lookthrough",
    "gen_tax_module.py": "tax", "gen_distributions_module.py": "distributions",
    "gen_bondstats_module.py": "bondstats", "gen_ls_changes.py": "changes",
}

def send_heartbeat(name, errori, modules, data_date):
    """POST del battito. Fail-SOFT: un guardiano che rompe l'archivio sarebbe assurdo."""
    if DRY:
        log(f"[heartbeat] (dry) name={name} errori={errori} moduli_ok={sum(1 for v in modules.values() if v)}/{len(modules)}")
        return
    try:
        secret = None
        with open(os.path.join(REPO, ".env.local")) as f:
            for line in f:
                if line.startswith("CRON_SECRET="):
                    secret = line.split("=", 1)[1].strip().strip('"').strip("'"); break
        if not secret:
            log("!! [heartbeat] CRON_SECRET non trovato in .env.local — salto"); return
        payload = json.dumps({
            "name": name, "ok": errori == 0, "errors_count": errori,
            "metrics": {"modules": modules, "data_date": data_date},
        }).encode("utf-8")
        req = urllib.request.Request(
            "https://rebalix.com/api/heartbeat", data=payload, method="POST",
            headers={"Authorization": f"Bearer {secret}", "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            log(f"[heartbeat] inviato ({r.status})")
    except Exception as e:
        log(f"!! [heartbeat] invio fallito (non blocca l'archivio): {e}")

def autodeploy():
    """Se i moduli dati versionati sono cambiati (nuova cedola, nuovo trimestre, look-through
    aggiornato…): committa i SOLI file generati, push su Codeberg, e DEPLOY IN PRODUZIONE.
    Sicurezza: il deploy parte da un WORKTREE GIT PULITO all'ultimo commit → in produzione va
    solo il codice COMMITTATO, mai la WIP eventualmente aperta nel repo. Isolata: un errore qui
    non blocca l'archiviazione. Ritorna True se non c'era nulla da deployare o il deploy è
    riuscito; False se il deploy è fallito (→ conta come errore nel battito del guardiano).
    Il deploy viene RITENTATO (fallimenti rete/build spesso transitori); se fallisce comunque,
    l'output COMPLETO di vercel finisce nel log (prima si perdeva → causa non diagnosticabile)."""
    if DRY:
        log("[deploy] (simulazione) commit + deploy dei moduli dati saltato"); return True
    if not os.path.isdir(REPO):
        log(f"[deploy] repo non trovato ({REPO}) — salto."); return True
    branch = subprocess.run([GIT, "-C", REPO, "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    if branch != "main":
        log(f"[deploy] branch = {branch} (non main) — salto commit/deploy per sicurezza."); return True
    files = [f for f in DATA_FILES if os.path.exists(os.path.join(REPO, f))]
    try:
        # stage SOLO i moduli dati (mai altro), poi verifica se qualcosa è davvero cambiato
        subprocess.run([GIT, "-C", REPO, "add", "--"] + files, check=True)
        if subprocess.run([GIT, "-C", REPO, "diff", "--cached", "--quiet", "--"] + files).returncode == 0:
            log("[deploy] moduli dati invariati — nessun deploy."); return True
        changed = subprocess.run([GIT, "-C", REPO, "diff", "--cached", "--name-only", "--"] + files,
                                 capture_output=True, text=True).stdout.split()
        msg = ("data(blog-ls): refresh automatico dei moduli versionati\n\n"
               "Rigenerati dall'archiviatore Vanguard LifeStrategy (dato ufficiale piu fresco).\n\n"
               "Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>")
        subprocess.run([GIT, "-C", REPO, "commit", "-m", msg, "--"] + files, check=True)
        log(f"[deploy] commit dei moduli: {', '.join(changed)}")
        # ANTI-RETROCESSIONE (lezione 13 ago 2026): con più macchine che pushano, deployare
        # una base non allineata a origin/main retrocede in prod il lavoro delle altre.
        # Rebase + push obbligatori: se una delle due fallisce, deploy ANNULLATO (False → guardiano).
        if subprocess.run([GIT, "-C", REPO, "fetch", "origin", "main"]).returncode != 0:
            log("!! [deploy] fetch origin fallito — deploy ANNULLATO (base non verificabile)"); return False
        if subprocess.run([GIT, "-C", REPO, "rebase", "-X", "theirs", "origin/main"]).returncode != 0:
            subprocess.run([GIT, "-C", REPO, "rebase", "--abort"])
            log("!! [deploy] rebase su origin/main fallito — deploy ANNULLATO (risolvere a mano)"); return False
        if subprocess.run([GIT, "-C", REPO, "push", "origin", "main"]).returncode != 0:
            log("!! [deploy] push fallito DOPO il rebase — deploy ANNULLATO (mai deployare una base non pushata)"); return False
        head = subprocess.run([GIT, "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        # deploy da worktree pulito: SOLO il codice committato finisce in produzione
        wt = tempfile.mkdtemp(prefix="rebalix-deploy-")
        try:
            subprocess.run([GIT, "-C", REPO, "worktree", "add", "--detach", wt, head], check=True)
            vsrc = os.path.join(REPO, ".vercel")
            if os.path.isdir(vsrc):
                shutil.copytree(vsrc, os.path.join(wt, ".vercel"))
            r = None
            for attempt in range(1, 4):
                r = subprocess.run([VERCEL, "--prod", "--yes"], cwd=wt, capture_output=True, text=True, timeout=900)
                if r.returncode == 0:
                    for line in (r.stdout + r.stderr).splitlines():
                        if any(k in line for k in ("Production:", "Aliased:")):
                            log("[deploy] " + line.strip())
                    log(f"[deploy] deploy prod OK ({head[:8]}) al tentativo {attempt}")
                    return True
                log(f"!! [deploy] tentativo {attempt}/3 fallito (exit {r.returncode})")
                if attempt < 3:
                    time.sleep(20)
            out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()[-1800:] if r else "(nessun output)"
            log(f"!! [deploy] DEPLOY FALLITO dopo 3 tentativi ({head[:8]}). Il commit è su Codeberg "
                f"ma NON in produzione. Output vercel:\n{out}")
            return False
        finally:
            subprocess.run([GIT, "-C", REPO, "worktree", "remove", "--force", wt])
    except Exception as e:
        log(f"!! auto-deploy fallito: {e}")
        return False

def archive_newsletter():
    """Blocco trimestrale: scarica il report Vanguard e, se è un trimestre NUOVO, lo archivia
    coi factsheet. Isolato in funzione così i suoi `return` anticipati non saltano il battito."""
    tmp = tempfile.NamedTemporaryFile(suffix=".pdf", delete=False).name
    req = urllib.request.Request(NEWSLETTER, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        open(tmp, "wb").write(r.read())
    q = quarter_of(tmp)
    if not q:
        log("!! non riesco a leggere la data dal report — interrompo"); return
    dest = os.path.join(ARCHIVE, q["anno"], f"{q['mese']}.pdf")
    log(f"report online = {q['mese']} {q['anno']}")
    if os.path.exists(dest):
        log(f"già archiviato ({os.path.relpath(dest, ARCHIVE)}) — niente da fare.")
        return
    log(f"NUOVO trimestre! archivio {os.path.relpath(dest, ARCHIVE)} + 13 factsheet")
    os.makedirs(os.path.dirname(dest), exist_ok=True)
    if not DRY:
        os.replace(tmp, dest)
    fs_dir = os.path.join(ARCHIVE, "factsheets", q["label"])
    if not DRY:
        os.makedirs(fs_dir, exist_ok=True)
    ok = 0
    for name, fn in FACTSHEETS.items():
        if fetch(FS_BASE + fn, os.path.join(fs_dir, name + ".pdf")):
            ok += 1
    # fisco/cedole (EXTRA_DOCS) NON scaricati qui: li tiene freschi refresh_extra_docs(), chiamata
    # ogni run indipendentemente — dal prossimo run scriverà in questa cartella (ora la più recente).
    log(f"fatto: report + {ok}/{len(FACTSHEETS)} factsheet in factsheets/{q['label']}/")

def main():
    log(f"--- avvio archiviatore {'(SIMULAZIONE)' if DRY else ''} ---")
    errori = 0
    try:
        capture_lookthrough()  # ogni run, auto-dedup per data
    except Exception as e:
        errori += 1; log(f"!! capture_lookthrough: {e}")
    try:
        refresh_extra_docs()  # ogni run: fisco IRRP + cedole, scollegato dal trigger trimestrale
    except Exception as e:
        errori += 1; log(f"!! refresh_extra_docs: {e}")
    # ogni run: sincronizza i moduli dati del sito con l'archivio (AUM, paniere, radiografia)
    # parse_ls.py PER PRIMO: ri-estrae ls_timeseries.json da tutti i PDF trimestrali archiviati,
    # così AUM / paniere euro / duration (che ne dipendono) riflettono l'ultimo report senza passi manuali.
    modules = {}
    for s in ("parse_ls.py", "gen_aum_module.py", "gen_holdings_module.py", "gen_holdings_uk_module.py", "gen_lookthrough_module.py", "gen_tax_module.py", "gen_distributions_module.py", "gen_bondstats_module.py", "gen_ls_changes.py"):
        modules[LS_GEN_TO_MODULE[s]] = regen(s)
    if not autodeploy():  # deploy fallito = i dati freschi non sono arrivati in prod → allerta
        errori += 1
    errori += sum(1 for v in modules.values() if not v)
    try:
        archive_newsletter()
    except Exception as e:
        errori += 1; log(f"!! archivio newsletter fallito: {e}")
    # dati TRIMESTRALI: nessuna data-del-dato giornaliera da riportare (data_date=None)
    send_heartbeat("lifestrategy", errori, modules, None)

if __name__ == "__main__":
    main()
