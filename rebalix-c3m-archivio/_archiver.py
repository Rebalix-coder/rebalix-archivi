#!/usr/bin/env python3
"""Archiviatore automatico C3M (Amundi Euro Government Bond 0-6M, FR0010754200).

Nato il 28 lug 2026 per l'articolo «monetario n.2» (confronto con Xeon): le composizioni
non si ricostruiscono a posteriori, quindi si archivia PRIMA di scrivere (regola playbook).

- Snapshot giornaliero da /mapi/ProductAPI/getProductsData (API pubblica, niente gate a curl):
  caratteristiche (NAV+data, AUM, TER, SRRI...) + spaccati (Top10 fondo/indice, paesi, rating,
  scadenze — il paniere COMPLETO non è pubblico: Amundi espone solo questi aggregati) + metriche
  dichiarate (performance annuali fondo/indice: servono da controprova ai nostri calcoli).
  ⚠️ Il corpo della richiesta usa `breakDown` SINGOLARE {aggregationFields:[...]} — il plurale
  `breakDowns` esiste solo nella risposta (mezz'ora persa a capirlo, non ricapiterà).
- Raw per data-dato (idempotente) + history JSONL dedup (una riga per data di posizione).
- Serie storiche complete (officialNav + adjustedBenchPrice, riscritte a ogni giro: la
  «adjusted» è RIBASATA — confrontare sempre rendimenti, mai livelli).
- Spread bid/ask ~10:45 via Yahoo (C3M.MI e XEON.MI insieme: servono al confronto).
- Documenti mensili: factsheet (URL con data fine-mese PREVEDIBILE) + KID/prospetto
  (URL con data che ruota a ogni versione: si riprova l'ultimo noto, 404 = allarme).
- Heartbeat al guardiano (name=c3m, fail-soft).
Niente regen/autodeploy in v1: i moduli dati nasceranno con l'articolo.
Uso: python3 _archiver.py [--dry-run]
"""
import os, sys, json, time, datetime, hashlib, subprocess, tempfile, shutil, urllib.request, urllib.parse, urllib.error

# launchd parte con PATH minimale: senza questa riga ogni subprocess con shebang env muore.
os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")

ARCHIVE = os.path.expanduser("~/backups/rebalix-c3m-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
ISIN = "FR0010754200"
MAPI = "https://www.amundietf.it/mapi/ProductAPI/getProductsData"
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"
DRY = "--dry-run" in sys.argv

CHARACTERISTICS = [
    "NAV", "NAV_DATE_DISPLAYED", "AUM", "AUM_IN_EURO", "FUND_AUM", "FUND_AUM_IN_EURO",
    "TER", "TOTAL_EXPENSE_RATIO", "SRRI", "POSITION_AS_OF_DATE", "FUND_BREAKDOWNS_AS_OF_DATE",
    "BENCHMARK_NAME", "BENCHMARK_TICKER", "BENCHMARK_NUMBER_OF_COMPONENTS",
    "FUND_REPLICATION_METHODOLOGY", "FUND_SECURITIES_LENDING", "DISTRIBUTION_POLICY",
    "MNEMO", "SHARE_MARKETING_NAME", "FUND_SFDR_CLASSIFICATION",
    # autorizzazione alla vendita (passporting) e ticker per piazza: appunto di Linus 29/7 —
    # «autorizzato in un paese» ≠ «quotato su quella borsa», l'articolo mostra entrambi
    "PASSPORTED_COUNTRIES", "MAIN_LISTINGS",
]
BREAKDOWNS = ["FUND_TOP10", "FUND_COUNTRIES", "FUND_MATURITIES", "FUND_RATINGS",
              "INDEX_TOP10", "INDEX_COUNTRIES", "INDEX_MATURITIES", "INDEX_RATINGS"]
METRICS = ([{"indicator": i, "period": p}
            for i in ("shareCalendarPerformance", "benchmarkCalendarPerformance")
            for p in [str(y) for y in range(2016, datetime.date.today().year + 1)]] +
           [{"indicator": i, "period": p}
            for i in ("shareAnnualizedPerformance", "benchmarkAnnualizedPerformance")
            for p in ("YTD", "ONE_YEAR", "THREE_YEARS", "FIVE_YEARS", "TEN_YEARS", "SINCE_INCEPTION")])
SERIES = ["officialNav", "adjustedBenchPrice", "shareAumInMCcy"]  # AUM: storico ufficiale 2017→ (idea Linus 29/7)
# URL documenti: la data nel percorso ruota a ogni versione → ultimo noto + allarme sul 404.
DOCS = {
    "kid":        "https://www.amundietf.it/pdfDocuments/kid-priips/FR0010754200/ITA/ITA/20260428",
    "prospetto":  "https://www.amundietf.it/pdfDocuments/prospectus/FR0010754200/ENG/ITA/20260414",
}
FACTSHEET = "https://www.amundietf.it/pdfDocuments/monthly-factsheet/FR0010754200/ITA/ITA/RETAIL/ETF/{ymd}"

# ── Cablaggio pubblicazione (30/7, lancio articolo): regen moduli + autodeploy.
GIT = shutil.which("git") or "/usr/bin/git"
VERCEL = shutil.which("vercel") or "/usr/local/bin/vercel"
GENERATORI = ["gen_c3m_performance.py", "gen_c3m_composition.py", "gen_c3m_tax.py",
              "gen_c3m_aum.py", "gen_c3m_xeon_series.py"]  # gen_c3m_changes gira già nel passo variazioni
DATA_FILES = ["lib/blog/c3m-performance.ts", "lib/blog/c3m-composition.ts", "lib/blog/c3m-tax.ts",
              "lib/blog/c3m-aum.ts", "lib/blog/c3m-xeon-series.ts", "lib/blog/c3m-changes.ts"]


def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M}  {msg}"
    print(line)
    if not DRY:
        with open(os.path.join(ARCHIVE, "_archiver.log"), "a") as f:
            f.write(line + "\n")


