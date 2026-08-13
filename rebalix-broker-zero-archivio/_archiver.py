#!/usr/bin/env python3
"""Archiviatore mensile dell'Osservatorio «PAC gratuito ed ETF senza commissioni».

Scarica le liste UFFICIALI a zero commissioni dei 5 broker che le pubblicano
per-ISIN (Fineco, Moneyfarm, BG Saxo, Directa, XTB), le archivia con data,
rigenera l'indice del cerca-ETF e i conteggi della tabella comparativa, e se
qualcosa è cambiato committa + deploya (worktree pulito, come l'archiviatore
LifeStrategy). La PROSA delle schede resta editoriale: questo script tocca SOLO
lib/blog/broker-zero-isin-index.json e lib/blog/broker-zero-counts.json.

Fail-soft per fonte: se una fonte non risponde o il conteggio è anomalo
(<60% del mese prima o sotto il minimo assoluto) si TIENE il dato precedente di
quel broker e si segnala l'errore nel battito del guardiano — mai pubblicare un
crollo che in realtà è un cambio di formato della fonte.

Uso: python3 _archiver.py [--dry-run] [--force] [--no-deploy]
Cadenza: launchd il 1° del mese (RunAtLoad recupera i mesi col Mac spento:
lo stato in _state.json evita i doppi giri nello stesso mese).
"""
import os, re, sys, json, time, shutil, tempfile, datetime, subprocess, urllib.request, html as htmllib

os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")

ARCHIVE = os.path.expanduser("~/backups/rebalix-broker-zero-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
INDEX_REL = "lib/blog/broker-zero-isin-index.json"
COUNTS_REL = "lib/blog/broker-zero-counts.json"
GIT = shutil.which("git") or "/usr/bin/git"
VERCEL = shutil.which("vercel") or "/usr/local/bin/vercel"
PDFTOTEXT = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"

DRY = "--dry-run" in sys.argv
FORCE = "--force" in sys.argv
NO_DEPLOY = "--no-deploy" in sys.argv
TODAY = datetime.date.today()
YM = f"{TODAY:%Y-%m}"
SNAPDIR = os.path.join(ARCHIVE, "snapshots", YM)

ISIN_RE = re.compile(r"\b([A-Z]{2}[A-Z0-9]{9}[0-9])\b")
UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15"}

# soglie di sanità: sotto il minimo assoluto (o <60% del giro prima) la fonte è "sospetta"
MIN_COUNTS = {"fineco": 100, "moneyfarm": 200, "bgsaxo": 100, "directa": 400, "xtb": 500}

def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M}  {msg}"
    print(line)
    if not DRY:
        with open(os.path.join(ARCHIVE, "_archiver.log"), "a") as f:
            f.write(line + "\n")

def fetch(url, dest=None, min_size=500, timeout=120):
    # NB: scarica e salva ANCHE in dry-run (i parser devono poter leggere i file);
    # il dry riguarda solo scritture nel repo, stato, deploy e battito.
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if len(data) < min_size:
        raise RuntimeError(f"risposta sospetta ({len(data)}B) da {url}")
    if dest:
        with open(dest, "wb") as f:
            f.write(data)
    return data

def pdf_text(pdf_path):
    out = subprocess.run([PDFTOTEXT, "-layout", pdf_path, "-"], capture_output=True, timeout=300)
    if out.returncode != 0:
        raise RuntimeError(f"pdftotext fallito su {pdf_path}")
    return out.stdout.decode("utf-8", errors="ignore")

MESI = {"gennaio": 1, "febbraio": 2, "marzo": 3, "aprile": 4, "maggio": 5, "giugno": 6,
        "luglio": 7, "agosto": 8, "settembre": 9, "ottobre": 10, "novembre": 11, "dicembre": 12}

def parse_data_it(s):
    m = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d\d)", s)
    if not m or m.group(2).lower() not in MESI:
        return None
    return datetime.date(int(m.group(3)), MESI[m.group(2).lower()], int(m.group(1)))

