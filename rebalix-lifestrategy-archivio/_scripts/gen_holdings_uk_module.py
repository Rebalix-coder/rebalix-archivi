#!/usr/bin/env python3
"""Rigenera lib/blog/ls-holdings-uk.ts: il PANIERE dei cinque LifeStrategy INGLESI (OEIC, GBP),
incluso il LifeStrategy 100 che la gamma in euro non ha. Fonte: composizione ufficiale dei
sottostanti comunicata da Vanguard UK (endpoint borHoldings). Le linee di liquidità/cambio
(CRNY, MM.CASH) sono accorpate in una voce netta. Chiamato dall'archiviatore."""
import os, sys, json, urllib.request
from collections import OrderedDict

DEST = os.path.expanduser("~/progetti/rebalix/lib/blog/ls-holdings-uk.ts")
EP = "https://www.vanguard.co.uk/gpx/graphql"
PORT = {"20": "9233", "40": "9236", "60": "9239", "80": "9242", "100": "9232"}
Q = "query($portIds:[String!]){borHoldings(portIds:$portIds){holdings(limit:1500){items{issuerName securityLongDescription marketValuePercentage securityType effectiveDate}}}}"

def fetch(pid):
    req = urllib.request.Request(EP, data=json.dumps({"query": Q, "variables": {"portIds": [pid]}}).encode(),
        headers={"Content-Type": "application/json", "X-Consumer-ID": "b2b", "User-Agent": "Mozilla/5.0"})
    d = json.loads(urllib.request.urlopen(req, timeout=45).read())
    return d["data"]["borHoldings"][0]["holdings"]["items"]

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print(f"[uk] repo non trovato ({DEST}) — salto."); return
    funds, eff = {}, ""
    for lvl, pid in PORT.items():
        items = fetch(pid)
        rows, cash = [], 0.0
        for it in items:
            pct = it.get("marketValuePercentage")
            if pct is None: continue
            pct = float(pct)
            st = (it.get("securityType") or "").upper()
            if st in ("CRNY", "MM.CASH") or not it.get("securityLongDescription") and not it.get("issuerName"):
                cash += pct; continue
            name = (it.get("securityLongDescription") or it.get("issuerName") or "").strip()
            if name: rows.append({"name": name, "pct": pct})
            if it.get("effectiveDate"): eff = str(it["effectiveDate"])[:10]
        # accorpa eventuali duplicati per nome, ordina desc, arrotonda
        agg = OrderedDict()
        for r in rows: agg[r["name"]] = agg.get(r["name"], 0.0) + r["pct"]
        out = sorted(({"name": k, "pct": round(v, 1)} for k, v in agg.items() if abs(v) >= 0.05), key=lambda x: -x["pct"])
        if abs(cash) >= 0.05: out.append({"name": "Liquidità e cambio (netto)", "pct": round(cash, 1)})
        funds[lvl] = out
    def arr(lst):
        return "[\n      " + ",\n      ".join(f'{{ name: {json.dumps(x["name"], ensure_ascii=False)}, pct: {x["pct"]:g} }}' for x in lst) + ",\n    ]"
    order = ["20", "40", "60", "80", "100"]
    body = f'''/**
 * Paniere dei cinque Vanguard LifeStrategy INGLESI (OEIC, in sterline), incluso il
 * LifeStrategy 100 che la gamma in euro non ha. Composizione ufficiale dei sottostanti
 * comunicata da Vanguard UK. Liquidità/cambio accorpate in una voce netta.
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_holdings_uk_module.py`.
 */
export type Holding = {{ name: string; pct: number }}
export type LsHoldingsUk = {{ updated: string; funds: Record<'20' | '40' | '60' | '80' | '100', Holding[]> }}

export const LS_HOLDINGS_UK: LsHoldingsUk = {{
  updated: '{eff[:7]}',
  funds: {{
{chr(10).join(f"    '{k}': {arr(funds[k])}," for k in order)}
  }},
}}
'''
    open(DEST, "w").write(body)
    print(f"[uk] scritto {DEST}: eff {eff[:7]} · LS20 {len(funds['20'])} / LS100 {len(funds['100'])} righe")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"[uk] ERRORE: {e}", file=sys.stderr); sys.exit(1)
