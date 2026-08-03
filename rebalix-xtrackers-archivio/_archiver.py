#!/usr/bin/env python3
"""Archiviatore automatico Xtrackers multi-asset (Diversified Portfolio + Portfolio XQUI).
- Scarica ogni giorno la composizione ufficiale dal sito DWS (API JSON pubblica).
- Archivia il JSON grezzo per data-dato (idempotente: stessa data = stesso file).
- Accumula la storia in un JSONL per ETF: una riga per (data, tipo-tabella), auto-dedup.
  Da qui l'articolo calcolera' derive dei pesi e date dei ribilanciamenti.
- Salva anche la serie NAV ufficiale DWS (sovrascritta a ogni run: e' sempre la storia completa).
- Look-through dei mattoncini (~settimanale): per ogni sottostante aggrega paesi/settori/
  valute/classi dalle posizioni complete (il dato aggregato DWS non esiste: lo calcoliamo noi).
- Factsheet PDF mensili dei 5 multi-asset e dei sottostanti (URL stabile per ISIN).
- Fiscalita' white list: scarica dalla pagina DWS ogni nuovo file semestrale (auto-cattura).
- iShares Portfolio (Growth/Moderate/Conservative, ex BlackRock ESG Multi-Asset):
  composizione dall'endpoint JSON della pagina prodotto; il JSON non espone la data
  del dato, quindi la dedup e' per IMPRONTA dei pesi (nuova riga solo se cambiano).
- VanEck Multi-Asset: TODO posizioni (bloccate dal consenso cookie; ribilanciamento
  annuale a settembre, urgenza bassa) — prezzi via Yahoo come per tutti.
Uso: python3 _archiver.py [--dry-run]
"""
import os, re, sys, json, time, hashlib, datetime, urllib.request, urllib.parse, subprocess, tempfile, shutil

# launchd parte con PATH minimale (/usr/bin:/bin:...): senza /usr/local/bin lo shebang
# «#!/usr/bin/env node» di vercel non trova node e il deploy muore con exit 127.
os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")

ARCHIVE = os.path.expanduser("~/backups/rebalix-xtrackers-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
GIT = shutil.which("git") or "/usr/bin/git"
VERCEL = shutil.which("vercel") or "/usr/local/bin/vercel"
# moduli dati versionati che i generatori rigenerano (gli UNICI file che il deploy auto committa)
DATA_FILES = ["lib/blog/xd-performance.ts", "lib/blog/xd-holdings.ts",
              "lib/blog/xd-lookthrough.ts", "lib/blog/xd-aum.ts",
              "lib/blog/xd-tax.ts", "lib/blog/xeon-tax.ts",  # fiscalità white list dal DB
              "lib/blog/xd-costs.ts",  # costi estratti dai KID PRIIPs (DWS + Vanguard)
              "lib/blog/xd-changes.ts"]  # registro variazioni paniere (soglie dichiarate)
BASE = "https://etf.dws.com/api/pdp/it-it/etf/"

ETFS = {
 "xeq2": "LU3116008346-diversified-portfolio-20-equity-ucits-etf-1c",
 "xeq4": "LU3116008429-diversified-portfolio-40-equity-ucits-etf-1c",
 "xeq6": "LU3116008692-diversified-portfolio-60-equity-ucits-etf-1c",
 "xeq8": "LU3116008775-diversified-portfolio-80-equity-ucits-etf-1c",
 "xqui": "LU0397221945-portfolio-ucits-etf-1c",
}

# iShares Portfolio (ex BlackRock ESG Multi-Asset): id pagina prodotto + ISIN
ISHARES = {
 "magr": ("313190", "IE00BLLZQ805"),  # Growth       — MAGR.MI
 "modr": ("313193", "IE00BLLZQS08"),  # Moderate     — MODR.MI
 "macv": ("313196", "IE00BLP53M98"),  # Conservative — MACV.MI
}
ISHARES_URL = "https://www.ishares.com/ch/professionals/en/products/{pid}/x/1495092304805.ajax?tab=all&fileType=json"

DRY = "--dry-run" in sys.argv

def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M}  {msg}"
    print(line)
    if not DRY:
        with open(os.path.join(ARCHIVE, "_archiver.log"), "a") as f:
            f.write(line + "\n")

NET_ERR = (urllib.error.URLError, OSError)  # gaierror/timeout/connessione sono sottoclassi

