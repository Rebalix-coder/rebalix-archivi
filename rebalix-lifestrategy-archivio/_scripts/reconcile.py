#!/usr/bin/env python3
"""LIVELLO B — ricalcolo indipendente della composizione LS60 dai factsheet dei sottostanti.
Confronta il nostro look-through (peso_sleeve x composizione_interna) coi numeri pubblicati
da Vanguard. Tutti i factsheet sono al 31 mag 2026; il look-through pubblicato di Vanguard
disponibile è al 31 mar 2026 (report trimestrale) -> scarto temporale dichiarato."""
import pdfplumber, re, os

FS = os.path.join(os.path.dirname(__file__), "factsheets")

# file factsheet -> nome-chiave del sottostante nella lista LS
FILES = {
 "all-world":"FTSE All-World", "developed-world":"FTSE Developed World",
 "north-america":"FTSE North America", "emerging":"FTSE Emerging Markets",
 "dev-europe":"FTSE Developed Europe", "japan":"FTSE Japan",
 "asia-pac":"FTSE Developed Asia Pacific ex Japan",
 "global-agg":"Global Aggregate Bond", "usd-treasury":"USD Treasury Bond",
 "eur-govt":"EUR Eurozone Government Bond", "usd-corp":"USD Corporate Bond",
 "eur-corp":"EUR Corporate Bond", "uk-gilt":"U.K. Gilt",
}
BONDS = {"global-agg","usd-treasury","eur-govt","usd-corp","eur-corp","uk-gilt"}

def text(f):
    with pdfplumber.open(os.path.join(FS, f)) as pdf:
        return "\n".join(pg.extract_text() or "" for pg in pdf.pages)

def countries(t):
    i = t.find("Market allocation")
    if i < 0: return {}
    j = t.find("Source", i)
    seg = t[i+len("Market allocation"): j if j > 0 else i+700]
    d = {}
    for m in re.finditer(r"([A-Z][A-Za-z .&'-]+?)\s+(\d{1,3}\.\d)%?", seg):
        name = re.sub(r"\s+", " ", m.group(1)).strip()
        if name and name[0].isupper() and name not in d:
            d[name] = float(m.group(2))
    return d

def duration(t):
    m = re.search(r"duration\s+(\d+\.\d)\s*years", t)
    return float(m.group(1)) if m else None

# 1) pesi LS60 (31 mar 2026) dalla serie già validata (ls_timeseries.json)
import json
KWMAP = {"all-world":"All-World","developed-world":"Developed World","north-america":"North America",
 "emerging":"Emerging","dev-europe":"Developed Europe","japan":"Japan","asia-pac":"Asia Pacific",
 "global-agg":"Global Aggregate","usd-treasury":"USD Treasury","eur-govt":"Eurozone Government",
 "usd-corp":"USD Corporate","eur-corp":"EUR Corporate","uk-gilt":"Gilt"}
ts = json.load(open(os.path.join(os.path.dirname(__file__),"ls_timeseries.json")))
ls60 = next(r["fondi"]["60"] for r in ts if r["data_riferimento"]=="2026-03-31")
weights = {}
for f, kw in KWMAP.items():
    for h in ls60["holdings"]:
        if kw in h["etf"]:
            weights[f] = h["peso"]; break
print("Pesi LS60 riconosciuti (mar 2026):", {k: weights.get(k) for k in FILES})
print(f"  somma pesi = {round(sum(weights.values()),1)}%\n")

# 2) composizione interna di ciascun sottostante
comp = {}
for f, kw in FILES.items():
    t = text(f + ".pdf")
    comp[f] = {"us": countries(t).get("United States"), "dur": duration(t) if f in BONDS else None,
               "countries": countries(t)}
    tag = "BOND" if f in BONDS else "EQ  "
    print(f"{tag} {f:<15} US={str(comp[f]['us']):>6}  dur={str(comp[f]['dur']):>5}  w={str(weights.get(f)):>5}")

# 3) ricostruzione peso USA totale
usw = sum((weights.get(f,0)/100.0)*(comp[f]['us'] or 0) for f in FILES)
# 4) duration del solo comparto bond (media pesata sui pesi-bond)
bw = sum(weights.get(f,0) for f in BONDS)
dur = sum(weights.get(f,0)*(comp[f]['dur'] or 0) for f in BONDS)/bw if bw else None

print("\n=== QUADRATURA (nostro ricalcolo mag-2026 vs Vanguard pubblicato mar-2026) ===")
print(f"  Peso USA ricostruito : {usw:.1f}%   |  Vanguard pubblicato: 57.7%   -> scarto {usw-57.7:+.1f}")
print(f"  Duration bond ricostr: {dur:.2f} anni |  Vanguard pubblicato: 6.3 anni -> scarto {dur-6.3:+.2f}")
