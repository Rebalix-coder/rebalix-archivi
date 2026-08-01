#!/usr/bin/env python3
"""Sezione 3 per TUTTI e 4 i LS (20/40/60/80) dalla GraphQL ufficiale Vanguard.
Cache per portId (ogni sleeve interrogato una volta). Mostra come scala col rischio."""
import json, urllib.request, os
from collections import defaultdict

EP="https://www.it.vanguard/gpx/graphql"
PORT={"FTSE All-World":("9679","eq"),"FTSE Developed World":("9675","eq"),"FTSE North America":("9680","eq"),
 "FTSE Emerging Markets":("9678","eq"),"FTSE Developed Europe":("9520","eq"),"FTSE Japan":("9674","eq"),
 "FTSE Developed Asia Pacific":("9522","eq"),"S&P 500":("9694","eq"),
 "Global Aggregate":("9443","bd"),"USD Treasury":("9518","bd"),"Eurozone Government":("9591","bd"),
 "USD Corporate":("9516","bd"),"EUR Corporate":("9659","bd"),"Gilt":("9519","bd")}

def gql(q,port,extra=None):
    v={"p":[port]};
    if extra:v.update(extra)
    req=urllib.request.Request(EP,data=json.dumps({"query":q,"variables":v}).encode(),
        headers={"Content-Type":"application/json","X-Consumer-ID":"b2b","Origin":"https://www.it.vanguard","User-Agent":"Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req,timeout=30).read()).get("data")
Q_CO="query($p:[String!]!){funds(portIds:$p){marketAllocation{countryName fundMktPercent holdingStatCode}}}"
Q_SE="query($p:[String!]!){funds(portIds:$p){sectorDiversification{sectorName fundPercent}}}"
Q_CR="query($p:[String!]!,$l:Boolean){creditQualityHistory(portIds:$p){creditQuality(getLatest:$l){compositions{name value}}}}"
Q_MA="query($p:[String!]!,$l:Boolean){maturityHistory(portIds:$p){maturity(getLatest:$l){compositions{name value}}}}"

CACHE={}
def sleeve_data(port):
    if port in CACHE: return CACHE[port]
    ma=(gql(Q_CO,port)["funds"][0].get("marketAllocation")) or []
    by=defaultdict(dict)
    for r in ma:
        if r["countryName"] and r["fundMktPercent"] is not None: by[r["holdingStatCode"]][r["countryName"]]=r["fundMktPercent"]
    co=max(by.items(),key=lambda kv:(kv[0].startswith("FTC"),95<=sum(kv[1].values())<=105,sum(kv[1].values())))[1] if by else {}
    se={r["sectorName"]:r["fundPercent"] for r in (gql(Q_SE,port)["funds"][0].get("sectorDiversification") or []) if r["fundPercent"] is not None}
    def comp(q,root,sub):
        d=gql(q,port,{"l":True})
        try:return {r["name"]:r["value"] for r in d[root][0][sub][0]["compositions"] if r.get("value") is not None}
        except:return {}
    cr=comp(Q_CR,"creditQualityHistory","creditQuality")
    mt=comp(Q_MA,"maturityHistory","maturity")
    CACHE[port]=(co,se,cr,mt); return CACHE[port]

ts=json.load(open(os.path.join(os.path.dirname(__file__),"ls_timeseries.json")))
rec=next(r for r in ts if r["data_riferimento"]=="2026-03-31")
def fund_agg(eq):
    hold=rec["fondi"][eq]["holdings"]
    W={};
    for kw,(port,typ) in PORT.items():
        for h in hold:
            if kw in h["etf"]: W[kw]=h["peso"];break
    eqW=sum(v for k,v in W.items() if PORT[k][1]=="eq"); bdW=sum(v for k,v in W.items() if PORT[k][1]=="bd")
    geo,sec,cred,mat=defaultdict(float),defaultdict(float),defaultdict(float),defaultdict(float)
    for kw,w in W.items():
        port,typ=PORT[kw]; co,se,cr,mt=sleeve_data(port)
        for c,p in co.items(): geo[c]+=w/100.0*p
        if typ=="eq":
            for s,p in se.items(): sec[s]+=w/eqW*p
        else:
            for n,p in cr.items(): cred[n]+=w/bdW*p
            for n,p in mt.items(): mat[n]+=w/bdW*p
    return eqW,bdW,geo,sec,cred,mat

funds={}
for eq in ["20","40","60","80"]: funds[eq]=fund_agg(eq)

print(f"{'':<22}" + "".join(f"LS{e:>8}" for e in ["20","40","60","80"]))
print("azioni/bond".ljust(22)+"".join(f"{funds[e][0]:.0f}/{funds[e][1]:.0f}".rjust(10) for e in ["20","40","60","80"]))
for label,idx,key in [("USA %",2,"United States"),("Cina %",2,"China"),("Italia %",2,"Italy"),
                      ("Tech %",3,"Technology"),("Finanziari %",3,"Financials"),
                      ("bond AAA+AA %",4,None),("bond BBB %",4,"BBB"),("scad. 1-5a %",5,"1 - 5 Years")]:
    row=label.ljust(22)
    for e in ["20","40","60","80"]:
        d=funds[e][idx]
        if key: v=d.get(key,0)
        else: v=d.get("AAA",0)+d.get("AA",0)
        row+=f"{v:>10.1f}"
    print(row)