def net_retry(fn, *a, **kw):
    """Ritenta una chiamata di rete prima di arrendersi. I singhiozzi DNS del Mac sono
    TRANSITORI ma azzeravano l'intero giro (21/07/2026: un blip = 15 errori, 3 moduli non
    rigenerati e un buco permanente nelle serie giornaliere AUM/spread). Pause 5s poi 20s."""
    pause = [5, 20]
    for i in range(3):
        try:
            return fn(*a, **kw)
        except NET_ERR as e:
            if i == 2:
                raise
            log(f"   rete instabile ({type(e).__name__}) — ritento tra {pause[i]}s")
            time.sleep(pause[i])

def fetch_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    def _go():
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8"))
    return net_retry(_go)

def asof_of(table):
    """Data 'Fonte: DWS gg/mm/aaaa' (o gg.mm.aaaa nelle lingue estere) -> 'aaaa-mm-gg'."""
    for disc in table.get("disclaimers") or []:
        m = re.search(r"(\d{2})[./](\d{2})[./](\d{4})", disc.get("text") or "")
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return None

def parse_table(table):
    """Estrae le posizioni da una tabella holdings DWS. Riconosce i due formati:
    - 'full'    : ISIN in header + Nome/Peso %/Valore di mercato/Classe (pesi esatti + controvalori)
    - 'weights' : Nome(link)/ISIN/Classe/Ponderazione (solo pesi, ma spesso data piu' fresca)
    Ritorna (kind, positions) o (None, None) se il formato non e' riconosciuto."""
    cols = [c.get("value") or "" for c in table.get("columns") or []]
    rows = table.get("values") or []
    if "Peso %" in " ".join(cols):
        kind, pos = "full", []
        for r in rows:
            isin = (r.get("header") or {}).get("value")
            pos.append({
                "isin": isin,
                "nome": (r.get("column_0") or {}).get("value"),
                "peso": (r.get("column_1") or {}).get("sortValue"),
                "ctv_eur": (r.get("column_2") or {}).get("sortValue"),
                "classe": (r.get("column_5") or {}).get("value"),
            })
        return kind, pos
    if any("Ponderazione" in c for c in cols):
        kind, pos = "weights", []
        for r in rows:
            if not (r.get("column_1") or {}).get("value"):
                continue  # righe di subtotale per classe (senza ISIN)
            nome_cell = (r.get("column_0") or {}).get("value")
            nome = nome_cell.get("text") if isinstance(nome_cell, dict) else nome_cell
            pos.append({
                "isin": (r.get("column_1") or {}).get("value"),
                "nome": nome,
                "peso": (r.get("column_3") or {}).get("sortValue"),
                "classe": (r.get("column_2") or {}).get("value"),
            })
        return kind, pos
    return None, None

def seen_keys(hist_path):
    keys = set()
    if os.path.exists(hist_path):
        with open(hist_path) as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    keys.add((rec["asof"], rec["kind"]))
                except Exception:
                    pass
    return keys

