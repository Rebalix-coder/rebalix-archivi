#!/usr/bin/env python3
"""Sezione 3 completa del LS60 dalla GraphQL ufficiale Vanguard:
paesi + settori (azionario) + credito (bond) + scadenze (bond). Aggregati e pesati."""
import json, urllib.request, os
from collections import defaultdict

EP = "https://www.it.vanguard/gpx/graphql"
SLEEVES = {
 "FTSE All-World":("9679","eq"), "FTSE Developed World":("9675","eq"),
 "FTSE North America":("9680","eq"), "FTSE Emerging Markets":("9678","eq"),
 "FTSE Developed Europe":("9520","eq"), "FTSE Japan":("9674","eq"),
 "FTSE Developed Asia Pacific":("9522","eq"),
 "Global Aggregate":("9443","bd"), "USD Treasury":("9518","bd"),
 "Eurozone Government":("9591","bd"), "USD Corporate":("9516","bd"),
 "EUR Corporate":("9659","bd"), "Gilt":("9519","bd"),
}
def gql(query, port, extra=None):
    v = {"p":[port]};
    if extra: v.update(extra)
    req = urllib.request.Request(EP, data=json.dumps({"query":query,"variables":v}).encode(),
        headers={"Content-Type":"application/json","X-Consumer-ID":"b2b","Origin":"https://www.it.vanguard","User-Agent":"Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=30).read()).get("data")

Q_CO = "query($p:[String!]!){funds(portIds:$p){marketAllocation{countryName fundMktPercent holdingStatCode}}}"
Q_SE = "query($p:[String!]!){funds(portIds:$p){sectorDiversification{sectorName fundPercent}}}"
Q_CR = "query($p:[String!]!,$l:Boolean){creditQualityHistory(portIds:$p){creditQuality(getLatest:$l){compositions{name value}}}}"
Q_MA = "query($p:[String!]!,$l:Boolean){maturityHistory(portIds:$p){maturity(getLatest:$l){compositions{name value}}}}"

def countries(port):
    ma = (gql(Q_CO,port)["funds"][0].get("marketAllocation")) or []
    by=defaultdict(dict)
    for r in ma:
        if r["countryName"] and r["fundMktPercent"] is not None: by[r["holdingStatCode"]][r["countryName"]]=r["fundMktPercent"]
    if not by: return {}
    return max(by.items(), key=lambda kv:(kv[0].startswith("FTC"), 95<=sum(kv[1].values())<=105, sum(kv[1].values())))[1]
def sectors(port):
    sd=(gql(Q_SE,port)["funds"][0].get("sectorDiversification")) or []
    return {r["sectorName"]:r["fundPercent"] for r in sd if r["fundPercent"] is not None}
def comps(query,root,sub,port):
    d=gql(query,port,{"l":True})
    try: c=d[root][0][sub][0]["compositions"]
    except Exception: return {}
    return {r["name"]:r["value"] for r in (c or []) if r.get("value") is not None}

ts=json.load(open(os.path.join(os.path.dirname(__file__),"ls_timeseries.json")))
ls60=next(r["fondi"]["60"] for r in ts if r["data_riferimento"]=="2026-03-31")
def W(kw):
    for h in ls60["holdings"]:
        if kw in h["etf"]: return h["peso"]
    return 0
eqW=sum(W(k) for k,(p,t) in SLEEVES.items() if t=="eq")
bdW=sum(W(k) for k,(p,t) in SLEEVES.items() if t=="bd")

geo,sec,cred,mat=defaultdict(float),defaultdict(float),defaultdict(float),defaultdict(float)
for kw,(port,typ) in SLEEVES.items():
    w=W(kw)
    for c,p in countries(port).items(): geo[c]+=w/100.0*p
    if typ=="eq":
        for s,p in sectors(port).items(): sec[s]+=w/eqW*p
    else:
        for n,p in comps(Q_CR,"creditQualityHistory","creditQuality",port).items(): cred[n]+=w/bdW*p
        for n,p in comps(Q_MA,"maturityHistory","maturity",port).items(): mat[n]+=w/bdW*p

def show(t,d,n=12):
    print(f"\n{t}  (Σ {sum(d.values()):.1f})")
    for k,v in sorted(d.items(),key=lambda x:-x[1])[:n]: print(f"   {v:5.1f}  {k}")
show("PAESI (intero portafoglio)",geo,16)
show("SETTORI (azionario)",sec)
show("CREDITO (obbligazionario)",cred)
show("SCADENZE (obbligazionario)",mat)
