#!/usr/bin/env python3
"""Rigenera lib/blog/ls-holdings.ts del sito dal record più recente di ls_timeseries.json:
il PANIERE (mattoncini ETF + peso %) dei quattro LifeStrategy. Chiamato dall'archiviatore."""
import json, os, sys

ARCHIVE = os.path.expanduser("~/backups/rebalix-lifestrategy-archivio")
TS_JSON = os.path.join(ARCHIVE, "_scripts", "ls_timeseries.json")
DEST = os.path.expanduser("~/progetti/rebalix/lib/blog/ls-holdings.ts")

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print(f"[holdings] repo non trovato ({DEST}) — salto."); return
    d = sorted(json.load(open(TS_JSON)), key=lambda r: r["data_riferimento"])
    rec = d[-1]
    funds = {}
    for lvl in ["20", "40", "60", "80"]:
        h = rec["fondi"].get(lvl, {}).get("holdings", [])
        funds[lvl] = [{"name": x["etf"].strip(), "pct": round(x["peso"], 1)} for x in h]
    def arr(lst):
        return "[\n      " + ",\n      ".join(f'{{ name: {json.dumps(x["name"], ensure_ascii=False)}, pct: {x["pct"]:g} }}' for x in lst) + ",\n    ]"
    body = f'''/**
 * Paniere (mattoncini ETF + peso %) dei quattro Vanguard LifeStrategy — Livello A: numeri
 * PUBBLICATI da Vanguard nel report trimestrale (nostro archivio). Somma ~100% per fondo.
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_holdings_module.py`. Non
 * modificare a mano.
 */
export type Holding = {{ name: string; pct: number }}
export type LsHoldings = {{ updated: string; funds: Record<'20' | '40' | '60' | '80', Holding[]> }}

export const LS_HOLDINGS: LsHoldings = {{
  updated: '{rec["data_riferimento"][:7]}',
  funds: {{
    '20': {arr(funds["20"])},
    '40': {arr(funds["40"])},
    '60': {arr(funds["60"])},
    '80': {arr(funds["80"])},
  }},
}}
'''
    open(DEST, "w").write(body)
    print(f"[holdings] scritto {DEST}: LS20 {len(funds['20'])} / LS40 {len(funds['40'])} / LS60 {len(funds['60'])} / LS80 {len(funds['80'])} mattoncini, trimestre {rec['data_riferimento'][:7]}")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"[holdings] ERRORE: {e}", file=sys.stderr); sys.exit(1)