def archive_holdings(key, slug):
    data = fetch_json(BASE + slug + "/holdings")
    hist_path = os.path.join(ARCHIVE, "history", key + ".jsonl")
    seen = seen_keys(hist_path)
    dates, nuovi = [], 0
    for table in data.get("tables") or []:
        kind, pos = parse_table(table)
        asof = asof_of(table)
        if not kind or not asof or not pos:
            continue
        dates.append(asof)
        if (asof, kind) in seen:
            continue
        tot = sum(p["peso"] or 0 for p in pos)
        rec = {"asof": asof, "kind": kind, "n": len(pos), "somma_pesi": round(tot, 4), "posizioni": pos}
        if not DRY:
            os.makedirs(os.path.dirname(hist_path), exist_ok=True)
            with open(hist_path, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        nuovi += 1
        if abs(tot - 100) > 1.5:
            log(f"!! {key}: somma pesi {kind} = {tot:.2f}% (attesa ~100) — controllare")
    if not dates:
        log(f"!! {key}: nessuna tabella riconosciuta — formato DWS cambiato?")
        return
    # JSON grezzo keyato per data-dato piu' recente: idempotente, riscrivibile
    raw = os.path.join(ARCHIVE, "raw", key, max(dates) + ".json")
    if not DRY:
        os.makedirs(os.path.dirname(raw), exist_ok=True)
        with open(raw, "w") as f:
            json.dump(data, f, ensure_ascii=False)
    log(f"{key}: dato al {max(dates)}, {nuovi} snapshot nuovi" + (" (gia' in archivio)" if nuovi == 0 else ""))

def archive_nav(key, slug):
    """Serie NAV ufficiale DWS dal lancio: sempre completa, quindi basta l'ultima copia."""
    data = fetch_json(BASE + slug + "/performancechart")
    n = len(data.get("values") or [])
    if n == 0:
        log(f"!! {key}: serie NAV vuota — salto")
        return
    if not DRY:
        os.makedirs(os.path.join(ARCHIVE, "nav"), exist_ok=True)
        with open(os.path.join(ARCHIVE, "nav", key + ".json"), "w") as f:
            json.dump(data, f, ensure_ascii=False)
    log(f"{key}: NAV ufficiale, {n} punti")

# etichette di colonna: canonico -> varianti it/en (i due ETF swap esistono solo su en-lu)
LABELS = {
    "peso": ("Peso %", "% Weight"),
    "nome": ("Nome", "Name"),
    "paese": ("Paese", "Country"),
    "industria": ("Industria", "Industry"),
    "classe": ("Classe di investimento", "Asset class"),
}

def col_map(table):
    """Mappa canonica -> chiave riga (le chiavi non sono posizionali: usare 'key')."""
    per_label = {(c.get("value") or "").strip(): c.get("key") for c in table.get("columns") or []}
    out = {}
    for canon, varianti in LABELS.items():
        for v in varianti:
            if v in per_label:
                out[canon] = per_label[v]
                break
    return out

def fetch_json_locale(path):
    """API DWS: prova it-it, poi en-lu (prodotti non registrati in Italia, es. gli swap)."""
    for loc in ("it-it", "en-lu"):
        try:
            data = fetch_json(f"https://etf.dws.com/api/pdp/{loc}/etf/{path}")
            if data and data.get("tables"):
                return data
        except Exception:
            continue
    return None

def underlying_isins():
    """ISIN unici dei mattoncini dall'ultimo snapshot 'full' di ogni multi-asset (cash escluso)."""
    isins = set()
    for key in ETFS:
        path = os.path.join(ARCHIVE, "history", key + ".jsonl")
        if not os.path.exists(path):
            continue
        ultimo = None
        with open(path) as f:
            for line in f:
                rec = json.loads(line)
                if rec.get("kind") == "full":
                    ultimo = rec
        for p in (ultimo or {}).get("posizioni", []):
            isin = p.get("isin") or ""
            if re.match(r"^[A-Z]{2}[A-Z0-9]{10}$", isin):
                isins.add(isin)
    return sorted(isins)

def lookthrough_fresh(isin, giorni=6):
    """True se abbiamo gia' un aggregato recente per questo sottostante."""
    path = os.path.join(ARCHIVE, "lookthrough", isin + ".jsonl")
    if not os.path.exists(path):
        return False
    ultimo = None
    with open(path) as f:
        for line in f:
            try:
                ultimo = json.loads(line)["asof"]
            except Exception:
                pass
    if not ultimo:
        return False
    eta = datetime.date.today() - datetime.date.fromisoformat(ultimo)
    return eta.days < giorni

def archive_lookthrough():
    """Radiografia dei mattoncini: paesi/settori/valute/classi aggregati DA NOI dalle
    posizioni complete di ogni sottostante (DWS non pubblica l'aggregato via API).
    ~Settimanale per sottostante (dedup per asof); il grezzo multi-MB NON si salva."""
    for isin in underlying_isins():
        if lookthrough_fresh(isin):
            continue
        data = fetch_json_locale(isin + "/holdings")
        if not data:
            log(f"!! lookthrough {isin}: nessun dato su it-it/en-lu (ETC oro?) — salto")
            continue
        best = None
        for table in data.get("tables") or []:
            cm = col_map(table)
            if "peso" in cm and "classe" in cm:
                best = (table, cm)
                break
        if not best:
            log(f"!! lookthrough {isin}: nessuna tabella posizioni riconosciuta — salto")
            continue
        table, cm = best
        asof = asof_of(table)
        agg = {"paese": {}, "industria": {}, "classe": {}}
        top, n = [], 0
        for r in table.get("values") or []:
            peso = (r.get(cm["peso"]) or {}).get("sortValue") or 0
            n += 1
            for dim in ("paese", "industria", "classe"):
                chiave_col = cm.get(dim)
                if chiave_col:
                    val = (r.get(chiave_col) or {}).get("value") or "n.d."
                    agg[dim][val] = round(agg[dim].get(val, 0) + peso, 4)
            nome = (r.get(cm.get("nome", "column_0")) or {}).get("value")
            if isinstance(nome, dict):
                nome = nome.get("text")
            top.append({"isin": (r.get("header") or {}).get("value"), "nome": nome, "peso": peso})
        top.sort(key=lambda p: -(p["peso"] or 0))
        rec = {"asof": asof, "n_posizioni": n,
               "aggregati": {k: dict(sorted(v.items(), key=lambda kv: -kv[1])) for k, v in agg.items() if v},
               "top20": top[:20]}
        path = os.path.join(ARCHIVE, "lookthrough", isin + ".jsonl")
        if not DRY:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        log(f"lookthrough {isin}: {n} posizioni al {asof}")

def _scarica_pdf(isin, tipo_doc):
    """PDF DWS a URL stabile per ISIN (Factsheet o PRIIPs KID), it con ripiego de."""
    for lingua in ("it/it", "de/de"):  # gli swap non registrati in Italia hanno solo il tedesco
        url = f"https://etf.dws.com/download/asset/product/{isin}/audience/Retail/{tipo_doc}/{lingua}"
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=60) as r:
                blob = r.read()
            if blob.startswith(b"%PDF") and len(blob) >= 20_000:
                return blob
        except Exception:
            pass
    return None