def net_retry(fn, *a, **kw):
    """3 tentativi (0s/5s/20s): un blip DNS non deve bucare una serie giornaliera."""
    for i, pausa in enumerate((0, 5, 20)):
        if pausa:
            time.sleep(pausa)
        try:
            return fn(*a, **kw)
        except (urllib.error.URLError, OSError, TimeoutError) as e:
            ultimo = e
            log(f"   [retry {i+1}/3] {e}")
    raise ultimo


def mapi_post(body):
    def _go():
        req = urllib.request.Request(MAPI, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json", "User-Agent": UA})
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    return net_retry(_go)


def scrivi(path, contenuto, binario=False):
    if DRY:
        log(f"   (dry) scriverei {path}")
        return
    full = os.path.join(ARCHIVE, path)
    os.makedirs(os.path.dirname(full), exist_ok=True)
    with open(full, "wb" if binario else "w") as f:
        f.write(contenuto if binario else json.dumps(contenuto, ensure_ascii=False, indent=1))


def append_jsonl(path, riga, chiave):
    """Aggiunge una riga se la chiave non è già presente. Ritorna True se scritta."""
    full = os.path.join(ARCHIVE, path)
    if os.path.exists(full):
        with open(full) as f:
            for l in f:
                try:
                    if json.loads(l).get("chiave") == chiave:
                        return False
                except json.JSONDecodeError:
                    continue
    if DRY:
        log(f"   (dry) appenderei {chiave} a {path}")
        return True
    with open(full, "a") as f:
        f.write(json.dumps({"chiave": chiave, **riga}, ensure_ascii=False) + "\n")
    return True


def archive_snapshot():
    """Caratteristiche + spaccati + metriche dichiarate → raw per data + history dedup."""
    d = mapi_post({"productIds": [ISIN], "productType": "PRODUCT",
                   "characteristics": CHARACTERISTICS,
                   "breakDown": {"aggregationFields": BREAKDOWNS},
                   # paniere COMPLETO (55 strumenti con ISIN/peso/quantità): scovato da Linus
                   # 29/7 sul sito («SCARICA LA COMPOSIZIONE»), forma richiesta dal widget JS
                   "composition": {"compositionFields": ["date", "type", "bbg", "isin", "name",
                                                          "weight", "quantity", "currency",
                                                          "sector", "country", "countryOfRisk"]},
                   "metrics": METRICS})
    p = d["products"][0]
    car = p.get("characteristics") or {}
    asof = car.get("POSITION_AS_OF_DATE") or datetime.date.today().isoformat()
    if not car.get("NAV"):
        raise RuntimeError("snapshot senza NAV: risposta anomala, non archivio")
    scrivi(f"raw/{asof}.json", p)  # idempotente: stessa data-dato = stesso file
    # history composizione: una riga per data di posizione (spaccati + paniere completo)
    comp = p.get("composition") or {}
    if append_jsonl("history/composizione.jsonl",
                    {"breakDowns": p.get("breakDowns") or [], "composition": comp}, asof):
        log(f"   composizione nuova per {asof} "
            f"({comp.get('totalNumberOfInstruments', '?')} strumenti nel paniere completo)")
    # history NAV/AUM: una riga per data NAV
    nav_ms = car.get("NAV_DATE_DISPLAYED")
    nav_date = datetime.datetime.utcfromtimestamp(nav_ms / 1000).date().isoformat() if nav_ms else asof
    append_jsonl("history/nav-aum.jsonl",
                 {"nav": car.get("NAV"), "aum": car.get("AUM"), "ter": car.get("TER")}, nav_date)
    # metriche dichiarate (controprova dei nostri calcoli): tenute nel raw, basta così
    return nav_date


def archive_series():
    """Serie complete NAV + indice ribasato, riscritte a ogni giro (sono la storia intera)."""
    oggi = datetime.date.today().isoformat()
    d = mapi_post({"productIds": [ISIN], "productType": "PRODUCT",
                   "historics": [{"indicator": s, "startDate": "2005-01-01", "endDate": oggi} for s in SERIES]})
    for h in d["products"][0].get("historics") or []:
        punti = h.get("historicalData") or []
        if len(punti) < 100:
            raise RuntimeError(f"serie {h.get('indicator')}: solo {len(punti)} punti, non sovrascrivo")
        scrivi(f"nav/{h['indicator']}.json", punti)
    log(f"   serie aggiornate ({', '.join(SERIES)})")


def archive_spread():
    """Bid/ask di C3M.MI e XEON.MI (rito cookie+crumb Yahoo). Book valido solo a mercato aperto:
    fuori orario Borsa Italiana (~9:15-17:25 ora locale) il book è stantio/largo → non si registra
    (verificato al primo giro delle 22:11: spread C3M 0,21% con bid a -1,8% dal prezzo = spazzatura)."""
    ora = datetime.datetime.now()
    if not (datetime.time(9, 30) <= ora.time() <= datetime.time(17, 25)):
        log(f"   spread: mercato chiuso ({ora:%H:%M}), salto")
        return
    jar = urllib.request.HTTPCookieProcessor()
    opener = urllib.request.build_opener(jar)
    opener.addheaders = [("User-Agent", UA)]
    try:
        opener.open("https://fc.yahoo.com", timeout=30).read()
    except Exception:
        pass  # risponde 404 DI PROPOSITO (serve solo il cookie): niente retry, sarebbe rumore
    crumb = net_retry(lambda: opener.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=30).read().decode())
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols=C3M.MI,XEON.MI&crumb={urllib.parse.quote(crumb)}"
    quotes = json.loads(net_retry(lambda: opener.open(url, timeout=60).read())).get("quoteResponse", {}).get("result") or []
    oggi = datetime.date.today().isoformat()
    for q in quotes:
        bid, ask = q.get("bid"), q.get("ask")
        if not bid or not ask or bid <= 0 or ask <= bid * 0.9:
            log(f"   spread {q.get('symbol')}: book non valido (bid={bid} ask={ask}), salto")
            continue
        append_jsonl("spread.jsonl", {"symbol": q.get("symbol"), "bid": bid, "ask": ask,
                                      "spread_pct": round((ask - bid) / ((ask + bid) / 2) * 100, 4),
                                      # AUM (netAssets) accumulato per il futuro grafico XEON
                                      # (pattern XD: DWS non lo espone via REST — 30/7)
                                      "aum": q.get("netAssets"), "price": q.get("regularMarketPrice")},
                     f"{oggi}|{q.get('symbol')}")
    log(f"   spread registrato per {len(quotes)} simboli")


