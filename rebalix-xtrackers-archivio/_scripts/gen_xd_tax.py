#!/usr/bin/env python3
"""Rigenera il modulo versionato `lib/blog/xd-tax.ts`: fiscalità white list dei 4
Xtrackers Diversified Portfolio + XQUI, DAL DATABASE `etf_whitelist` (non piu' a mano).

Prima era curato a mano → rischio staleness al giro di semestre. Ora la QUOTA e
l'ALIQUOTA arrivano dal DB (stessa fonte del motore fiscale del prodotto), come gia'
fa il LifeStrategy con gen_tax_module.py. I campi EDITORIALI (fonte narrativa, data di
verifica umana, prima quota reale attesa) restano costanti qui sotto: cambiano solo
quando un umano rivede la storia (⏰ gen 2027, quando il 0% transitorio diventera' reale).

Output DETERMINISTICO (nessuna data-di-oggi): il file cambia — e quindi si ridistribuisce —
solo quando cambia il dato nel DB (cioe' a ogni nuovo semestre white list).
Golden (fail-loud): tutti e 5 gli ISIN presenti, quota in [0,100]. Se manca, NON scrive.
"""
import os, re, sys, json, urllib.request

REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "xd-tax.ts")

# ISIN → chiave nel modulo ('20'/'40'/'60'/'80' per i funds, 'xqui' a parte)
FUNDS_ISIN = {"20": "LU3116008346", "40": "LU3116008429", "60": "LU3116008692", "80": "LU3116008775"}
XQUI_ISIN = "LU0397221945"

# --- campi EDITORIALI (un umano li rivede quando cambia la storia, non il dato) ---
FONTE = "File white list DWS (foglio Ratios) + Circ. AE 11/E/2012 + conferma intermediario (Directa)"
VERIFICATO_IL = "2026-07-14"        # verifica umana a tre fonti (norma + file + broker)
PRIMA_QUOTA_REALE = "2027-01"        # quando dovrebbe comparire la prima quota vera

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

def db_quote(env, isin):
    url = env["NEXT_PUBLIC_SUPABASE_URL"]
    key = env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SECRET_KEY")
    q = f"/rest/v1/etf_whitelist?isin=eq.{isin}&order=valid_from.desc&limit=1&select=whitelist_pct,valid_from,valid_to"
    req = urllib.request.Request(env["NEXT_PUBLIC_SUPABASE_URL"] + q,
                                 headers={"apikey": key, "Authorization": "Bearer " + key})
    rows = json.loads(net_retry(lambda: urllib.request.urlopen(req, timeout=30).read()))
    return rows[0] if rows else None

def aliquota(wl):
    return round(12.5 * wl / 100 + 26 * (1 - wl / 100), 2)

def fund_ts(wl):
    return f"{{ wl: {round(wl, 3):g}, aliquota: {aliquota(wl):g}, transitorio: {'true' if wl == 0 else 'false'} }}"

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print(f"[xd-tax] repo non trovato — salto."); return
    env = load_env()
    if not env.get("NEXT_PUBLIC_SUPABASE_URL"):
        print("[xd-tax] env DB assente — salto."); return
    quote = {}
    semestre = None
    for key, isin in {**FUNDS_ISIN, "xqui": XQUI_ISIN}.items():
        row = db_quote(env, isin)
        if not row:
            sys.exit(f"!! xd-tax: ISIN {isin} ({key}) assente da etf_whitelist — modulo NON scritto")
        wl = float(row["whitelist_pct"])
        if not (0 <= wl <= 100):
            sys.exit(f"!! xd-tax: {key} quota {wl} fuori [0,100] — modulo NON scritto")
        quote[key] = wl
        semestre = {"dal": row["valid_from"], "al": row["valid_to"]}
    body = f"""/**
 * Fiscalità italiana dei 4 Xtrackers Diversified Portfolio (+ XQUI): quota di titoli
 * di Stato «white list» (tassata al 12,5% invece del 26%) e aliquota effettiva sulla
 * plusvalenza. QUOTA e ALIQUOTA vengono dal DB `etf_whitelist` (aggiornato ogni semestre
 * dall'ingestione dei file emittente): niente piu' staleness silenziosa.
 *
 * Nota narrativa: la quota 0% dei quattro Diversified Portfolio e' TRANSITORIA (fondi
 * nati 29/01/2026, senza rendiconti quando il file e' stato compilato — Circ. AE 11/E/2012).
 * La prima quota reale e' attesa col semestre {PRIMA_QUOTA_REALE}: a quel punto il numero
 * cambia da solo, ma la STORIA nel testo dell'articolo va rivista a mano.
 *
 * FILE VERSIONATO E RIGENERATO da `_scripts/gen_xd_tax.py` (archivio Xtrackers). Non modificare a mano.
 */
export type XdTaxFund = {{
  wl: number // quota white list dell'emittente per il semestre corrente (%)
  aliquota: number // aliquota effettiva sulla plusvalenza: 12,5·wl + 26·(1−wl) (%)
  transitorio: boolean // true = quota zero (fondo di nuova istituzione, non strutturale)
}}
export type XdTax = {{
  semestre: {{ dal: string; al: string }} // periodo di validità del file emittente
  fonte: string
  verificatoIl: string
  primaQuotaRealeAttesa: string
  funds: Record<'20' | '40' | '60' | '80', XdTaxFund>
  xqui: XdTaxFund // Xtrackers Portfolio (LU0397221945), per la disambiguazione e il futuro articolo
}}

export const XD_TAX: XdTax = {{
  semestre: {{ dal: '{semestre["dal"]}', al: '{semestre["al"]}' }},
  fonte: '{FONTE}',
  verificatoIl: '{VERIFICATO_IL}',
  primaQuotaRealeAttesa: '{PRIMA_QUOTA_REALE}',
  funds: {{
    '20': {fund_ts(quote["20"])},
    '40': {fund_ts(quote["40"])},
    '60': {fund_ts(quote["60"])},
    '80': {fund_ts(quote["80"])},
  }},
  xqui: {fund_ts(quote["xqui"])},
}}
"""
    with open(DEST, "w") as f:
        f.write(body)
    print(f"[xd-tax] scritto {DEST}: XEQ wl={quote['20']:g}% (alq {aliquota(quote['20']):g}), "
          f"XQUI wl={quote['xqui']:g}% (alq {aliquota(quote['xqui']):g}), semestre {semestre['dal']}→{semestre['al']}")

if __name__ == "__main__":
    main()