# ── Parser per fonte: ognuno ritorna (entries_broker, names) ──────────────────
# entries_broker: {isin: [[canale, soglia, scadenza], ...]} — il broker id lo aggiunge il chiamante.

def src_fineco(snap):
    pdf = os.path.join(snap, "fineco-promo.pdf")
    fetch("https://images.fineco.it/cms/mail/immagini/docs/2022_Promo_ETF/PromoETFZeroCommissioni_Lista.pdf",
          pdf, min_size=50_000)
    txt = pdf_text(pdf)
    entries, names = {}, {}
    for line in txt.splitlines():
        m = ISIN_RE.search(line)
        if not m or not line.strip().startswith(m.group(1)):
            continue
        isin = m.group(1)
        entries.setdefault(isin, [["both", 0, "M"]])
        parts = re.split(r"\s{2,}", line.strip())
        if len(parts) >= 2 and len(parts[1]) > 12:
            names.setdefault(isin, parts[1][:80])
    return entries, names

def src_moneyfarm(snap):
    page = fetch("https://www.moneyfarm.com/it/pac-diy/", timeout=90).decode("utf-8", errors="ignore")
    m = re.search(r'href="(https://[^"]*T_and_Cs[^"]*\.pdf)"', page)
    if not m:
        raise RuntimeError("link T&C promo non trovato nella pagina PAC")
    pdf = os.path.join(snap, "moneyfarm-tc.pdf")
    fetch(m.group(1), pdf, min_size=100_000)
    txt = pdf_text(pdf)
    parts = re.split(r"REGOLAMENTO DELL.INIZIATIVA", txt)[1:]
    entries, names = {}, {}
    for part in parts:
        v = re.search(r"valida dal\s+(.{4,30}?)\s+(?:fino\s+)?al\s+(.{4,30}?)\s*\(", part)
        fine = parse_data_it(v.group(2)) if v else None
        if not fine or fine < TODAY:
            continue  # promo scaduta o data illeggibile: fuori (come da T&C)
        fine_iso = fine.isoformat()
        l2 = part.find("LISTA 2")
        lista1, lista2 = part[: l2 if l2 > 0 else len(part)], part[l2:] if l2 > 0 else ""
        for mm in ISIN_RE.finditer(lista1):
            entries.setdefault(mm.group(1), []).append(["spot", 1000, fine_iso])
        for mm in ISIN_RE.finditer(lista2):
            entries.setdefault(mm.group(1), []).append(["pac", 0, fine_iso])
        for line in part.splitlines():
            mm = ISIN_RE.search(line)
            if mm and line.strip().startswith(mm.group(1)):
                cols = re.split(r"\s{2,}", line.strip())
                if len(cols) >= 3:
                    names.setdefault(mm.group(1), " ".join(cols[2:])[:80])
    return entries, names

def src_bgsaxo(snap):
    dest = os.path.join(snap, "bgsaxo-list.html")
    data = fetch("https://www.bgsaxo.it/rates-and-conditions/autoinvest-etf-list", dest,
                 min_size=20_000, timeout=300).decode("utf-8", errors="ignore")
    entries, names = {}, {}
    for m in re.finditer(r"<td>([^<]{8,90})</td><td>([A-Z]{2}[A-Z0-9]{9}[0-9])</td>", data):
        isin = m.group(2)
        entries.setdefault(isin, [["pac", 0, ""]])
        names.setdefault(isin, htmllib.unescape(m.group(1))[:80])
    return entries, names

DIRECTA_SPOT_SKIP = ("VONTOBEL", "BNP PARIBAS")  # accordi-certificati: fuori perimetro ETF

