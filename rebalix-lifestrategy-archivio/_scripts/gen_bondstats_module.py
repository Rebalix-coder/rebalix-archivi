#!/usr/bin/env python3
"""Rigenera lib/blog/ls-bondstats.ts: le statistiche della parte OBBLIGAZIONARIA dei quattro
Vanguard LifeStrategy dal report trimestrale (ls_timeseries.json, estratto da parse_ls):
duration modificata e rendimento a scadenza (uguali per tutti = stessi mattoncini bond) + la
quota di bond per linea. Da qui il sito ricava la sensibilità ai tassi del fondo intero
(duration × %bond). Chiamato dall'archiviatore."""
import os, sys, json

ARCHIVE = os.path.expanduser("~/backups/rebalix-lifestrategy-archivio")
DEST = os.path.expanduser("~/progetti/rebalix/lib/blog/ls-bondstats.ts")
SRC = os.path.join(ARCHIVE, "_scripts", "ls_timeseries.json")
BOND = ("Bond", "Treasury", "Gilt", "Government", "Aggregate", "Corporate")

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print(f"[bond] repo non trovato ({DEST}) — salto."); return
    ts = json.load(open(SRC))
    # ultimo trimestre che ha la duration (i report vecchi non la riportavano)
    rec = next((r for r in reversed(ts) if any(r["fondi"].get(l, {}).get("durata_modificata") for l in ("20", "40", "60", "80"))), None)
    if not rec:
        print("[bond] nessuna duration nei report — salto."); return
    funds = {}
    for lv in ("20", "40", "60", "80"):
        f = rec["fondi"].get(lv, {})
        bondpct = round(sum(h["peso"] for h in f.get("holdings", []) if any(b in h["etf"] for b in BOND)), 1)
        funds[lv] = {
            "duration": f.get("durata_modificata"),
            "ytm": f.get("rendimento_scadenza"),
            "bondPct": bondpct,
        }
    body = f'''/**
 * Statistiche della parte OBBLIGAZIONARIA dei quattro Vanguard LifeStrategy, dal report
 * trimestrale ufficiale: `duration` (modificata, in anni), `ytm` (rendimento a scadenza %) e
 * `bondPct` (quota di obbligazioni della linea). Duration e YTM sono ~uguali per tutte le linee
 * (stessi ETF obbligazionari sotto); la sensibilità ai tassi del FONDO INTERO = duration × bondPct.
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_bondstats_module.py`.
 */
export type LsBondStats = {{
  updated: string
  funds: Record<'20' | '40' | '60' | '80', {{ duration: number; ytm: number; bondPct: number }}>
}}

export const LS_BONDSTATS: LsBondStats = {{
  updated: '{rec["data_riferimento"][:7]}',
  funds: {{
{chr(10).join(f"    '{k}': {{ duration: {funds[k]['duration']:g}, ytm: {funds[k]['ytm']:g}, bondPct: {funds[k]['bondPct']:g} }}," for k in ('20','40','60','80'))}
  }},
}}
'''
    open(DEST, "w").write(body)
    print(f"[bond] scritto {DEST}: {rec['data_riferimento'][:7]} · duration LS20 {funds['20']['duration']} / YTM {funds['20']['ytm']}%")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"[bond] ERRORE: {e}", file=sys.stderr); sys.exit(1)
