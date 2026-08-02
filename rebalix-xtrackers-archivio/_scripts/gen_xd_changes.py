#!/usr/bin/env python3
"""Registro delle VARIAZIONI del paniere dei 4 Xtrackers Diversified Portfolio
(gemello di gen_c3m_changes, voluto da Linus 1/8/2026 dopo il caso del monetario
DWS entrato in XEQ6 senza che nessuna superficie lo raccontasse).

MECCANICA — diversa dal C3M in un punto chiave: l'archivio XD conserva TUTTI gli
snapshot «full» per profilo (history/xeq*.jsonl), quindi il registro si RICALCOLA
deterministicamente dall'intera storia a ogni giro: niente file di stato, backfill
automatico, idempotente. Confronto contro l'ultimo stato SEGNALATO (non giorno-su-
giorno: le derive lente non sfuggono).

EVENTI (soglie dichiarate in pagina):
- mattoncino che ENTRA/ESCE dal paniere: sempre segnalato (kind in/out)
- peso di un mattoncino: |Δ| ≥ 1,0 punti rispetto all'ultimo stato segnalato (kind weight)
Si tracciano solo le posizioni con ISIN (i mattoncini); la riga cash non è un evento.

NB nomi: il feed DWS non risolve i mattoncini non-ETF (caso monetario interno,
nome «--») → NAME_OVERRIDE, da tenere allineato all'OVERRIDE di gen_xd_holdings.
"""
import json, os, sys, datetime

ARCHIVE = os.path.expanduser("~/backups/rebalix-xtrackers-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "xd-changes.ts")

PROFILI = {"20": "xeq2", "40": "xeq4", "60": "xeq6", "80": "xeq8"}
SOGLIA_PESO = 1.0
NAME_OVERRIDE = {"IE00BZ3FDF20": "Deutsche Managed Euro Fund Z (monetario DWS)"}


def snapshots(key):
    """Tutti gli snapshot full del profilo, in ordine cronologico, dedup per asof."""
    per_asof = {}
    path = os.path.join(ARCHIVE, "history", key + ".jsonl")
    with open(path) as f:
        for line in f:
            r = json.loads(line)
            if r.get("kind") == "full":
                per_asof[r["asof"]] = r
    return [per_asof[a] for a in sorted(per_asof)]


def mattoncini(snap):
    """isin → (nome, peso) delle sole posizioni con ISIN."""
    out = {}
    for p in snap["posizioni"]:
        isin = p.get("isin")
        if not isin or isin.startswith("_"):
            continue
        nome = NAME_OVERRIDE.get(isin) or p.get("nome") or ""
        out[isin] = (nome if nome.strip() not in ("", "--") else isin, p["peso"] or 0)
    return out


def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print("[xd-changes] repo non trovato — salto."); return
    eventi, baselines = [], {}
    for prof, key in PROFILI.items():
        snaps = snapshots(key)
        if not snaps:
            sys.exit(f"[xd-changes] {key}: nessuno snapshot full — NON scrivo")
        baselines[prof] = snaps[0]["asof"]
        stato = mattoncini(snaps[0])          # baseline: nessun evento
        for snap in snaps[1:]:
            cur = mattoncini(snap)
            for isin in sorted(set(stato) | set(cur)):
                prima = stato.get(isin)
                dopo = cur.get(isin)
                if prima is None and dopo is not None:
                    eventi.append({"date": snap["asof"], "profile": prof, "kind": "in",
                                   "isin": isin, "name": dopo[0], "from": 0, "to": round(dopo[1], 2)})
                    stato[isin] = dopo
                elif dopo is None and prima is not None:
                    eventi.append({"date": snap["asof"], "profile": prof, "kind": "out",
                                   "isin": isin, "name": prima[0], "from": round(prima[1], 2), "to": 0})
                    del stato[isin]
                elif prima is not None and dopo is not None:
                    if abs(dopo[1] - prima[1]) >= SOGLIA_PESO:
                        eventi.append({"date": snap["asof"], "profile": prof, "kind": "weight",
                                       "isin": isin, "name": dopo[0],
                                       "from": round(prima[1], 2), "to": round(dopo[1], 2)})
                        stato[isin] = dopo

    eventi.sort(key=lambda e: (e["date"], e["profile"]), reverse=True)
    updated = eventi[0]["date"] if eventi else max(baselines.values())
    ts = f"""/**
 * Registro delle variazioni del paniere dei 4 Xtrackers Diversified Portfolio,
 * con soglie dichiarate (mattoncino entra/esce: sempre; peso ±{SOGLIA_PESO} pt rispetto
 * all'ultimo stato segnalato). RICALCOLATO dall'intera storia degli snapshot a ogni
 * giro (deterministico, niente stato). Baseline per profilo: {json.dumps(baselines)}.
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_xd_changes.py`
 * (archivio Xtrackers). Non modificare a mano.
 */
export type XdChange = {{
  date: string
  profile: '20' | '40' | '60' | '80'
  kind: 'in' | 'out' | 'weight'
  isin: string
  name: string
  from: number
  to: number
}}

export const XD_CHANGES: {{
  updated: string
  baselines: Record<'20' | '40' | '60' | '80', string>
  thresholdPt: number
  events: XdChange[]
}} = {{
  updated: '{updated}',
  baselines: {json.dumps(baselines)},
  thresholdPt: {SOGLIA_PESO},
  events: {json.dumps(eventi, ensure_ascii=False)},
}}
"""
    vecchio = open(DEST).read() if os.path.exists(DEST) else None
    if ts == vecchio:
        print(f"[xd-changes] invariato ({len(eventi)} eventi)"); return
    with open(DEST, "w") as f:
        f.write(ts)
    print(f"[xd-changes] scritto: {len(eventi)} eventi (baseline {min(baselines.values())})")


if __name__ == "__main__":
    main()