def src_directa(snap):
    entries, names = {}, {}
    emits = json.loads(fetch("https://www.directa.it/api/v1/tabelle/pac", timeout=60))
    if not DRY:
        json.dump(emits, open(os.path.join(snap, "directa-pac-emittenti.json"), "w"))
    pac_isins = set()
    for e in emits:
        rows = json.loads(fetch(f"https://www.directa.it/api/v1/tabelle/pac?EMIT={e['EMIT']}", timeout=60))
        if not DRY:
            json.dump(rows, open(os.path.join(snap, f"directa-pac-{e['EMIT']}.json"), "w"))
        for row in rows:
            isin = row.get("Isin", "")
            if ISIN_RE.fullmatch(isin or ""):
                pac_isins.add(isin)
                entries.setdefault(isin, []).append(["pac", 0, ""])
                if row.get("Descrizione"):
                    names.setdefault(isin, row["Descrizione"][:80])
    idx = fetch("https://www1.directatrading.com/trading/cwzerc?USER=I",
                os.path.join(snap, "directa-spot-index.html"), min_size=3_000, timeout=90
                ).decode("utf-8", errors="ignore")
    rows = re.findall(r'<A href="(/trading/detcwc\?USER=I&EMIT=[^"]+)"[^>]*>\s*<i>([^<]+)</i>'
                      r'.*?<td align="center"[^>]*>\s*([\d/]+)\s*</td>\s*<td align="right"[^>]*>\s*([\d\.]+)\s*</td>',
                      idx, re.S)
    if len(rows) < 10:
        raise RuntimeError(f"indice spot Directa: solo {len(rows)} accordi (formato cambiato?)")
    seen = set()
    for href, nome, scad, soglia in rows:
        if any(nome.strip().upper().startswith(s) for s in DIRECTA_SPOT_SKIP):
            continue
        url = "https://www1.directatrading.com" + htmllib.unescape(href)
        if url in seen:
            continue
        seen.add(url)
        d, mth, y = scad.split("/")
        fine = f"{y}-{mth}-{d}"
        t_eur = int(soglia.replace(".", ""))
        sub = fetch(url, os.path.join(snap, f"directa-spot-{re.sub('[^A-Za-z0-9]', '_', nome.strip())[:30]}.html"),
                    min_size=800, timeout=60).decode("utf-8", errors="ignore")
        for isin in set(ISIN_RE.findall(sub)):
            prev = [x for x in entries.get(isin, []) if x[0] == "spot"]
            if prev:
                if t_eur < prev[0][1]:
                    prev[0][1], prev[0][2] = t_eur, fine
            else:
                entries.setdefault(isin, []).append(["spot", t_eur, fine])
        time.sleep(1)  # gentilezza verso il server
    return entries, names, len(pac_isins)

def src_xtb(snap):
    docs = fetch("https://www.xtb.com/it/specifiche-dello-strumento/documenti", timeout=90
                 ).decode("utf-8", errors="ignore")
    m = re.search(r'href="([^"]*Tabella_Strumenti_OMI[^"]*\.pdf)"', docs)
    if not m:
        raise RuntimeError("PDF Tabella OMI non trovato nella pagina documenti XTB")
    url = m.group(1)
    if url.startswith("/"):
        url = "https://www.xtb.com" + url
    pdf = os.path.join(snap, "xtb-omi.pdf")
    fetch(url, pdf, min_size=200_000, timeout=300)
    txt = pdf_text(pdf)
    hdrs = list(re.finditer(r"\n\s*Diritti Frazionari relativi a ETF, ETN, ETC\s*\n", txt))
    if not hdrs:
        raise RuntimeError("sezione Diritti Frazionari ETF non trovata nel PDF XTB")
    sec = txt[hdrs[-1].end():]
    entries, names = {}, {}
    for line in sec.splitlines():
        mm = ISIN_RE.search(line)
        if not mm:
            continue
        isin = mm.group(1)
        entries.setdefault(isin, [["both", 0, ""]])
        parts = re.split(r"\s{2,}", line.strip())
        try:
            i = next(k for k, p in enumerate(parts) if ISIN_RE.fullmatch(p))
            if i >= 2 and len(parts[i - 1]) > 8:
                names.setdefault(isin, parts[i - 1][:80])
        except StopIteration:
            pass
    return entries, names