def archive_factsheets():
    """Factsheet PDF mensili (5 multi-asset + tutti i mattoncini) e KID PRIIPs mensili
    (soli 5 multi-asset: e' dove si vedono cambi di costi/rischio — riesame almeno annuale
    per regolamento, ma possibile in ogni momento). Una copia per mese di calendario."""
    mese = f"{datetime.date.today():%Y-%m}"
    cartella = os.path.join(ARCHIVE, "factsheets", mese)
    multi = [slug.split("-")[0] for slug in ETFS.values()]
    da_scaricare = [(isin, "Factsheet", isin + ".pdf") for isin in multi + underlying_isins()]
    da_scaricare += [(isin, "PRIIPs%20KIDs", isin + "-kid.pdf") for isin in multi]
    ok = tot = 0
    for isin, tipo_doc, nomefile in da_scaricare:
        dest = os.path.join(cartella, nomefile)
        if os.path.exists(dest):
            continue
        tot += 1
        blob = _scarica_pdf(isin, tipo_doc)
        if blob is None:
            log(f"!! {tipo_doc} {isin}: non scaricabile (it/de) — salto")
            continue
        if not DRY:
            os.makedirs(cartella, exist_ok=True)
            with open(dest, "wb") as f:
                f.write(blob)
        ok += 1
    if tot:
        log(f"factsheet+kid {mese}: scaricati {ok}/{tot} nuovi")

