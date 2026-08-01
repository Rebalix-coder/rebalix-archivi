#!/usr/bin/env python3
"""Rigenera lib/blog/ls-lookthrough.ts del sito dallo snapshot look-through più recente
(lookthrough/{date}.json): la RADIOGRAFIA (paesi + settori) dei quattro LifeStrategy,
aggregata dai sottostanti via GraphQL Vanguard. Chiamato dall'archiviatore (cattura mensile)."""
import json, os, sys, glob

ARCHIVE = os.path.expanduser("~/backups/rebalix-lifestrategy-archivio")
DEST = os.path.expanduser("~/progetti/rebalix/lib/blog/ls-lookthrough.ts")

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print(f"[xray] repo non trovato ({DEST}) — salto."); return
    snaps = sorted(glob.glob(os.path.join(ARCHIVE, "lookthrough", "*.json")))
    if not snaps:
        print("[xray] nessuno snapshot look-through — salto."); return
    d = json.load(open(snaps[-1]))
    def clean(dct):  # arrotonda a 2 decimali, scarta i quasi-zero, ordina desc
        items = sorted(((k, round(v, 2)) for k, v in dct.items() if v and v >= 0.05), key=lambda kv: -kv[1])
        return dict(items)
    # I settori arrivano in due tassonomie: gli ETF FTSE usano ICB, l'ETF S&P 500 (solo in LS80)
    # usa GICS → doppioni (Technology + Information Technology, ecc.). Uniformo GICS→ICB e ri-sommo,
    # così i settori sono coerenti tra tutte le linee (l'azionario è lo stesso ovunque).
    SECTOR_CANON = {"Information Technology": "Technology", "Communication Services": "Telecommunications", "Materials": "Basic Materials"}
    def canon_sectors(dct):
        out = {}
        for k, v in dct.items():
            out.setdefault(SECTOR_CANON.get(k, k), 0.0)
            out[SECTOR_CANON.get(k, k)] += v
        return out
    funds = {}
    for lvl in ["20", "40", "60", "80"]:
        f = d["funds"].get(lvl, {})
        funds[lvl] = {"paesi": clean(f.get("paesi", {})), "paesiAzioni": clean(f.get("paesi_azioni", {})),
                      "paesiObblig": clean(f.get("paesi_obblig", {})), "settori": clean(canon_sectors(f.get("settori", {}))),
                      "credito": clean(f.get("credito", {}))}
    def obj(dct):
        return "{ " + ", ".join(f'{json.dumps(k, ensure_ascii=False)}: {v:g}' for k, v in dct.items()) + " }"
    def fundBody(lvl):
        return f'''{{
      paesi: {obj(funds[lvl]["paesi"])},
      paesiAzioni: {obj(funds[lvl]["paesiAzioni"])},
      paesiObblig: {obj(funds[lvl]["paesiObblig"])},
      settori: {obj(funds[lvl]["settori"])},
      credito: {obj(funds[lvl]["credito"])},
    }}'''
    body = f'''/**
 * Radiografia look-through dei quattro Vanguard LifeStrategy: ripartizione per PAESE
 * (geografia aggregata), per SETTORE (parte azionaria) e per QUALITÀ DEL CREDITO (parte
 * obbligazionaria), sommando la composizione dei fondi sottostanti (fonte Vanguard). È una
 * FOTO CORRENTE: si aggiorna ogni mese con la cattura.
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_lookthrough_module.py`.
 */
export type Xray = {{ paesi: Record<string, number>; paesiAzioni: Record<string, number>; paesiObblig: Record<string, number>; settori: Record<string, number>; credito: Record<string, number> }}
export type LsLookthrough = {{ effectiveDate: string; weightsAsof: string; funds: Record<'20' | '40' | '60' | '80', Xray> }}

export const LS_LOOKTHROUGH: LsLookthrough = {{
  effectiveDate: '{d.get("effective_date", "")}',
  weightsAsof: '{d.get("weights_asof", "")}',
  funds: {{
    '20': {fundBody("20")},
    '40': {fundBody("40")},
    '60': {fundBody("60")},
    '80': {fundBody("80")},
  }},
}}
'''
    open(DEST, "w").write(body)
    nP = len(funds["60"]["paesi"]); nS = len(funds["60"]["settori"])
    print(f"[xray] scritto {DEST}: effective {d.get('effective_date')}, LS60 {nP} paesi / {nS} settori")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"[xray] ERRORE: {e}", file=sys.stderr); sys.exit(1)
