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
import os, re, sys, json, shutil, datetime, subprocess, urllib.request, urllib.error, hashlib, time, signal, tempfile, uuid

os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")

ARCHIVE = os.path.expanduser("~/backups/rebalix-etf-registry-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
# (16 set 2026, Linus «conserviamo tutto») ARCHIVIO RAW delle risposte delle fonti di composizione: i lettori che
# accettano --raw-dir salvano la risposta com'è (gz + indice) prima del parsing; i lettori senza il flag lo ignorano.
RAW_DIR = os.path.expanduser("~/backups/rebalix-raw-archivio")
os.makedirs(RAW_DIR, exist_ok=True)
NODE = shutil.which("node") or "/usr/local/bin/node"
STATE = os.path.join(ARCHIVE, "_state.json")

DRY = "--dry-run" in sys.argv
FORCE = "--force" in sys.argv
TODAY = datetime.date.today()
YM = f"{TODAY:%Y-%m}"
# provenienza del CODICE DI ACQUISIZIONE (18 set 2026): chi ha prodotto la «dopo» dell'edizione, oltre al commit del repo
GIRO_AVVIATO_IL = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
ARCHIVIATORE_MD5 = __import__("hashlib").md5(open(os.path.abspath(__file__), "rb").read()).hexdigest()


def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M}  {msg}"
    print(line)
    if not DRY:
        with open(os.path.join(ARCHIVE, "_archiver.log"), "a") as f:
            f.write(line + "\n")


DELISTED = []  # riempito dal main col riepilogo dei delisting del giro
HOST_VPS = "rebalix-vps"  # dove esistono baseline, semaforo e l'edizione: lì l'edizione è OBBLIGATORIA


def gate_acquisizione(nome, returncode, esiti_path):
    """GATE DI ACQUISIZIONE (Linus, 18 set 2026): un writer previsto dall'edizione deve aver TERMINATO e DICHIARATO il proprio
    esito. Una dichiarazione negativa prodotta correttamente (DATA_NON_DISPONIBILE, FONDO_DI_FONDI) è accettabile; l'assenza
    della dichiarazione perché il lettore è morto non lo è. Torna (ok, motivo)."""
    if returncode != 0:
        return False, f"{nome}: exit {returncode}"
    try:
        d = json.load(open(esiti_path))
    except Exception as e:
        return False, f"{nome}: --out mancante o illeggibile ({esiti_path}: {str(e)[:60]})"
    c, per = d.get("conteggi") or {}, (d.get("perimetro") or {}).get("n")
    chiavi = ("fotografabili", "fondi_di_fondi", "senza_data", "falliti")
    if per is None or any(k not in c for k in chiavi):
        return False, f"{nome}: --out senza perimetro o conteggi completi"
    somma = sum(c[k] for k in chiavi)
    if somma != per:
        return False, f"{nome}: universo non contabilizzato: perimetro {per} ≠ {' + '.join(str(c[k]) for k in chiavi)} = {somma}"
    esiti = d.get("esiti") or []
    if len(esiti) != per - c["falliti"]:
        return False, f"{nome}: {len(esiti)} esiti per {per - c['falliti']} fondi attesi (perimetro − falliti)"
    dich = d.get("dichiarazioni") or {}
    if len(dich.get("FONDO_DI_FONDI", [])) != c["fondi_di_fondi"] or len(dich.get("DATA_NON_DISPONIBILE", [])) != c["senza_data"]:
        return False, f"{nome}: dichiarazioni non coerenti coi conteggi"
    return True, f"{nome}: exit 0 · perimetro {per} = {' + '.join(f'{c[k]} {k}' for k in chiavi)}"


def edizione_mensile(ym, acquisizioni, esegui, leggi_stato, ed_dir, f_dopo, f_acq, node, log):
    """L'EDIZIONE del mese, con i comandi INIETTATI (testabile senza VPS). `acquisizioni` = {nome: (returncode, esiti_path)} dei
    writer previsti; se uno non passa il gate, NESSUN passo parte (né apri, né esporta, né congela-dopo). Torna (stato, errore)."""
    dich = []
    for nome, (rc, esiti_path) in acquisizioni.items():
        ok, motivo = gate_acquisizione(nome, rc, esiti_path)
        log(f"  |edizione:gate| {'✓' if ok else '✗'} {motivo}")
        if not ok:
            return None, f"gate di acquisizione: {motivo} — l'edizione non si congela su una fotografia stantia"
        dich += ["--dichiarazioni", esiti_path]
    try:
        esegui("apri", [node, "scripts/edizione.mjs", "apri", "--mese", ym])
        stato = leggi_stato()
        if stato and stato.get("dopo"):
            log(f"  |edizione:esporta| la «dopo» è già congelata ({stato['dopo']['sha256'][:12]}…): non si riesporta")
        else:
            esegui("esporta", [node, "scripts/esporta-foto-completa.mjs", "--out", f_dopo, "--acquisizione", f_acq] + dich)
            esegui("congela-dopo", [node, "scripts/edizione.mjs", "congela-dopo", "--mese", ym, "--file", f_dopo, "--acquisizione", f_acq])
        esegui("confronta", [node, "scripts/edizione.mjs", "confronta", "--mese", ym, "--commit"])
        esegui("completa", [node, "scripts/edizione.mjs", "completa", "--mese", ym, "--commit"])   # COMPARED → COMPLETE nel DB (secondo testimone)
        st = leggi_stato()
        return (st or {}).get("stato"), None
    except Exception as e:
        st = leggi_stato()
        return (st or {}).get("stato"), str(e)


def marcatore_fine_giro(state, ym, modules, edizione_richiesta, edizione_stato, errore, adesso, archiviatore_md5, avviato_il):
    """Che cosa scrivere in _state.json in fondo al giro (contratto dell'edizione, Linus 18 set 2026).

    `last_ym = ym` SOLO se il giro è davvero concluso: se l'edizione era richiesta (VPS), deve essere arrivata a COMPLETE.
    Altrimenti il mese resta RECUPERABILE alla sveglia successiva: si conservano `in_corso_ym`, i moduli già eseguiti e
    l'errore, ma il mese NON si dichiara concluso (il `last_ym` precedente resta quello che era).
    """
    concluso = (not edizione_richiesta) or edizione_stato == "COMPLETE"
    base = {k: v for k, v in state.items() if k not in ("in_corso_ym", "iniziato_il", "moduli", "errore", "edizione")}
    if concluso:
        return {**base, "last_ym": ym, "at": adesso, "iniziato_il": avviato_il, "archiviatore_md5": archiviatore_md5,
                "moduli": modules, "limitazioni": EXTRA_METRICS.get("limitazioni", {}), "preflight": EXTRA_METRICS.get("preflight", PREFLIGHT), "documenti": EXTRA_METRICS.get("documenti", {}), "edizione": edizione_stato}
    return {**base, "in_corso_ym": ym, "iniziato_il": avviato_il, "archiviatore_md5": archiviatore_md5, "moduli": modules, "limitazioni": EXTRA_METRICS.get("limitazioni", {}), "preflight": EXTRA_METRICS.get("preflight", PREFLIGHT), "documenti": EXTRA_METRICS.get("documenti", {}),
            "edizione": edizione_stato, "errore": errore or "edizione non arrivata a COMPLETE"}


# ---------------------------------------------------------------------------
# (ETF-20 passo 5, 27 ott 2026 — rev. 2 dopo il riesame dell'auditor) RIFIUTI VISIBILI e BATTITO DEI PANIERI
# - GIRO = identificativo di QUESTA esecuzione: va ai lettori con la guardia (--giro) e al compositore del battito; rapporti e righe
#   dei rifiuti valgono solo se lo portano (un rapporto del mese prima non prova il giro corrente);
# - EXTRA_METRICS = metriche allegate al battito (blocco «panieri» composto da scripts/panieri-battito.mjs);
# - le due funzioni sotto sono ESEGUIBILI fuori dal giro (prova con comandi finti: prova-runner-passo5.py).
EXTRA_METRICS = {}

# ── LIMITAZIONI DICHIARATE del giro (27 ott 2026, condizioni del 2/11/2026; parere auditor 27/10, una voce per modulo con GO di Linus) ──
# File ARCHIVE/LIMITAZIONI-GIRO.json: {"giro": "YYYY-MM", "salta": ["documents", "doc-archive", "doc-langs"], "motivo": "…", "go": "…"}.
# Effetti distinti per modulo: documents = aggiornamento dei COLLEGAMENTI ai documenti (URL nel registro); doc-archive = ARCHIVIAZIONE
# dei PDF (archiviatore storico senza indice/versioni); doc-langs = QUALIFICAZIONE DELLE LINGUE senza provenienza.
# Regole: senza file → nessuna limitazione. File presente ma illeggibile, senza "giro", di un ALTRO mese, con moduli non ammessi o senza
# motivo/GO → il giro NON PARTE (uscita 3): una limitazione vecchia non si applica né si ignora in silenzio. I moduli saltati NON entrano
# in `modules` (né verdi né rossi): stanno nel battito (metrics.limitazioni) e nel marcatore di fine giro (limitazioni), con motivo e GO.
LIMITAZIONI_FILE = os.path.join(ARCHIVE, "LIMITAZIONI-GIRO.json")
MODULI_LIMITABILI = ("documents", "doc-archive", "doc-langs")
LIMITAZIONI = {"attive": False, "salta": (), "giro": None, "motivo": None, "go": None}

# ── MODULI DOCUMENTALI CORRETTI (rev. 4, 28 ott 2026; auditor: «correzioni dei moduli documentali per il 2/11»; criterio del piano
# straordinaria rev. 3 §1 del 25/10: «la fase 2 non usa più l'archiviatore… usa la macchina dei lotti») ──
# |documents| scrive i collegamenti come prima MA con fotografia prima/dopo delle 6 colonne URL (righe vive), elenco delle scritture,
#   COLLAUDO dei documenti ricevuti (collaudo-documenti-ricevuti.mjs --come utente) sulle sole classi toccate e revalidazione delle loro
#   schede con corpo validato: senza fotografia «prima» il modulo NON parte (nessuna scrittura non collaudabile).
# |doc-archive| NON scrive più nell'archivio canonico: PROVA con conservazione (archive-etf-documents.mjs --conserva-in <FASC_DOCUMENTI>/<YM>/
#   prova-archivio): indice-prova.jsonl + PDF conservati + confronto testo/immagini; archiviazione canonica, lingua (R1/R2/R2-bis) e
#   controllo per riga avvengono poi con la macchina dei LOTTI (indice → lotti → COMMIT da sorgenti conservate, anteprima approvata, GO).
# |doc-langs| RIMOSSO: la lingua si decide nei lotti con provenienza; enrich-doc-langs sovrascriverebbe le colonne con provenienza.
# (rev. 5) dopo una prova VALIDA: lotti per regole scritte → prova offline → verifica → COMMIT autorizzato dal file di GO (lotti_automatici).
# Tutto finisce in EXTRA_METRICS["documenti"] (battito) e nel marcatore di fine giro. Funzioni eseguibili fuori dal giro (prova-documenti-rev4.py).
FASC_DOCUMENTI = os.path.expanduser("~/fascicoli/giro-documenti")
DB_ENV_FILE = os.path.expanduser("~/backups/rebalix-db/.env")
PSQL = shutil.which("psql") or "psql"
SITO = "https://rebalix.com"
COLONNE_URL = ("kid_url", "kid_url_en", "prospectus_url", "prospectus_url_en", "factsheet_url", "factsheet_url_en")


def _env_db():
    """Ambiente con le variabili PG* del file ~/backups/rebalix-db/.env (psql le usa senza URL)."""
    env = dict(os.environ)
    try:
        with open(DB_ENV_FILE) as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip('"').strip("'")
    except Exception as e:
        log(f"!! ambiente del DB non leggibile ({e})")
    return env