# ── Guardiano ─────────────────────────────────────────────────────────────────

def send_heartbeat(errori, modules, data_date):
    if DRY:
        log(f"[heartbeat] (dry) errori={errori} moduli_ok={sum(1 for v in modules.values() if v)}/{len(modules)}")
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
        payload = json.dumps({"name": "broker-zero", "ok": errori == 0, "errors_count": errori,
                              "metrics": {"modules": modules, "data_date": data_date}}).encode()
        req = urllib.request.Request("https://rebalix.com/api/heartbeat", data=payload, method="POST",
                                     headers={"Authorization": f"Bearer {secret}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            log(f"[heartbeat] inviato ({r.status})")
    except Exception as e:
        log(f"!! [heartbeat] invio fallito (non blocca): {e}")

def autodeploy(files):
    """Commit dei SOLI file generati + push + deploy da worktree pulito (pattern LS)."""
    if DRY or NO_DEPLOY:
        log("[deploy] saltato (dry/no-deploy)")
        return True
    branch = subprocess.run([GIT, "-C", REPO, "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    if branch != "main":
        log(f"[deploy] branch {branch} ≠ main — salto per sicurezza")
        return True
    try:
        subprocess.run([GIT, "-C", REPO, "add", "--"] + files, check=True)
        if subprocess.run([GIT, "-C", REPO, "diff", "--cached", "--quiet", "--"] + files).returncode == 0:
            log("[deploy] file invariati — nessun deploy")
            return True
        msg = ("data(blog-broker-zero): refresh automatico liste a zero commissioni\n\n"
               "Rigenerati dall'archiviatore mensile dell'osservatorio broker.\n\n"
               "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
        subprocess.run([GIT, "-C", REPO, "commit", "-m", msg, "--"] + files, check=True)
        log("[deploy] commit dei dati rigenerati")
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
                    log(f"[deploy] deploy prod OK ({head[:8]}) al tentativo {attempt}")
                    return True
                log(f"!! [deploy] tentativo {attempt}/3 fallito (exit {r.returncode})")
                if attempt < 3:
                    time.sleep(20)
            out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()[-1500:] if r else "(nessun output)"
            log(f"!! [deploy] FALLITO dopo 3 tentativi. Output vercel:\n{out}")
            return False
        finally:
            subprocess.run([GIT, "-C", REPO, "worktree", "remove", "--force", wt])
    except Exception as e:
        log(f"!! auto-deploy fallito: {e}")
        return False

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    state_path = os.path.join(ARCHIVE, "_state.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    if not FORCE and state.get("last_ok", "")[:7] == YM:
        log(f"giro di {YM} già completato ({state['last_ok']}) — niente da fare (usa --force per rifare)")
        return
    os.makedirs(SNAPDIR, exist_ok=True)
    log(f"=== giro {YM} avviato (dry={DRY}) ===")

    old = json.load(open(os.path.join(REPO, INDEX_REL)))
    old_by_broker = {}
    for isin, rows in old["entries"].items():
        for b, c, t, e in rows:
            old_by_broker.setdefault(b, {}).setdefault(isin, []).append([c, t, e])

    modules, errori = {}, 0
    fresh = {}
    directa_pac_count = None

    for broker, fn in [("fineco", src_fineco), ("moneyfarm", src_moneyfarm),
                       ("bgsaxo", src_bgsaxo), ("directa", src_directa), ("xtb", src_xtb)]:
        try:
            out = fn(SNAPDIR)
            if broker == "directa":
                entries, names, directa_pac_count = out
            else:
                entries, names = out
            prev_n = len(old_by_broker.get(broker, {}))
            if len(entries) < MIN_COUNTS[broker] or (prev_n and len(entries) < 0.6 * prev_n):
                raise RuntimeError(f"conteggio anomalo: {len(entries)} (prima {prev_n}) — formato cambiato?")
            fresh[broker] = (entries, names)
            modules[broker] = True
            log(f"[{broker}] ok: {len(entries)} ISIN")
        except Exception as e:
            log(f"!! [{broker}] {e} — TENGO il dato del giro precedente")
            modules[broker] = False
            errori += 1
            fresh[broker] = (old_by_broker.get(broker, {}), {})
            if broker == "directa":
                directa_pac_count = None

    # ricompone indice: entries {isin: [[b,c,t,e],...]} + nomi (precedenza: directa, bgsaxo, moneyfarm, fineco, xtb)
    entries, names = {}, {}
    for broker in ["fineco", "moneyfarm", "bgsaxo", "directa", "xtb"]:
        for isin, rows in fresh[broker][0].items():
            for c, t, e in rows:
                entries.setdefault(isin, []).append([broker, c, t, e])
    for broker in ["directa", "bgsaxo", "moneyfarm", "fineco", "xtb"]:
        for isin, nm in fresh[broker][1].items():
            if isin in entries:
                names.setdefault(isin, nm)
    for isin, nm in old.get("names", {}).items():  # non perdere nomi già noti
        if isin in entries:
            names.setdefault(isin, nm)

    # diff per broker (entrati/usciti) — per il log e per counts.json
    diff = {}
    for broker in ["fineco", "moneyfarm", "bgsaxo", "directa", "xtb"]:
        old_set = set(old_by_broker.get(broker, {}))
        new_set = set(fresh[broker][0])
        added, removed = len(new_set - old_set), len(old_set - new_set)
        if added or removed:
            diff[broker] = {"in": added, "out": removed}
            log(f"[diff] {broker}: +{added} −{removed}")

    changed = dict(sorted(entries.items())) != dict(sorted(old["entries"].items()))
    if not changed:
        log("liste invariate rispetto al giro precedente — indice fermo, nessun deploy")
        if not DRY:
            state["last_ok"] = TODAY.isoformat()
            json.dump(state, open(state_path, "w"))
        send_heartbeat(errori, {**modules, "deploy": True}, old["updated"])
        log("=== giro completato (invariato) ===")
        return

    counts = {
        "updated": TODAY.isoformat(),
        "counts": {
            "fineco": len(fresh["fineco"][0]),
            "directa": directa_pac_count if directa_pac_count is not None
                       else json.load(open(os.path.join(REPO, COUNTS_REL)))["counts"]["directa"],
            "bgsaxo": len(fresh["bgsaxo"][0]),
            "moneyfarm": len(fresh["moneyfarm"][0]),
        },
        "diff": diff,
    }
    new_index = {"updated": TODAY.isoformat(), "entries": dict(sorted(entries.items())), "names": names}
    if DRY:
        log(f"[dry] scriverei indice ({len(entries)} ISIN) e counts {counts['counts']}")
    else:
        json.dump(new_index, open(os.path.join(REPO, INDEX_REL), "w"), separators=(",", ":"), ensure_ascii=False)
        json.dump(counts, open(os.path.join(REPO, COUNTS_REL), "w"), indent=2, ensure_ascii=False)
        log(f"indice rigenerato: {len(entries)} ISIN, {len(names)} nomi; counts {counts['counts']}")

    deploy_ok = autodeploy([INDEX_REL, COUNTS_REL])
    if not deploy_ok:
        errori += 1
    if not DRY and (errori == 0 or deploy_ok):
        state["last_ok"] = TODAY.isoformat()
        json.dump(state, open(state_path, "w"))
    send_heartbeat(errori, {**modules, "deploy": deploy_ok}, TODAY.isoformat())
    log(f"=== giro completato ({errori} errori) ===")

if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"!!! ERRORE FATALE: {e}")
        send_heartbeat(99, {"fatal": False}, None)
        raise
