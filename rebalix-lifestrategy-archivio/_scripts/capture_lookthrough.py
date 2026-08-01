#!/usr/bin/env python3
"""Cattura mensile del look-through GraphQL ufficiale Vanguard (tutti e 4 i LS).
Salva uno snapshot datato in <ARCHIVE>/lookthrough/{effectiveDate}.json.
Auto-dedup: se lo snapshot di quella data esiste già, non fa nulla.
Serve ad ACCUMULARE la storia granulare da oggi (l'API dà solo la foto corrente)."""
import json, urllib.request, os, sys, datetime
from collections import defaultdict

ARCHIVE = os.path.expanduser("~/backups/rebalix-lifestrategy-archivio")
EP = "https://www.it.vanguard/gpx/graphql"
PORT={"FTSE All-World":("9679","eq"),"FTSE Developed World":("9675","eq"),"FTSE North America":("9680","eq"),
 "FTSE Emerging Markets":("9678","eq"),"FTSE Developed Europe":("9520","eq"),"FTSE Japan":("9674","eq"),
 "FTSE Developed Asia Pacific":("9522","eq"),"S&P 500":("9694","eq"),
 "Global Aggregate":("9443","bd"),"USD Treasury":("9518","bd"),"Eurozone Government":("9591","bd"),
 "USD Corporate":("9516","bd"),"EUR Corporate":("9659","bd"),"Gilt":("9519","bd")}
def gql(q,port,extra=None):
    v={"p":[port]}
    if extra: v.update(extra)
    req=urllib.request.Request(EP,data=json.dumps({"query":q,"variables":v}).encode(),
        headers={"Content-Type":"application/json","X-Consumer-ID":"b2b","Origin":"https://www.it.vanguard","User-Agent":"Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req,timeout=45).read()).get("data")
Q_CO="query($p:[String!]!){funds(portIds:$p){marketAllocation{date countryName fundMktPercent holdingStatCode}}}"
Q_SE="query($p:[String!]!){funds(portIds:$p){sectorDiversification{sectorName fundPercent}}}"
Q_CR="query($p:[String!]!,$l:Boolean){creditQualityHistory(portIds:$p){creditQuality(getLatest:$l){compositions{name value}}}}"
Q_MA="query($p:[String!]!,$l:Boolean){maturityHistory(portIds:$p){maturity(getLatest:$l){compositions{name value}}}}"
CACHE={}; EFFDATE=[None]
def sleeve(port):
    if port in CACHE: return CACHE[port]
    ma=(gql(Q_CO,port)["funds"][0].get("marketAllocation")) or []
    for r in ma:
        if r.get("date"): EFFDATE[0]=r["date"]; break
    by=defaultdict(dict)
    for r in ma:
        if r["countryName"] and r["fundMktPercent"] is not None: by[r["holdingStatCode"]][r["countryName"]]=r["fundMktPercent"]
    co=max(by.items(),key=lambda kv:(kv[0].startswith("FTC"),95<=sum(kv[1].values())<=105,sum(kv[1].values())))[1] if by else {}
    se={r["sectorName"]:r["fundPercent"] for r in (gql(Q_SE,port)["funds"][0].get("sectorDiversification") or []) if r["fundPercent"] is not None}
    def comp(q,root,sub):
        d=gql(q,port,{"l":True})
        try:return {r["name"]:r["value"] for r in d[root][0][sub][0]["compositions"] if r.get("value") is not None}
        except:return {}
    CACHE[port]=(co,se,comp(Q_CR,"creditQualityHistory","creditQuality"),comp(Q_MA,"maturityHistory","maturity"))
    return CACHE[port]

def main():
    # controllo-data economico: una sola chiamata per sapere l'effectiveDate e dedup subito
    sleeve("9679")
    date0=EFFDATE[0] or datetime.date.today().isoformat()
    dest0=os.path.join(ARCHIVE,"lookthrough",date0+".json")
    if os.path.exists(dest0):
        print(f"[capture] snapshot {date0} già presente — niente da fare."); return
    # pesi correnti dei 4 fondi dall'ultima serie parsata
    tsf=os.path.join(os.path.dirname(os.path.abspath(__file__)),"ls_timeseries.json")
    ts=json.load(open(tsf))
    rec=max(ts,key=lambda r:r["data_riferimento"])
    snap={"weights_asof":rec["data_riferimento"],"funds":{}}
    for eq in ["20","40","60","80"]:
        hold=rec["fondi"].get(eq,{}).get("holdings",[]); W={}
        for kw,(port,typ) in PORT.items():
            for h in hold:
                if kw in h["etf"]: W[kw]=h["peso"];break
        eqW=sum(v for k,v in W.items() if PORT[k][1]=="eq") or 1
        bdW=sum(v for k,v in W.items() if PORT[k][1]=="bd") or 1
        geo,geo_eq,geo_bd,sec,cred,mat=defaultdict(float),defaultdict(float),defaultdict(float),defaultdict(float),defaultdict(float),defaultdict(float)
        for kw,w in W.items():
            port,typ=PORT[kw]; co,se,cr,mt=sleeve(port)
            for c,p in co.items(): geo[c]+=w/100.0*p  # geografia sull'intero portafoglio
            if typ=="eq":
                for c,p in co.items(): geo_eq[c]+=w/eqW*p  # geografia della SOLA parte azionaria
                for s,p in se.items(): sec[s]+=w/eqW*p
            else:
                for c,p in co.items(): geo_bd[c]+=w/bdW*p  # geografia della SOLA parte obbligazionaria
                for n,p in cr.items(): cred[n]+=w/bdW*p
                for n,p in mt.items(): mat[n]+=w/bdW*p
        rnd=lambda d:{k:round(v,3) for k,v in d.items()}
        snap["funds"][eq]={"paesi":rnd(geo),"paesi_azioni":rnd(geo_eq),"paesi_obblig":rnd(geo_bd),"settori":rnd(sec),"credito":rnd(cred),"scadenze":rnd(mat)}
    date=EFFDATE[0] or datetime.date.today().isoformat()
    snap["effective_date"]=date
    outdir=os.path.join(ARCHIVE,"lookthrough"); os.makedirs(outdir,exist_ok=True)
    dest=os.path.join(outdir,date+".json")
    if os.path.exists(dest):
        print(f"[capture] snapshot {date} già presente — niente da fare."); return
    json.dump(snap,open(dest,"w"),ensure_ascii=False,indent=1)
    print(f"[capture] salvato snapshot look-through {date} -> lookthrough/{date}.json")

if __name__=="__main__":
    try: main()
    except Exception as e:
        print(f"[capture] ERRORE: {e}", file=sys.stderr); sys.exit(1)
