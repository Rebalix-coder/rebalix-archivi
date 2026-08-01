#!/usr/bin/env python3
"""LIVELLO B esteso a TUTTI e 4 i fondi LS (20/40/60/80).
Composizione = share-class-agnostica -> un calcolo per LIVELLO (Acc=Dist identici).
Confronto: nostro ricalcolo (14 factsheet, 31 mag) vs pubblicato Vanguard (report 31 mar)."""
import pdfplumber, re, os, json

BASE = os.path.dirname(__file__)
FS = os.path.join(BASE, "factsheets")

FILES = {
 "all-world":"All-World","developed-world":"Developed World","north-america":"North America",
 "emerging":"Emerging","dev-europe":"Developed Europe","japan":"Japan","asia-pac":"Asia Pacific",
 "sp500":"S&P 500","global-agg":"Global Aggregate","usd-treasury":"USD Treasury",
 "eur-govt":"Eurozone Government","usd-corp":"USD Corporate","eur-corp":"EUR Corporate","uk-gilt":"Gilt",
}
BONDS = {"global-agg","usd-treasury","eur-govt","usd-corp","eur-corp","uk-gilt"}
FUND_HEADER = re.compile(r"Vanguard LifeStrategy (\d{2})% Equity UCITS ETF")
NUM = re.compile(r"^-?\d{1,2},\d$")

def text(f):
    with pdfplumber.open(os.path.join(FS, f)) as pdf:
        return "\n".join(pg.extract_text() or "" for pg in pdf.pages)

def us_of(t):
    i = t.find("Market allocation")
    if i < 0: return None
    m = re.search(r"United States\s+(\d{1,3}\.\d)", t[i:i+300])
    return float(m.group(1)) if m else None

def dur_of(t):
    m = re.search(r"duration\s+(\d+\.\d)\s*years", t)
    return float(m.group(1)) if m else None

# composizione interna dei 14 sottostanti
comp = {}
for f in FILES:
    t = text(f + ".pdf")
    comp[f] = {"us": us_of(t), "dur": dur_of(t) if f in BONDS else None}

# USA pubblicato per fondo dal report trimestrale (mar-2026): unico valore 40-68 per pagina-dettaglio
pub_us = {}
with pdfplumber.open(os.path.join(FS, "newsletter.pdf")) as pdf:
    for pg in pdf.pages:
        tt = pg.extract_text() or ""
        found = set(FUND_HEADER.findall(tt))
        if len(found) == 1:
            eq = found.pop()
            cands = [float(w["text"].replace(",", ".")) for w in pg.extract_words()
                     if NUM.match(w["text"]) and 40 <= float(w["text"].replace(",", ".")) <= 68 and w["x0"] > 200]
            if len(cands) == 1:
                pub_us[eq] = cands[0]

# pesi + duration pubblicata per fondo dalla serie validata
ts = json.load(open(os.path.join(BASE, "ls_timeseries.json")))
rec = next(r for r in ts if r["data_riferimento"] == "2026-03-31")

def file_for(name):
    for f, kw in FILES.items():
        if kw in name: return f
    return None

print(f"{'Fondo':<7}{'USA nostro':>11}{'USA Vguard':>11}{'Δ':>6}   {'Dur nostro':>11}{'Dur Vguard':>11}{'Δ':>6}")
print("-"*64)
for eq in ["20","40","60","80"]:
    fund = rec["fondi"][eq]
    w = {}
    for h in fund["holdings"]:
        f = file_for(h["etf"])
        if f: w[f] = h["peso"]
    us_recon = sum((w[f]/100.0)*(comp[f]["us"] or 0) for f in w)
    bw = sum(w[f] for f in w if f in BONDS)
    dur_recon = sum(w[f]*(comp[f]["dur"] or 0) for f in w if f in BONDS)/bw if bw else 0
    us_p = pub_us.get(eq); dur_p = fund.get("durata_modificata")
    dus = f"{us_recon-us_p:+.1f}" if us_p else "?"
    dd = f"{dur_recon-dur_p:+.2f}" if dur_p else "?"
    print(f"LS{eq:<5}{us_recon:>10.1f}%{('%.1f%%'%us_p) if us_p else '   ?':>11}{dus:>6}   {dur_recon:>9.2f}a {(('%.1f a'%dur_p) if dur_p else '?'):>10}{dd:>6}")
print("\n(Acc e Dist di ogni livello: composizione identica -> stessi numeri. Distinzione solo su prezzi+fisco.)")