def archive_fiscalita():
    """Fiscalita' white list (quota titoli pubblici, D.L. 138/2011): DWS pubblica un Excel
    ogni semestre. Scarichiamo dalla pagina ogni periodo che ancora manca in archivio."""
    url = "https://etf.dws.com/it-it/informativa-prodotti/etf-documenti/fiscalita-degli-etf/"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        html = r.read().decode("utf-8", "ignore")
    pat = re.compile(r'href="(https://etf\.dws\.com/download/asset/[0-9a-f-]{36})"'
                     r'(.{0,600}?)dal (\d{2})-(\d{2})-(\d{4}) al (\d{2})-(\d{2})-(\d{4})', re.S)
    trovati = 0
    for m in pat.finditer(html):
        trovati += 1
        nome = f"{m.group(5)}-{m.group(4)}-{m.group(3)}_{m.group(8)}-{m.group(7)}-{m.group(6)}.xlsx"
        dest = os.path.join(ARCHIVE, "fiscalita", nome)
        if os.path.exists(dest):
            continue
        blob_req = urllib.request.Request(m.group(1), headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(blob_req, timeout=60) as r:
            blob = r.read()
        if len(blob) < 5_000:
            log(f"!! fiscalita {nome}: file sospetto ({len(blob)}B) — salto")
            continue
        if not DRY:
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            with open(dest, "wb") as f:
                f.write(blob)
        log(f"fiscalita: NUOVO semestre archiviato -> {nome}")
    if not trovati:
        log("!! fiscalita: nessun link trovato nella pagina — layout DWS cambiato?")

TICKER_SPREAD = {  # tutti i prodotti monitorati: ticker Yahoo per lo snapshot denaro/lettera
 "xeq2": "XEQ2.MI", "xeq4": "XEQ4.MI", "xeq6": "XEQ6.MI", "xeq8": "XEQ8.MI",
 "xqui": "XQUI.MI", "magr": "MAGR.MI", "modr": "MODR.MI", "macv": "MACV.MI",
 "vaneck_dtm": "DTM.AS", "vaneck_ntm": "NTM.AS", "vaneck_tof": "TOF.AS",
}

def archive_spread():
    """Fotografia quotidiana del denaro/lettera (bid/ask) alle ~10:30, a mercato aperto:
    nel tempo diventa la serie empirica dello spread (il pedaggio nascosto dei fondi
    poco scambiati). Yahoo richiede il rito cookie+crumb. Fail-soft: se il book e'
    vuoto (mercato chiuso, festivo) si logga e basta. Una riga per run in spread.jsonl."""
    import http.cookiejar
    cj = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))
    opener.addheaders = [("User-Agent", "Mozilla/5.0")]
    try:
        opener.open("https://fc.yahoo.com", timeout=30).read()
    except urllib.error.HTTPError:
        pass  # risponde 404 di proposito: serve solo a farci dare il cookie
    crumb = net_retry(lambda: opener.open("https://query1.finance.yahoo.com/v1/test/getcrumb", timeout=30).read().decode())
    syms = ",".join(TICKER_SPREAD.values())
    url = f"https://query1.finance.yahoo.com/v7/finance/quote?symbols={syms}&crumb={urllib.parse.quote(crumb)}"
    quotes = json.loads(net_retry(lambda: opener.open(url, timeout=60).read())).get("quoteResponse", {}).get("result") or []
    per_sym = {q.get("symbol"): q for q in quotes}
    adesso = f"{datetime.datetime.now():%Y-%m-%d %H:%M}"
    validi = 0
    rec = {"rilevato": adesso, "quote": {}}
    for key, sym in TICKER_SPREAD.items():
        q = per_sym.get(sym) or {}
        bid, ask = q.get("bid"), q.get("ask")
        entry = {"bid": bid, "ask": ask, "bid_size": q.get("bidSize"), "ask_size": q.get("askSize"),
                 "ultimo": q.get("regularMarketPrice"), "aum": q.get("netAssets")}
        if bid and ask and ask > 0 and ask >= bid:
            entry["spread_pct"] = round((ask - bid) / ((ask + bid) / 2) * 100, 4)
            validi += 1
        rec["quote"][key] = entry
    if not DRY:
        with open(os.path.join(ARCHIVE, "spread.jsonl"), "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    log(f"spread: snapshot {adesso}, {validi}/{len(TICKER_SPREAD)} book validi"
        + ("" if validi else " (mercato chiuso?)"))

def raw_num(x):
    """Le celle numeriche iShares sono {'display':…,'raw':…}: prendi il raw."""
    return x.get("raw") if isinstance(x, dict) else x

