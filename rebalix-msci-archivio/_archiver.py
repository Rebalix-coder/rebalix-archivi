#!/usr/bin/env python3
"""Archiviatore + guardiano MSCI World (nato 12 ago 2026, col lancio dell'articolo).

Mantiene la promessa pubblica del box «Come si aggiorna questa pagina»
(/blog/msci-world): i DATI si rinnovano col factsheet mensile, le REGOLE
si sorvegliano sui documenti ufficiali. Due compiti, giro SETTIMANALE:

1) FACTSHEET (5 varianti, URL stabili con contenuto che ruota ogni mese):
   scarica, legge la data di rilevazione dentro il PDF; se è NUOVA archivia
   i PDF per data + estrae i numeri chiave (costituenti, top10, fondamentali,
   pesi paese/settore, turnover) in un JSON e scrive il DIFF vs mese prima
   in CHANGES.md → da lì si aggiorna a mano lib/blog/msci-world-data.ts
   (MAI auto-edit del repo da cron: lezione incidente coefficienti 10 ago).

2) REGOLE: (a) HEAD sugli 8 PDF di metodologia noti — un 404 = MSCI ha
   pubblicato una nuova edizione (i filename sono datati) → allarme;
   (b) hash del testo delle pagine consultazioni e market classification →
   cambiamento = segnalazione. MAI modifica automatica dell'articolo.

Notifiche: CHANGES.md nell'archivio + notifica macOS (osascript) + heartbeat
al guardiano archiver-health (name=msci, fail-soft). Uso: _archiver.py [--dry-run]
"""
import os, sys, json, re, datetime, hashlib, subprocess, shutil, urllib.request

os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")