def cron_secret():
    try:
        with open(os.path.join(REPO, ".env.local")) as f:
            for line in f:
                if line.startswith("CRON_SECRET="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
    except Exception:
        pass
    return None


ISIN_RE = re.compile(r"^[A-Z]{2}[A-Z0-9]{10}$")
TIPO_DI_COLONNA = {"kid_url": "kid_it", "kid_url_en": "kid_en", "prospectus_url": "prospetto_it", "prospectus_url_en": "prospetto_en", "factsheet_url": "factsheet_it", "factsheet_url_en": "factsheet_en"}


def interpreta_foto(testo):
    """(rev. 4b) Valida l'uscita di psql: prima riga = conteggio delle righe vive, poi una riga TSV per classe con 7 campi, ISIN valido e
    univoco, numero di righe = conteggio. Ritorna ({isin: (url…)}, None) oppure (None, motivo): fotografia non interpretabile = niente avvio."""
    righe = [r for r in (testo or "").split("\n") if r != ""]
    if not righe:
        return None, "uscita di psql vuota"
    try:
        attese = int(righe[0].strip())
    except ValueError:
        return None, f"prima riga non è il conteggio delle righe vive: {righe[0][:40]!r}"
    foto = {}
    for i, riga in enumerate(righe[1:], start=2):
        campi = riga.split("\t")
        if len(campi) != 1 + len(COLONNE_URL):
            return None, f"riga {i}: {len(campi)} campi invece di {1 + len(COLONNE_URL)} ({riga[:40]!r})"
        if not ISIN_RE.match(campi[0]):
            return None, f"riga {i}: ISIN non valido {campi[0]!r}"
        if campi[0] in foto:
            return None, f"riga {i}: ISIN duplicato {campi[0]}"
        foto[campi[0]] = tuple(campi[1:])
    if len(foto) != attese:
        return None, f"perimetro non riconciliato: {len(foto)} righe lette, {attese} righe vive dichiarate dal conteggio"
    if not foto:
        return None, "nessuna riga viva"
    return foto, None


def foto_colonne_documenti(percorso):
    """Fotografia delle 6 colonne URL dei documenti (etf_registry, righe vive) in un TSV validato; {isin: (url…)} oppure None se fallisce."""
    sql_conteggio = "select count(*) from etf_registry where delisted_at is null"
    sql_righe = ("select isin||E'\\t'||" + "||E'\\t'||".join(f"coalesce({c},'')" for c in COLONNE_URL)
                 + " from etf_registry where delisted_at is null order by isin")
    try:
        r = subprocess.run([PSQL, "-At", "-c", sql_conteggio, "-c", sql_righe], capture_output=True, text=True, timeout=300, env=_env_db())
    except Exception as e:
        log(f"!! fotografia colonne documenti fallita ({e})")
        return None
    if r.returncode != 0:
        log(f"!! fotografia colonne documenti: psql exit {r.returncode} {(r.stderr or '').strip()[:120]}")
        return None
    foto, motivo = interpreta_foto(r.stdout)
    if foto is None:
        log(f"!! fotografia colonne documenti NON interpretabile: {motivo}")
        return None
    with open(percorso, "w") as f:
        f.write(r.stdout)
    return foto


def differenze_documenti(prima, dopo):
    """[(isin, colonna, prima, dopo)] per ogni cella cambiata fra le due fotografie (stesso perimetro: lo verifica il chiamante)."""
    out = []
    for isin in sorted(set(prima) & set(dopo)):
        p, d = prima[isin], dopo[isin]
        for i, c in enumerate(COLONNE_URL):
            if p[i] != d[i]:
                out.append((isin, c, p[i], d[i]))
    return out


def revalidate_schede(isins, fasc):
    """POST /api/revalidate?scope=schede per lotti di 200 con il CONTRATTO approvato: ok true, scartati = [] (array presente e vuoto),
    troppi false, isin = ISIN del lotto, schede_letterali = 6 × ISIN."""
    secret = cron_secret()
    if not secret:
        log("!! documents-revalidate: CRON_SECRET non trovato — salto")
        return False, []
    esiti = []
    for i in range(0, len(isins), 200):
        lotto = isins[i:i + 200]
        n = i // 200 + 1
        req = urllib.request.Request(f"{SITO}/api/revalidate?scope=schede&isins={','.join(lotto)}", data=b"", method="POST",
                                     headers={"Authorization": f"Bearer {secret}"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                corpo, stato = r.read().decode("utf-8", "replace"), r.status
        except urllib.error.HTTPError as e:
            corpo, stato = (e.read().decode("utf-8", "replace") if hasattr(e, "read") else ""), e.code
        except Exception as e:
            corpo, stato = str(e), 0
        with open(os.path.join(fasc, f"revalidate-{n}.json"), "w") as f:
            f.write(corpo)
        try:
            j = json.loads(corpo)
        except Exception:
            j = {}
        if not isinstance(j, dict):
            j = {}
        ok = (stato == 200 and j.get("ok") is True and isinstance(j.get("scartati"), list) and len(j["scartati"]) == 0
              and j.get("troppi") is False and j.get("isin") == len(lotto) and j.get("schede_letterali") == 6 * len(lotto))
        esiti.append({"lotto": n, "n": len(lotto), "http": stato, "ok": ok, "isin": j.get("isin"), "schede_letterali": j.get("schede_letterali"), "scartati": j.get("scartati") if isinstance(j.get("scartati"), list) else "assente"})
        log(f"  |documents-revalidate| lotto {n}: HTTP {stato} · {len(lotto)} ISIN · {'corpo conforme' if ok else 'NON conforme'} (isin {j.get('isin')}, schede_letterali {j.get('schede_letterali')}/{6 * len(lotto)}, scartati {'[]' if isinstance(j.get('scartati'), list) and not j['scartati'] else j.get('scartati', 'assente')})")
    return all(e["ok"] for e in esiti), esiti


def riconcilia_collaudo(attesi, percorso_jsonl):
    """(rev. 4b) Ogni documento MODIFICATO (isin, tipo, url nuovo) deve avere nel JSONL del collaudo una riga con stesso isin, tipo e url
    e verdetto «ricevuto e verificato». Ritorna (ok, {verificati, mancanti, non_conformi, url_diversi})."""
    esiti = []
    try:
        with open(percorso_jsonl) as f:
            for l in f:
                if l.strip():
                    esiti.append(json.loads(l))
    except Exception as e:
        return False, {"errore": f"esiti del collaudo non leggibili: {str(e)[:80]}", "verificati": 0, "mancanti": [f"{a[0]}/{a[1]}" for a in attesi]}
    per_doc = {(e.get("isin"), e.get("tipo")): e for e in esiti}
    verificati, mancanti, non_conformi, url_diversi = 0, [], [], []
    for isin, tipo, url in attesi:
        e = per_doc.get((isin, tipo))
        if e is None:
            mancanti.append(f"{isin}/{tipo}")
        elif e.get("url") != url:
            url_diversi.append(f"{isin}/{tipo}: collaudato {str(e.get('url'))[-40:]} ≠ scritto {url[-40:]}")
        elif e.get("verdetto") != "ricevuto e verificato":
            non_conformi.append(f"{isin}/{tipo}: {e.get('verdetto')}")
        else:
            verificati += 1
    return (not mancanti and not non_conformi and not url_diversi and verificati == len(attesi)), {"verificati": verificati, "mancanti": mancanti, "non_conformi": non_conformi, "url_diversi": url_diversi, "esiti_letti": len(esiti)}


def collaudo_documents(prima, fasc, modules):
    """(rev. 4/4b) dopo |documents|: fotografia «dopo» validata e riconciliata nel perimetro, elenco delle scritture, collaudo dei documenti
    ricevuti sulle classi toccate RICONCILIATO documento per documento, revalidazione con contratto completo; tutto nel fascicolo e nel battito."""
    m = EXTRA_METRICS.setdefault("documenti", {})
    dopo = foto_colonne_documenti(os.path.join(fasc, "documents-colonne-dopo.tsv"))
    if dopo is None:
        log("!! documents: fotografia «dopo» fallita — scritture NON riconciliate")
        modules["documents-collaudo"] = False
        m["documents"] = "scritture non riconciliate (fotografia dopo fallita)"
        return
    if set(prima) != set(dopo):
        log(f"!! documents: perimetro cambiato fra le fotografie (solo prima {len(set(prima) - set(dopo))}, solo dopo {len(set(dopo) - set(prima))}) — scritture NON riconciliate")
        modules["documents-collaudo"] = False
        m["documents"] = f"scritture non riconciliate (perimetro cambiato: solo prima {len(set(prima) - set(dopo))}, solo dopo {len(set(dopo) - set(prima))})"
        return
    diff = differenze_documenti(prima, dopo)
    with open(os.path.join(fasc, "documents-scritture.tsv"), "w") as f:
        for isin, col, a, b in diff:
            f.write(f"{isin}\t{col}\t{a}\t{b}\n")
    attesi = [(isin, TIPO_DI_COLONNA[col], b) for isin, col, a, b in diff if b]
    rimossi = [f"{isin}/{TIPO_DI_COLONNA[col]}" for isin, col, a, b in diff if not b]
    isins = sorted({d[0] for d in diff})
    m["documents"] = {"celle_cambiate": len(diff), "classi": len(isins), "documenti_da_collaudare": len(attesi), "collegamenti_rimossi": rimossi, "fascicolo": fasc}
    log(f"  |documents| scritture riconciliate: {len(diff)} celle su {len(isins)} classi, {len(attesi)} documenti da collaudare, {len(rimossi)} collegamenti rimossi (documents-scritture.tsv)")
    if not isins:
        modules["documents-collaudo"] = True
        return
    lista = os.path.join(fasc, "documents-classi-toccate.txt")
    with open(lista, "w") as f:
        f.write("\n".join(isins) + "\n")
    cartella = os.path.join(fasc, "collaudo")
    rc = None
    try:
        cl = subprocess.run([NODE, "scripts/collaudo-documenti-ricevuti.mjs", "--file", lista, "--come", "utente", "--out", cartella],
                            cwd=REPO, capture_output=True, text=True, timeout=3600)
        with open(os.path.join(fasc, "collaudo-stdout.tsv"), "w") as f:
            f.write((cl.stdout or "") + "\n" + (cl.stderr or ""))
        for line in (cl.stdout or "").strip().splitlines()[-2:]:
            log(f"  |documents-collaudo| {line}")
        rc = cl.returncode
    except Exception as e:
        log(f"!! documents-collaudo fallito (non blocca): {e}")
        m["collaudo"] = {"errore": str(e)[:120]}
    ric_ok, ric = (False, {"verificati": 0, "mancanti": [f"{a[0]}/{a[1]}" for a in attesi]}) if rc is None else riconcilia_collaudo(attesi, os.path.join(cartella, "collaudo-documenti-ricevuti.jsonl"))
    modules["documents-collaudo"] = rc == 0 and ric_ok
    m["collaudo"] = {"uscita": rc, "classi": len(isins), **ric}
    if not modules["documents-collaudo"]:
        log(f"!! documents-collaudo: uscita {rc} · riconciliazione {'ok' if ric_ok else 'FALLITA'} (verificati {ric.get('verificati')}/{len(attesi)}, mancanti {len(ric.get('mancanti', []))}, non conformi {len(ric.get('non_conformi', []))}, url diversi {len(ric.get('url_diversi', []))}) — vedi {cartella}")
    else:
        log(f"  |documents-collaudo| riconciliazione: {ric['verificati']}/{len(attesi)} documenti modificati ricevuti e verificati")
    ok, esiti = revalidate_schede(isins, fasc)
    modules["documents-revalidate"] = ok
    m["revalidate"] = esiti


def _sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for blocco in iter(lambda: f.read(1 << 20), b""):
            h.update(blocco)
    return h.hexdigest()


CAMPI_RIEPILOGO = ("quando", "url", "ok", "nonRaggiungibili", "nonPdf", "errori", "associazioni", "invariate", "diverse", "nuove", "nonLeggibili", "spurie", "nonConclusivi", "conservati")
SHA256_RE = re.compile(r"^[0-9a-f]{64}$")


def verifica_prova_archivio(prova_dir, t_lancio):
    """(rev. 4b/4c) L'indice della prova è di QUESTA corsa ed è integro: ogni riga JSON con url, quando ≥ lancio, esito, associazioni; ogni
    PDF conservato ha nell'indice un'impronta SHA-256 OBBLIGATORIA e il contenuto la rispetta; riepilogo-prova.json è un OGGETTO di questa
    corsa con i campi obbligatori e conteggi RICONCILIATI con l'indice (url, esiti, associazioni, decisioni, file conservati).
    Ritorna (ok, dettagli, motivi)."""
    motivi = []
    indice = os.path.join(prova_dir, "indice-prova.jsonl")
    if not os.path.exists(indice):
        return False, {"indice_righe": 0}, ["indice-prova.jsonl assente"]
    righe, conservati, verificati = 0, 0, 0
    conteggi = {"ok": 0, "nonRaggiungibili": 0, "nonPdf": 0, "errori": 0, "associazioni": 0, "invariate": 0, "diverse": 0, "nuove": 0, "nonLeggibili": 0, "conservati": 0}
    ESITO_CHIAVE = {"ok": "ok", "non raggiungibile": "nonRaggiungibili", "non-PDF": "nonPdf", "errore": "errori"}
    DECISIONE_CHIAVE = {"invariato": "invariate", "contenuto diverso": "diverse", "nuovo": "nuove", "ultima versione non leggibile": "nonLeggibili"}
    with open(indice) as f:
        for n, l in enumerate(f, start=1):
            if not l.strip():
                continue
            try:
                r = json.loads(l)
            except Exception:
                motivi.append(f"riga {n} dell'indice non è JSON"); continue
            righe += 1
            if not isinstance(r, dict) or not isinstance(r.get("url"), str) or not r.get("url") or r.get("esito") is None or not isinstance(r.get("associazioni"), list) or not isinstance(r.get("quando"), str):
                motivi.append(f"riga {n}: campi obbligatori mancanti (url/esito/associazioni/quando)"); continue
            if r["quando"] < t_lancio:
                motivi.append(f"riga {n}: istante {r['quando']} precedente al lancio {t_lancio} (indice vecchio)"); continue
            chiave = ESITO_CHIAVE.get(r["esito"])
            if chiave is None:
                motivi.append(f"riga {n}: esito sconosciuto {r['esito']!r}"); continue
            conteggi[chiave] += 1
            if r["esito"] == "ok":
                conteggi["associazioni"] += len(r["associazioni"])
                for a in r["associazioni"]:
                    dk = DECISIONE_CHIAVE.get(a.get("decisione") if isinstance(a, dict) else None)
                    if dk is None:
                        motivi.append(f"riga {n}: associazione {a.get('isin') if isinstance(a, dict) else '?'}/{a.get('tipo') if isinstance(a, dict) else '?'} con decisione sconosciuta")
                    else:
                        conteggi[dk] += 1
            for rel in r.get("conservati") or []:
                p = os.path.join(prova_dir, rel)
                if not os.path.isfile(p):
                    motivi.append(f"riga {n}: file conservato assente {rel}"); continue
                conservati += 1
                if rel.endswith(".pdf"):
                    conteggi["conservati"] += 1
                    if not isinstance(r.get("sha256"), str) or not SHA256_RE.match(r["sha256"]):
                        motivi.append(f"riga {n}: PDF conservato senza impronta sha256 nell'indice ({rel})"); continue
                    if _sha256_file(p) != r["sha256"]:
                        motivi.append(f"riga {n}: impronta del file conservato ≠ indice ({rel})"); continue
                    verificati += 1
            for a in r["associazioni"]:
                if isinstance(a, dict) and a.get("conservato") and a["conservato"] not in (r.get("conservati") or []):
                    motivi.append(f"riga {n}: associazione {a.get('isin')}/{a.get('tipo')} rimanda a un file non elencato fra i conservati")
    if righe == 0:
        motivi.append("indice senza righe")
    if conteggi["conservati"] != verificati:
        motivi.append(f"PDF conservati {conteggi['conservati']} ≠ impronte verificate {verificati}")
    riep_p = os.path.join(prova_dir, "riepilogo-prova.json")
    riep = None
    try:
        with open(riep_p) as f:
            riep = json.load(f)
    except Exception as e:
        motivi.append(f"riepilogo-prova.json assente o illeggibile ({str(e)[:60]})")
    if riep is not None and not isinstance(riep, dict):
        motivi.append(f"riepilogo-prova.json non è un oggetto ({type(riep).__name__})"); riep = None
    if isinstance(riep, dict):
        mancanti = [k for k in CAMPI_RIEPILOGO if k not in riep]
        if mancanti:
            motivi.append(f"riepilogo: campi obbligatori mancanti {mancanti}")
        else:
            if not isinstance(riep["quando"], str) or riep["quando"] < t_lancio:
                motivi.append("riepilogo di una corsa precedente (quando < lancio)")
            if riep["url"] != righe:
                motivi.append(f"riepilogo: url {riep['url']} ≠ righe dell'indice {righe}")
            for k in ("ok", "nonRaggiungibili", "nonPdf", "errori", "associazioni", "invariate", "diverse", "nuove", "nonLeggibili", "conservati"):
                if riep[k] != conteggi[k]:
                    motivi.append(f"riepilogo: {k} {riep[k]} ≠ indice {conteggi[k]}")
            if riep["ok"] + riep["nonRaggiungibili"] + riep["nonPdf"] + riep["errori"] != riep["url"]:
                motivi.append("riepilogo: esiti non sommano a url")
            if riep["invariate"] + riep["diverse"] + riep["nuove"] + riep["nonLeggibili"] != riep["associazioni"]:
                motivi.append("riepilogo: decisioni non sommano a associazioni")
    dettagli = {"indice_righe": righe, "file_conservati": conservati, "impronte_verificate": verificati, "conteggi_indice": conteggi, "riepilogo": {k: riep.get(k) for k in CAMPI_RIEPILOGO} if isinstance(riep, dict) else None}
    return (not motivi), dettagli, motivi[:20]


# ── PERCORSO DOCUMENTALE AUTOMATICO VERIFICABILE (rev. 5, 28 ott 2026; GO di Linus alla sola preparazione) ──
ARCH_DOCS = os.path.expanduser("~/backups/rebalix-docs-archivio")
REGOLE_LOTTI = os.path.join(REPO, "docs", "giro-documenti", "regole-lotti-automatici.json")
COPIONE_COMMIT = os.path.join(ARCHIVE, "esegui-commit-lotto-giro.sh")
COLLAUDO_PAGINA = os.path.join(ARCHIVE, "collaudo-pagina-documenti.py")
BUDGET_LOTTI_MIN = int(os.environ.get("REBALIX_BUDGET_LOTTI_MIN", "300"))
TIMEOUT_LOTTO_S = int(os.environ.get("REBALIX_TIMEOUT_LOTTO_S", str(2 * 3600)))


def _sha256_testo(testo_):
    return hashlib.sha256(testo_.encode("utf-8") if isinstance(testo_, str) else testo_).hexdigest()


def leggi_autocommit(percorso, ym, regole_sha):
    """Autorizzazione al COMMIT automatico: file {giro, regole_sha256, go}. Ritorna {stato: 'autorizzato'|'non autorizzato'|'non valido', motivo, go}."""
    if not os.path.exists(percorso):
        return {"stato": "non autorizzato", "motivo": "file di GO assente: i lotti restano pronti per il COMMIT con GO", "go": None}
    try:
        with open(percorso) as f:
            j = json.load(f)
    except Exception as e:
        return {"stato": "non valido", "motivo": f"file di GO illeggibile ({str(e)[:60]})", "go": None}
    if not isinstance(j, dict):
        return {"stato": "non valido", "motivo": "file di GO non è un oggetto", "go": None}
    if j.get("giro") != ym:
        return {"stato": "non valido", "motivo": f"file di GO per il giro {j.get('giro')!r}, giro corrente {ym}", "go": None}
    if j.get("regole_sha256") != regole_sha:
        return {"stato": "non valido", "motivo": f"file di GO per regole {str(j.get('regole_sha256'))[:12]} ≠ regole in uso {regole_sha[:12]}", "go": None}
    if not str(j.get("go") or "").strip():
        return {"stato": "non valido", "motivo": "file di GO senza «go» (le parole di Linus)", "go": None}
    return {"stato": "autorizzato", "motivo": "file di GO valido", "go": str(j["go"]).strip()}


ATTESA_TERM_S = int(os.environ.get("REBALIX_ATTESA_TERM_S", "30"))


MARCATORE_LANCIO = "REBALIX_LANCIO"


def _pid_con_marcatore(marca, escludi=()):
    """PID vivi il cui AMBIENTE porta REBALIX_LANCIO=<marca>: figli e nipoti del lancio anche se hanno cambiato gruppo o sessione (setsid).
    Linux: /proc/<pid>/environ (leggibile per i processi dell'utente); macOS: `ps -E` elenca l'ambiente dopo gli argomenti."""
    voluto = f"{MARCATORE_LANCIO}={marca}"
    pids = set()
    if os.path.isdir("/proc"):
        for d in os.listdir("/proc"):
            if not d.isdigit() or int(d) in escludi:
                continue
            try:
                with open(f"/proc/{d}/environ", "rb") as f:
                    if voluto.encode() in f.read().split(b"\0"):
                        pids.add(int(d))
            except Exception:
                continue
        return pids
    try:
        out = subprocess.check_output(["ps", "-axE", "-o", "pid=,stat=,command="], text=True, errors="replace")
    except Exception:
        return pids
    for l in out.splitlines():
        p = l.split(None, 2)
        if len(p) == 3 and not p[1].startswith("Z") and voluto in p[2].split():
            try:
                if int(p[0]) not in escludi:
                    pids.add(int(p[0]))
            except ValueError:
                pass
    return pids


def _processi_del_lancio(pgid, sid, marca, escludi=()):
    """{pid: (pgid, descrizione)} dei processi VIVI appartenenti al lancio: stesso gruppo, stessa sessione (dove ps la espone) o marcatore
    d'ambiente; zombie (stat Z) esclusi; `escludi` = PID da ignorare (il processo stesso del runner)."""
    vivi = {}
    try:
        out = subprocess.check_output(["ps", "-eo", "pid=,pgid=,sess=,stat=,args="], text=True, errors="replace")
    except Exception:
        out = ""
    for l in out.splitlines():
        p = l.split(None, 4)
        if len(p) < 4 or p[3].startswith("Z"):
            continue
        try:
            pid, pg, ss = int(p[0]), int(p[1]), int(p[2])
        except ValueError:
            continue
        if pid in escludi:
            continue
        if pg == pgid or (sid and ss == sid and ss > 1):
            vivi[pid] = (pg, (p[4] if len(p) > 4 else "")[:100])
    for pid in _pid_con_marcatore(marca, escludi):
        if pid not in vivi:
            try:
                pg = os.getpgid(pid)
            except Exception:
                pg = None
            vivi[pid] = (pg, "(trovato dal marcatore d'ambiente)")
    return vivi


def _ferma_lancio(pgid, sid, marca, escludi=()):
    """TERM a ogni gruppo e a ogni processo del lancio, attesa fino a ATTESA_TERM_S, poi KILL; ritorna i residui dopo il KILL (attesi 0)."""
    def segnala(sig):
        vivi = _processi_del_lancio(pgid, sid, marca, escludi)
        for pg in {v[0] for v in vivi.values() if v[0]}:
            try:
                os.killpg(pg, sig)
            except Exception:
                pass
        for pid in vivi:
            try:
                os.kill(pid, sig)
            except Exception:
                pass
        return vivi
    if not segnala(signal.SIGTERM):
        return 0
    for _ in range(ATTESA_TERM_S):
        time.sleep(1)
        if not _processi_del_lancio(pgid, sid, marca, escludi):
            return 0
    segnala(signal.SIGKILL)
    time.sleep(1)
    return len(_processi_del_lancio(pgid, sid, marca, escludi))


def _lancia(cmd, timeout, env=None, cwd=None):
    """(rev. 5b/5c) Esegue `cmd` in un GRUPPO e in una SESSIONE propri (setsid) con un MARCATORE d'ambiente, stdout/stderr su FILE, e lo
    aspetta. Alla fine conta i processi del LANCIO (gruppo ∪ sessione ∪ marcatore: anche i nipoti che hanno fatto setsid) e li ferma.
    Ritorna (rc, out, err, info). Timeout → TERM/KILL e riconteggio: 124 solo se non resta nulla, 126 se l'arresto è incompleto.
    Uscita normale con processi del lancio ancora vivi → li ferma e ritorna 127 (residui dopo l'uscita): mai un successo."""
    marca = uuid.uuid4().hex
    info = {"timeout": False, "residui_dopo_uscita": 0, "residui_finali": 0, "marcatore": marca}
    ambiente = dict(env if env is not None else os.environ)
    ambiente[MARCATORE_LANCIO] = marca
    me = (os.getpid(),)
    fo = tempfile.NamedTemporaryFile(prefix="lancia-out-", delete=False)
    fe = tempfile.NamedTemporaryFile(prefix="lancia-err-", delete=False)

    def leggi():
        try:
            fo.flush(); fe.flush()
            with open(fo.name, errors="replace") as a, open(fe.name, errors="replace") as b:
                o, e = a.read(), b.read()
        except Exception:
            o, e = "", ""
        for f in (fo, fe):
            try:
                f.close(); os.unlink(f.name)
            except Exception:
                pass
        return o, e
    try:
        p = subprocess.Popen(cmd, cwd=cwd or REPO, env=ambiente, stdout=fo, stderr=fe, start_new_session=True)
    except Exception as e:
        leggi()
        return 125, "", str(e), info
    pgid = sid = p.pid
    try:
        rc = p.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        info["timeout"] = True
        _ferma_lancio(pgid, sid, marca, me)
        try:
            p.wait(timeout=10)
        except Exception:
            pass
        info["residui_finali"] = len(_processi_del_lancio(pgid, sid, marca, me))
        out, err = leggi()
        return (124 if info["residui_finali"] == 0 else 126), out, err + f"\ntimeout {timeout}s (residui finali {info['residui_finali']})", info
    res = _processi_del_lancio(pgid, sid, marca, me)
    if res:
        info["residui_dopo_uscita"] = len(res)
        info["residui"] = [f"{pid} (gruppo {v[0]}): {v[1]}" for pid, v in list(res.items())[:5]]
        info["residui_finali"] = _ferma_lancio(pgid, sid, marca, me)
        out, err = leggi()
        return 127, out, err + f"\n{len(res)} processi del lancio ancora vivi dopo l'uscita {rc}: fermati (residui finali {info['residui_finali']})", info
    out, err = leggi()
    return rc, out, err, info


def _esegui(cmd, timeout, env=None, cwd=None):
    rc, out, err, _info = _lancia(cmd, timeout, env=env, cwd=cwd)
    return rc, out, err


def _sha256_file_(p):
    with open(p, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _iso_a_dt(s):
    try:
        return datetime.datetime.fromisoformat(str(s).replace("Z", "+00:00"))
    except Exception:
        return None


def verifica_valida(ver, rc, lotto, anteprima, t_avvio):
    """(rev. 5b) L'anteprima è approvabile SOLO se: uscita 0, rapporto di QUESTA esecuzione, approvabile === true, nessun motivo, conteggi
    coerenti con il lotto, impronte collegate a lotto e anteprima. Ritorna (ok, motivi)."""
    motivi = []
    if rc != 0:
        motivi.append(f"verificatore uscita {rc}")
    if not isinstance(ver, dict):
        return False, motivi + ["rapporto del verificatore assente o non è un oggetto"]
    if ver.get("approvabile") is not True:
        motivi.append("rapporto: approvabile ≠ true")
    if ver.get("motivi"):
        motivi.append(f"rapporto con {len(ver['motivi'])} motivi (es. {str(ver['motivi'][0])[:80]})")
    q = _iso_a_dt(ver.get("quando"))
    if q is None or q < t_avvio - datetime.timedelta(seconds=2):
        motivi.append(f"rapporto non di questa esecuzione (quando {ver.get('quando')!r}, lancio {t_avvio.isoformat(timespec='seconds')})")
    try:
        if ver.get("lotto_sha256") != _sha256_file_(lotto):
            motivi.append("rapporto: impronta del lotto ≠ file del lotto")
        if ver.get("anteprima_sha256") != _sha256_file_(anteprima):
            motivi.append("rapporto: impronta dell'anteprima ≠ file dell'anteprima")
        with open(lotto) as f:
            n_voci = len(json.load(f).get("voci") or [])
    except Exception as e:
        return False, motivi + [f"file del lotto/anteprima non leggibili: {str(e)[:60]}"]
    c = ver.get("conteggi") if isinstance(ver.get("conteggi"), dict) else {}
    if not (c.get("voci") == n_voci and c.get("righe") == n_voci and c.get("verificate") == n_voci and n_voci > 0):
        motivi.append(f"conteggi non coerenti con il lotto ({n_voci} voci): {c}")
    for k in ("mancanti", "non_verificate", "impronte_diverse", "url_bloccanti"):
        if c.get(k, 0) not in (0, None):
            motivi.append(f"conteggi: {k} = {c.get(k)}")
    return (not motivi), motivi


def attese_da_anteprima(lotto, anteprima):
    """Attese per voce del lotto, derivate dall'ANTEPRIMA APPROVATA (non dal rapporto del copione): lingua «scritta e verificata» se
    azione_lingua è scrivi/invalida con patch, URL «scritto e verificato» se azione_url è «da scrivere», altrimenti «n/p».
    Ritorna ({(isin, tipo): {"lingua": …, "url": …}}, motivi)."""
    motivi = []
    with open(lotto) as f:
        voci = json.load(f).get("voci") or []
    with open(anteprima) as f:
        righe = json.load(f).get("righe") or []
    attese = {}
    for v in voci:
        k = (v.get("isin"), v.get("tipo"))
        if k in attese:
            motivi.append(f"lotto: associazione {k[0]}/{k[1]} ripetuta")
        attese[k] = {"lingua": "n/p", "url": "n/p"}
    for r in righe:
        k = (r.get("isin"), r.get("tipo"))
        if k not in attese:
            motivi.append(f"anteprima: riga {k[0]}/{k[1]} estranea al lotto")
            continue
        al = r.get("azione_lingua") if isinstance(r.get("azione_lingua"), dict) else None
        if al and al.get("azione") in ("scrivi", "invalida") and isinstance(al.get("patch"), dict):
            attese[k]["lingua"] = "scritta e verificata"
        if r.get("azione_url") == "da scrivere":
            attese[k]["url"] = "scritto e verificato"
    return attese, motivi


def riscontro_commit(w, t_avvio, lotto, anteprima):
    """(rev. 5b/5c) Un COMMIT è riuscito solo se il copione ha lasciato in QUESTA corsa esito.txt con «ESITO: ok» e uno stato per voce
    coerente IN OGNI RIGA: associazioni = voci del lotto (nessuna mancante, estranea o doppia), ogni riga archiviata, controllata,
    «completo», con lingua e URL uguali alle attese derivate dall'anteprima approvata; i conteggi ricostruiti dal dettaglio coincidono con
    il RIEPILOGO del copione e con il lotto. Ritorna (ok, motivi, riepilogo_testo)."""
    motivi = []
    esito_p = os.path.join(w, "esito.txt")
    try:
        if datetime.datetime.fromtimestamp(os.path.getmtime(esito_p), datetime.timezone.utc) < t_avvio - datetime.timedelta(seconds=2):
            motivi.append("esito.txt di una corsa precedente")
        with open(esito_p) as f:
            righe_e = [l.strip() for l in f if "ESITO" in l]
        ultimo = righe_e[-1] if righe_e else ""
        if "ESITO: ok" not in ultimo:
            motivi.append(f"esito finale non è «ESITO: ok» ({ultimo[:120]})")
    except Exception as e:
        return False, [f"esito.txt assente o illeggibile ({str(e)[:60]})"], ""
    try:
        attese, m_att = attese_da_anteprima(lotto, anteprima)
        motivi += m_att
    except Exception as e:
        return False, motivi + [f"lotto/anteprima non leggibili ({str(e)[:60]})"], ""
    riep, righe = {}, []
    try:
        with open(os.path.join(w, "stato-per-voce.tsv")) as f:
            for l in f:
                l = l.rstrip("\n")
                if l.startswith("#RIEPILOGO"):
                    for campo in l.split("\t")[1:]:
                        k, _, v = campo.rpartition(" ")
                        riep[k] = v
                elif l and not l.startswith("#") and not l.startswith("isin\t"):
                    righe.append(l.split("\t"))
    except Exception as e:
        return False, motivi + [f"stato per voce assente ({str(e)[:60]})"], ""
    if not riep:
        return False, motivi + ["RIEPILOGO dello stato per voce assente"], ""
    viste = {}
    for r in righe:
        if len(r) < 7:
            motivi.append(f"riga per voce malformata: {r[:3]}"); continue
        k = (r[0], r[1])
        if k in viste:
            motivi.append(f"{k[0]}/{k[1]}: riga per voce DOPPIA"); continue
        viste[k] = r
        if k not in attese:
            motivi.append(f"{k[0]}/{k[1]}: riga per voce ESTRANEA al lotto"); continue
        if r[2] != "1":
            motivi.append(f"{k[0]}/{k[1]}: non archiviata")
        if r[3] != "1":
            motivi.append(f"{k[0]}/{k[1]}: senza riga di controllo")
        if r[4] != attese[k]["lingua"]:
            motivi.append(f"{k[0]}/{k[1]}: lingua «{r[4]}» ≠ attesa dall'anteprima «{attese[k]['lingua']}»")
        if r[5] != attese[k]["url"]:
            motivi.append(f"{k[0]}/{k[1]}: URL «{r[5]}» ≠ atteso dall'anteprima «{attese[k]['url']}»")
        if r[6] != "completo":
            motivi.append(f"{k[0]}/{k[1]}: stato «{r[6]}» ≠ completo")
    for k in attese:
        if k not in viste:
            motivi.append(f"{k[0]}/{k[1]}: voce del lotto SENZA riga per voce")
    n_voci = len(attese)
    ric = {"voci": len(righe), "archiviate": sum(1 for r in righe if len(r) > 2 and r[2] == "1"), "controlli": sum(1 for r in righe if len(r) > 3 and r[3] == "1"),
           "complete": sum(1 for r in righe if len(r) > 6 and r[6] == "completo"), "parziali": sum(1 for r in righe if len(r) > 6 and r[6].startswith("PARZIALE")),
           "lingue_ok": sum(1 for r in righe if len(r) > 4 and r[4] == "scritta e verificata"), "lingue_att": sum(1 for a in attese.values() if a["lingua"] != "n/p"),
           "url_ok": sum(1 for r in righe if len(r) > 5 and r[5] == "scritto e verificato"), "url_att": sum(1 for a in attese.values() if a["url"] != "n/p")}

    def n(k):
        try:
            return int(riep.get(k, "x"))
        except ValueError:
            return None
    for k in ("voci", "archiviate", "controlli", "complete"):
        if n(k) != n_voci:
            motivi.append(f"riepilogo: {k} {riep.get(k)} ≠ {n_voci} voci del lotto")
        if ric[k] != n_voci:
            motivi.append(f"dettaglio: {k} ricostruite {ric[k]} ≠ {n_voci} voci del lotto")
    for k in ("parziali", "non eseguite", "nuovi file fuori attesa", "registro non autorizzato", "archivio preesistente alterato"):
        if n(k) != 0:
            motivi.append(f"riepilogo: {k} = {riep.get(k)}")
    if ric["parziali"] != 0:
        motivi.append(f"dettaglio: {ric['parziali']} righe parziali")
    if riep.get("lingue") != f"{ric['lingue_att']}/{ric['lingue_att']}" or ric["lingue_ok"] != ric["lingue_att"]:
        motivi.append(f"lingue: riepilogo {riep.get('lingue')} · dettaglio {ric['lingue_ok']} · attese dall'anteprima {ric['lingue_att']}")
    if riep.get("url") != f"{ric['url_att']}/{ric['url_att']}" or ric["url_ok"] != ric["url_att"]:
        motivi.append(f"url: riepilogo {riep.get('url')} · dettaglio {ric['url_ok']} · attesi dall'anteprima {ric['url_att']}")
    return (not motivi), motivi, " ".join(f"{k} {v}" for k, v in riep.items())


def lotti_automatici(prova_dir, modules):
    """Dopo una prova dell'archivio VALIDA: regole → lotti riconciliati → per lotto PROVA → verifica → COMMIT se autorizzato (entro budget)."""
    m = EXTRA_METRICS.setdefault("documenti", {}).setdefault("lotti", {})
    t_inizio = datetime.datetime.now()
    scadenza = t_inizio + datetime.timedelta(minutes=BUDGET_LOTTI_MIN)
    # 1. regole
    try:
        with open(REGOLE_LOTTI, "rb") as f:
            regole_bytes = f.read()
        regole = json.loads(regole_bytes.decode("utf-8"))
        regole_sha = _sha256_testo(regole_bytes)
    except Exception as e:
        log(f"!! lotti-automatici NON eseguiti: regole non leggibili ({REGOLE_LOTTI}: {str(e)[:80]})")
        modules["lotti-automatici"] = False
        m.update({"stato": "regole non leggibili", "regole": REGOLE_LOTTI})
        return
    m.update({"regole": REGOLE_LOTTI, "regole_versione": regole.get("versione"), "regole_sha256": regole_sha, "budget_min": BUDGET_LOTTI_MIN})
    # 2. lotti dall'indice
    lotti_dir = os.path.join(prova_dir, "lotti")
    rc, out, err = _esegui([NODE, "scripts/lotti-automatici-da-indice.mjs", "--indice", os.path.join(prova_dir, "indice-prova.jsonl"), "--regole", REGOLE_LOTTI, "--out", lotti_dir, "--base", prova_dir], 600)
    for line in (out + err).strip().splitlines()[-6:]:
        log(f"  |lotti-automatici| {line}")
    ric = None
    try:
        with open(os.path.join(lotti_dir, "riconciliazione-lotti.json")) as f:
            ric = json.load(f)
    except Exception:
        ric = None
    if isinstance(ric, dict):
        m["riconciliazione"] = {k: ric.get(k) for k in ("associazioni_indice", "in_lotto", "escluse", "non_proposte", "per_motivo", "lotti", "errori")}
    if rc == 3:
        log("  |lotti-automatici| nulla da archiviare: tutte le associazioni invariate, escluse o non proposte (vedi riconciliazione)")
        modules["lotti-automatici"] = True
        m["stato"] = "nessun lotto"
        return
    if rc != 0 or not isinstance(ric, dict) or ric.get("errori"):
        log(f"!! lotti-automatici: uscita {rc} — riconciliazione incompleta o regole non valide: nessun lotto eseguito")
        modules["lotti-automatici"] = False
        m["stato"] = f"errore (uscita {rc})"
        return
    nomi = sorted(f for f in os.listdir(lotti_dir) if f.startswith("lotto-") and f.endswith(".json"))
    # (rev. 5b) COERENZA lotti ↔ riconciliazione PRIMA di eseguire: nessun duplicato, stesse associazioni, stessi conteggi per lotto
    ass_ric = set(f"{t.get('isin')}/{t.get('tipo')}" for t in (ric.get("tabella") or []) if t.get("categoria") == "lotto")
    viste, conteggi_lotti, incoerenze = {}, {}, []
    for nome_file in nomi:
        try:
            with open(os.path.join(lotti_dir, nome_file)) as f:
                lj = json.load(f)
            voci = lj.get("voci") if isinstance(lj, dict) else None
        except Exception as e:
            incoerenze.append(f"{nome_file}: non leggibile ({str(e)[:60]})"); continue
        if not isinstance(voci, list) or not voci:
            incoerenze.append(f"{nome_file}: senza voci"); continue
        conteggi_lotti[nome_file] = len(voci)
        for v in voci:
            k = f"{v.get('isin')}/{v.get('tipo')}"
            if k in viste:
                incoerenze.append(f"{k}: associazione presente in {viste[k]} e in {nome_file}")
            viste[k] = nome_file
            if k not in ass_ric:
                incoerenze.append(f"{k}: nel lotto {nome_file} ma non «lotto» nella riconciliazione")
    for k in sorted(ass_ric - set(viste)):
        incoerenze.append(f"{k}: «lotto» nella riconciliazione ma in nessun file di lotto")
    if sum(conteggi_lotti.values()) != ric.get("in_lotto"):
        incoerenze.append(f"voci nei lotti {sum(conteggi_lotti.values())} ≠ in_lotto {ric.get('in_lotto')} nella riconciliazione")
    slug = lambda s: re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-")
    lotti_ric = {slug(k): v for k, v in (ric.get("lotti") or {}).items()}
    for nome_file, nv in conteggi_lotti.items():
        nome = nome_file[len("lotto-"):-len(".json")]
        if lotti_ric.get(nome) != nv:
            incoerenze.append(f"{nome_file}: {nv} voci ≠ {lotti_ric.get(nome)} dichiarate nella riconciliazione")
    if incoerenze:
        log(f"!! lotti-automatici: lotti NON coerenti con la riconciliazione ({len(incoerenze)}; es. {incoerenze[0][:120]}) — nessun lotto eseguito")
        modules["lotti-automatici"] = False
        m["stato"] = "lotti incoerenti con la riconciliazione"
        m["incoerenze"] = incoerenze[:10]
        return
    modules["lotti-automatici"] = True
    m["coerenza_lotti"] = {"lotti": len(nomi), "associazioni": len(viste)}
    OFF_REG = os.environ.get("REBALIX_LOTTI_OFFLINE_REGISTRO"); OFF_SRC = os.environ.get("REBALIX_LOTTI_OFFLINE_SORGENTI")
    offline = bool(OFF_REG and OFF_SRC)
    if offline:
        log("  |lotti-automatici| MODALITÀ OFFLINE DI PROVA (mai in produzione): registro JSON e sorgenti locali al posto di DB e rete — il battito la segna ROSSA")
        m["offline_di_prova"] = True
        modules["lotti-offline-di-prova"] = False   # un giro reale con i ganci di prova nell'ambiente deve risultare rosso al guardiano
    blocco = None
    # 3. autorizzazione al COMMIT
    aut = leggi_autocommit(os.path.join(FASC_DOCUMENTI, f"AUTOCOMMIT-DOCUMENTI-{YM}.json"), YM, regole_sha)
    m["autorizzazione"] = aut
    log(f"  |lotti-automatici| {len(nomi)} lotti · COMMIT {aut['stato']} ({aut['motivo']})")
    rc_git, head, _ = _esegui(["git", "-C", REPO, "rev-parse", "HEAD"], 60)
    head = head.strip()
    dett = m.setdefault("dettaglio", {})
    m.update({"lotti_totali": len(nomi), "prove_ok": 0, "approvabili": 0, "commit_ok": 0, "commit_falliti": 0, "non_eseguiti_budget": 0, "pronti_per_go": 0, "commit_sospesi": 0, "verifiche_non_valide": 0, "commit_non_riscontrati": 0})
    budget_rosso = False
    for nome_file in nomi:
        nome = nome_file[len("lotto-"):-len(".json")]
        lotto = os.path.join(lotti_dir, nome_file)
        d = dett.setdefault(nome, {})
        if datetime.datetime.now() >= scadenza:
            d["stato"] = "non eseguito per budget"
            m["non_eseguiti_budget"] += 1
            budget_rosso = True
            log(f"  |lotto-{nome}| NON eseguito: budget di {BUDGET_LOTTI_MIN} min esaurito (resta pronto per un giro successivo)")
            continue
        # 3a. PROVA offline sui file conservati
        ant_tsv = os.path.join(lotti_dir, f"{nome}-anteprima.tsv")
        ant_json = os.path.join(lotti_dir, f"{nome}-anteprima.json")
        cmd_prova = [NODE, "scripts/lotto-documenti-mirato.mjs", "--file", lotto, "--anteprima", ant_tsv, "--sorgenti-conservate", prova_dir, "--archivio", ARCH_DOCS, "--scarica-in", os.path.join(lotti_dir, f"{nome}-scarico")]
        if offline:
            cmd_prova += ["--registro-json", OFF_REG, "--sorgenti-locali", OFF_SRC]
        rc_p, out_p, err_p = _esegui(cmd_prova, TIMEOUT_LOTTO_S)
        with open(os.path.join(lotti_dir, f"{nome}-prova.out"), "w") as f:
            f.write(out_p + "\n" + err_p)
        d["prova_uscita"] = rc_p
        if rc_p != 0 or not os.path.exists(ant_json):
            d["stato"] = f"prova fallita (uscita {rc_p})"
            modules[f"lotto-{nome}"] = False
            log(f"!! lotto-{nome}: prova fallita (uscita {rc_p}): {(err_p or out_p).strip().splitlines()[-1:] or ''}")
            continue
        m["prove_ok"] += 1
        # 3b. verifica automatica dell'anteprima
        ver_json = os.path.join(lotti_dir, f"{nome}-verifica.json")
        t_ver = datetime.datetime.now(datetime.timezone.utc)
        rc_v, out_v, err_v = _esegui([NODE, "scripts/verifica-anteprima-lotto.mjs", "--lotto", lotto, "--anteprima", ant_json, "--out", ver_json], 600)
        try:
            with open(ver_json) as f:
                ver = json.load(f)
        except Exception:
            ver = None
        ok_ver, motivi_ver = verifica_valida(ver, rc_v, lotto, ant_json, t_ver)
        d["verifica"] = {"uscita": rc_v, "valida": ok_ver, "conteggi": (ver or {}).get("conteggi") if isinstance(ver, dict) else None, "motivi": motivi_ver[:5]}
        if not ok_ver:
            d["stato"] = "anteprima NON approvabile" if rc_v != 0 else "verifica NON valida (rapporto non collegato o incoerente)"
            modules[f"lotto-{nome}"] = False
            if rc_v == 0:
                m["verifiche_non_valide"] += 1
            log(f"!! lotto-{nome}: {d['stato']} ({len(motivi_ver)} motivi; es. {(motivi_ver or ['?'])[0][:110]})")
            continue
        m["approvabili"] += 1
        if aut["stato"] != "autorizzato":
            d["stato"] = "pronto per COMMIT con GO (anteprima verificata)"
            m["pronti_per_go"] += 1
            modules[f"lotto-{nome}"] = "pronto"
            log(f"  |lotto-{nome}| anteprima verificata ({ver.get('conteggi', {}).get('voci')} voci): pronto per il COMMIT con GO")
            continue
        if blocco:
            d["stato"] = f"pronto per COMMIT con GO — COMMIT SOSPESO: {blocco}"
            m["commit_sospesi"] += 1
            modules[f"lotto-{nome}"] = "sospeso"
            modules["lotti-commit-sospesi"] = False
            log(f"!! lotto-{nome}: COMMIT SOSPESO ({blocco}); anteprima verificata conservata")
            continue
        # 3c. COMMIT con il copione (foto prima/dopo, verifiche per voce, revalidate, collaudo pubblico)
        with open(lotto, "rb") as f:
            sha_l = _sha256_testo(f.read())
        with open(ant_json, "rb") as f:
            sha_a = _sha256_testo(f.read())
        w = os.path.join(lotti_dir, f"{nome}-commit")
        env = dict(os.environ, LOTTO=lotto, APPROVATA=ant_json, SORGENTI=prova_dir, W=w, ATTESO=head, SHA_LOTTO=sha_l, SHA_APPROVATA=sha_a, REPO=REPO, ARCH=ARCH_DOCS, NODE=NODE,
                   COLLAUDO=COLLAUDO_PAGINA, ORA_LIMITE=scadenza.strftime("%H%M") if scadenza.date() == t_inizio.date() else "2359")
        if offline:
            env.update(OFFLINE_REGISTRO=OFF_REG, OFFLINE_SORGENTI=OFF_SRC)
        t_commit = datetime.datetime.now(datetime.timezone.utc)
        rc_c, out_c, err_c, info_c = _lancia(["/bin/bash", COPIONE_COMMIT], TIMEOUT_LOTTO_S + 600, env=env)
        with open(os.path.join(lotti_dir, f"{nome}-commit.out"), "w") as f:
            f.write(out_c + "\n" + err_c)
        ok_r, motivi_r, riep_r = riscontro_commit(w, t_commit, lotto, ant_json)
        d["commit"] = {"uscita": rc_c, "riscontro": ok_r, "motivi": motivi_r[:5], "riepilogo": riep_r[:300], "processi": info_c, "cartella": w, "go": aut["go"]}
        if rc_c == 0 and ok_r:
            d["stato"] = "COMMIT riuscito, riscontrato, revalidato e collaudato"
            m["commit_ok"] += 1
            modules[f"lotto-{nome}"] = True
            log(f"  |lotto-{nome}| COMMIT ok e riscontrato · {riep_r[:160]}")
            continue
        modules[f"lotto-{nome}"] = False
        if rc_c == 0 and not ok_r:
            d["stato"] = "COMMIT NON riscontrato (uscita 0 ma riscontro finale incoerente)"
            m["commit_non_riscontrati"] += 1
            blocco = f"COMMIT di {nome} non riscontrato ({(motivi_r or ['?'])[0][:80]})"
        elif rc_c in (2, 7):
            d["stato"] = f"COMMIT non avvenuto (uscita {rc_c}: nulla scritto)"
            m["commit_falliti"] += 1
        else:
            d["stato"] = f"COMMIT fallito o incerto (uscita {rc_c})"
            m["commit_falliti"] += 1
            blocco = f"lotto {nome}: uscita {rc_c}" + (" con residui/arresto incompleto" if rc_c in (124, 126, 127) else "")
        log(f"!! lotto-{nome}: {d['stato']} · {(motivi_r or [''])[0][:120] if rc_c == 0 else (err_c or out_c).strip()[-160:]} — nessun rilancio automatico{'; COMMIT successivi SOSPESI' if blocco else ''}")
    if budget_rosso:
        modules["lotti-budget"] = False
    if blocco:
        m["blocco_commit"] = blocco
    m["durata_min"] = round((datetime.datetime.now() - t_inizio).total_seconds() / 60, 1)


def leggi_limitazioni(percorso, ym):
    """Limitazioni dichiarate per il giro `ym` (vedi sopra). Senza file: nessuna. File non valido: SystemExit(3), il giro non parte."""
    if not os.path.exists(percorso):
        return {"attive": False, "salta": (), "giro": None, "motivo": None, "go": None}
    try:
        with open(percorso) as f:
            j = json.load(f)
    except Exception as e:
        log(f"ARRESTO: {percorso} illeggibile ({e}) — il giro non parte")
        raise SystemExit(3)
    giro = j.get("giro") if isinstance(j, dict) else None
    salta_ = j.get("salta") if isinstance(j, dict) else None
    if giro != ym:
        log(f"ARRESTO: {percorso} dichiara il giro {giro!r} ma il giro corrente è {ym}: rimuovere o aggiornare il file — il giro non parte")
        raise SystemExit(3)
    if not isinstance(salta_, list) or not salta_ or any(s not in MODULI_LIMITABILI for s in salta_):
        log(f"ARRESTO: {percorso}: 'salta' deve elencare solo moduli fra {MODULI_LIMITABILI} (trovato {salta_!r}) — il giro non parte")
        raise SystemExit(3)
    if not str(j.get("motivo") or "").strip() or not str(j.get("go") or "").strip():
        log(f"ARRESTO: {percorso}: servono 'motivo' e 'go' (la parola di Linus) — il giro non parte")
        raise SystemExit(3)
    lim = {"attive": True, "salta": tuple(salta_), "giro": giro, "motivo": str(j["motivo"]).strip(), "go": str(j["go"]).strip()}
    log(f"LIMITAZIONI DICHIARATE per il giro {giro}: salta {', '.join(lim['salta'])} — {lim['motivo']} (GO: {lim['go']})")
    return lim


def salta(nome):
    """True se il modulo è escluso dal giro per limitazione dichiarata: lo registra (log, battito, marcatore) e il chiamante NON lo lancia."""
    if nome not in LIMITAZIONI["salta"]:
        return False
    log(f"  |{nome}| SALTATO per limitazione dichiarata (giro {LIMITAZIONI['giro']}; GO: {LIMITAZIONI['go']}) — {LIMITAZIONI['motivo']}")
    EXTRA_METRICS.setdefault("limitazioni", {})[nome] = {"giro": LIMITAZIONI["giro"], "motivo": LIMITAZIONI["motivo"], "go": LIMITAZIONI["go"]}
    return True

FASC_PANIERI = os.path.expanduser("~/fascicoli/panieri-giro")
LETTORI_CON_GUARDIA = ("amundi", "lgim")
GIRO = f"{TODAY}T{datetime.datetime.now().strftime('%H%M%S')}-{os.getpid()}"

def argomenti_lettore(emittente, primario, giro=None, fasc=None, raw_dir=None, node=None):
    """Comando del lettore primario di panieri: per i lettori con la guardia aggiunge rifiuti visibili, rapporto del giro e identificativo."""
    giro = giro or GIRO; fasc = fasc or FASC_PANIERI; raw_dir = raw_dir or RAW_DIR; node = node or NODE
    argomenti = [node, primario, "--commit", "--raw-dir", raw_dir]
    if emittente in LETTORI_CON_GUARDIA:
        os.makedirs(fasc, exist_ok=True)
        argomenti += ["--rifiuti", os.path.join(fasc, f"rifiuti-{emittente}-{TODAY}.jsonl"),
                      "--esito", os.path.join(fasc, f"esito-{emittente}-{TODAY}.json"),
                      "--giro", giro]
    return argomenti


# ── PREFLIGHT OBBLIGATORIO (27 ott 2026, percorso D rev. 3; auditor: «un meccanismo autorizzato che impedisca il giro con preflight
# assente o fallito», «verificare l'intera catena rapporto valido → marcatore valido → autorizzazione, comprese le evidenze richiamate»).
# Sulla VPS, fuori dal --dry-run, il giro PARTE solo se esiste PREFLIGHT_DIR/PREFLIGHT-OK-<YM>.json scritto dal controllo finale
# CONFORME della mattina (controllo-finale-2-novembre.sh rev. 3): giro == YM, verdetto == CONFORME, orario di oggi e non più vecchio di
# PREFLIGHT_MAX_ORE, E le evidenze richiamate (riepilogo del controllo e della sonda completa dell'1/11 nel fascicolo indicato) esistono,
# hanno le impronte sha256 dichiarate, portano «VERDETTO FINALE: CONFORME» e la sonda completa è datata ieri o oggi. Altrimenti uscita 3
# prima di ogni modulo. Unica alternativa: PREFLIGHT-DEROGA-<YM>.json con «motivo» e «go» (le parole di Linus), registrata nel log, nel
# battito e nel marcatore. Mai un terzo stato.
PREFLIGHT_DIR = os.path.expanduser("~/fascicoli/preflight")
PREFLIGHT_MAX_ORE = 6
PREFLIGHT = {"stato": "non richiesto"}


def _arresto_preflight(msg):
    log(f"ARRESTO: {msg} — il giro non parte")
    raise SystemExit(3)


def _evidenza_conforme(fascicolo, voce, nome, adesso=None, data_attesa=None):
    """Una evidenza richiamata dal marcatore: file presente nel fascicolo, sha256 uguale al dichiarato, «VERDETTO FINALE: CONFORME»
    dentro; se data_attesa è data, il nome del file deve portare quella data (AAAAMMGG). Ritorna il percorso o arresta."""
    if not isinstance(voce, dict) or not voce.get("riepilogo") or not voce.get("sha256"):
        _arresto_preflight(f"marcatore senza l'evidenza «{nome}» (riepilogo e sha256)")
    percorso = os.path.join(fascicolo, os.path.basename(str(voce["riepilogo"])))
    if not os.path.isfile(percorso):
        _arresto_preflight(f"evidenza «{nome}» richiamata dal marcatore ma assente: {percorso}")
    with open(percorso, "rb") as f:
        contenuto = f.read()
    if hashlib.sha256(contenuto).hexdigest() != str(voce["sha256"]).lower():
        _arresto_preflight(f"evidenza «{nome}» alterata: sha256 diverso da quello dichiarato nel marcatore ({percorso})")
    if not any(l.startswith("VERDETTO FINALE: CONFORME") for l in contenuto.decode("utf-8", "replace").split("\n")):
        _arresto_preflight(f"evidenza «{nome}» senza «VERDETTO FINALE: CONFORME» ({percorso})")
    if data_attesa and not any(d in os.path.basename(percorso) for d in data_attesa):
        _arresto_preflight(f"evidenza «{nome}» non datata ieri/oggi ({os.path.basename(percorso)}; attese {data_attesa})")
    return percorso


def verifica_preflight(cartella, ym, adesso=None):
    """Ritorna il dizionario del preflight accettato (marcatore con evidenze verificate, o deroga); altrimenti SystemExit(3)."""
    adesso = adesso or datetime.datetime.now()
    marcatore = os.path.join(cartella, f"PREFLIGHT-OK-{ym}.json")
    deroga = os.path.join(cartella, f"PREFLIGHT-DEROGA-{ym}.json")
    if os.path.exists(marcatore):
        try:
            with open(marcatore) as f:
                j = json.load(f)
        except Exception as e:
            _arresto_preflight(f"{marcatore} illeggibile ({e})")
        if not isinstance(j, dict) or j.get("giro") != ym or j.get("verdetto") != "CONFORME":
            _arresto_preflight(f"{marcatore} non è un preflight CONFORME del giro {ym} (giro={j.get('giro') if isinstance(j, dict) else None!r}, verdetto={j.get('verdetto') if isinstance(j, dict) else None!r})")
        try:
            quando = datetime.datetime.strptime(str(j.get("quando"))[:19], "%Y-%m-%dT%H:%M:%S")
        except Exception:
            _arresto_preflight(f"{marcatore} senza orario leggibile ('quando')")
        eta = (adesso - quando).total_seconds() / 3600
        if quando.date() != adesso.date() or eta < 0 or eta > PREFLIGHT_MAX_ORE:
            _arresto_preflight(f"preflight del {quando:%Y-%m-%d %H:%M} non è di oggi entro {PREFLIGHT_MAX_ORE} ore (ora {adesso:%Y-%m-%d %H:%M})")
        fascicolo = str(j.get("fascicolo") or "")
        if not fascicolo or not os.path.isdir(fascicolo):
            _arresto_preflight(f"{marcatore} senza fascicolo delle evidenze leggibile ('fascicolo'={fascicolo!r})")
        ieri_oggi = [(adesso - datetime.timedelta(days=1)).strftime("%Y%m%d"), adesso.strftime("%Y%m%d")]
        ev_controllo = _evidenza_conforme(fascicolo, j.get("controllo_finale"), "controllo finale", adesso)
        ev_completa = _evidenza_conforme(fascicolo, j.get("sonda_completa"), "sonda completa", adesso, data_attesa=ieri_oggi)
        p = {"stato": "conforme", "quando": j.get("quando"), "file": marcatore, "evidenze": {"controllo_finale": ev_controllo, "sonda_completa": ev_completa}}
        log(f"PREFLIGHT CONFORME per il giro {ym}: {marcatore} ({j.get('quando')}); evidenze verificate: {os.path.basename(ev_controllo)}, {os.path.basename(ev_completa)}")
        EXTRA_METRICS["preflight"] = p
        return p
    if os.path.exists(deroga):
        try:
            with open(deroga) as f:
                j = json.load(f)
        except Exception as e:
            _arresto_preflight(f"{deroga} illeggibile ({e})")
        if not isinstance(j, dict) or j.get("giro") != ym or not str(j.get("motivo") or "").strip() or not str(j.get("go") or "").strip():
            _arresto_preflight(f"{deroga} non valida (servono giro == {ym}, 'motivo' e 'go' = la parola di Linus)")
        p = {"stato": "deroga", "motivo": str(j["motivo"]).strip(), "go": str(j["go"]).strip(), "file": deroga}
        log(f"PREFLIGHT IN DEROGA per il giro {ym}: {p['motivo']} (GO: {p['go']}) — il giro parte senza controllo finale conforme")
        EXTRA_METRICS["preflight"] = p
        return p
    _arresto_preflight(f"nessun preflight conforme per il giro {ym} ({marcatore} assente) e nessuna deroga ({deroga})")



def battito_panieri(modules, uscite, giro=None, fasc=None, repo=None, node=None, log_fn=None):
    """Compone il blocco «panieri» (scripts/panieri-battito.mjs) e lo allega al battito in EXTRA_METRICS['panieri'].
    Il compositore legge SOLO i rapporti di questo giro; se fallisce il blocco manca e il guardiano segnala il rapporto assente.
    Nessuna scrittura nel DB. Ritorna il codice di uscita del compositore."""
    giro = giro or GIRO; fasc = fasc or FASC_PANIERI; repo = repo or REPO; node = node or NODE; log_fn = log_fn or log
    os.makedirs(fasc, exist_ok=True)
    uscite_arg = ",".join(f"{k}={'' if v is None else v}" for k, v in uscite.items())
    battito_file = os.path.join(fasc, f"battito-{TODAY}.json")
    try:
        pb = subprocess.run([node, "scripts/panieri-battito.mjs", "--cartella", fasc, "--giorno", f"{TODAY}", "--giro", giro,
                             "--lettori", ",".join(LETTORI_CON_GUARDIA), "--uscite", uscite_arg,
                             "--aperti", os.path.join(fasc, "anomalie-aperte.json"), "--out", battito_file],
                            cwd=repo, capture_output=True, text=True, timeout=300)
        for line in (pb.stdout or "").strip().splitlines()[-4:]:
            log_fn(f"  |panieri-battito| {line}")
        modules["panieri-battito"] = pb.returncode == 0
        if pb.returncode == 0:
            with open(battito_file) as f:
                EXTRA_METRICS["panieri"] = json.load(f)
        else:
            log_fn(f"!! panieri-battito uscita {pb.returncode}: {(pb.stderr or '').strip()[-300:]}")
        return pb.returncode
    except Exception as e:
        log_fn(f"!! panieri-battito fallito (non blocca): {e}")
        modules["panieri-battito"] = False
        return -1

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
                              "metrics": {"host": os.uname().nodename, "modules": modules, "data_date": f"{TODAY}",
                                          "delisted": DELISTED, **EXTRA_METRICS}}).encode()
        req = urllib.request.Request("https://rebalix.com/api/heartbeat", data=payload, method="POST",
                                     headers={"Authorization": f"Bearer {secret}",
                                              "Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=30) as r:
            log(f"[heartbeat] inviato ({r.status})")
    except Exception as e:
        log(f"!! [heartbeat] invio fallito (non blocca): {e}")


def moduli_documentali(modules):
    """(27 ott 2026, limitazioni del giro; rev. 4 del 28 ott) |documents| = collegamenti ai documenti con fotografia prima/dopo, collaudo
    dei documenti ricevuti e revalidate delle schede toccate; |doc-archive-prova| = PROVA con conservazione (nessuna scrittura canonica);
    |kid-objectives| = obiettivi dal KID (invariato). Salto per limitazione dichiarata (salta(nome)) sui primi due. Provabile a banco."""
    # Documenti ufficiali (prospetto+factsheet): aggancia i fondi nuovi e vigila
    # sugli schemi-URL. Gli URL emittente sono stabili e aggiornati sul posto.
    if not DRY and not salta("documents"):
        fasc = os.path.join(FASC_DOCUMENTI, YM)
        os.makedirs(fasc, exist_ok=True)
        prima = foto_colonne_documenti(os.path.join(fasc, "documents-colonne-prima.tsv"))
        if prima is None:
            log("!! documents NON eseguito (rev. 4): senza fotografia «prima» delle colonne URL le scritture non sarebbero collaudabili")
            modules["documents"] = False
            EXTRA_METRICS.setdefault("documenti", {})["documents"] = "non eseguito: fotografia prima fallita"
        else:
            dd = None
        try:
            if prima is None:
                raise StopIteration
            dd = subprocess.run([NODE, "scripts/enrich-etf-documents.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=4*3600)
            with open(os.path.join(fasc, "documents-stdout.txt"), "w") as f:
                f.write((dd.stdout or "") + "\n" + (dd.stderr or ""))  # 16 ago: il giro pieno supera i 20 min; 2 set (debutto VPS): a inizio mese l'archivio del mese è VERGINE e l'ora piena non basta (morto a metà, ripreso a mano) → 4h
            for line in (dd.stdout or "").strip().splitlines()[-2:]:
                log(f"  |documents| {line}")
            modules["documents"] = dd.returncode == 0
        except StopIteration:
            pass
        except Exception as e:
            log(f"!! documents fallito (non blocca): {e}")
            modules["documents"] = False
        if prima is not None:
            collaudo_documents(prima, fasc, modules)   # (rev. 4) scritture riconciliate, collaudo dei documenti ricevuti, revalidate

    # Archivio storico dei PDF (KID/prospetto/factsheet): gli emittenti aggiornano
    # sul posto e la versione di ieri sparisce dal mondo — noi la teniamo. Dedup
    # per hash: si salva solo ciò che è cambiato. «La storia è valore» (Linus).
    if not DRY and not salta("doc-archive"):
        # (rev. 4/4b) PROVA con conservazione in una cartella PROPRIA di questa corsa (mai riusata): nessuna scrittura nell'archivio canonico;
        # indice + PDF conservati + confronto testo/immagini, poi VALIDATI e riconciliati con la corsa (verifica_prova_archivio);
        # l'archiviazione, la lingua e il controllo per riga seguono con i lotti (indice → lotti → COMMIT da sorgenti conservate, GO)
        prova_dir = os.path.join(FASC_DOCUMENTI, YM, f"prova-archivio-{GIRO}")
        if os.path.exists(prova_dir):
            log(f"!! doc-archive-prova NON eseguita: la cartella {prova_dir} esiste già (una prova non si riusa)")
            modules["doc-archive-prova"] = False
        else:
            os.makedirs(prova_dir)
            t_lancio = datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")
            try:
                da = subprocess.run([NODE, "scripts/archive-etf-documents.mjs", "--conserva-in", prova_dir],
                                    cwd=REPO, capture_output=True, text=True, timeout=6*3600)  # 7 ago: prima passata > 3h; 2/10: ~3 h
                with open(os.path.join(prova_dir, "stdout.txt"), "w") as f:
                    f.write((da.stdout or "") + "\n" + (da.stderr or ""))
                for line in (da.stdout or "").strip().splitlines()[-2:]:
                    log(f"  |doc-archive-prova| {line}")
                ok, dett, motivi = verifica_prova_archivio(prova_dir, t_lancio)
                modules["doc-archive-prova"] = da.returncode == 0 and ok
                EXTRA_METRICS.setdefault("documenti", {})["doc_archive_prova"] = {"uscita": da.returncode, "cartella": prova_dir, "valida": ok, "motivi": motivi, **dett}
                if modules["doc-archive-prova"]:
                    log(f"  |doc-archive-prova| indice {dett['indice_righe']} righe, {dett['file_conservati']} file conservati, {dett['impronte_verificate']} impronte verificate — archivio canonico NON scritto qui")
                    lotti_automatici(prova_dir, modules)   # (rev. 5) regole → lotti → prova → verifica → COMMIT autorizzato → riscontri, revalidate, collaudo
                else:
                    log(f"!! doc-archive-prova NON valida (uscita {da.returncode}): {'; '.join(motivi[:3]) or 'nessun motivo'} — vedi {prova_dir}")
            except Exception as e:
                log(f"!! doc-archive-prova fallito (non blocca): {e}")
                modules["doc-archive-prova"] = False

    # Obiettivi dal KID (12 ago): sezione PRIIPs estratta dai PDF appena archiviati
    # (marcatori per lingua it/en/de/fr, lingua verificata dal testo, guardie di
    # lunghezza/pulizia; i curati a mano — Avantis, Flexible — non si toccano).
    if not DRY:
        try:
            ko = subprocess.run([NODE, "scripts/extract-kid-objectives.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=3600)
            for line in (ko.stdout or "").strip().splitlines()[-10:]:
                log(f"  |kid-objectives| {line}")
            modules["kid-objectives"] = ko.returncode == 0
        except Exception as e:
            log(f"!! kid-objectives fallito (non blocca): {e}")
            modules["kid-objectives"] = False


def moduli_arricchimento(modules):
    """(27 ott 2026, limitazioni del giro) i tre lettori dei documenti in archivio e gli arricchitori: il loop di main() spostato qui
    IDENTICO; (rev. 4) |doc-langs| non c'è più: la lingua dei documenti si decide nei lotti con provenienza. Chiamata da main()."""
    if not DRY:
        log("  |doc-langs| non eseguito (rev. 4): la lingua dei documenti si decide nei lotti sullo stesso originale, con provenienza (R1/R2/R2-bis)")
    # I TRE LETTORI DEI DOCUMENTI IN ARCHIVIO (18 ago 2026, caso Xeon senza TER/politica/AUM
    # trovato da Linus): il feed Xtrackers porta solo nome/indice/valuta e LGIM non dà AUM né
    # politica, quindi TER, politica di distribuzione e patrimonio si leggono dai KID e dai
    # factsheet gia' archiviati in ~/backups/rebalix-docs-archivio (senza rete per i primi
    # tre, ~390 pdftotext
    # locali). QUI, dopo tutti gli arricchimenti e PRIMA del motore, perche' il motore legge
    # ter/dp/aum. Golden a mano dentro ogni script: se un golden fallisce lo script NON scrive
    # nulla ed esce 2 -> modulo rosso e il guardiano lo segnala (comportamento voluto).
    for nome, script in (("kid-xtrackers", "enrich-kid-xtrackers.mjs"),
                         ("kid-politica", "enrich-kid-politica.mjs"),
                         ("factsheet-aum", "enrich-factsheet-aum.mjs"),
                         # 18 ago sera: anagrafica dei 58 ETP 21Shares (benchmark_raw,
                         # kid_url IT, factsheet_url). UNICO del gruppo che tocca la RETE:
                         # 58 HEAD sul CDN 21Shares, ~1 min.
                         ("21shares-anagrafica", "enrich-21shares-anagrafica.mjs"),
                         # 19 ago (fase 2 «campi», decisione Linus «prima i documenti, poi i
                         # campi»): anagrafica Xtrackers dall'API pdp it-it (lancio, domicilio,
                         # SRRI, AUM — rete: ~390 GET, ~4 min) e data di lancio 21Shares dal
                         # JSON-LD delle pagine prodotto (rete: 58 GET). Scrivono solo dove vuoto.
                         ("xtrackers-pdp", "enrich-xtrackers-pdp.mjs"),
                         ("21shares-inception", "enrich-21shares-inception.mjs"),
                         # SFDR (19 ago): dal KID/factsheet in archivio (art. 8/9 dichiarati;
                         # silenzio = art. 6 ETICHETTATO solo per Xtrackers/iShares/SPDR/LGIM,
                         # con guardia ESG-nel-nome), poi dagli allegati del prospetto-ombrello
                         # (Vanguard/UBS), infine UNA sola forma nel campo (normalizza-sfdr, che
                         # non tocca mai la provenienza). Tutti scrivono solo dove il campo e'
                         # muto: i fondi nuovi del censimento nascono gia' classificati.
                         ("sfdr-da-kid", "enrich-sfdr-da-kid.mjs"),
                         ("sfdr-da-prospetto", "enrich-sfdr-da-prospetto.mjs"),
                         ("sfdr-normalizza", "normalizza-sfdr.mjs"),
                         # 20 ago, chiusura rassegna orfani (specifica sessione Database ETF):
                         # ter-21shares = TER dai KID PRIIPs, solo-dove-vuoto (oggi 58/58 pieni:
                         # protegge gli ETP FUTURI — era il buco che il censimento azzerava,
                         # incidente 18 ago); doc-langs = colonne *_en dopo |documents|;
                         # replica-from-kid = replica di riserva dal KID, solo-dove-vuoto.
                         # NON agganciati: rating-breakdown (valutare per g.17, decisione
                         # aperta) e whitelist-tickers (fuori: ha il suo giro).
                         ("21shares-ter", "enrich-ter-21shares.mjs"),
                         # (rev. 4, 28 ott 2026) "doc-langs" RIMOSSO: enrich-doc-langs scriveva kid_lang/factsheet_lang senza provenienza
                         # dall'«ultimo file per nome»; la lingua si decide nei lotti sullo stesso originale (R1/R2/R2-bis, lib-lingua-documenti)
                         ("replica-from-kid", "enrich-replica-from-kid.mjs"),
                         # 3 set (agenda Database ETF): indice dichiarato NEL KID dove
                         # benchmark_raw e' vuoto (caso Vanguard 18 ago: fondi nuovi non
                         # ancora nel PDF pro ma gia' nel KID). Solo-dove-vuoto, mai dedotto.
                         ("benchmark-da-kid", "enrich-benchmark-da-kid.mjs")):
        if DRY or salta(nome):
            continue
        try:
            d = subprocess.run([NODE, f"scripts/{script}", "--commit"],
                               cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (d.stdout or "").strip().splitlines()[-2:]:
                log(f"  |{nome}| {line}")
            modules[nome] = d.returncode == 0
            if d.returncode != 0:
                log(f"!! {nome}: exit {d.returncode} (golden fallito? nulla scritto)")
        except Exception as e:
            log(f"!! {nome} fallito (non blocca): {e}")
            modules[nome] = False


def main():
    # stato: un solo giro per mese (RunAtLoad può svegliarci più volte)
    state = {}
    global LIMITAZIONI
    LIMITAZIONI = leggi_limitazioni(LIMITAZIONI_FILE, YM)   # (27 ott 2026) file assente = nessuna; file non valido = il giro non parte (uscita 3)
    global PREFLIGHT
    if not DRY and os.uname().nodename == HOST_VPS:   # (27 ott 2026) sulla VPS il giro parte SOLO con preflight conforme (evidenze verificate) o deroga con GO
        PREFLIGHT = verifica_preflight(PREFLIGHT_DIR, YM)
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
    USCITE_PANIERI = {}   # (ETF-20 passo 5) codice di uscita dei lettori con la guardia, per il battito dei panieri
    for m in re.finditer(r"^\s{2}(\w[\w&]*): (\d+) righe", out, re.M):
        modules[m.group(1)] = True
    for m in re.finditer(r"^\s{2}✗ (\w[\w&]*):", out, re.M):
        modules[m.group(1)] = False
    falliti = sum(1 for v in modules.values() if not v)
    ok = p.returncode == 0 and falliti == 0 and len(modules) > 0

    # ISIN marcati chiusi in questo giro (rigo nel battito, decisione Linus 15 ago
    # 2026: il delisting sotto soglia era MUTO — 17 ETC Xtrackers spenti in silenzio
    # il 13 ago; ora l'elenco arriva sempre al guardiano, che lo mette in mail)
    delisted = []
    for m in re.finditer(r"^\s{2}(\w[\w&]*): (\d+) ISIN marcati delisted_at=\S+: (.*)$", out, re.M):
        delisted.append({"issuer": m.group(1), "n": int(m.group(2)), "isin": m.group(3).strip()})
    if delisted:
        log(f"  ISIN marcati chiusi in questo giro: {sum(d['n'] for d in delisted)}")
    DELISTED.extend(delisted)

    # (18 set 2026, contratto dell'edizione) il mese NON si marca «fatto» qui, dopo il primo modulo: si marca in FONDO al
    # giro. Un giro interrotto a metà ripartirà alla sveglia successiva; i moduli sono upsert idempotenti e l'edizione dei
    # confronti riprende dal proprio stato (stessa impronta = si salta, impronta diversa = errore).
    if not DRY:
        with open(STATE, "w") as f:
            json.dump({**state, "in_corso_ym": YM, "iniziato_il": GIRO_AVVIATO_IL}, f)
    log(f"esito: exit={p.returncode}, emittenti ok={sum(1 for v in modules.values() if v)}/{len(modules)}")

    # ETC/ETP (Xtrackers da etc.dws.com, ricetta a parte: la sitemap ETF non li ha).
    # 15 ago 2026: i 17 ETC erano stati spenti dal delisting per emittente del
    # censimento ETF (segnalato da Linus su DE000A2T5DZ1) — ora il delisting è per
    # fonte e gli ETC si rileggono qui ogni giro. NON-fatale, modulo |etc|.
    if not DRY:
        try:
            e = subprocess.run([NODE, "scripts/ingest-etc.mjs", "--commit"],
                               cwd=REPO, capture_output=True, text=True, timeout=900)
            for line in ((e.stdout or "") + (e.stderr or "")).strip().splitlines()[-4:]:
                log(f"  |etc| {line}")
            modules["etc"] = e.returncode == 0
        except Exception as ex:
            log(f"!! etc fallito (non blocca): {ex}")
            modules["etc"] = False

    # Costi di transazione dai KID (trimestrale di fatto: lo script salta le righe
    # con estrazione più fresca di 80 giorni). NON-fatale: un problema qui non deve
    # oscurare il giro principale — finisce nel battito come modulo dedicato.
    if not DRY:
        try:
            # cadenza MENSILE dal 26 ago (ok Linus: «su TER e costi di transazione ogni
            # mese saremo aggiornati») — max-age 25: ogni giro rilegge TUTTI i KID
            # (~3.160, ~80-100 min → tagliola a 2h30). Il modulo ora estrae anche la
            # riga «commissioni di gestione» e ALLINEA il TER al KID quando il feed
            # anagrafico resta indietro (caso UBS Core World, aprile→agosto).
            k = subprocess.run([NODE, "scripts/enrich-kid-costs.mjs", "--commit", "--max-age", "25"],
                               cwd=REPO, capture_output=True, text=True, timeout=9000)
            for line in (k.stdout or "").strip().splitlines()[-4:]:
                log(f"  |kid| {line}")
            modules["kid-costs"] = k.returncode == 0
        except Exception as e:
            log(f"!! kid-costs fallito (non blocca): {e}")
            modules["kid-costs"] = False

    # Classificazioni per i filtri del motore (regione/settore/strategie/frequenza
    # + borse dichiarate). Ha le SUE attese interne (regione azionaria >=99%):
    # exit 1 = orfani nuovi da decidere -> modulo rosso nel battito, dati non
    # scritti a meta'. NON-fatale per il giro.
    if not DRY:
        try:
            c = subprocess.run([NODE, "scripts/enrich-etf-classificazione.mjs", "--commit"],
                               cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (c.stdout or "").strip().splitlines()[-4:]:
                log(f"  |classif| {line}")
            modules["classificazione"] = c.returncode == 0
        except Exception as e:
            log(f"!! classificazione fallita (non blocca): {e}")
            modules["classificazione"] = False

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

    # SERIE INDICE dove il file emittente non la porta o la ferma (17 ago 2026, rilievo
    # Linus IE00BDBRDM35): iShares dalla pagina prodotto (it→de→ch), Invesco per classe
    # da performance/rolling. Scrivono solo i buchi (bench assente o fermo > 60 gg),
    # golden interni; NON fatali, moduli |bench-ishares| e |bench-invesco| nel battito.
    if not DRY:
        for nome, script, tetto in (("bench-ishares", "scripts/ingest-etf-bench-ishares-pagina.mjs", 5400),
                                    ("bench-invesco", "scripts/ingest-etf-bench-invesco-pagina.mjs", 2400)):
            try:
                bx = subprocess.run([NODE, script, "--commit"], cwd=REPO, capture_output=True, text=True, timeout=tetto)
                for line in ((bx.stdout or "") + (bx.stderr or "")).strip().splitlines()[-3:]:
                    log(f"  |{nome}| {line}")
                modules[nome] = bx.returncode == 0
            except Exception as e:
                log(f"!! {nome} fallito (non blocca): {e}")
                modules[nome] = False

    # Frequenza di distribuzione (dichiarata Vanguard + contata dagli archivi
    # serie iShares/UBS appena aggiornati). Non sovrascrive mai il dichiarato.
    if not DRY:
        try:
            fq = subprocess.run([NODE, "scripts/enrich-dist-frequency.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (fq.stdout or "").strip().splitlines()[-2:]:
                log(f"  |distfreq| {line}")
            modules["dist-frequency"] = fq.returncode == 0
        except Exception as e:
            log(f"!! dist-frequency fallita (non blocca): {e}")
            modules["dist-frequency"] = False

    # Prestito titoli dai KID (frase dichiarata; salta le righe gia' valorizzate,
    # quindi a regime tocca solo i fondi nuovi). Golden UBS interno.
    if not DRY:
        try:
            sl = subprocess.run([NODE, "scripts/enrich-securities-lending.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=4*3600)
            for line in (sl.stdout or "").strip().splitlines()[-2:]:
                log(f"  |lending| {line}")
            modules["sec-lending"] = sl.returncode == 0
        except Exception as e:
            log(f"!! sec-lending fallito (non blocca): {e}")
            modules["sec-lending"] = False

    # Indicatore di rischio KID (SRI 1-7, dichiarato). Salta i gia' valorizzati.
    if not DRY:
        try:
            kr = subprocess.run([NODE, "scripts/enrich-kid-risk.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=4*3600)
            for line in (kr.stdout or "").strip().splitlines()[-2:]:
                log(f"  |kidrisk| {line}")
            modules["kid-risk"] = kr.returncode == 0
        except Exception as e:
            log(f"!! kid-risk fallito (non blocca): {e}")
            modules["kid-risk"] = False

    # Borse DICHIARATE dagli emittenti (tabelle listini vere: pagine iShares,
    # API Amundi, raw UBS). Giro PIENO ogni mese: coglie borse aggiunte/ritirate.
    # Modulo nato dalla bonifica 7 ago (il vecchio criterio dentro |classif|
    # corruppe 752 righe). Golden interni MDAX/CSPX dentro lo script.
    if not DRY:
        try:
            dl = subprocess.run([NODE, "scripts/enrich-declared-listings.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=2*3600)
            for line in (dl.stdout or "").strip().splitlines()[-3:]:
                log(f"  |declared| {line}")
            modules["declared-listings"] = dl.returncode == 0
        except Exception as e:
            log(f"!! declared-listings fallito (non blocca): {e}")
            modules["declared-listings"] = False

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

    # MODELLO fondo→classe→listing (12 set 2026, Fase 1/2/2b): dopo registro e ticker, le classi
    # NUOVE ricevono fund_id (build-etf-fund, golden), le sedi le linee dichiarate dagli emittenti
    # (enrich-listings-emittente: il listino della borsa vince sempre) e la tabella delle linee si
    # rinfresca (build-listing-lines, golden). Idempotenti, NON bloccano: modulo proprio ciascuno.
    if not DRY:
        for nome, script, tetto in (("fondo", "scripts/build-etf-fund.mjs", 1200),
                                    ("listing-emittente", "scripts/enrich-listings-emittente.mjs", 1800),
                                    ("linee", "scripts/build-listing-lines.mjs", 900),
                                    # (13 set 2026, cantiere con l'auditor, doc §5.4) il ticker della white list come regola:
                                    # riempie ticker/tickers_by_mic SOLO dove null (eredita' dall'ISIN + etf_listings), mai rete;
                                    # va lanciato anche a mano subito dopo ogni ingest semestrale. Nel battito dopo il 1o giro verde (2/10).
                                    ("whitelist-ticker", "scripts/enrich-whitelist-ticker-interno.mjs", 900)):
            try:
                m = subprocess.run([NODE, script, "--commit"], cwd=REPO, capture_output=True, text=True, timeout=tetto)
                for line in ((m.stdout or "") + (m.stderr or "")).strip().splitlines()[-2:]:
                    log(f"  |{nome}| {line}")
                modules[nome] = m.returncode == 0
            except Exception as e:
                log(f"!! {nome} fallito (non blocca): {e}")
                modules[nome] = False

    moduli_documentali(modules)   # (27 ott 2026) documents · doc-archive · kid-objectives, con le limitazioni dichiarate

    # Gestione attiva/passiva + replica di riserva (17 ago 2026, Lavoro A del brief
    # guardiano): emittente -> KID (obiettivi appena estratti) -> Xetra, solo dichiarato.
    # Golden 10+4 dentro lo script (exit 1 = non scrive); exit 2 = sentinella
    # «Active nel nome senza fonte» (attesa, es. JPM IE000H0H26Q8): NON e' un guasto,
    # l'elenco resta nel log. Va PRIMA del motore, che legge management/replication_fallback.
    if not DRY:
        try:
            gs = subprocess.run([NODE, "scripts/enrich-etf-gestione.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (gs.stdout or "").strip().splitlines()[-8:]:
                log(f"  |gestione| {line}")
            modules["gestione"] = gs.returncode in (0, 2)
        except Exception as e:
            log(f"!! gestione fallito (non blocca): {e}")
            modules["gestione"] = False

    # Metriche obbligazionarie DICHIARATE (17 ago 2026, decisione Linus): duration
    # (col tipo dell'emittente), ripartizione per rating e per scadenza — dai
    # factsheet appena archiviati (Vanguard/SPDR/JPM/LGIM/UBS/Amundi) e dalle pagine
    # prodotto (iShares UK, DWS via Chromium headless). Golden 8 dentro lo script
    # (exit 1 = non scrive). Chi non ha il dato conserva il valore precedente.
    # Va PRIMA del motore (che potra' leggerne il filtro duration).
    if not DRY:
        try:
            bm = subprocess.run([NODE, "scripts/enrich-bond-metrics.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=3600)
            for line in (bm.stdout or "").strip().splitlines()[-14:]:
                log(f"  |bond-metrics| {line}")
            modules["bond-metrics"] = bm.returncode == 0
        except Exception as e:
            log(f"!! bond-metrics fallito (non blocca): {e}")
            modules["bond-metrics"] = False

    # Eredita' duration/rating/scadenze dalle classi SORELLE (20 ago 2026): proprieta'
    # del portafoglio, identico tra classi dello stesso fondo (principio della gestione).
    # Solo-dove-vuoto, concordanza ±0,2 anni tra sorelle, eredita' in raw.bondMetricsSorella.
    # Va DOPO bond-metrics (eredita cio' che il giro ha appena letto dai factsheet).
    if not DRY:
        try:
            bs = subprocess.run([NODE, "scripts/enrich-bond-metrics-sorelle.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=1200)
            for line in (bs.stdout or "").strip().splitlines()[-4:]:
                log(f"  |bond-metrics-sorelle| {line}")
            modules["bond-metrics-sorelle"] = bs.returncode == 0
        except Exception as e:
            log(f"!! bond-metrics-sorelle fallito (non blocca): {e}")
            modules["bond-metrics-sorelle"] = False

    # Tracking difference 12 mesi (dalle serie appena aggiornate): fondo vs indice
    # col metodo dei rapporti, solo dove onesta (TR o classi acc). Golden DAX/C3M/
    # CSPX dentro lo script; rete di sanita' |TD|>3% = scarto, mai numeri falsi.
    if not DRY:
        try:
            td = subprocess.run([NODE, "scripts/enrich-tracking-difference.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=3600)
            for line in (td.stdout or "").strip().splitlines()[-3:]:
                log(f"  |td| {line}")
            modules["tracking-difference"] = td.returncode == 0
        except Exception as e:
            log(f"!! tracking-difference fallita (non blocca): {e}")
            modules["tracking-difference"] = False

    # TD DICHIARATA dall'emittente — SPDR dalla pagina prodotto (17 ago 2026): fondo/indice
    # per anno + cumulati month-end -> etf_registry.td_dichiarata + td_1y. Golden SPY5. NON fatale.
    # ⚠️ RIPOSIZIONATO 21 ago (verdetto prova generale): era stato incollato DOPO la chiamata
    # a main(), dove nei giri veri non veniva MAI eseguito (main esce con sys.exit) e nei giri
    # saltati crashava con NameError su `modules` (variabile locale di main). Ora sta qui,
    # con gli altri arricchitori, prima del motore che legge i campi che scrive.
    if not DRY:
        try:
            ts = subprocess.run([NODE, "scripts/enrich-td-spdr.mjs", "--commit"], cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in ((ts.stdout or "") + (ts.stderr or "")).strip().splitlines()[-2:]:
                log(f"  |td-spdr| {line}")
            modules["td-spdr"] = ts.returncode == 0
        except Exception as e:
            log(f"!! td-spdr fallito (non blocca): {e}")
            modules["td-spdr"] = False

    moduli_arricchimento(modules)   # (27 ott 2026) lettori dei documenti in archivio e arricchitori, doc-langs limitabile

    # ULTIMO: ricostruisce le righe pronte del motore /cerca-etf (etf_search_rows)
    # da tutte le fonti appena aggiornate. Golden interni (Xeon, CSPX, numerosita')
    # dentro lo script: se violati esce 1 e il guardiano lo segnala.
    if not DRY:
        try:
            mt = subprocess.run([NODE, "scripts/build-motore-dataset.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=3600)
            for line in (mt.stdout or "").strip().splitlines()[-2:]:
                log(f"  |motore| {line}")
            modules["motore"] = mt.returncode == 0
        except Exception as e:
            log(f"!! motore fallito (non blocca): {e}")
            modules["motore"] = False

    # GUARDIANO DI COMPLETEZZA delle schede (18 ago 2026): tabella emittente×campo dei
    # buchi, soglia 2%, exit 2 se ci sono righe rosse. Sta QUI e non nel giro serale
    # perche' la completezza dipende da censimento+arricchimenti (che girano qui), non
    # dalle serie NAV quotidiane: nel daily avrebbe mandato un allarme ROSSO OGNI GIORNO
    # con gli stessi buchi noti. Batte `etf-completezza` con ok=false e errors_count=N
    # righe rosse: nel guardiano e' dichiarato 🟡 «da sapere» (digest del lunedi'),
    # perche' i buchi sono un PIANO DI LAVORO, non un guasto da correre a curare.
    if not DRY:
        try:
            cp = subprocess.run([NODE, "scripts/audit-completezza-schede.mjs"],
                                cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (cp.stdout or "").strip().splitlines()[-3:]:
                log(f"  |completezza| {line}")
            modules["completezza"] = cp.returncode in (0, 2)  # 2 = righe rosse: atteso, non guasto del modulo
        except Exception as e:
            log(f"!! completezza fallita (non blocca): {e}")
            modules["completezza"] = False

    # Metal detector delle serie (Linus, 9 ago): audit post-ingest con la
    # pipeline di lettura completa (cure da lib/serie-riparazioni.json).
    # exit 2 = anomalie DURE nuove -> modulo rosso, il guardiano abbaia;
    # le osservazioni morbide restano solo a verbale qui nel log.
    if not DRY:
        try:
            au = subprocess.run([NODE, "scripts/audit-serie-anomalie.mjs"],
                                cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (au.stdout or "").strip().splitlines():
                log(f"  |audit| {line}")
            modules["audit"] = au.returncode == 0
            if au.returncode != 0:
                log("!! AUDIT: anomalie DURE nelle serie appena ingerite - vedi righe |audit| sopra")
        except Exception as e:
            log(f"!! audit fallito (non blocca): {e}")
            modules["audit"] = False

    # Censimento tick sporchi nei BENCHMARK (10 ago, caso SGLN): il despike a
    # lettura li cura da solo, questo e' il termometro — exit 2 = esplosione
    # rispetto alla baseline (24 fondi) -> modulo rosso, guardiano.
    if not DRY:
        try:
            ab = subprocess.run([NODE, "scripts/audit-bench-spikes.mjs"],
                                cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (ab.stdout or "").strip().splitlines()[-6:]:
                log(f"  |audit-bench| {line}")
            modules["audit-bench"] = ab.returncode == 0
            if ab.returncode != 0:
                log("!! AUDIT-BENCH: esplosione di tick sporchi nei benchmark - vedi righe sopra")
        except Exception as e:
            log(f"!! audit-bench fallito (non blocca): {e}")
            modules["audit-bench"] = False

    # Composizioni Xtrackers (Fase B, 10 ago): export constituent DWS per ISIN
    # -> etf_holdings (posizioni+settori+paesi). La scheda gestisce i sintetici
    # (paniere sostitutivo, niente mappa). Rifacimento mensile completo.
    if not DRY:
        try:
            hx = subprocess.run([NODE, "scripts/ingest-etf-holdings-xtrackers.mjs", "--commit", "--raw-dir", RAW_DIR],
                                cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (hx.stdout or "").strip().splitlines()[-3:]:
                log(f"  |holdings-xtrackers| {line}")
            modules["holdings-xtrackers"] = hx.returncode == 0
            if hx.returncode != 0:
                log("!! HOLDINGS XTRACKERS: troppi falliti - vedi righe sopra")
        except Exception as e:
            log(f"!! holdings-xtrackers fallito (non blocca): {e}")
            modules["holdings-xtrackers"] = False

    # Composizioni SPDR (Fase B/2, 10 ago): holdings-daily ufficiale per slug
    # con verifica ISIN-nel-file (impossibile ingerire il fondo sbagliato).
    if not DRY:
        try:
            hs = subprocess.run([NODE, "scripts/ingest-etf-holdings-spdr.mjs", "--commit", "--raw-dir", RAW_DIR],
                                cwd=REPO, capture_output=True, text=True, timeout=2400)
            for line in (hs.stdout or "").strip().splitlines()[-3:]:
                log(f"  |holdings-spdr| {line}")
            modules["holdings-spdr"] = hs.returncode == 0
            if hs.returncode != 0:
                log("!! HOLDINGS SPDR: raccolto a zero - vedi righe sopra")
        except Exception as e:
            log(f"!! holdings-spdr fallito (non blocca): {e}")
            modules["holdings-spdr"] = False

    # Composizioni Avantis (emittente n.10, 10 ago): __data.json del sito
    if not DRY:
        try:
            ha = subprocess.run([NODE, "scripts/ingest-etf-holdings-avantis.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (ha.stdout or "").strip().splitlines():
                log(f"  |holdings-avantis| {line}")
            modules["holdings-avantis"] = ha.returncode == 0
        except Exception as e:
            log(f"!! holdings-avantis fallito (non blocca): {e}")
            modules["holdings-avantis"] = False

    # Composizioni Invesco (emittente n.11, 14 ago): holdings/fund via Chromium
    # headless (WAF anti-bot, lib-invesco-fetch) — timeout largo: ~290 fondi.
    if not DRY:
        try:
            hi = subprocess.run([NODE, "scripts/ingest-etf-holdings-invesco.mjs", "--commit", "--raw-dir", RAW_DIR],
                                cwd=REPO, capture_output=True, text=True, timeout=3600)
            for line in (hi.stdout or "").strip().splitlines()[-3:]:
                log(f"  |holdings-invesco| {line}")
            modules["holdings-invesco"] = hi.returncode == 0
        except Exception as e:
            log(f"!! holdings-invesco fallito (non blocca): {e}")
            modules["holdings-invesco"] = False

    # Audit di COPERTURA arricchimenti × emittente (15 ago, rilievo Linus): un
    # emittente a 0% dove gli altri stanno alti = modulo mai lanciato → rosso.
    if not DRY:
        try:
            ac = subprocess.run([NODE, "scripts/audit-copertura-emittenti.mjs"],
                                cwd=REPO, capture_output=True, text=True, timeout=600)
            for line in (ac.stdout or "").strip().splitlines()[-6:]:
                log(f"  |copertura| {line}")
            modules["copertura"] = ac.returncode == 0
        except Exception as e:
            log(f"!! copertura fallito (non blocca): {e}")
            modules["copertura"] = False

    # AUM/TER di classe da Xetra dove mancano (15 ago): Xtrackers e chiunque
    # quoti a Francoforte senza dato — fonte borsa, header firmati, golden TER.
    if not DRY:
        try:
            xe = subprocess.run([NODE, "scripts/enrich-etf-xetra.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (xe.stdout or "").strip().splitlines()[-3:]:
                log(f"  |xetra| {line}")
            modules["xetra"] = xe.returncode == 0
        except Exception as e:
            log(f"!! xetra fallito (non blocca): {e}")
            modules["xetra"] = False

    # Composizioni iShares dal componente `holdings` dell'API (18 set 2026, Linus «un writer, un ritmo»): UNICO writer
    # delle composizioni iShares — il file fundDownload del modulo |series| alimenta solo serie e benchmark (regola in
    # scripts/lib-composizioni-writer.mjs). Fotografia ancorata alla FINE DEL MESE PRECEDENTE (target = ultimo giorno;
    # ripiego dichiarato all'indietro ≤ 5 giorni; oltre, nessuna scrittura e DATA_NON_DISPONIBILE esplicito); i 9 Portfolio
    # (fondi di fondi) non si scrivono per regola. L'esito per OGNI fondo va in --out: l'edizione (più sotto) lo legge come
    # DICHIARAZIONI (NON_CONFRONTABILE:FONDO_DI_FONDI / DATA_NON_DISPONIBILE). Prova a vuoto del 18/9 sui 910: 37 min, 171 MB.
    MESE_PRECEDENTE = (TODAY.replace(day=1) - datetime.timedelta(days=1)).strftime("%Y-%m")
    ISHARES_RC = None   # exit del lettore: None = mai terminato (eccezione/timeout) → il gate dell'edizione lo tratta come morto
    ISHARES_ESITI = os.path.join(os.path.expanduser("~/backups/rebalix-edizioni"), YM, "acquisizione", "ishares-api.json")
    if not DRY:
        try:
            os.makedirs(os.path.dirname(ISHARES_ESITI), exist_ok=True)
            hh_is = subprocess.run([NODE, "scripts/ingest-etf-holdings-ishares-api.mjs", "--min-pos", "0", "--mese", MESE_PRECEDENTE,
                                    "--raw-dir", RAW_DIR, "--out", ISHARES_ESITI, "--commit"],
                                   cwd=REPO, capture_output=True, text=True, timeout=3*3600)
            for line in (hh_is.stdout or "").strip().splitlines()[-9:]:
                log(f"  |holdings-ishares| {line}")
            modules["holdings-ishares"] = hh_is.returncode == 0
            ISHARES_RC = hh_is.returncode
        except Exception as e:
            log(f"!! holdings-ishares fallito (non blocca il giro; blocca l'EDIZIONE: gate di acquisizione): {e}")
            modules["holdings-ishares"] = False

    # Composizioni Vanguard (Fase B/3, notte 10-11 ago): GraphQL gpx ufficiale
    # (borHoldings paginato + marketAllocation + sectorDiversification).
    if not DRY:
        try:
            hv = subprocess.run([NODE, "scripts/ingest-etf-holdings-vanguard.mjs", "--commit", "--raw-dir", RAW_DIR],
                                cwd=REPO, capture_output=True, text=True, timeout=2400)
            for line in (hv.stdout or "").strip().splitlines()[-2:]:
                log(f"  |holdings-vanguard| {line}")
            modules["holdings-vanguard"] = hv.returncode == 0
            if hv.returncode != 0:
                log("!! HOLDINGS VANGUARD: troppi falliti - vedi righe sopra")
        except Exception as e:
            log(f"!! holdings-vanguard fallito (non blocca): {e}")
            modules["holdings-vanguard"] = False

    # Composizioni dai FACTSHEET ARCHIVIATI (fabbrica dei factsheet, notte
    # 10-11 ago): JPM, LGIM, UBS, Amundi. Nessun download: si rilegge l'ultimo
    # PDF in ~/backups/rebalix-docs-archivio (che il giro-documenti rinfresca).
    # exit 2 dei parser = piu' falliti che ok -> modulo rosso.
    # 16 ago: JPM passa alla fonte emittente COMPLETA (product-data dailyHoldingsAll,
    # tutte le posizioni, giornaliero) — il factsheet resta solo per LGIM/UBS/Amundi.
    # 3 set (agenda Database ETF, dopo la notte del 22-23 ago che porto' la copertura
    # al 98,3%): anche Amundi/LGIM/UBS passano alle fonti-API a LISTA COMPLETA
    # (Amundi getProductsData+composition, LGIM CSV Fundholdings, UBS getConstituentsExcel
    # GraphQL); il factsheet resta RIPIEGO se l'API esce male — mai perdere il raccolto
    # del mese. Franklin (emittente n.15, 28 ago) entra col suo dailyholdings GraphQL.
    if not DRY:
        for emittente, primario, ripiego in (
                ("jpm", "scripts/ingest-etf-holdings-jpm.mjs", None),
                ("lgim", "scripts/ingest-etf-holdings-lgim-api.mjs", "scripts/ingest-etf-holdings-lgim-factsheet.mjs"),
                ("ubs", "scripts/ingest-etf-holdings-ubs-api.mjs", "scripts/ingest-etf-holdings-ubs-factsheet.mjs"),
                ("amundi", "scripts/ingest-etf-holdings-amundi-api.mjs", "scripts/ingest-etf-holdings-amundi-factsheet.mjs"),
                ("franklin", "scripts/ingest-etf-holdings-franklin.mjs", None)):
            try:
                # (ETF-20 passo 5) lettori con la guardia: rifiuti visibili per ISIN, rapporto del giro e identificativo dell'esecuzione
                hf = subprocess.run(argomenti_lettore(emittente, primario),
                                    cwd=REPO, capture_output=True, text=True, timeout=3600)
                if emittente in LETTORI_CON_GUARDIA:
                    USCITE_PANIERI[emittente] = hf.returncode
                for line in (hf.stdout or "").strip().splitlines()[-2:]:
                    log(f"  |holdings-{emittente}| {line}")
                if hf.returncode != 0 and ripiego:
                    log(f"!! holdings-{emittente}: fonte API exit {hf.returncode} — ripiego sul factsheet")
                    hf = subprocess.run([NODE, ripiego, "--commit"],
                                        cwd=REPO, capture_output=True, text=True, timeout=2400)
                    for line in (hf.stdout or "").strip().splitlines()[-2:]:
                        log(f"  |holdings-{emittente}| (ripiego) {line}")
                modules[f"holdings-{emittente}"] = hf.returncode == 0
                if hf.returncode != 0:
                    log(f"!! HOLDINGS {emittente.upper()}: troppi falliti - vedi righe sopra")
            except Exception as e:
                log(f"!! holdings-{emittente} fallito (non blocca): {e}")
                modules[f"holdings-{emittente}"] = False
                if emittente in LETTORI_CON_GUARDIA:
                    USCITE_PANIERI[emittente] = None   # non lanciato / eccezione: il battito lo dirà «rapporto mancante»

    # (ETF-20 passo 5, 27 ott 2026) BATTITO DEI PANIERI: rapporti riconciliabili + rifiuti verificati + anomalie aperte, legati a GIRO
    if not DRY:
        battito_panieri(modules, USCITE_PANIERI)

    # Composizioni Melanion (emittente n.16, 6 ott 2026 — GO Linus, 3 audit muti):
    # CSV quotidiano dichiarato dalla scheda, 5 GET con pausa 10,5 s (Crawl-delay del
    # robots della fonte), grezzi conservati in ~/backups/rebalix-raw-archivio. ~1 min.
    if not DRY:
        try:
            hm = subprocess.run([NODE, "scripts/ingest-etf-holdings-melanion.mjs",
                                 "--raw-dir", os.path.expanduser("~/backups/rebalix-raw-archivio"), "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=900)
            for line in ((hm.stdout or "") + (hm.stderr or "")).strip().splitlines()[-2:]:
                log(f"  |holdings-melanion| {line}")
            modules["holdings-melanion"] = hm.returncode == 0
        except Exception as e:
            log(f"!! holdings-melanion fallito (non blocca): {e}")
            modules["holdings-melanion"] = False

    # DIVIDENDI (industrializzazione 11 ago sera): storico cedole in
    # etf_distributions. Vanguard via gpx (distributionDetails), iShares dal
    # foglio Distributions del fundDownload (stesso file delle serie).
    # Tabella append-only: l'upsert aggiunge le cedole nuove, mai perdite.
    if not DRY:
        for emittente, script in (("vanguard", "scripts/ingest-etf-distributions-vanguard.mjs"),
                                  ("ishares", "scripts/ingest-etf-distributions-ishares.mjs"),
                                  ("spdr", "scripts/ingest-etf-distributions-spdr.mjs"),
                                  ("xtrackers", "scripts/ingest-etf-distributions-xtrackers.mjs"),
                                  ("amundi", "scripts/ingest-etf-distributions-amundi.mjs"),   # API emittente dividendAmount (15 ago)
                                  ("ubs", "scripts/ingest-etf-distributions-ubs.mjs"),         # nav-details gia archiviato (15 ago)
                                  ("jpm", "scripts/ingest-etf-distributions-jpm.mjs"),         # historicalData?cusip=ISIN, aperto (16 ago)
                                  ("franklin", "scripts/ingest-etf-distributions-franklin.mjs"),  # GraphQL DistributionHistory: ex+record+pay dall'emittente (28 ago, agganciato 3 set)
                                  ("lgim", "scripts/ingest-etf-distributions-lgim.mjs"),  # Dividend Calendar XLSX del fund centre (lit 1131): log cumulativo di gamma dal 2014, golden ±1% (4 set; il lettore Borsa Italiana e DECLASSATO a sentinella: mai piu fonte scritta)
                                  ("invesco", "scripts/ingest-etf-distributions-invesco.mjs")):  # storico dedotto NAV vs Adjusted NAV + buchi BI (16 ago), golden AT1 CoCo
            try:
                dv = subprocess.run([NODE, script, "--commit"],
                                    cwd=REPO, capture_output=True, text=True, timeout=3600)
                for line in (dv.stdout or "").strip().splitlines()[-2:]:
                    log(f"  |dividendi-{emittente}| {line}")
                modules[f"dividendi-{emittente}"] = dv.returncode == 0
                if dv.returncode != 0:
                    log(f"!! DIVIDENDI {emittente.upper()}: troppi falliti - vedi righe sopra")
            except Exception as e:
                log(f"!! dividendi-{emittente} fallito (non blocca): {e}")
                modules[f"dividendi-{emittente}"] = False

    # DATE delle cedole Invesco dallo storico XLSX ufficiale (23 ago, trovato da Linus:
    # «Export data» sulla pagina prodotto): riempie record/pay dove vuoti e aggiunge
    # stacchi mancanti (fonte emittente, vince su nav-adjusted). Chromium headless (WAF):
    # sta QUI, mensile e da solo — mai due Chromium in parallelo sulla VPS. NON fatale.
    if not DRY:
        try:
            di = subprocess.run([NODE, "scripts/enrich-distributions-date-invesco.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=3600)
            for line in (di.stdout or "").strip().splitlines()[-2:]:
                log(f"  |dividendi-date-invesco| {line}")
            modules["dividendi-date-invesco"] = di.returncode == 0
        except Exception as e:
            log(f"!! dividendi-date-invesco fallito (non blocca): {e}")
            modules["dividendi-date-invesco"] = False

    # DURATION Invesco dall'API dell'emittente (4 set 2026, regola Linus: API -> factsheet ->
    # pagina -> NULL, nessuna stima): characteristics.effectiveDuration, giornaliera, kind
    # effettiva. Chromium (WAF): qui, mensile, da solo, DOPO le date Invesco. NON fatale.
    if not DRY:
        try:
            dm = subprocess.run([NODE, "scripts/enrich-bond-metrics-invesco-api.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (dm.stdout or "").strip().splitlines()[-2:]:
                log(f"  |bond-metrics-invesco-api| {line}")
            modules["bond-metrics-invesco-api"] = dm.returncode == 0
        except Exception as e:
            log(f"!! bond-metrics-invesco-api fallito (non blocca): {e}")
            modules["bond-metrics-invesco-api"] = False

    # MODIFIED DURATION UBS dalla pagina prodotto (HA4 getAmrFundAttributes, 4 set 2026): plain
    # fetch con token pubblico, niente Chromium. Colma le classi il cui factsheet IT ha solo il
    # glossario; un «0» senza data non si scrive. NON fatale.
    if not DRY:
        try:
            du = subprocess.run([NODE, "scripts/enrich-bond-metrics-ubs-api.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (du.stdout or "").strip().splitlines()[-2:]:
                log(f"  |bond-metrics-ubs-api| {line}")
            modules["bond-metrics-ubs-api"] = du.returncode == 0
        except Exception as e:
            log(f"!! bond-metrics-ubs-api fallito (non blocca): {e}")
            modules["bond-metrics-ubs-api"] = False

    # FOTO MENSILE composizioni -> etf_holdings_history (10 ago): DOPO i raccolti
    # holdings, cosi' la foto e' del mese fresco. Idempotente: rilanci nello
    # stesso mese completano i buchi. exit 2 = foto incompleta -> guardiano.
    if not DRY:
        try:
            hh = subprocess.run([NODE, "scripts/snapshot-etf-holdings.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=1800)
            for line in (hh.stdout or "").strip().splitlines():
                log(f"  |holdings-history| {line}")
            modules["holdings-history"] = hh.returncode == 0
            if hh.returncode != 0:
                log("!! HOLDINGS-HISTORY: foto mensile incompleta o fallita")
        except Exception as e:
            log(f"!! holdings-history fallito (non blocca): {e}")
            modules["holdings-history"] = False
        # email a Linus quando esiste la SECONDA foto (17 ago 2026): anteprima «Cosa è
        # cambiato» pronta da guardare prima di accendere HOLDINGS_CHANGES_LIVE. Non fatale.
        try:
            na = subprocess.run([NODE, "scripts/notifica-anteprima-cambi.mjs"], cwd=REPO, capture_output=True, text=True, timeout=300)
            for line in ((na.stdout or "") + (na.stderr or "")).strip().splitlines()[-2:]:
                log(f"  |anteprima-cambi| {line}")
        except Exception as e:
            log(f"!! anteprima-cambi (non blocca): {e}")

    # EDIZIONE MENSILE DEI CONFRONTI (contratto runner ↔ baseline ↔ motore, Linus 18 set 2026; sostituisce il diff
    # «ultima foto per glob vs --dopo db» del 3 set). Il runner decide QUALE coppia: la baseline ASSEGNATA a questo mese
    # (~/backups/rebalix-baseline/<YM>/: manifest + file + atto, per impronta) e la «dopo» esportata ADESSO dal DB appena
    # raccolto e congelata su disco con impronta e provenienza PRIMA del confronto. Il motore decide SE ogni coppia è
    # confrontabile e scrive un esito per OGNI fondo. Stato esplicito PREPARING→FROZEN→COMPARED→COMPLETE in
    # ~/backups/rebalix-edizioni/<YM>/stato.json: un rilancio riprende dal primo passo mancante, mai riscrive.
    # In fondo, «completa» congela la baseline del mese prossimo (= la «dopo» di oggi, manifest ORIGINAL_ACQUIRED_IN_RUN).
    # Solo sulla VPS (dove esistono baseline e semaforo): il gemello Mac salta senza rosso.
    BASELINE_DIR = os.path.expanduser("~/backups/rebalix-baseline")
    EDIZIONI_DIR = os.path.expanduser("~/backups/rebalix-edizioni")
    EDIZIONE_RICHIESTA = os.uname().nodename == HOST_VPS   # sulla VPS l'edizione è obbligatoria: senza baseline assegnata non esiste un giro valido
    edizione_stato, edizione_errore = None, None
    if not DRY and EDIZIONE_RICHIESTA and not os.path.isdir(os.path.join(BASELINE_DIR, YM)):
        edizione_errore = f"nessuna baseline assegnata a {YM} in {BASELINE_DIR}: l'edizione non può esistere (il motore non cerca alternative)"
        log(f"!! EDIZIONE {YM} BLOCCATA: {edizione_errore}")
        modules["edizione"] = False
    if not DRY and os.path.isdir(os.path.join(BASELINE_DIR, YM)):
        ed_dir = os.path.join(EDIZIONI_DIR, YM)
        esport = os.path.join(ed_dir, "esportazione")
        os.makedirs(esport, exist_ok=True)
        f_dopo, f_acq = os.path.join(esport, "foto-dopo.tsv.gz"), os.path.join(esport, "acquisizione.json")
        env_ed = dict(os.environ, REBALIX_ARCHIVIATORE_MD5=ARCHIVIATORE_MD5, REBALIX_GIRO_AVVIATO_IL=GIRO_AVVIATO_IL,
                      REBALIX_MODULI=json.dumps(modules))

        def passo_edizione(nome, cmd, tetto=3600):
            r = subprocess.run(cmd, cwd=REPO, capture_output=True, text=True, timeout=tetto, env=env_ed)
            for line in ((r.stdout or "") + (r.stderr or "")).strip().splitlines()[-8:]:
                log(f"  |edizione:{nome}| {line}")
            if r.returncode != 0:
                raise RuntimeError(f"{nome} → exit {r.returncode}")

        def stato_edizione():
            try:
                return json.load(open(os.path.join(ed_dir, "stato.json")))
            except Exception:
                return None

        # GATE DI ACQUISIZIONE: i writer previsti dall'edizione (oggi: iShares API, unico writer delle composizioni iShares)
        # devono aver terminato e dichiarato l'esito di TUTTO il loro perimetro; altrimenti l'edizione resta in HOLD, il mese
        # non si marca «fatto» e il prossimo lancio riprende (Linus 18/9: «un reader crashato è diverso da un reader che
        # termina dicendo “questi 8 fondi non hanno una fotografia disponibile”»).
        acquisizioni = {"holdings-ishares": (ISHARES_RC if ISHARES_RC is not None else -1, ISHARES_ESITI)}
        edizione_stato, edizione_errore = edizione_mensile(YM, acquisizioni, passo_edizione, stato_edizione, ed_dir, f_dopo, f_acq, NODE, log)
        modules["edizione"] = edizione_stato == "COMPLETE" and edizione_errore is None
        if edizione_errore:
            log(f"!! EDIZIONE {YM} {'BLOCCATA' if edizione_stato is None else 'interrotta allo stato ' + str(edizione_stato)} (il resto del giro prosegue; il mese NON sarà marcato «fatto»: riprende al prossimo lancio): {edizione_errore}")
    elif not DRY and not EDIZIONE_RICHIESTA:
        log(f"  |edizione| nessuna baseline assegnata a {YM} in {BASELINE_DIR}: edizione saltata (atteso fuori dalla VPS)")

    # CASSAFORTE delle foto complete (21 ago / 16 set: «conserviamo tutto», nessuna rotazione). Resta com'è: dopo il
    # contratto dell'edizione non è più letta da nessun confronto (la «dopo» congelata vive nell'edizione).
    FOTO_SH = os.path.expanduser("~/backups/rebalix-cron/foto-panieri.sh")
    if not DRY and os.path.exists(FOTO_SH):
        try:
            fp = subprocess.run(["/bin/bash", FOTO_SH], capture_output=True, text=True, timeout=1800)
            for line in ((fp.stdout or "") + (fp.stderr or "")).strip().splitlines()[-3:]:
                log(f"  |foto-panieri| {line}")
            modules["foto-panieri"] = fp.returncode == 0
        except Exception as e:
            log(f"!! foto-panieri fallita (non blocca): {e}")
            modules["foto-panieri"] = False

    # CRONOLOGIA MENSILE dei panieri (23 ago, decisione Linus «partire subito»): una
    # riga per isin×mese in etf_holdings_mensile + revalidate on-demand delle schede a
    # fine corsa — per quello il figlio deve avere CRON_SECRET nell'ambiente.
    if not DRY:
        try:
            envx = dict(os.environ)
            with open(os.path.join(REPO, ".env.local")) as f:
                for line in f:
                    if line.startswith("CRON_SECRET="):
                        envx["CRON_SECRET"] = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break
            rp = subprocess.run([NODE, "scripts/riepilogo-panieri-mensile.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=1800, env=envx)
            for line in (rp.stdout or "").strip().splitlines()[-3:]:
                log(f"  |riepilogo-panieri| {line}")
            modules["riepilogo-panieri"] = rp.returncode == 0
        except Exception as e:
            log(f"!! riepilogo-panieri fallito (non blocca): {e}")
            modules["riepilogo-panieri"] = False

    # SETTORE DAL PANIERE + TEMA DAL NOME (cantiere classificazione 21-22 ago, regola
    # «dichiarato batte dedotto»): si ricalcolano sui panieri appena raccolti. Scrivono
    # nel registro; il motore (che in questo giro e' gia' passato) li raccoglie al giro
    # successivo — lag di un mese noto e accettato. exit 2 = etichette orfane/fuori
    # tassonomia -> modulo rosso a verbale, decisione umana.
    if not DRY:
        for nome, script in (("settori-paniere", "enrich-settori-paniere.mjs"),
                             ("temi", "enrich-temi.mjs")):
            try:
                sx = subprocess.run([NODE, f"scripts/{script}", "--commit"],
                                    cwd=REPO, capture_output=True, text=True, timeout=1800)
                for line in (sx.stdout or "").strip().splitlines()[-2:]:
                    log(f"  |{nome}| {line}")
                modules[nome] = sx.returncode == 0
            except Exception as e:
                log(f"!! {nome} fallito (non blocca): {e}")
                modules[nome] = False

    # Registro ESMA MMF (Linus, 9 ago): la promessa del hub /etf-monetari.
    # Rilegge il registro ufficiale (Reg. UE 2017/1131) e rinnova l'incrocio
    # in lib/esma-mmf.json. exit 2 = ritiro/sparizione di un autorizzato o
    # zero incroci -> modulo rosso, email del guardiano (poi serve deploy).
    if not DRY:
        try:
            mm = subprocess.run([NODE, "scripts/ingest-esma-mmf.mjs"],
                                cwd=REPO, capture_output=True, text=True, timeout=900)
            for line in (mm.stdout or "").strip().splitlines():
                log(f"  |esma-mmf| {line}")
            modules["esma-mmf"] = mm.returncode == 0
            if mm.returncode != 0:
                log("!! ESMA MMF: ritiro/sparizione o zero incroci - vedi righe sopra")
            # il json rinnovato va COMMITTATO (16 ago 2026: restava sporco nell'albero
            # e il `git pull --rebase` dell'ExecStartPre dei timer sarebbe fallito →
            # daily 15:15 muto). Commit + rebase + push; se il push è respinto lo si
            # vede nel log e nel giro dopo (l'albero resta pulito col commit locale).
            ch = subprocess.run(["git", "status", "--porcelain", "lib/esma-mmf.json"], cwd=REPO, capture_output=True, text=True).stdout.strip()
            if ch:
                subprocess.run(["git", "add", "lib/esma-mmf.json"], cwd=REPO)
                subprocess.run(["git", "-c", "user.name=rebalix-vps", "-c", "user.email=vps@rebalix.com", "commit", "-q", "-m",
                                f"data(esma-mmf): rilevazione ESMA MMF {TODAY} (modulo |esma-mmf| del runner)"], cwd=REPO)
                pr = subprocess.run(["git", "pull", "--rebase", "-q", "origin", "main"], cwd=REPO, capture_output=True, text=True)
                ps = subprocess.run(["git", "push", "-q", "origin", "main"], cwd=REPO, capture_output=True, text=True)
                log(f"  |esma-mmf| json committato · pull {'ok' if pr.returncode == 0 else 'KO'} · push {'ok' if ps.returncode == 0 else 'KO: ' + (ps.stderr or '')[:80]}")
        except Exception as e:
            log(f"!! esma-mmf fallito (non blocca): {e}")
            modules["esma-mmf"] = False

    # Golden ESTERNO (Linus, 9 ago): metriche nostre vs serie del grafico
    # JustETF sul roster dei 7 (SOLO verifica, mai fonte). Date allineate,
    # tolleranze strette. exit 2 = scarto vero -> modulo rosso, email;
    # fonte irraggiungibile = ⚠ a verbale, nessun falso allarme.
    if not DRY:
        try:
            ge = subprocess.run([NODE, "scripts/golden-confronto-esterno.mjs"],
                                cwd=REPO, capture_output=True, text=True, timeout=900)
            for line in (ge.stdout or "").strip().splitlines():
                log(f"  |golden-esterno| {line}")
            modules["golden-esterno"] = ge.returncode == 0
            if ge.returncode != 0:
                log("!! GOLDEN ESTERNO: metriche fuori tolleranza - vedi righe sopra")
        except Exception as e:
            log(f"!! golden-esterno fallito (non blocca): {e}")
            modules["golden-esterno"] = False

    # il mese è «fatto» solo QUI, in fondo al giro, e solo se l'edizione (dove è richiesta) è COMPLETE (18 set 2026): prima, un
    # giro interrotto dopo il registro risultava concluso. Un mese non concluso resta recuperabile alla sveglia successiva.
    if not DRY:
        nuovo = marcatore_fine_giro(state, YM, modules, EDIZIONE_RICHIESTA, edizione_stato, edizione_errore,
                                    f"{datetime.datetime.now():%Y-%m-%d %H:%M}", ARCHIVIATORE_MD5, GIRO_AVVIATO_IL)
        with open(STATE, "w") as f:
            json.dump(nuovo, f)
        if nuovo.get("last_ym") != YM:
            log(f"!! mese {YM} NON marcato «fatto» ({nuovo.get('errore')}): il prossimo lancio lo riprende")
            ok = False
    send_heartbeat(ok, falliti + (0 if p.returncode == 0 else 1), modules)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
