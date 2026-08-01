#!/usr/bin/env python3
"""Rigenera lib/blog/ls-tax.ts del sito dal documento fiscale IRRP di Vanguard
(factsheets/{trimestre}/tax-italy-reduced-rate.xlsx): la quota di titoli di Stato
«white-list» per ciascuna linea LifeStrategy (tassata al 12,5% invece del 26%) e
l'aliquota reale che ne risulta. Vanguard aggiorna l'IRRP ogni semestre. Chiamato
dall'archiviatore. Aliquota = 12,5%·wl + 26%·(1−wl)."""
import os, sys, glob, openpyxl

ARCHIVE = os.path.expanduser("~/backups/rebalix-lifestrategy-archivio")
DEST = os.path.expanduser("~/progetti/rebalix/lib/blog/ls-tax.ts")
# ISIN ad accumulazione per livello (Acc e Dist condividono la stessa quota white-list).
ACC = {"IE00BMVB5K07": "20", "IE00BMVB5M21": "40", "IE00BMVB5P51": "60", "IE00BMVB5R75": "80"}
# I due ETF del confronto fai-da-te: azionario VWCE (assente dall'IRRP = 26%, nessuna riduzione)
# e obbligazionario VAGF (presente, quota white-list → aliquota ridotta). Auto-aggiornati come le linee.
DIY = {"IE00BK5BQT80": "eq", "IE00BG47KH54": "bd"}

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print(f"[tax] repo non trovato ({DEST}) — salto."); return
    files = sorted(glob.glob(os.path.join(ARCHIVE, "factsheets", "*", "tax-italy-reduced-rate.xlsx")))
    if not files:
        print("[tax] IRRP non trovato — salto."); return
    ws = openpyxl.load_workbook(files[-1], data_only=True).active
    rows = list(ws.iter_rows(values_only=True))
    hdr = next(i for i, r in enumerate(rows) if r and any(str(c or "").strip() == "ISIN" for c in r))
    cols = [str(c or "") for c in rows[hdr]]
    ci = cols.index("ISIN")
    cwl = next(i for i, c in enumerate(cols) if "Reduced" in c)
    ceff = next((i for i, c in enumerate(cols) if "Effective" in c), None)
    def aliq_of(wl):  # wl frazione 0..1 → aliquota reale %
        return round(12.5 * wl + 26.0 * (1 - wl), 2)
    funds, diy, eff = {}, {"eq": 26.0, "bd": 26.0}, ""  # VWCE/VAGF: default 26 se assenti dall'IRRP
    for r in rows[hdr + 1:]:
        isin = str(r[ci] or "").strip()
        if isin in ACC and r[cwl] is not None:
            wl = float(r[cwl])
            funds[ACC[isin]] = {"wl": round(wl * 100, 1), "aliquota": aliq_of(wl)}
            if ceff is not None and r[ceff]:
                eff = str(r[ceff])[:7]
        elif isin in DIY and r[cwl] is not None:
            diy[DIY[isin]] = aliq_of(float(r[cwl]))
    if len(funds) < 4:
        print(f"[tax] trovate solo {len(funds)} linee — salto."); return
    order = ["20", "40", "60", "80"]
    body = f'''/**
 * Fiscalità italiana dei Vanguard LifeStrategy: quota di titoli di Stato «white-list»
 * (tassata al 12,5% invece del 26%) e aliquota reale sulla plusvalenza, per linea.
 * Fonte: documento IRRP di Vanguard (aggiornato ogni semestre). Aliquota = 12,5%·wl + 26%·(1−wl).
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_tax_module.py`. Non modificare a mano.
 */
export type LsTax = {{
  updated: string
  bolloPct: number
  funds: Record<'20' | '40' | '60' | '80', {{ wl: number; aliquota: number }}>
  diy: {{ eq: number; bd: number }}
}}

export const LS_TAX: LsTax = {{
  updated: '{eff}',
  bolloPct: 0.2,
  funds: {{
{chr(10).join(f"    '{k}': {{ wl: {funds[k]['wl']:g}, aliquota: {funds[k]['aliquota']:g} }}," for k in order)}
  }},
  diy: {{ eq: {diy['eq']:g}, bd: {diy['bd']:g} }},
}}
'''
    open(DEST, "w").write(body)
    print(f"[tax] scritto {DEST}: eff {eff} · aliquota LS60 {funds['60']['aliquota']}% · fai-da-te VWCE {diy['eq']}% / VAGF {diy['bd']}%")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"[tax] ERRORE: {e}", file=sys.stderr); sys.exit(1)
