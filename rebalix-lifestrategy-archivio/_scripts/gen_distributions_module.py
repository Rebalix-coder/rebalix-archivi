#!/usr/bin/env python3
"""Rigenera lib/blog/ls-distributions.ts: lo STORICO DISTRIBUZIONI (cedole) dei quattro
Vanguard LifeStrategy a DISTRIBUZIONE (EUR). Tutto NATIVO-VANGUARD, così combacia con la
pagina ufficiale al centesimo:
- importo per quota = `distributionAmount` (INC) del GraphQL `periodicDistributions`;
- rendimento per-cedola = importo / `reinvestPrice` (il prezzo Vanguard alla data di stacco);
- rendimento storico a 12 mesi = `YLDHIST` (il «Rendimento storico» mostrato in pagina).
Fonte: GraphQL pubblico Vanguard IT, header b2b. Chiamato dall'archiviatore."""
import os, sys, json, urllib.request
from collections import OrderedDict

DEST = os.path.expanduser("~/progetti/rebalix/lib/blog/ls-distributions.ts")
EP = "https://www.it.vanguard/gpx/graphql"
# portId del fondo a DISTRIBUZIONE per livello (i gemelli ad accumulo sono i pari sotto)
PORT = {"20": "9491", "40": "9493", "60": "9495", "80": "9497"}
Q = ("query($portIds:[String!]!,$startDate:String){"
     "funds(portIds:$portIds){portId profile{fundCurrency}"
     "distributionDetails{periodicDistributions(limit:0,startDate:$startDate){items{"
     "exDividendDate payableDate reinvestPrice "
     "taxDetails{totalDistributionAmount distributionAmount currencyCode}}}}}"
     "polarisAnalyticsHistory(portIds:$portIds){monthly{yields{fund(getLatest:true){items{codes{"
     "YLDHIST{percent effectiveDate}}}}}}}}")

def fetch(pid):
    body = json.dumps({"query": Q, "variables": {"portIds": [pid], "startDate": "2018-01-01"}}).encode()
    req = urllib.request.Request(EP, data=body, headers={
        "Content-Type": "application/json", "X-Consumer-ID": "b2b", "User-Agent": "Mozilla/5.0"})
    return json.loads(urllib.request.urlopen(req, timeout=45).read())["data"]

def amount(td_list):
    """Importo per quota = distributionAmount (INC). `totalDistributionAmount` è tipicamente null."""
    if not td_list: return None
    td = td_list[0]
    v = td.get("distributionAmount")
    if v is None: v = td.get("totalDistributionAmount")
    return float(v) if v is not None else None

def yield_hist(d):
    """Rendimento storico ufficiale (YLDHIST) + data: quello mostrato sulla pagina Vanguard."""
    try:
        codes = d["polarisAnalyticsHistory"][0]["monthly"]["yields"]["fund"]["items"][0]["codes"]
        y = codes.get("YLDHIST")
        if y and y.get("percent") is not None:
            return round(float(y["percent"]), 2), (y.get("effectiveDate") or "")[:10]
    except Exception:
        pass
    return None, ""

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print(f"[dist] repo non trovato ({DEST}) — salto."); return
    funds, cur, last, asof = {}, "EUR", "", ""
    for lvl, pid in PORT.items():
        d = fetch(pid)
        f = (d.get("funds") or [{}])[0]
        cur = (f.get("profile") or {}).get("fundCurrency") or cur
        rows = []
        for it in ((f.get("distributionDetails") or {}).get("periodicDistributions") or {}).get("items", []):
            amt = amount(it.get("taxDetails"))
            ex = (it.get("exDividendDate") or "")[:10]
            if amt is None or not ex: continue
            rp = it.get("reinvestPrice")
            y = round(100 * amt / float(rp), 2) if rp else None  # rendimento per-cedola (prezzo Vanguard)
            rows.append({"ex": ex, "pay": (it.get("payableDate") or "")[:10], "amount": round(amt, 6), "y": y})
        agg = OrderedDict()
        for r in rows: agg[r["ex"]] = r
        out = sorted(agg.values(), key=lambda x: x["ex"], reverse=True)
        if out: last = max(last, out[0]["ex"])
        yh, ya = yield_hist(d)
        if ya: asof = max(asof, ya)
        funds[lvl] = {"yield12m": yh, "items": out}
        print(f"[dist] LS{lvl} (port {pid}): {len(out)} distribuzioni, rendimento storico {yh} (al {ya})")

    def arr(items):
        if not items: return "[]"
        return "[\n        " + ",\n        ".join(
            f'{{ ex: {json.dumps(x["ex"])}, pay: {json.dumps(x["pay"])}, amount: {x["amount"]:g}, y: {json.dumps(x.get("y"))} }}' for x in items
        ) + ",\n      ]"
    order = ["20", "40", "60", "80"]
    body = f'''/**
 * Storico distribuzioni (cedole) dei quattro Vanguard LifeStrategy a DISTRIBUZIONE (EUR).
 * Tutto nativo-Vanguard (combacia con la pagina ufficiale): `amount` = importo lordo per
 * quota; `y` = rendimento per-cedola (importo / reinvestPrice Vanguard); `yield12m` =
 * «Rendimento storico» ufficiale a 12 mesi (YLDHIST) al {asof or '—'}.
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_distributions_module.py`.
 */
export type Distribution = {{ ex: string; pay: string; amount: number; y: number | null }}
export type LsDistributions = {{
  updated: string
  yieldAsof: string
  currency: string
  funds: Record<'20' | '40' | '60' | '80', {{ yield12m: number | null; items: Distribution[] }}>
}}

export const LS_DISTRIBUTIONS: LsDistributions = {{
  updated: {json.dumps(last[:7])},
  yieldAsof: {json.dumps(asof)},
  currency: {json.dumps(cur)},
  funds: {{
{chr(10).join(f"    '{k}': {{ yield12m: {json.dumps(funds[k]['yield12m'])}, items: {arr(funds[k]['items'])} }}," for k in order)}
  }},
}}
'''
    open(DEST, "w").write(body)
    print(f"[dist] scritto {DEST}: aggiornato {last[:7]}, rendimento al {asof}, valuta {cur}")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"[dist] ERRORE: {e}", file=sys.stderr); sys.exit(1)
