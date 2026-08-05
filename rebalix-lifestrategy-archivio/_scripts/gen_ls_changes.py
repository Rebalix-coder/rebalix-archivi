#!/usr/bin/env python3
"""Registro delle VARIAZIONI del paniere dei 4 Vanguard LifeStrategy (gemello di
gen_xd_changes sul lato Xtrackers, voluto da Linus 4/8/2026). Fonte: ls_timeseries.json
(i report TRIMESTRALI del nostro archivio) → confronto tra report consecutivi
DISPONIBILI (i due trimestri PDF-immagine non hanno holdings: il confronto salta al
successivo). Ricalcolato dall'intera storia a ogni giro: deterministico, niente stato.

EVENTI (soglie dichiarate in pagina):
- mattoncino che ENTRA/ESCE: segnalato solo se il peso in gioco è ≥ FLOOR (0,25%).
  Il report stampa i pesi arrotondati a 0,1: le gambe minime (0,0–0,1%) compaiono e
  scompaiono dalla tabella SENZA che la posizione cambi davvero — contarle come
  eventi pubblicherebbe falsi «entra/esce» (verificato: LS80 dic-2024, EUR Corp 0,1%
  e UK Gilt 0,0% «usciti» e «rientrati» il trimestre dopo → rumore, non eventi).
- peso: |Δ| ≥ 1,0 punti tra un report e il successivo disponibile.

La chiave è il NOME dell'ETF (il report trimestrale non espone ISIN dei mattoncini).
"""
import json, os, sys

ARCHIVE = os.path.expanduser("~/backups/rebalix-lifestrategy-archivio")
TS_JSON = os.path.join(ARCHIVE, "_scripts", "ls_timeseries.json")
REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "ls-changes.ts")

FONDI = ["20", "40", "60", "80"]
SOGLIA_PESO = 1.0   # punti percentuali
FLOOR = 0.25        # sotto: arrotondamento del report, non un evento


def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print("[ls-changes] repo non trovato — salto."); return
    data = sorted(json.load(open(TS_JSON)), key=lambda r: r["data_riferimento"])
    # trimestri con holdings per TUTTI i fondi che li hanno (i PDF-immagine restano fuori)
    quarters = []
    for r in data:
        per_fondo = {}
        for f in FONDI:
            hs = (r["fondi"].get(f) or {}).get("holdings") or []
            if hs:
                per_fondo[f] = {h["etf"]: h["peso"] for h in hs}
        if per_fondo:
            quarters.append((r["data_riferimento"][:10], per_fondo))
    if len(quarters) < 2:
        print("[ls-changes] meno di 2 report con holdings — salto."); return

    eventi = []
    baselines = {}
    for f in FONDI:
        avail = [(d, pf[f]) for d, pf in quarters if f in pf]
        if avail:
            baselines[f] = avail[0][0]
        for (d0, h0), (d1, h1) in zip(avail, avail[1:]):
            for name in sorted(set(h0) | set(h1)):
                a, b = h0.get(name), h1.get(name)
                if a is None and (b or 0) >= FLOOR:
                    eventi.append({"date": d1, "profile": f, "kind": "in", "name": name, "from": 0, "to": b})
                elif b is None and (a or 0) >= FLOOR:
                    eventi.append({"date": d1, "profile": f, "kind": "out", "name": name, "from": a, "to": 0})
                elif a is not None and b is not None and abs(b - a) >= SOGLIA_PESO:
                    eventi.append({"date": d1, "profile": f, "kind": "weight", "name": name, "from": a, "to": b})
    eventi.sort(key=lambda e: (e["date"], e["profile"], e["name"]), reverse=True)
    last = quarters[-1][0]

    body = f'''/**
 * Registro delle variazioni del paniere dei 4 Vanguard LifeStrategy, dai report
 * TRIMESTRALI del nostro archivio (Vanguard sovrascrive i precedenti). Soglie
 * dichiarate: mattoncino entra/esce con peso ≥ {FLOOR}% (sotto è arrotondamento del
 * report, non un evento); peso ±{SOGLIA_PESO:g} pt tra un report e il successivo
 * disponibile. Ricalcolato dall'intera storia a ogni giro (deterministico).
 * Baseline per fondo: {json.dumps(baselines)}.
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_ls_changes.py`
 * (archivio LifeStrategy). Non modificare a mano.
 */
export type LsChange = {{
  date: string
  profile: '20' | '40' | '60' | '80'
  kind: 'in' | 'out' | 'weight'
  name: string
  from: number
  to: number
}}

export const LS_CHANGES: {{
  updated: string
  baselines: Record<'20' | '40' | '60' | '80', string>
  thresholdPt: number
  floorPct: number
  events: LsChange[]
}} = {{
  updated: '{last}',
  baselines: {json.dumps(baselines)},
  thresholdPt: {SOGLIA_PESO:g},
  floorPct: {FLOOR:g},
  events: {json.dumps(eventi, ensure_ascii=False)},
}}
'''
    with open(DEST, "w") as f:
        f.write(body)
    print(f"[ls-changes] scritto {DEST}: {len(eventi)} eventi su {len(quarters)} report (ultimo {last})")


if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"[ls-changes] ERRORE: {e}", file=sys.stderr); sys.exit(1)
