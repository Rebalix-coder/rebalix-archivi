#!/usr/bin/env python3
import json, os
BASE = os.path.dirname(__file__)
data = json.load(open(os.path.join(BASE, "ls_timeseries.json")))

# --- patch manuale per i 2 PDF-immagine (letti a vista, solo LS60) ---
manual = {
 "2024-09-30": {"isin":"IE00BMVB5P51","aum_eur_m":423.4,"ter":0.25,
   "durata_modificata":6.5,"rendimento_scadenza":3.7,"pe":22.4,"dividend_yield":1.9,
   "perf_ytd":11.36,"credito":{"AAA":3.9,"AA":20.0,"A":8.0,"BBB":7.3,"NR":0.5},
   "us_geo":57.5,
   "holdings":[("FTSE All-World",19.3),("FTSE Developed World",19.3),("Global Aggregate Bond EUR H",19.0),
     ("FTSE North America",12.7),("USD Treasury Bond EUR H",7.5),("USD Corp Bond EUR H",5.3),
     ("EUR Eurozone Gov Bond",5.2),("FTSE Emerging Markets",4.1),("FTSE Developed Europe",2.9),
     ("EUR Corp Bond",1.8),("FTSE Japan",1.2),("UK Gilt EUR H",0.9),("FTSE Dev Asia Pac ex Japan",0.8)]},
 "2025-06-30": {"isin":"IE00BMVB5P51","aum_eur_m":581.6,"ter":0.25,
   "durata_modificata":6.3,"rendimento_scadenza":3.8,"pe":22.4,"dividend_yield":1.8,
   "perf_ytd":-0.55,"credito":{"AAA":3.8,"AA":20.0,"A":8.0,"BBB":7.2,"NR":0.7},
   "us_geo":57.5,
   "holdings":[("Global Aggregate Bond EUR H",19.3),("FTSE All-World",19.2),("FTSE Developed World",19.2),
     ("FTSE North America",12.8),("USD Treasury Bond EUR H",7.6),("EUR Eurozone Gov Bond",5.1),
     ("USD Corp Bond EUR H",5.0),("FTSE Emerging Markets",4.2),("FTSE Developed Europe",3.0),
     ("EUR Corp Bond",1.8),("FTSE Japan",1.1),("UK Gilt EUR H",0.9),("FTSE Dev Asia Pac ex Japan",0.8)]},
}

def short(name):
    return (name.replace("Vanguard ","").replace(" UCITS ETF","")
            .replace(" EUR Hedged"," EUR H").replace("Global Aggregate Bond","Global Agg Bond")
            .replace("Developed","Dev").replace("Emerging Markets","EM")
            .replace("Asia Pacific ex Japan","Asia Pac ex JP").replace("North America","N.America"))

rows = {}  # date -> ls60 dict
for rec in data:
    f = rec["fondi"].get("60")
    if f: rows[rec["data_riferimento"]] = f
# inject manual
for dt, m in manual.items():
    rows[dt] = m

dates = sorted(rows.keys())

# --- tabella sintetica ---
print(f"{'Trimestre':<12}{'AUM €M':>9}{'#ETF':>6}{'Durata':>8}{'YTM%':>7}{'P/E':>7}{'US%':>7}")
print("-"*56)
for dt in dates:
    f = rows[dt]
    hold = f["holdings"]
    n = len(hold)
    dur = f.get("durata_modificata") or "-"
    ytm = f.get("rendimento_scadenza") or "-"
    pe  = f.get("pe") or "-"
    us  = f.get("us_geo","?")
    aum = f.get("aum_eur_m","?")
    print(f"{dt:<12}{aum:>9}{n:>6}{str(dur):>8}{str(ytm):>7}{str(pe):>7}{str(us):>7}")

# --- traiettoria dei mattoncini principali ---
def w(f, key):
    for h in f["holdings"]:
        name = h[0] if isinstance(h, tuple) else h["etf"]
        peso = h[1] if isinstance(h, tuple) else h["peso"]
        if key in short(name): return peso
    return None
sleeves = ["FTSE All-World","Dev World","N.America","Global Agg Bond","EM","Dev Europe","USD Treasury"]
print("\nMattoncini principali (peso %):")
print(f"{'Trimestre':<12}" + "".join(f"{s[:12]:>13}" for s in sleeves))
for dt in dates:
    f = rows[dt]
    print(f"{dt:<12}" + "".join(f"{str(w(f,s) or '-'):>13}" for s in sleeves))

# --- cambi nell'insieme di mattoncini ---
print("\nVariazioni dell'insieme di ETF sottostanti:")
prev = None
for dt in dates:
    f = rows[dt]
    names = set(short(h[0] if isinstance(h,tuple) else h["etf"]) for h in f["holdings"])
    if prev is not None:
        added = names - prev
        removed = prev - names
        if added or removed:
            print(f"  {dt}: +{sorted(added)}  -{sorted(removed)}")
    prev = names
print("  (vuoto = nessun cambio nell'insieme; solo i pesi si muovono)")
