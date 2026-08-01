#!/usr/bin/env python3
"""Rigenera il modulo versionato `lib/blog/xd-holdings.ts` (Xtrackers Diversified
Portfolio): composizione completa dei 4 profili dall'ultimo snapshot 'full'
dell'archivio (fonte: API DWS, archiviata ogni giorno alle 10:30).

Oltre alle posizioni, calcola le tre letture-firma dell'articolo:
  - aggregato per classe (azioni / obbligazioni / oro / liquidita')
  - quota SWAP-BASED del portafoglio (replica sintetica: 0% nel profilo 20 -> ~44% nell'80)
  - quote HY ed EMERGENTI del paniere obbligazionario, SEPARATE (Linus 15/7: classi
    molto diverse): due costanti di design distinte, HY=5% e EM=15% dei bond ovunque
Sanita' (fail-loud): pesi ~100, snapshot non piu' vecchio di 7 giorni, 4 profili presenti.
Scrive solo se la cartella del repo esiste (macchina di sviluppo).
"""
import json, os, sys, datetime

ARCHIVE = os.path.expanduser("~/backups/rebalix-xtrackers-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "xd-holdings.ts")

PROFILI = {"20": "xeq2", "40": "xeq4", "60": "xeq6", "80": "xeq8"}
CLASSI = {"Azionari": "azioni", "Obbligazionari": "obbligazioni",
          "Materie Prime": "oro", "Cash": "liquidita"}

def e_hy(nome):
    return "high yield" in (nome or "").lower()

def e_em(nome):
    n = (nome or "").lower()
    return "j.p. morgan" in n and "bond" in n

def ultimo_full(key):
    ultimo = None
    with open(os.path.join(ARCHIVE, "history", key + ".jsonl")) as f:
        for line in f:
            r = json.loads(line)
            if r.get("kind") == "full":
                ultimo = r
    return ultimo

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print(f"[xd-hold] repo non trovato ({DEST}) — salto."); return
    profili_out, asof_min = {}, None
    for prof, key in PROFILI.items():
        r = ultimo_full(key)
        if not r:
            sys.exit(f"!! {key}: nessuno snapshot 'full' in archivio — modulo NON scritto")
        eta = (datetime.date.today() - datetime.date.fromisoformat(r["asof"])).days
        if eta > 7:
            sys.exit(f"!! {key}: snapshot del {r['asof']} ({eta} giorni fa) — stantio, modulo NON scritto")
        if abs(r["somma_pesi"] - 100) > 1.5:
            sys.exit(f"!! {key}: somma pesi {r['somma_pesi']}% — modulo NON scritto")
        asof_min = min(asof_min or r["asof"], r["asof"])
        classi = {v: 0.0 for v in CLASSI.values()}
        swap = hy = em = bond_tot = 0.0
        posizioni = []
        for p in r["posizioni"]:
            peso = p["peso"] or 0
            classe = CLASSI.get(p.get("classe") or "", "liquidita")
            classi[classe] = round(classi[classe] + peso, 4)
            nome = p.get("nome") or ""
            if "Swap" in nome:
                swap += peso
            if classe == "obbligazioni":
                bond_tot += peso
                if e_hy(nome):
                    hy += peso
                if e_em(nome):
                    em += peso
            posizioni.append({"isin": p.get("isin"), "nome": nome, "peso": peso, "classe": classe})
        posizioni.sort(key=lambda x: -(x["peso"] or 0))
        profili_out[prof] = {
            "asof": r["asof"], "n": len(posizioni), "classi": classi,
            "swapPct": round(swap, 2),
            "hyPct": round(hy, 2), "emPct": round(em, 2),
            "hySuBondPct": round(hy / bond_tot * 100, 1) if bond_tot else 0,
            "emSuBondPct": round(em / bond_tot * 100, 1) if bond_tot else 0,
            "posizioni": posizioni,
        }
    def pos_ts(p):
        isin = f"'{p['isin']}'" if p["isin"] and not p["isin"].startswith("_") else "null"
        nome = p["nome"].replace("'", "\\'")
        return (f"{{ isin: {isin}, nome: '{nome}', peso: {p['peso']:g}, classe: '{p['classe']}' }}")
    blocchi = []
    for prof, d in profili_out.items():
        c = d["classi"]
        blocchi.append(f"""  '{prof}': {{
    asof: '{d["asof"]}', n: {d["n"]},
    classi: {{ azioni: {c["azioni"]:g}, obbligazioni: {c["obbligazioni"]:g}, oro: {c["oro"]:g}, liquidita: {c["liquidita"]:g} }},
    swapPct: {d["swapPct"]:g}, hyPct: {d["hyPct"]:g}, emPct: {d["emPct"]:g}, hySuBondPct: {d["hySuBondPct"]:g}, emSuBondPct: {d["emSuBondPct"]:g},
    posizioni: [
      {(",{}      ".format(chr(10))).join(pos_ts(p) for p in d["posizioni"])},
    ],
  }}""")
    oggi = datetime.date.today().isoformat()
    body = f"""/**
 * Composizione completa dei 4 Xtrackers Diversified Portfolio, dall'ultimo snapshot
 * dell'archivio Rebalix (fonte: dati ufficiali DWS, fotografati ogni giorno).
 * Include le letture-firma: quota swap-based (replica sintetica) e le quote SEPARATE
 * di high yield (5% dei bond per design) e debito emergente (15% dei bond per design).
 * NB: il debito emergente e' un misto investment grade / high yield — nell'articolo
 * si dice "parte spinta del paniere"; la qualita' si legge emittente per emittente.
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_xd_holdings.py`
 * (archivio Xtrackers). Non modificare a mano.
 */
export type XdPosizione = {{ isin: string | null; nome: string; peso: number; classe: 'azioni' | 'obbligazioni' | 'oro' | 'liquidita' }}
export type XdProfilo = {{
  asof: string
  n: number
  classi: {{ azioni: number; obbligazioni: number; oro: number; liquidita: number }}
  swapPct: number // % del portafoglio in mattoncini a replica sintetica
  hyPct: number // % del portafoglio in high yield (societari sotto investment grade)
  emPct: number // % del portafoglio in debito emergente (sovrani, misto IG/HY)
  hySuBondPct: number // high yield in % del solo paniere obbligazionario (~5% per design)
  emSuBondPct: number // emergenti in % del solo paniere obbligazionario (~15% per design)
  posizioni: XdPosizione[]
}}
export type XdHoldings = {{ updated: string; profili: Record<'20' | '40' | '60' | '80', XdProfilo> }}

export const XD_HOLDINGS: XdHoldings = {{
  updated: '{oggi}',
  profili: {{
{(",{}".format(chr(10))).join(blocchi)},
  }},
}}
"""
    with open(DEST, "w") as f:
        f.write(body)
    riass = " | ".join(f"{p}: swap {d['swapPct']}%, HY {d['hySuBondPct']}%+EM {d['emSuBondPct']}% dei bond"
                       for p, d in profili_out.items())
    print(f"[xd-hold] scritto {DEST} (asof {asof_min}) — {riass}")

if __name__ == "__main__":
    main()
