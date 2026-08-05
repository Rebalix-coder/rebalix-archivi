#!/usr/bin/env python3
"""Rigenera il modulo versionato `lib/blog/ls-aum.ts` del sito dall'archivio
`ls_timeseries.json`. Chiamato dall'archiviatore a ogni run: così l'AUM del grafico
del blog resta aggiornato senza interventi manuali. Include solo i trimestri con AUM
per tutti e 4 i fondi (i report PDF-immagine, senza AUM leggibile, restano esclusi).
Scrive solo se la cartella del repo esiste (macchina di sviluppo)."""
import json, os, sys, glob, datetime

ARCHIVE = os.path.expanduser("~/backups/rebalix-lifestrategy-archivio")
TS_JSON = os.path.join(ARCHIVE, "_scripts", "ls_timeseries.json")
REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "ls-aum.ts")

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print(f"[aum] repo non trovato ({DEST}) — salto."); return
    data = sorted(json.load(open(TS_JSON)), key=lambda r: r["data_riferimento"])
    quarters, aum = [], {"20": [], "40": [], "60": [], "80": []}
    for r in data:
        vals = {k: r["fondi"].get(k, {}).get("aum_eur_m") for k in aum}
        if any(v is None for v in vals.values()):
            continue  # trimestre PDF-immagine senza AUM → escluso
        quarters.append(r["data_riferimento"][:7])
        for k in aum: aum[k].append(vals[k])
    if not quarters:
        print("[aum] nessun trimestre con AUM completo — salto."); return
    # Data di ARRIVO del report più recente (mtime del PDF in {anno}/{Mese}.pdf): è la data
    # in cui la pagina ha iniziato a mostrare il dato nuovo → alimenta il dateModified
    # dell'articolo (il report di giugno esce con ~5 settimane di lag: senza questo campo
    # la data di modifica resterebbe ferma alla pubblicazione). Deterministico tra i run.
    pdfs = glob.glob(os.path.join(ARCHIVE, "[12][0-9][0-9][0-9]", "*.pdf"))
    archived_at = max((datetime.date.fromtimestamp(os.path.getmtime(p)) for p in pdfs), default=None)
    archived_str = archived_at.isoformat() if archived_at else ""
    def arr(xs): return "[" + ", ".join(f"{x:g}" for x in xs) + "]"
    body = f'''/**
 * Patrimonio (AUM) trimestrale dei quattro Vanguard LifeStrategy europei, in milioni di euro.
 * Fonte: report trimestrali Vanguard archiviati da noi (Vanguard sovrascrive i precedenti).
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_aum_module.py`
 * (chiamato dall'archiviatore). Non modificare a mano. I trimestri con report PDF-immagine
 * (AUM non leggibile) sono esclusi.
 */
export type LsAum = {{
  updated: string // ultimo trimestre incluso (YYYY-MM)
  reportArchivedAt: string // quando il report più recente è ARRIVATO nell'archivio (YYYY-MM-DD)
  quarters: string[] // 'YYYY-MM' (fine trimestre)
  aum: Record<'20' | '40' | '60' | '80', number[]> // €M, allineati a `quarters`
}}

export const LS_AUM: LsAum = {{
  updated: '{quarters[-1]}',
  reportArchivedAt: '{archived_str}',
  quarters: [{", ".join(f"'{q}'" for q in quarters)}],
  aum: {{
    '20': {arr(aum["20"])},
    '40': {arr(aum["40"])},
    '60': {arr(aum["60"])},
    '80': {arr(aum["80"])},
  }},
}}
'''
    with open(DEST, "w") as f:
        f.write(body)
    print(f"[aum] scritto {DEST}: {len(quarters)} trimestri, ultimo {quarters[-1]}, totale attuale €{sum(aum[k][-1] for k in aum):.0f}M")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"[aum] ERRORE: {e}", file=sys.stderr); sys.exit(1)
