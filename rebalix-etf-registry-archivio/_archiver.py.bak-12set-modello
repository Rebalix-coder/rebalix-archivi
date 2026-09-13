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
import os, re, sys, glob, json, shutil, datetime, subprocess, urllib.request

os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")

ARCHIVE = os.path.expanduser("~/backups/rebalix-etf-registry-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
NODE = shutil.which("node") or "/usr/local/bin/node"
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


DELISTED = []  # riempito dal main col riepilogo dei delisting del giro


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
                                          "delisted": DELISTED}}).encode()
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

    # ISIN marcati chiusi in questo giro (rigo nel battito, decisione Linus 15 ago
    # 2026: il delisting sotto soglia era MUTO — 17 ETC Xtrackers spenti in silenzio
    # il 13 ago; ora l'elenco arriva sempre al guardiano, che lo mette in mail)
    delisted = []
    for m in re.finditer(r"^\s{2}(\w[\w&]*): (\d+) ISIN marcati delisted_at=\S+: (.*)$", out, re.M):
        delisted.append({"issuer": m.group(1), "n": int(m.group(2)), "isin": m.group(3).strip()})
    if delisted:
        log(f"  ISIN marcati chiusi in questo giro: {sum(d['n'] for d in delisted)}")
    DELISTED.extend(delisted)

    if ok and not DRY:
        with open(STATE, "w") as f:
            json.dump({"last_ym": YM, "at": f"{datetime.datetime.now():%Y-%m-%d %H:%M}"}, f)
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

    # Documenti ufficiali (prospetto+factsheet): aggancia i fondi nuovi e vigila
    # sugli schemi-URL. Gli URL emittente sono stabili e aggiornati sul posto.
    if not DRY:
        try:
            dd = subprocess.run([NODE, "scripts/enrich-etf-documents.mjs", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=4*3600)  # 16 ago: il giro pieno supera i 20 min; 2 set (debutto VPS): a inizio mese l'archivio del mese è VERGINE e l'ora piena non basta (morto a metà, ripreso a mano) → 4h
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
                                cwd=REPO, capture_output=True, text=True, timeout=6*3600)  # 7 ago: prima passata > 3h
            for line in (da.stdout or "").strip().splitlines()[-2:]:
                log(f"  |doc-archive| {line}")
            modules["doc-archive"] = da.returncode == 0
        except Exception as e:
            log(f"!! doc-archive fallito (non blocca): {e}")
            modules["doc-archive"] = False

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
                         ("doc-langs", "enrich-doc-langs.mjs"),
                         ("replica-from-kid", "enrich-replica-from-kid.mjs"),
                         # 3 set (agenda Database ETF): indice dichiarato NEL KID dove
                         # benchmark_raw e' vuoto (caso Vanguard 18 ago: fondi nuovi non
                         # ancora nel PDF pro ma gia' nel KID). Solo-dove-vuoto, mai dedotto.
                         ("benchmark-da-kid", "enrich-benchmark-da-kid.mjs")):
        if DRY:
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
            hx = subprocess.run([NODE, "scripts/ingest-etf-holdings-xtrackers.mjs", "--commit"],
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
            hs = subprocess.run([NODE, "scripts/ingest-etf-holdings-spdr.mjs", "--commit"],
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
            hi = subprocess.run([NODE, "scripts/ingest-etf-holdings-invesco.mjs", "--commit"],
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

    # Composizioni Vanguard (Fase B/3, notte 10-11 ago): GraphQL gpx ufficiale
    # (borHoldings paginato + marketAllocation + sectorDiversification).
    if not DRY:
        try:
            hv = subprocess.run([NODE, "scripts/ingest-etf-holdings-vanguard.mjs", "--commit"],
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
                hf = subprocess.run([NODE, primario, "--commit"],
                                    cwd=REPO, capture_output=True, text=True, timeout=3600)
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

    # DIFF DEI PANIERI + FOTO SU DISCO (decisione Linus 21 ago: «foto complete su disco
    # VPS, nel DB solo il derivato»; agganciato il 3 set dopo il collaudo su SWDA).
    # L'ORDINE e' la sostanza: PRIMA il diff (ultima foto in cassaforte vs DB appena
    # raccolto -> etf_holdings_diff), POI la foto nuova, che diventa la «prima» del mese
    # prossimo. Solo dove esiste la cassaforte (VPS): il gemello Mac salta senza rosso.
    # ⚠️ contratto foto: TSV.gz CON riga d'intestazione (foto-panieri.sh la scrive dal
    # 2 set — leggiFoto del diff la esige, lezione del primo demo).
    FOTO_SH = os.path.expanduser("~/backups/rebalix-cron/foto-panieri.sh")
    FOTO_DIR = os.path.expanduser("~/backups/rebalix-holdings-foto")
    if not DRY and os.path.exists(FOTO_SH):
        try:
            foto = sorted(glob.glob(os.path.join(FOTO_DIR, "etf_holdings-*.tsv.gz")))
            if not foto:
                raise RuntimeError("nessuna foto in cassaforte")
            df = subprocess.run([NODE, "scripts/diff-etf-holdings.mjs", "--prima", foto[-1], "--dopo", "db", "--commit"],
                                cwd=REPO, capture_output=True, text=True, timeout=3600)
            for line in (df.stdout or "").strip().splitlines()[-8:]:
                log(f"  |diff-panieri| {line}")
            modules["diff-panieri"] = df.returncode == 0
        except Exception as e:
            log(f"!! diff-panieri fallito (non blocca): {e}")
            modules["diff-panieri"] = False
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

    send_heartbeat(ok, falliti + (0 if p.returncode == 0 else 1), modules)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