ARCHIVE = os.path.expanduser("~/backups/rebalix-msci-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.4 Safari/605.1.15"
DRY = "--dry-run" in sys.argv
PDFTOTEXT = shutil.which("pdftotext") or "/opt/homebrew/bin/pdftotext"

FACTSHEETS = {
    "usd-net":   "https://www.msci.com/documents/10199/255599/msci-world-index-usd-net.pdf",
    "eur-net":   "https://www.msci.com/documents/10199/255599/msci-world-index-eur-net.pdf",
    "eur-gross": "https://www.msci.com/documents/10199/255599/msci-world-index-eur-gross.pdf",
    "gbp-net":   "https://www.msci.com/documents/10199/255599/msci-world-index-gbp-net.pdf",
    "gbp-gross": "https://www.msci.com/documents/10199/255599/msci-world-index-gbp-gross.pdf",
}
# Edizioni correnti (ago 2026): un 404 qui significa «nuova edizione pubblicata,
# filename cambiato» → andare a prendere la nuova e aggiornare questa lista.
METHODOLOGY = {
    "gimi":        "https://www.msci.com/indexes/documents/methodology/1_MSCI_Global_Investable_Market_Indexes_Methodology_20260706.pdf",
    "corp-events": "https://www.msci.com/indexes/documents/methodology/0_MSCI_Corporate_Events_Methodology_20260210.pdf",
    "calculation": "https://www.msci.com/indexes/documents/methodology/0_MSCI_Index_Calculation_Methodology_20260512.pdf",
    "policies":    "https://www.msci.com/indexes/documents/methodology/0_MSCI_Index_Policies_20260127.pdf",
    "glossary":    "https://www.msci.com/indexes/documents/methodology/0_MSCI_Index_Glossary_of_Terms_20260105.pdf",
    "gics":        "https://www.msci.com/indexes/documents/methodology/1_MSCI_Global_Industry_Classification_Standard_GICS_Methodology_20250220.pdf",
    "fundamental": "https://www.msci.com/indexes/documents/methodology/0_MSCI_Fundamental_Data_Methodology_20240625.pdf",
    "classification": "https://www.msci.com/downloads/web/msci-com/indexes/index-resources/market-classification/MSCI_MARKET_CLASSIFICATION_FRAMEWORK_2026.pdf",
}
PAGES = {
    "consultations": "https://www.msci.com/indexes/index-resources/consultations",
    "market-classification": "https://www.msci.com/indexes/index-resources/market-classification",
}
MESI = {"JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
        "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12}
SETTORI = ["Information Technology", "Financials", "Industrials", "Health Care",
           "Consumer Discretionary", "Communication Services", "Consumer Staples",
           "Energy", "Materials", "Utilities", "Real Estate"]

def log(msg):
    print(f"[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)

def http(url, method="GET", timeout=60):
    req = urllib.request.Request(url, method=method, headers={"User-Agent": UA})
    return urllib.request.urlopen(req, timeout=timeout)

def pdf_text(path):
    out = subprocess.run([PDFTOTEXT, "-layout", path, "-"], capture_output=True, text=True, check=True).stdout
    # i salti pagina (\f) impedirebbero al ^ di re.M di vedere l'inizio riga
    return out.replace("\f", "\n")

def estrai(testo):
    """Numeri chiave dal testo -layout di un factsheet. Fail-loud sui campi cardine."""
    out = {}
    m = re.search(r"With ([\d,]+) constituents", testo)
    out["constituents"] = int(m.group(1).replace(",", "")) if m else None
    # data di rilevazione: piè di pagina «JUL 31, 2026 …» (inizio riga, poi altro testo)
    m = re.search(r"^([A-Z]{3}) (\d{1,2}), (\d{4})\b", testo, re.M)
    out["asOf"] = f"{int(m.group(3)):04d}-{MESI[m.group(1)]:02d}-{int(m.group(2)):02d}" if m and m.group(1) in MESI else None
    # top 10: totale della tabella («Total    23,643.52    26.41»)
    m = re.search(r"Total\s+[\d,]+\.\d+\s+(\d+\.\d+)", testo)
    out["top10Pct"] = float(m.group(1)) if m else None
    # fondamentali: riga «MSCI World …» nella sezione performance (ultimi 4 numeri = DY, P/E, P/E fwd, P/B)
    m = re.search(r"FUNDAMENTALS.*?MSCI World((?:\s+-?\d[\d.,]*){12,13})", testo, re.S)
    if m:
        nums = [float(x.replace(",", "")) for x in m.group(1).split()]
        out["divYieldPct"], out["pe"], out["peFwd"], out["pb"] = nums[-4:]
    # turnover: sezione risk, riga MSCI World, primo numero
    m = re.search(r"INDEX RISK AND RETURN.*?MSCI World\s+(\d+\.\d+)", testo, re.S)
    out["turnoverPct"] = float(m.group(1)) if m else None
    # pesi settore e paese: coppie «Nome XX.XX%» dalla legenda
    out["sectors"] = {s: float(m.group(1)) for s in SETTORI
                      if (m := re.search(re.escape(s) + r"\s+(\d+\.?\d*)%", testo))}
    out["countries"] = {p: float(m.group(1)) for p in
                        ["United States", "Japan", "United Kingdom", "Canada", "France", "Other"]
                        if (m := re.search(re.escape(p) + r"\s+(\d+\.?\d*)%", testo))}
    return out

def main():
    os.makedirs(ARCHIVE, exist_ok=True)
    state_path = os.path.join(ARCHIVE, "_state.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    errori, segnali = 0, []

    # ---- 1) factsheet: nuova rilevazione? ----
    tmp = os.path.join(ARCHIVE, "_tmp.pdf")
    try:
        with http(FACTSHEETS["eur-net"]) as r, open(tmp, "wb") as f:
            f.write(r.read())
        dati = estrai(pdf_text(tmp))
        as_of = dati.get("asOf")
        if not as_of or not dati.get("constituents"):
            raise ValueError(f"estrazione incompleta: asOf={as_of} constituents={dati.get('constituents')}")
        if as_of != state.get("factsheetAsOf"):
            log(f"factsheet NUOVO: {state.get('factsheetAsOf')} → {as_of} — archivio le 5 varianti")
            destdir = os.path.join(ARCHIVE, "factsheet", as_of)
            if not DRY:
                os.makedirs(destdir, exist_ok=True)
                os.replace(tmp, os.path.join(destdir, "eur-net.pdf"))
                for nome, url in FACTSHEETS.items():
                    if nome == "eur-net":
                        continue
                    with http(url) as r, open(os.path.join(destdir, f"{nome}.pdf"), "wb") as f:
                        f.write(r.read())
                json.dump(dati, open(os.path.join(destdir, "estratto-eur-net.json"), "w"), indent=1)
            prima = state.get("factsheetDati", {})
            diff = [f"- {k}: {prima.get(k)} → {dati.get(k)}" for k in
                    ("constituents", "top10Pct", "pe", "peFwd", "pb", "divYieldPct", "turnoverPct")
                    if prima.get(k) != dati.get(k)]
            segnali.append(f"📊 Factsheet MSCI World aggiornato al {as_of}. Variazioni:\n" + "\n".join(diff) +
                           "\n→ aggiornare lib/blog/msci-world-data.ts (asOf, numeri, pesi) e rideployare.")
            state["factsheetAsOf"], state["factsheetDati"] = as_of, dati
        else:
            log(f"factsheet invariato (rilevazione {as_of})")
    except Exception as e:
        errori += 1
        log(f"!! factsheet: {e}")
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)

    # ---- 2) metodologie: 404 = nuova edizione ----
    # NB: il server MSCI rifiuta le HEAD (404 anche su file esistenti, scoperto al
    # primo giro 12/8/2026) → GET con Range di cortesia, si leggono pochi byte.
    for nome, url in METHODOLOGY.items():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Range": "bytes=0-255"})
            with urllib.request.urlopen(req, timeout=45) as r:
                primi = r.read(256)
            if not primi.startswith(b"%PDF"):
                raise ValueError("la risposta non è un PDF")
            log(f"metodologia {nome}: ok")
        except Exception as e:
            segnali.append(f"📕 Metodologia «{nome}» non più raggiungibile ({e}): probabile NUOVA EDIZIONE "
                           f"pubblicata da MSCI. Cercarla, rileggerla (diff col nostro archivio in "
                           f"docs/indici/msci-world-base-fattuale.md) e aggiornare l'articolo se serve.")

    # ---- 3) pagine consultazioni / classificazione: hash del testo ----
    for nome, url in PAGES.items():
        try:
            with http(url, timeout=45) as r:
                corpo = r.read()
            testo = re.sub(rb"<script.*?</script>|<style.*?</style>", b"", corpo, flags=re.S)
            testo = re.sub(rb"<[^>]+>", b" ", testo)
            testo = re.sub(rb"\s+", b" ", testo)
            h = hashlib.sha256(testo).hexdigest()
            prev = state.get(f"page:{nome}")
            if prev and prev != h:
                segnali.append(f"📄 Pagina MSCI «{nome}» cambiata ({url}): possibile nuova consultazione o "
                               f"riclassificazione — da leggere.")
            state[f"page:{nome}"] = h
            log(f"pagina {nome}: {'cambiata' if prev and prev != h else 'invariata' if prev else 'baseline salvata'}")
        except Exception as e:
            log(f"!! pagina {nome} non raggiungibile ({e}) — non conto come errore: MSCI a volte filtra i bot")

    # ---- segnalazioni ----
    if segnali and not DRY:
        with open(os.path.join(ARCHIVE, "CHANGES.md"), "a") as f:
            f.write(f"\n## {datetime.date.today().isoformat()}\n\n" + "\n\n".join(segnali) + "\n")
        try:
            subprocess.run(["osascript", "-e",
                            f'display notification "{len(segnali)} segnalazioni in CHANGES.md" with title "Guardiano MSCI World"'],
                           check=False, timeout=10)
        except Exception:
            pass
    for s in segnali:
        log("SEGNALE: " + s.splitlines()[0])

    if not DRY:
        json.dump(state, open(state_path, "w"), indent=1)

    # ---- heartbeat (fail-soft) ----
    try:
        secret = None
        with open(os.path.join(REPO, ".env.local")) as f:
            for l in f:
                if l.startswith("CRON_SECRET="):
                    secret = l.split("=", 1)[1].strip().strip('"').strip("'")
        if secret and not DRY:
            payload = json.dumps({"name": "msci", "ok": errori == 0, "errors_count": errori,
                                  "metrics": {"host": os.uname().nodename, "segnali": len(segnali), "factsheetAsOf": state.get("factsheetAsOf")}}).encode()
            req = urllib.request.Request("https://rebalix.com/api/heartbeat", data=payload, method="POST",
                                         headers={"Content-Type": "application/json", "Authorization": f"Bearer {secret}"})
            urllib.request.urlopen(req, timeout=30).read()
            log("[heartbeat] battito inviato")
    except Exception as e:
        log(f"!! [heartbeat] fallito (non conto come errore dati): {e}")

    log(f"fine giro: errori={errori} segnali={len(segnali)}")
    sys.exit(1 if errori else 0)

main()
