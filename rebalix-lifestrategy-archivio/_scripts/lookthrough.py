#!/usr/bin/env python3
"""Look-through completo LS60: aggrega paesi/settori/credito dei 13 sottostanti,
pesati per la composizione LS60 (mar-2026). Split azioni/bond come il foglio del forum.
Fonte: factsheet ufficiali Vanguard (31 mag 2026). Riconciliazione USA vs pubblicato."""
import pdfplumber, re, os, json
from collections import defaultdict

FS = os.path.join(os.path.dirname(__file__), "factsheets")
EQUITY = {"all-world","developed-world","north-america","emerging","dev-europe","japan","asia-pac","sp500"}
BOND   = {"global-agg","usd-treasury","eur-govt","usd-corp","eur-corp","uk-gilt"}
KW = {"all-world":"All-World","developed-world":"Developed World","north-america":"North America",
 "emerging":"Emerging","dev-europe":"Developed Europe","japan":"Japan","asia-pac":"Asia Pacific",
 "sp500":"S&P 500","global-agg":"Global Aggregate","usd-treasury":"USD Treasury",
 "eur-govt":"Eurozone Government","usd-corp":"USD Corporate","eur-corp":"EUR Corporate","uk-gilt":"Gilt"}

def text(f):
    with pdfplumber.open(os.path.join(FS, f+".pdf")) as pdf:
        return "\n".join(pg.extract_text() or "" for pg in pdf.pages)

def countries(t):
    i = t.find("Market allocation")
    if i < 0: return {}
    seg = t[i+len("Market allocation"):]
    # il blocco paesi finisce alla prossima sezione
    stops = [seg.find(s) for s in ("Distribution by","Source","Sector categories","Glossary") if seg.find(s)>0]
    if stops: seg = seg[:min(stops)]
    d = {}
    for m in re.finditer(r"([A-Z][A-Za-z .&'-]+?)\s+(\d{1,3}\.\d)%?", seg):
        name = re.sub(r"\s+"," ",m.group(1)).strip()
        if name and name[0].isupper() and name not in d and name not in ("Market","Source"):
            d[name] = float(m.group(2))
    return d

def maturity(t):
    i = t.find("Distribution by credit maturity")
    if i < 0: return {}
    seg = t[i:t.find("Distribution by credit quality", i) if t.find("Distribution by credit quality",i)>0 else i+400]
    d = {}
    for m in re.finditer(r"((?:Under|Over)?\s?[\d]{0,2}\s?-?\s?[\d]{1,2}\s?(?:Year|Years)?)\s+(\d{1,2}\.\d)", seg):
        lbl = re.sub(r"\s+"," ",m.group(1)).strip()
        if re.search(r"\d", lbl): d[lbl] = float(m.group(2))
    return d

def sectors(t):
    # blocco settori ICB, tra "Sector"/"Industry" e "Market allocation"
    i = t.find("Market allocation")
    seg = t[max(0,i-600):i] if i>0 else t
    d = {}
    for m in re.finditer(r"([A-Z][A-Za-z ]+?)\s+(\d{1,2}\.\d)%?", seg):
        name = m.group(1).strip()
        if name in ("Technology","Financials","Health Care","Consumer Discretionary","Consumer Staples",
                    "Industrials","Energy","Utilities","Real Estate","Telecommunications","Basic Materials",
                    "Materials","Communication Services"):
            d[name] = float(m.group(2))
    return d

def credit(t):
    d = {}
    for r in ["AAA","AA","A","BBB","Not Rated","Less than BBB"]:
        m = re.search(rf"\b{re.escape(r)}\s+(\d{{1,2}}\.\d)%?", t)
        if m: d[r] = float(m.group(1))
    return d

# pesi LS60 mar-2026
ts = json.load(open(os.path.join(os.path.dirname(__file__),"ls_timeseries.json")))
ls60 = next(r["fondi"]["60"] for r in ts if r["data_riferimento"]=="2026-03-31")
W = {}
for f,kw in KW.items():
    for h in ls60["holdings"]:
        if kw in h["etf"]: W[f]=h["peso"]; break

geo_eq, geo_bd, sec_agg, cred_agg, mat_agg = (defaultdict(float) for _ in range(5))
eqW = sum(W[f] for f in EQUITY if f in W); bdW = sum(W[f] for f in BOND if f in W)
for f in W:
    t = text(f); w = W[f]/100.0
    for c,p in countries(t).items():
        (geo_eq if f in EQUITY else geo_bd)[c] += w*p/100.0
    if f in EQUITY:
        for s,p in sectors(t).items(): sec_agg[s] += (W[f]/eqW)*p  # settori = % del solo azionario
    if f in BOND:
        for r,p in credit(t).items(): cred_agg[r] += (W[f]/bdW)*p
        for lbl,p in maturity(t).items(): mat_agg[lbl] += (W[f]/bdW)*p

def show(title, d, tot=None):
    print(f"\n{title}" + (f"  (somma {sum(d.values())*(100 if tot=='frac' else 1):.1f})" if d else ""))
    for k,v in sorted(d.items(), key=lambda x:-x[1])[:14]:
        print(f"   {v*100 if tot=='frac' else v:5.1f}  {k}")

print(f"Pesi LS60: azioni={eqW:.1f}%  bond={bdW:.1f}%")
# geografia totale (azioni+bond) per paese
geo_tot = defaultdict(float)
for c,v in geo_eq.items(): geo_tot[c]+=v
for c,v in geo_bd.items(): geo_tot[c]+=v
show("PAESI (intero portafoglio, % del totale)", geo_tot, 'frac')
print(f"\n   di cui USA: azioni {geo_eq['United States']*100:.1f} + bond {geo_bd['United States']*100:.1f} = {geo_tot['United States']*100:.1f}%  | Vanguard pubblicato 57,7%")
show("SETTORI (azionario)", sec_agg)
show("CREDITO (obbligazionario)", cred_agg)
show("SCADENZE (obbligazionario)", mat_agg)
