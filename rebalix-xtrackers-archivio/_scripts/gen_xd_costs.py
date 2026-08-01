#!/usr/bin/env python3
"""Rigenera il modulo versionato `lib/blog/xd-costs.ts`: costi correnti reali (gestione +
transazione) dei 4 Xtrackers Diversified Portfolio + XQUI, a confronto coi 4 Vanguard
LifeStrategy — ESTRATTI DAI KID PRIIPs UFFICIALI, non più curati a mano.

Prima erano trascritti a mano da un umano che leggeva il PDF: corretto ma non scala
("quando avremo centinaia di articoli cosa facciamo?" — giusta obiezione). La
terminologia dei KID è IMPOSTA dalla normativa PRIIPs UE (Regolamento (UE) 1286/2014),
identica emittente per emittente: "Commissioni di gestione e altri costi amministrativi
o di esercizio" seguita da "Costi di transazione", SEMPRE in quest'ordine, sempre con
la frase fissa "X% del valore dell'investimento all'anno". Il parser si affida
all'ORDINE regolamentare (non alle etichette, che i motori PDF spezzano diversamente
dal numero a seconda dell'emittente — verificato su DWS e Vanguard, layout diversi
ma stesso ordine) → RIUSABILE su qualsiasi KID PRIIPs europeo, non solo questi due.

Fail-loud (golden): se un KID non dà ESATTAMENTE 2 corrispondenze, lo script si ferma
e NON scrive nulla — mai un numero indovinato o una tabella a metà.

I KID DWS sono quelli già archiviati mensilmente da `archive_factsheets()`. I KID
Vanguard (serve solo il confronto, non li archiva già nessuno) vengono scaricati qui
e salvati nella stessa cartella del mese corrente, per lo stesso paper-trail.
"""
import os, re, sys, glob, datetime, urllib.request
import pdfplumber

ARCHIVE = os.path.expanduser("~/backups/rebalix-xtrackers-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "xd-costs.ts")

# DWS: 4 Diversified Portfolio + XQUI (KID già in archivio, scaricati da archive_factsheets).
DWS_ISIN = {"20": "LU3116008346", "40": "LU3116008429", "60": "LU3116008692", "80": "LU3116008775"}
XQUI_ISIN = "LU0397221945"
# Vanguard LifeStrategy, classi ad accumulazione (ISIN verificati dalle schede prodotto ufficiali).
LS_ISIN = {"20": "IE00BMVB5K07", "40": "IE00BMVB5M21", "60": "IE00BMVB5P51", "80": "IE00BMVB5R75"}
LS_KID_URL = "https://fund-docs.vanguard.com/{isin}_priipskid_it.pdf"


def parse_priips_costs(pdf_path):
    """(gestione_pct, transazione_pct) da un KID PRIIPs UE — vedi docstring del modulo
    per il perché dell'approccio. Solleva ValueError se non trova ESATTAMENTE 2 numeri."""
    matches = []
    with pdfplumber.open(pdf_path) as pdf:
        for pg in pdf.pages:
            for table in pg.extract_tables():
                for row in table:
                    for cell in (row or []):
                        if not cell:
                            continue
                        m = re.search(r"(\d+[.,]\d+)\s*%\s*del valore dell.investimento all.anno", cell)
                        if m:
                            matches.append(float(m.group(1).replace(",", ".")))
    if len(matches) != 2:
        raise ValueError(f"attese 2 corrispondenze (gestione+transazione), trovate {len(matches)}: {matches}")
    return matches[0], matches[1]


def latest_dws_kid(isin):
    dirs = sorted(glob.glob(os.path.join(ARCHIVE, "factsheets", "*")))
    for d in reversed(dirs):
        p = os.path.join(d, isin + "-kid.pdf")
        if os.path.exists(p):
            return p
    return None


def fetch_vanguard_kid(isin):
    """Scarica il KID Vanguard e lo salva nella cartella del mese corrente (stesso
    paper-trail dei KID DWS): riusabile, ispezionabile, non un fetch usa-e-getta."""
    mese_dir = os.path.join(ARCHIVE, "factsheets", f"{datetime.date.today():%Y-%m}")
    dest = os.path.join(mese_dir, f"vanguard-{isin}-kid.pdf")
    if os.path.exists(dest):
        return dest
    url = LS_KID_URL.format(isin=isin.lower())
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=60) as r:
        data = r.read()
    if not data.startswith(b"%PDF") or len(data) < 20_000:
        raise RuntimeError(f"KID Vanguard {isin}: risposta non valida ({len(data)}B)")
    os.makedirs(mese_dir, exist_ok=True)
    with open(dest, "wb") as f:
        f.write(data)
    return dest


