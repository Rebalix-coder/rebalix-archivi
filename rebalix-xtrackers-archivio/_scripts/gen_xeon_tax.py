#!/usr/bin/env python3
"""Rigenera `lib/blog/xeon-tax.ts`: quota white list e aliquota effettiva di Xeon
(Xtrackers II EUR Overnight Rate Swap, LU0290358497) DAL DB `etf_whitelist`.

Prima il numero (78% / 15,5%) era HARDCODED nella prosa dell'articolo Xeon → sarebbe
driftato in silenzio a ogni semestre. Ora arriva dal DB e la prosa lo interpola.
Output deterministico: si ridistribuisce solo quando la quota di Xeon cambia (semestrale).
Golden: ISIN presente, quota in [0,100]; altrimenti NON scrive.
"""
import os, re, sys, json, urllib.request

REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "xeon-tax.ts")
XEON_ISIN = "LU0290358497"

def load_env():
    env = {}
    for f in (".env.local", ".env"):
        p = os.path.join(REPO, f)
        if os.path.exists(p):
            for l in open(p):
                m = re.match(r"^\s*([A-Z0-9_]+)\s*=\s*(.*)$", l)
                if m:
                    env.setdefault(m.group(1), m.group(2).strip().strip("\"'"))
    return env


NET_ERR = (urllib.error.URLError, OSError)

def net_retry(fn):
    """Ritenta le chiamate di rete: i singhiozzi DNS del Mac sono transitori ma
    facevano fallire il generatore per l'intera giornata (21/07/2026)."""
    import time
    for i, pausa in enumerate((5, 20, 0)):
        try:
            return fn()
        except NET_ERR as e:
            if i == 2:
                raise
            print(f"   rete instabile ({type(e).__name__}) — ritento tra {pausa}s")
            time.sleep(pausa)

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print("[xeon-tax] repo non trovato — salto."); return
    env = load_env()
    if not env.get("NEXT_PUBLIC_SUPABASE_URL"):
        print("[xeon-tax] env DB assente — salto."); return
    key = env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SECRET_KEY")
    q = f"/rest/v1/etf_whitelist?isin=eq.{XEON_ISIN}&order=valid_from.desc&limit=1&select=whitelist_pct,valid_from,valid_to"
    req = urllib.request.Request(env["NEXT_PUBLIC_SUPABASE_URL"] + q,
                                 headers={"apikey": key, "Authorization": "Bearer " + key})
    rows = json.loads(net_retry(lambda: urllib.request.urlopen(req, timeout=30).read()))
    if not rows:
        sys.exit(f"!! xeon-tax: {XEON_ISIN} assente da etf_whitelist — modulo NON scritto")
    wl = float(rows[0]["whitelist_pct"])
    if not (0 <= wl <= 100):
        sys.exit(f"!! xeon-tax: quota {wl} fuori [0,100] — modulo NON scritto")
    alq = round(12.5 * wl / 100 + 26 * (1 - wl / 100), 2)
    sem = {"dal": rows[0]["valid_from"], "al": rows[0]["valid_to"]}
    body = f"""/**
 * Fiscalità di Xeon (Xtrackers II EUR Overnight Rate Swap, LU0290358497): quota di
 * titoli di Stato white list e aliquota effettiva, DAL DB `etf_whitelist` (semestrale).
 * La prosa dell'articolo interpola questi valori: niente piu' numeri hardcoded che
 * driftano al giro di semestre.
 *
 * FILE VERSIONATO E RIGENERATO da `_scripts/gen_xeon_tax.py`. Non modificare a mano.
 */
export const XEON_TAX = {{
  wl: {round(wl, 2):g}, // quota white list (%) del semestre corrente
  aliquota: {alq:g}, // aliquota effettiva sulla plusvalenza (%): 12,5·wl + 26·(1−wl)
  semestre: {{ dal: '{sem["dal"]}', al: '{sem["al"]}' }},
}}
"""
    with open(DEST, "w") as f:
        f.write(body)
    print(f"[xeon-tax] scritto {DEST}: wl={wl:g}% → aliquota {alq:g}% (semestre {sem['dal']}→{sem['al']})")

if __name__ == "__main__":
    main()