def archive_ishares(key, pid, isin):
    """Composizione iShares Portfolio: colonne fisse dell'endpoint aaData
    (0=ticker, 1=nome, 2=settore, 3=classe, 4=controvalore, 5=peso, 9=ISIN, 21=valuta).
    Niente data-dato nel JSON -> dedup per impronta dei pesi, datata al giorno di rilevazione."""
    req = urllib.request.Request(ISHARES_URL.format(pid=pid), headers={"User-Agent": "Mozilla/5.0"})
    def _go():
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read().decode("utf-8-sig"))
    data = net_retry(_go)
    rows = data.get("aaData") or []
    if not rows:
        log(f"!! {key}: nessuna posizione dall'endpoint iShares — formato cambiato?")
        return
    pos = []
    for r in rows:
        pos.append({
            "ticker": r[0], "nome": r[1], "settore": r[2], "classe": r[3],
            "ctv_eur": raw_num(r[4]), "peso": raw_num(r[5]),
            "isin": r[9] if isinstance(r[9], str) else None, "valuta": r[21],
        })
    impronta = hashlib.sha1(json.dumps(
        sorted((p["isin"] or p["ticker"] or "", round(p["peso"] or 0, 5)) for p in pos)
    ).encode()).hexdigest()[:16]
    hist_path = os.path.join(ARCHIVE, "history", key + ".jsonl")
    ultima = None
    if os.path.exists(hist_path):
        with open(hist_path) as f:
            for line in f:
                try:
                    ultima = json.loads(line).get("impronta")
                except Exception:
                    pass
    oggi = f"{datetime.date.today():%Y-%m-%d}"
    if impronta == ultima:
        log(f"{key}: composizione invariata (impronta {impronta}) — niente da fare")
        return
    tot = sum(p["peso"] or 0 for p in pos)
    if abs(tot - 100) > 1.5:
        log(f"!! {key}: somma pesi = {tot:.2f}% (attesa ~100) — controllare")
    rec = {"asof": oggi, "kind": "full", "fonte": "rilevazione", "impronta": impronta,
           "n": len(pos), "somma_pesi": round(tot, 4), "posizioni": pos}
    raw = os.path.join(ARCHIVE, "raw", key, oggi + ".json")
    if not DRY:
        os.makedirs(os.path.dirname(hist_path), exist_ok=True)
        with open(hist_path, "a") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        os.makedirs(os.path.dirname(raw), exist_ok=True)
        with open(raw, "w") as f:
            json.dump(data, f, ensure_ascii=False)
    log(f"{key}: {len(pos)} posizioni, NUOVA composizione (impronta {impronta})")

def regen(script):
    """Rigenera un modulo dati del sito (pattern LS). Isolata: un errore non blocca l'archivio.
    Ritorna True se il generatore è uscito con successo (usato dal battito del guardiano)."""
    if DRY:
        log(f"[dry] rigenererei via {script}"); return True
    try:
        g = subprocess.run([sys.executable, os.path.join(ARCHIVE, "_scripts", script)],
                           capture_output=True, text=True, timeout=300)
        for line in (g.stdout + g.stderr).splitlines():
            if line.strip(): log(line.strip())
        return g.returncode == 0
    except Exception as e:
        log(f"!! rigenerazione {script} fallita: {e}")
        return False