def cost_ts(gestione, transazione):
    tot = round(gestione + transazione, 3)
    return f"{{ gestionePct: {gestione:g}, transazionePct: {transazione:g}, totalePct: {tot:g}, stima: true }}"


def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print("[xd-costs] repo non trovato — salto."); return

    profili, xqui = {}, None
    for key, isin in DWS_ISIN.items():
        path = latest_dws_kid(isin)
        if not path:
            sys.exit(f"!! xd-costs: KID DWS {isin} ({key}) non in archivio — modulo NON scritto")
        g, t = parse_priips_costs(path)
        profili[key] = (g, t)
    xqui = parse_priips_costs(latest_dws_kid(XQUI_ISIN) or sys.exit("!! xd-costs: KID XQUI mancante"))

    lifestrategy = {}
    for key, isin in LS_ISIN.items():
        path = fetch_vanguard_kid(isin)
        lifestrategy[key] = parse_priips_costs(path)

    order = ["20", "40", "60", "80"]
    oggi = f"{datetime.date.today():%Y-%m-%d}"
    body = f'''/**
 * Costi dei 4 Xtrackers Diversified Portfolio (+ XQUI), a confronto coi Vanguard
 * LifeStrategy — commissioni di gestione + costi di transazione, ESTRATTI dai KID
 * PRIIPs ufficiali (terminologia imposta dalla normativa UE, identica per emittente).
 *
 * FILE VERSIONATO E RIGENERATO da `_scripts/gen_xd_costs.py` (archivio Xtrackers).
 * Non modificare a mano: al prossimo KID revisionato si riscrive da solo.
 */
export type XdCosto = {{
  gestionePct: number // «commissioni di gestione e altri costi» dal KID
  transazionePct: number // costi di transazione interni stimati, dal KID
  totalePct: number // somma: incidenza annua dei costi correnti
  stima: boolean // true = il KID dichiara i costi di transazione come stima
}}
export type XdCosts = {{
  fonte: string
  verificatoIl: string // data dell'ultima estrazione riuscita (YYYY-MM-DD)
  profili: Record<'20' | '40' | '60' | '80', XdCosto>
  xqui: XdCosto
  lifestrategy: Record<'20' | '40' | '60' | '80', XdCosto> // per il confronto nel § costi
}}

export const XD_COSTS: XdCosts = {{
  fonte: 'KID PRIIPs ufficiali (DWS e Vanguard), sezione «Costi correnti registrati ogni anno»',
  verificatoIl: '{oggi}',
  profili: {{
{chr(10).join(f"    '{k}': {cost_ts(*profili[k])}," for k in order)}
  }},
  xqui: {cost_ts(*xqui)},
  lifestrategy: {{
{chr(10).join(f"    '{k}': {cost_ts(*lifestrategy[k])}," for k in order)}
  }},
}}
'''
    with open(DEST, "w") as f:
        f.write(body)
    p60 = profili["60"]
    l60 = lifestrategy["60"]
    print(f"[xd-costs] scritto {DEST}: XEQ6 {round(p60[0]+p60[1],3)}% · LS60 {round(l60[0]+l60[1],3)}% · verificato {oggi}")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(f"[xd-costs] ERRORE: {e}", file=sys.stderr)
        sys.exit(1)
