#!/usr/bin/env python3
"""Look-through LS60 dalla GraphQL UFFICIALE di Vanguard (marketAllocation completa,
tutti i paesi). Aggrega i 13 sottostanti pesati. Cattura anche la Cina obbligazionaria."""
import json, urllib.request, os
from collections import defaultdict

EP = "https://www.it.vanguard/gpx/graphql"
# nome-sleeve -> (portId it.vanguard, tipo)
SLEEVES = {
 "FTSE All-World":("9679","eq"), "FTSE Developed World":("9675","eq"),
 "FTSE North America":("9680","eq"), "FTSE Emerging Markets":("9678","eq"),
 "FTSE Developed Europe":("9520","eq"), "FTSE Japan":("9674","eq"),
 "FTSE Developed Asia Pacific":("9522","eq"),
 "Global Aggregate":("9443","bd"), "USD Treasury":("9518","bd"),
 "Eurozone Government":("9591","bd"), "USD Corporate":("9516","bd"),
 "EUR Corporate":("9659","bd"), "Gilt":("9519","bd"),
}

def market_alloc(port):
    q = {"query":"query($p:[String!]!){funds(portIds:$p){profile{fundFullName} marketAllocation{countryName fundMktPercent holdingStatCode}}}",
         "variables":{"p":[port]}}
    req = urllib.request.Request(EP, data=json.dumps(q).encode(),
        headers={"Content-Type":"application/json","X-Consumer-ID":"b2b",
                 "Origin":"https://www.it.vanguard","User-Agent":"Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=30).read())["data"]["funds"]
    if not d: return None, []
    return d[0]["profile"]["fundFullName"], d[0].get("marketAllocation") or []

def clean_countries(ma):
    # raggruppa per schema di classificazione, salta i None
    by = defaultdict(dict)
    for r in ma:
        if r["countryName"] and r["fundMktPercent"] is not None:
            by[r["holdingStatCode"]][r["countryName"]] = r["fundMktPercent"]
    if not by: return {}
    # preferisci lo schema FTSE (FTCTYATPCS); altrimenti quello che somma ~100
    def score(code_dict):
        code, d = code_dict
        s = sum(d.values())
        return (code.startswith("FTC"), 1 if 95 <= s <= 105 else 0, s)
    best = max(by.items(), key=score)[1]
    return best

# pesi LS60 mar-2026
ts = json.load(open(os.path.join(os.path.dirname(__file__),"ls_timeseries.json")))
ls60 = next(r["fondi"]["60"] for r in ts if r["data_riferimento"]=="2026-03-31")
def weight(kw):
    for h in ls60["holdings"]:
        if kw in h["etf"]: return h["peso"]
    return None

agg = defaultdict(float); agg_eq = defaultdict(float); agg_bd = defaultdict(float)
print(f"{'sleeve':<28}{'peso':>6}{'paesi':>7}  Cina%")
for kw,(port,typ) in SLEEVES.items():
    w = weight(kw)
    if w is None: print(f"{kw:<28}  peso non trovato"); continue
    name, ma = market_alloc(port)
    cc = clean_countries(ma)
    china = cc.get("China",0)
    print(f"{kw:<28}{w:>6}{len(cc):>7}  {china:.2f}")
    for country,pct in cc.items():
        agg[country] += (w/100.0)*pct
        (agg_eq if typ=="eq" else agg_bd)[country] += (w/100.0)*pct

print(f"\n=== LOOK-THROUGH LS60 (API ufficiale, somma {sum(agg.values()):.1f}%) ===")
for c,v in sorted(agg.items(), key=lambda x:-x[1])[:16]:
    print(f"  {v:5.2f}  {c}")
print(f"\nCINA totale = azioni {agg_eq.get('China',0):.2f} + bond {agg_bd.get('China',0):.2f} = {agg.get('China',0):.2f}%  | Vanguard pubblicato 2,5%")
