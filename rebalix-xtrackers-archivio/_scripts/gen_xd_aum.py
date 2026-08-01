#!/usr/bin/env python3
"""Rigenera il modulo versionato `lib/blog/xd-aum.ts`: il patrimonio (AUM) dei 4
Diversified Portfolio, un punto al giorno, dagli snapshot dell'archiviatore
(spread.jsonl: quote Yahoo delle ~10:30 col campo netAssets — verificato coerente
coi controvalori DWS il 15/07/2026: 2,03/5,11 mln vs 2,03/5,07 nostri).
La serie parte dal 15/07/2026 e cresce da sola: per fondi micro la RACCOLTA è il
segnale da guardare (rischio chiusura) — il grafico dell'articolo racconta questo.
Sanita' (fail-loud): AUM in [0.05, 10000] mln, ultimo snapshot ≤5 giorni.
"""
import json, os, sys, datetime

ARCHIVE = os.path.expanduser("~/backups/rebalix-xtrackers-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "xd-aum.ts")
PROFILI = {"20": "xeq2", "40": "xeq4", "60": "xeq6", "80": "xeq8"}

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print(f"[xd-aum] repo non trovato — salto."); return
    # un punto per giorno (l'ultimo snapshot del giorno vince)
    per_giorno: dict = {}
    with open(os.path.join(ARCHIVE, "spread.jsonl")) as f:
        for line in f:
            r = json.loads(line)
            giorno = r["rilevato"][:10]
            vals = {}
            for prof, key in PROFILI.items():
                aum = (r["quote"].get(key) or {}).get("aum")
                if aum:
                    vals[prof] = round(aum / 1e6, 3)  # milioni di euro
            if len(vals) == len(PROFILI):
                per_giorno[giorno] = vals
    if not per_giorno:
        sys.exit("!! xd-aum: nessuno snapshot con AUM completo — modulo NON scritto")
    dates = sorted(per_giorno)
    eta = (datetime.date.today() - datetime.date.fromisoformat(dates[-1])).days
    if eta > 5:
        sys.exit(f"!! xd-aum: ultimo AUM {dates[-1]} ({eta} gg) — stantio, modulo NON scritto")
    for d in dates:
        for prof, v in per_giorno[d].items():
            if not (0.05 <= v <= 10000):
                sys.exit(f"!! xd-aum: {prof} {d} = {v} mln fuori range — modulo NON scritto")
    def arr(prof):
        return "[" + ", ".join(f"{per_giorno[d][prof]:g}" for d in dates) + "]"
    oggi = datetime.date.today().isoformat()
    body = f"""/**
 * Patrimonio gestito (AUM, milioni di euro) dei 4 Xtrackers Diversified Portfolio:
 * un punto al giorno dagli snapshot delle ~10:30 dell'archivio Rebalix (dal 15/07/2026).
 * Per fondi appena nati la RACCOLTA è il segnale da guardare: un fondo che non
 * raccoglie può essere chiuso dall'emittente. La serie cresce da sola ogni giorno.
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_xd_aum.py`
 * (archivio Xtrackers). Non modificare a mano.
 */
export type XdAum = {{
  updated: string
  dates: string[] // giorni di rilevazione (YYYY-MM-DD)
  aum: Record<'20' | '40' | '60' | '80', number[]> // milioni di euro
}}

export const XD_AUM: XdAum = {{
  updated: '{oggi}',
  dates: [{", ".join(f"'{d}'" for d in dates)}],
  aum: {{
    '20': {arr("20")},
    '40': {arr("40")},
    '60': {arr("60")},
    '80': {arr("80")},
  }},
}}
"""
    with open(DEST, "w") as f:
        f.write(body)
    ultimo = per_giorno[dates[-1]]
    print(f"[xd-aum] scritto {DEST}: {len(dates)} giorni, ultimo ({dates[-1]}): " +
          ", ".join(f"{p}%={v}M" for p, v in ultimo.items()))

if __name__ == "__main__":
    main()
