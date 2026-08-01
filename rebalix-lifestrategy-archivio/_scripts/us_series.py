#!/usr/bin/env python3
"""Serie storica robusta del peso USA (look-through Vanguard) per LS60.
USA = unico valore in [40,68] sulla pagina-dettaglio di un fondo. Nessuna
dipendenza dall'impaginazione delle intestazioni. Merge coi 2 trimestri-immagine."""
import os, re, glob
import pdfplumber

ARCHIVE = os.path.expanduser("~/Desktop/rebalix-lifestrategy-archivio")
NUM = re.compile(r"^-?\d{1,2},\d$")
FUND_HEADER = re.compile(r"Vanguard LifeStrategy (\d{2})% Equity UCITS ETF")
MONTHS = {"marzo":"03","giugno":"06","settembre":"09","dicembre":"12"}
def num(s): return float(s.replace(",", "."))

def refdate(path):
    base = re.sub(r"\.pdf$","",os.path.basename(path),flags=re.I).lower()
    base = re.sub(r"_\d{4}$","",base).strip()
    mm = MONTHS[base]; yr = os.path.basename(os.path.dirname(path))
    return f"{yr}-{mm}-{ {'03':'31','06':'30','09':'30','12':'31'}[mm] }"

def us_for_fund(pg):
    cands = [num(w["text"]) for w in pg.extract_words()
             if NUM.match(w["text"]) and 40 <= num(w["text"]) <= 68 and w["x0"] > 200]
    return cands

manual = {"2024-09-30":57.5, "2025-06-30":57.5}  # letti a vista dai PDF-immagine
series = {}
for path in sorted(glob.glob(os.path.join(ARCHIVE,"*","*.pdf"))):
    dt = refdate(path)
    with pdfplumber.open(path) as pdf:
        for pg in pdf.pages:
            t = pg.extract_text() or ""
            found = set(FUND_HEADER.findall(t))
            if found == {"60"}:  # pagina-dettaglio del solo LS60
                c = us_for_fund(pg)
                if len(c) == 1:
                    series[dt] = ("auto", c[0])
                elif len(c) > 1:
                    series[dt] = ("AMBIGUO", c)
for dt,v in manual.items():
    series.setdefault(dt, ("vista", v))

print("Peso USA nel LS60 (look-through ufficiale Vanguard)")
print(f"{'Trimestre':<12}{'USA %':>7}  fonte")
prev=None
for dt in sorted(series):
    src,v = series[dt]
    delta = f"  ({v-prev:+.1f})" if isinstance(prev,(int,float)) and isinstance(v,(int,float)) else ""
    print(f"{dt:<12}{str(v):>7}  {src}{delta}")
    if isinstance(v,(int,float)): prev=v
print(f"\ncopertura: {len(series)}/14 trimestri")