def _scarica(url, dest):
    def _go():
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=90) as r:
            return r.read()
    raw = net_retry(_go)
    if not raw.startswith(b"%PDF"):
        raise RuntimeError(f"non è un PDF ({len(raw)} byte): {url[-40:]}")
    scrivi(dest, raw, binario=True)


def archive_docs():
    """Factsheet del mese chiuso + KID/prospetto correnti.
    FACTSHEET: Amundi lo pubblica con LAG (1 ago 2026: quello di luglio non c'era ancora →
    404 per giorni). Si ritenta OGNI giorno finché appare; il 404 è ATTESA normale, non
    errore. Allarme vero (fail-loud) solo se manca ancora anche il factsheet di DUE mesi
    fa: a quel punto non è lag, è il pattern URL cambiato.
    KID/PROSPETTO: mensile nei primi 7 giorni; lì il 404 resta un ERRORE (= versione
    ruotata, la data nell'URL è cambiata → aggiornare DOCS a mano)."""
    oggi = datetime.date.today()
    fine_mese_scorso = oggi.replace(day=1) - datetime.timedelta(days=1)
    ymd = fine_mese_scorso.strftime("%Y%m%d")
    dest_fs = f"docs/factsheet_{ymd}.pdf"
    if not os.path.exists(os.path.join(ARCHIVE, dest_fs)):
        try:
            _scarica(FACTSHEET.format(ymd=ymd), dest_fs)
            log(f"   factsheet {ymd} archiviato")
        except Exception:
            due_mesi_fa = (fine_mese_scorso.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y%m%d")
            if os.path.exists(os.path.join(ARCHIVE, f"docs/factsheet_{due_mesi_fa}.pdf")):
                log(f"   factsheet {ymd}: non ancora pubblicato — si ritenta domani (lag normale Amundi)")
            else:
                raise RuntimeError(f"factsheet: mancano sia {ymd} sia {due_mesi_fa} — pattern URL cambiato?")
    if oggi.day > 7:
        return
    for nome, url in DOCS.items():
        ver = url.rsplit("/", 1)[-1]
        dest = f"docs/{nome}_{ver}.pdf"
        if not os.path.exists(os.path.join(ARCHIVE, dest)):
            # 404 qui = Amundi ha pubblicato una NUOVA versione (la data nell'URL è cambiata):
            # l'errore finisce nel conteggio → heartbeat → email. Si aggiorna DOCS a mano.
            _scarica(url, dest)
            log(f"   {nome} {ver} archiviato")


def send_heartbeat(errori, modules, data_date):
    """Batte al guardiano archiver-health. FAIL-SOFT: un heartbeat rotto non è un errore di dati."""
    if DRY:
        log(f"[heartbeat] (dry) c3m errori={errori} moduli={modules} data={data_date}")
        return
    try:
        secret = None
        with open(os.path.join(REPO, ".env.local")) as f:
            for l in f:
                if l.startswith("CRON_SECRET="):
                    secret = l.split("=", 1)[1].strip().strip('"').strip("'")
        if not secret:
            log("!! [heartbeat] CRON_SECRET non trovato in .env.local — salto")
            return
        payload = json.dumps({"name": "c3m", "ok": errori == 0, "errors_count": errori,
                              "metrics": {"modules": modules, "data_date": data_date}}).encode()
        req = urllib.request.Request("https://rebalix.com/api/heartbeat", data=payload, method="POST",
                                     headers={"Content-Type": "application/json",
                                              "Authorization": f"Bearer {secret}"})
        urllib.request.urlopen(req, timeout=30).read()
        log("[heartbeat] battito inviato")
    except Exception as e:
        log(f"!! [heartbeat] fallito (non conto come errore dati): {e}")


def regen(script):
    """Rigenera un modulo dati (pattern Xtrackers). Isolata: un errore non blocca l'archivio;
    i golden fail-loud dentro ai generatori lasciano in piedi l'ultimo modulo buono."""
    if DRY:
        log(f"[dry] rigenererei via {script}"); return True
    try:
        g = subprocess.run([sys.executable, os.path.join(ARCHIVE, "_scripts", script)],
                           capture_output=True, text=True, timeout=300)
        for line in (g.stdout + g.stderr).splitlines():
            if line.strip(): log("   " + line.strip())
        return g.returncode == 0
    except Exception as e:
        log(f"!! rigenerazione {script} fallita: {e}")
        return False


def autodeploy():
    """Moduli cambiati → commit dei SOLI file generati, push, deploy prod da worktree
    pulito (pattern identico a Xtrackers/LS). Output deterministico dei generatori =
    deploy solo quando i dati cambiano davvero."""
    if DRY:
        log("[deploy] (simulazione) salto"); return True
    if not os.path.isdir(REPO):
        log("[deploy] repo non trovato — salto."); return True
    branch = subprocess.run([GIT, "-C", REPO, "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    if branch != "main":
        log(f"[deploy] branch {branch} ≠ main — salto per sicurezza."); return True
    files = [f for f in DATA_FILES if os.path.exists(os.path.join(REPO, f))]
    try:
        subprocess.run([GIT, "-C", REPO, "add", "--"] + files, check=True)
        if subprocess.run([GIT, "-C", REPO, "diff", "--cached", "--quiet", "--"] + files).returncode == 0:
            log("[deploy] moduli dati invariati — nessun deploy."); return True
        msg = ("data(blog-c3m): refresh automatico dei moduli versionati\n\n"
               "Rigenerati dall'archiviatore C3M (golden test superati).\n\n"
               "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
        subprocess.run([GIT, "-C", REPO, "commit", "-m", msg, "--"] + files, check=True)
        log("[deploy] commit dei moduli c3m")
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
        wt = tempfile.mkdtemp(prefix="rebalix-deploy-c3m-")
        try:
            subprocess.run([GIT, "-C", REPO, "worktree", "add", "--detach", wt, head], check=True)
            vsrc = os.path.join(REPO, ".vercel")
            if os.path.isdir(vsrc):
                shutil.copytree(vsrc, os.path.join(wt, ".vercel"))
            r = None
            for attempt in range(1, 4):
                r = subprocess.run([VERCEL, "--prod", "--yes"], cwd=wt, capture_output=True, text=True, timeout=900)
                if r.returncode == 0:
                    log(f"[deploy] deploy prod OK ({head[:8]}) al tentativo {attempt}")
                    return True
                log(f"!! [deploy] tentativo {attempt}/3 fallito (exit {r.returncode})")
                if attempt < 3:
                    time.sleep(20)
            out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()[-1800:] if r else "(nessun output)"
            log(f"!! [deploy] DEPLOY FALLITO dopo 3 tentativi ({head[:8]}). Commit su Codeberg "
                f"ma NON in produzione. Output vercel:\n{out}")
            return False
        finally:
            subprocess.run([GIT, "-C", REPO, "worktree", "remove", "--force", wt])
    except Exception as e:
        log(f"!! auto-deploy fallito: {e}")
        return False


def main():
    log(("=== giro C3M (dry-run) ===" if DRY else "=== giro C3M ==="))
    errori = 0
    modules = {}
    data_date = None
    def rileva_variazioni():
        """Registro variazioni paniere (gen_c3m_changes): il RILEVAMENTO gira ogni
        giorno così gli eventi si accumulano anche prima della pubblicazione; il
        modulo nel repo si riscrive solo quando c'è un evento nuovo."""
        import subprocess
        r = subprocess.run([sys.executable, os.path.join(ARCHIVE, "_scripts", "gen_c3m_changes.py")],
                           capture_output=True, text=True, timeout=120)
        if r.returncode != 0:
            raise RuntimeError((r.stdout + r.stderr).strip()[-200:])
        log("   " + (r.stdout.strip().splitlines()[-1] if r.stdout.strip() else "variazioni ok"))

    for nome, step in (("snapshot", archive_snapshot), ("series", archive_series),
                       ("spread", archive_spread), ("docs", archive_docs),
                       ("variazioni", rileva_variazioni)):
        try:
            ris = step()
            modules[nome] = True
            if nome == "snapshot":
                data_date = ris
        except Exception as e:
            errori += 1
            modules[nome] = False
            log(f"!! {nome}: {e}")
    # regen moduli del sito + autodeploy (solo se i dati sono cambiati)
    for g in GENERATORI:
        chiave = g.replace("gen_", "").replace(".py", "").replace("_", "-")
        modules[chiave] = regen(g)
        if not modules[chiave]:
            errori += 1
    modules["deploy"] = autodeploy()
    if not modules["deploy"]:
        errori += 1
    send_heartbeat(errori, modules, data_date)
    log(f"fatto ({errori} errori)" if errori else "fatto, tutto OK")


if __name__ == "__main__":
    main()