def autodeploy():
    """Se i moduli dati sono cambiati: commit dei SOLI file generati, push, deploy prod
    da WORKTREE PULITO all'ultimo commit (mai la WIP). Pattern identico all'archiviatore LS.
    Ritorna True se non c'era nulla da deployare o il deploy è riuscito; False se il deploy
    è fallito (→ conta come errore nel battito del guardiano, così la staleness non è muta).
    Il deploy viene RITENTATO (i fallimenti di rete/build sono spesso transitori) e, se
    fallisce comunque, l'output COMPLETO di vercel finisce nel log (prima si perdeva)."""
    if DRY:
        log("[deploy] (simulazione) salto"); return True
    if not os.path.isdir(REPO):
        log(f"[deploy] repo non trovato — salto."); return True
    branch = subprocess.run([GIT, "-C", REPO, "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    if branch != "main":
        log(f"[deploy] branch {branch} ≠ main — salto per sicurezza."); return True
    files = [f for f in DATA_FILES if os.path.exists(os.path.join(REPO, f))]
    try:
        subprocess.run([GIT, "-C", REPO, "add", "--"] + files, check=True)
        if subprocess.run([GIT, "-C", REPO, "diff", "--cached", "--quiet", "--"] + files).returncode == 0:
            log("[deploy] moduli dati invariati — nessun deploy."); return True
        msg = ("data(blog-xd): refresh automatico dei moduli versionati\n\n"
               "Rigenerati dall'archiviatore Xtrackers (golden test superati).\n\n"
               "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
        subprocess.run([GIT, "-C", REPO, "commit", "-m", msg, "--"] + files, check=True)
        log("[deploy] commit dei moduli xd")
        if subprocess.run([GIT, "-C", REPO, "push", "origin", "main"]).returncode != 0:
            log("!! push Codeberg fallito — proseguo col deploy del commit locale")
        head = subprocess.run([GIT, "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        wt = tempfile.mkdtemp(prefix="rebalix-deploy-xd-")
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
            # tutti i tentativi falliti: logga l'output COMPLETO (troncato) per la diagnosi
            out = ((r.stdout or "") + "\n" + (r.stderr or "")).strip()[-1800:] if r else "(nessun output)"
            log(f"!! [deploy] DEPLOY FALLITO dopo 3 tentativi ({head[:8]}). Il commit è su Codeberg "
                f"ma NON in produzione. Output vercel:\n{out}")
            return False
        finally:
            subprocess.run([GIT, "-C", REPO, "worktree", "remove", "--force", wt])
    except Exception as e:
        log(f"!! auto-deploy fallito: {e}")
        return False

# ── Guardiano (dead-man's switch): a fine run mando un BATTITO all'endpoint Rebalix.
# Il cron /api/cron/archiver-health veglia i battiti e avvisa Linus se ne manca uno.
GEN_TO_MODULE = {  # script generatore -> chiave modulo attesa dal guardiano (lib/archiver-health)
    "gen_xd_performance.py": "xd-performance", "gen_xd_holdings.py": "xd-holdings",
    "gen_xd_lookthrough.py": "xd-lookthrough", "gen_xd_aum.py": "xd-aum",
    "gen_xd_tax.py": "xd-tax", "gen_xeon_tax.py": "xeon-tax",
    "gen_xd_costs.py": "xd-costs", "gen_xd_changes.py": "xd-changes",
}

def latest_nav_date():
    """Data del dato NAV più fresca fra i file nav/*.json (asOfDate 'gg/mm/aaaa' -> 'aaaa-mm-gg').
    È il segnale ANTI-STANTÌO: se la fonte DWS si congela, questa data smette di avanzare."""
    best = None
    try:
        nav_dir = os.path.join(ARCHIVE, "nav")
        for fn in os.listdir(nav_dir):
            if not fn.endswith(".json"): continue
            try:
                d = json.load(open(os.path.join(nav_dir, fn)))
                m = re.match(r"(\d{2})/(\d{2})/(\d{4})", str(d.get("asOfDate", "")))
                if m:
                    iso = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
                    if best is None or iso > best: best = iso
            except Exception:
                continue
    except Exception:
        pass
    return best

def send_heartbeat(name, errori, modules, data_date):
    """POST del battito. Fail-SOFT: un guardiano che rompe l'archivio sarebbe assurdo."""
    if DRY:
        log(f"[heartbeat] (dry) name={name} errori={errori} moduli_ok={sum(1 for v in modules.values() if v)}/{len(modules)} data={data_date}")
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
        # il battito DEVE arrivare: se manca, il guardiano crede l'archivio fermo e manda
        # un falso allarme (02/08/2026: blip DNS all'invio → email «xd-lookthrough/xd-changes
        # non rigenerati» mentre erano perfetti). net_retry come per le altre chiamate.
        status = net_retry(lambda: urllib.request.urlopen(req, timeout=30).status)
        log(f"[heartbeat] inviato ({status})")
    except Exception as e:
        log(f"!! [heartbeat] invio fallito (non blocca l'archivio): {e}")

def main():
    log(f"--- avvio archiviatore Xtrackers {'(SIMULAZIONE)' if DRY else ''} ---")
    errori = 0
    for key, slug in ETFS.items():
        for step in (archive_holdings, archive_nav):
            try:
                step(key, slug)
            except Exception as e:
                errori += 1
                log(f"!! {key} {step.__name__}: {e}")
    for key, (pid, isin) in ISHARES.items():
        try:
            archive_ishares(key, pid, isin)
        except Exception as e:
            errori += 1
            log(f"!! {key} archive_ishares: {e}")
    # ogni blocco e' isolato: un errore non blocca gli altri
    for step in (archive_spread, archive_lookthrough, archive_factsheets, archive_fiscalita):
        try:
            step()
        except Exception as e:
            errori += 1
            log(f"!! {step.__name__}: {e}")
    # rigenera i moduli del sito e, se cambiati, deploya (solo i file dati, da worktree pulito)
    modules = {}
    for g in ("gen_xd_performance.py", "gen_xd_holdings.py", "gen_xd_lookthrough.py", "gen_xd_aum.py",
              "gen_xd_tax.py", "gen_xeon_tax.py", "gen_xd_costs.py", "gen_xd_changes.py"):
        modules[GEN_TO_MODULE[g]] = regen(g)
    if not autodeploy():  # deploy fallito = i dati freschi non sono arrivati in prod → allerta
        errori += 1
    send_heartbeat("xtrackers", errori, modules, latest_nav_date())
    log(f"fatto ({errori} errori)" if errori else "fatto, tutto OK")

if __name__ == "__main__":
    main()
