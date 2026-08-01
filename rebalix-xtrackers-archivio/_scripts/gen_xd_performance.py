#!/usr/bin/env python3
"""Rigenera il modulo versionato `lib/blog/xd-performance.ts` (Xtrackers Diversified
Portfolio): rendimento cumulato e drawdown dei 4 profili, dal NAV UFFICIALE DWS
(serie completa dal lancio 29/01/2026, archiviata ogni giorno dall'archiviatore).
PERCHE' IL NAV e non il prezzo di borsa (deciso con Linus, 14 lug 2026): su fondi
giovani e piccoli il titolo puo' non scambiare per giorni (XEQ2: 59 chiusure ferme su
92) e la serie di borsa mostrerebbe gradini piatti e drawdown sottostimati (-2,7%
apparente vs -4,2% reale sul profilo 20). Il NAV e' il valore vero del paniere; e
combacia con la controprova che i lettori faranno (justETF usa il NAV: -4,15 vs
nostro -4,16). L'articolo include il box divulgativo "cos'e' il NAV".

GOLDEN TEST (fail-loud), a ruoli invertiti: la controprova ora e' YAHOO (prezzi di
Borsa Italiana) contro la serie principale NAV. Stesse tre soglie, tarate
per beccare DATI ROTTI (split non gestiti, buchi, simboli sbagliati, serie ferme) e
tollerare il rumore fisiologico prezzo-di-borsa vs NAV (il NAV usa le chiusure USA
delle 22:00, Borsa chiude alle 17:30: con l'azionario USA in pancia gli scarti di
livello ±0,5% sono normali — diagnosi del 14 lug 2026). Tre controlli:
  a) rendimento CUMULATO end-to-end Yahoo vs NAV: scarto ≤ 1,5 punti
  b) scarto MEDIANO sui rendimenti giornalieri ≤ 0,6 punti
  c) scarto massimo di LIVELLO ≤ 3% (uno split non gestito = ~50%: impossibile mancarlo)
Se uno fallisce, il modulo NON viene scritto: meglio nessun grafico che un grafico falso.

Regole metriche concordate (14 lug 2026): MAI annualizzare su serie <1 anno (il modulo
espone solo cumulato + drawdown), base = primo NAV comune (lancio), acc = total return.
Scrive solo se la cartella del repo esiste (macchina di sviluppo).
"""
import json, os, sys, datetime, urllib.request, statistics

ARCHIVE = os.path.expanduser("~/backups/rebalix-xtrackers-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "xd-performance.ts")

ETFS = {"20": ("xeq2", "XEQ2.MI"), "40": ("xeq4", "XEQ4.MI"),
        "60": ("xeq6", "XEQ6.MI"), "80": ("xeq8", "XEQ8.MI")}

SOGLIA_CUMULATO = 1.5    # punti: |cum% Yahoo - cum% NAV| end-to-end
SOGLIA_REND_MEDIANO = 0.6  # punti: scarto mediano sui rendimenti giornalieri
SOGLIA_LIVELLO = 3.0     # %: scarto massimo di livello (rileva split/fattori errati)
FRESCHEZZA_GIORNI = 7    # ultimo NAV in archivio non più vecchio di così


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

def yahoo_serie(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=max&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    def _go():
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.loads(r.read())["chart"]["result"][0]
    d = net_retry(_go)
    out = {}
    for ts, c in zip(d["timestamp"], d["indicators"]["quote"][0]["close"]):
        if c:
            out[datetime.datetime.utcfromtimestamp(ts).date().isoformat()] = round(c, 4)
    return out

def nav_serie(key):
    d = json.load(open(os.path.join(ARCHIVE, "nav", key + ".json")))
    out = {}
    for ts, box in d["values"]:
        out[datetime.datetime.utcfromtimestamp(ts / 1000).date().isoformat()] = box[0][0]
    return out

def golden_test(nome, yh, nav):
    comuni = sorted(set(yh) & set(nav))
    if len(comuni) < 30:
        sys.exit(f"!! golden test {nome}: solo {len(comuni)} date comuni Yahoo/NAV — dati insufficienti")
    # a) cumulato end-to-end
    cum_y = (yh[comuni[-1]] / yh[comuni[0]] - 1) * 100
    cum_n = (nav[comuni[-1]] / nav[comuni[0]] - 1) * 100
    diff_cum = abs(cum_y - cum_n)
    # b) rendimenti giornalieri
    diff_rend = [abs((yh[b] / yh[a] - 1) - (nav[b] / nav[a] - 1)) * 100
                 for a, b in zip(comuni, comuni[1:])]
    med_rend = statistics.median(diff_rend)
    # c) livello (rileva split/fattori errati)
    max_liv = max(abs(yh[d] / nav[d] - 1) * 100 for d in comuni)
    print(f"[golden] {nome}: {len(comuni)} date | cum Yahoo {cum_y:+.2f}% vs NAV {cum_n:+.2f}% "
          f"(diff {diff_cum:.2f} pt) | rend. mediano {med_rend:.3f} pt | livello max {max_liv:.2f}%")
    if diff_cum > SOGLIA_CUMULATO or med_rend > SOGLIA_REND_MEDIANO or max_liv > SOGLIA_LIVELLO:
        sys.exit(f"!! GOLDEN TEST FALLITO per {nome}: cum {diff_cum:.2f} pt (soglia {SOGLIA_CUMULATO}), "
                 f"rend {med_rend:.3f} pt (soglia {SOGLIA_REND_MEDIANO}), livello {max_liv:.2f}% "
                 f"(soglia {SOGLIA_LIVELLO}) — modulo NON scritto")
    return diff_cum, med_rend, max_liv

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print(f"[xd-perf] repo non trovato ({DEST}) — salto."); return
    serie, golden = {}, {}
    for prof, (key, sym) in ETFS.items():
        nav = nav_serie(key)
        ultima = max(nav)
        eta = (datetime.date.today() - datetime.date.fromisoformat(ultima)).days
        if eta > FRESCHEZZA_GIORNI:
            sys.exit(f"!! {key}: ultimo NAV {ultima} ({eta} giorni fa) — archivio stantio, modulo NON scritto")
        golden[prof] = golden_test(sym, yahoo_serie(sym), nav)
        serie[prof] = nav
    # base comune: prima data presente in tutte e quattro le serie NAV (= lancio)
    date_comuni = sorted(set.intersection(*(set(s) for s in serie.values())))
    start = date_comuni[0]
    cum, dd, max_dd = {}, {}, {}
    for prof, s in serie.items():
        base = s[start]
        cum[prof] = [round((s[d] / base - 1) * 100, 2) for d in date_comuni]
        picco, curva, peggio = -1e9, [], (0.0, start)
        for d in date_comuni:
            picco = max(picco, s[d])
            x = round((s[d] / picco - 1) * 100, 2)
            curva.append(x)
            if x < peggio[0]:
                peggio = (x, d)
        dd[prof] = curva
        max_dd[prof] = peggio
    peggior_cum = max(g[0] for g in golden.values())
    peggior_rend = max(g[1] for g in golden.values())
    def arr(xs): return "[" + ", ".join(f"{x:g}" for x in xs) + "]"
    oggi = datetime.date.today().isoformat()
    body = f"""/**
 * Performance dei 4 Xtrackers Diversified Portfolio: rendimento cumulato e drawdown (%)
 * dal NAV UFFICIALE DWS, dal lancio ({start}). Il NAV e non il prezzo di borsa: su
 * fondi giovani il titolo può non scambiare per giorni e la serie di borsa mostrerebbe
 * gradini e cali sottostimati (spiegato nel box "cos'è il NAV" dell'articolo).
 * Classi ad accumulazione = total return. NIENTE metriche annualizzate: la serie è
 * ancora giovane, cumulato e drawdown sono le uniche letture oneste.
 *
 * QUALITÀ: ogni serie NAV ha superato la verifica incrociata contro i prezzi di
 * Borsa Italiana (scarto peggiore sul cumulato end-to-end {peggior_cum:.2f} pt; sui
 * rendimenti giornalieri, mediana peggiore {peggior_rend:.3f} pt). Se la verifica
 * fallisce, questo file semplicemente non viene rigenerato.
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_xd_performance.py`
 * (archivio Xtrackers). Non modificare a mano.
 */
export type XdPerformance = {{
  updated: string // data di generazione (YYYY-MM-DD)
  start: string // prima seduta comune (base = 0%)
  dates: string[] // sedute (YYYY-MM-DD), allineate alle serie
  cum: Record<'20' | '40' | '60' | '80', number[]> // rendimento cumulato %
  dd: Record<'20' | '40' | '60' | '80', number[]> // drawdown % dal massimo
  maxDd: Record<'20' | '40' | '60' | '80', {{ pct: number; date: string }}>
}}

export const XD_PERFORMANCE: XdPerformance = {{
  updated: '{oggi}',
  start: '{start}',
  dates: [{", ".join(f"'{d}'" for d in date_comuni)}],
  cum: {{
    '20': {arr(cum["20"])},
    '40': {arr(cum["40"])},
    '60': {arr(cum["60"])},
    '80': {arr(cum["80"])},
  }},
  dd: {{
    '20': {arr(dd["20"])},
    '40': {arr(dd["40"])},
    '60': {arr(dd["60"])},
    '80': {arr(dd["80"])},
  }},
  maxDd: {{
    '20': {{ pct: {max_dd["20"][0]:g}, date: '{max_dd["20"][1]}' }},
    '40': {{ pct: {max_dd["40"][0]:g}, date: '{max_dd["40"][1]}' }},
    '60': {{ pct: {max_dd["60"][0]:g}, date: '{max_dd["60"][1]}' }},
    '80': {{ pct: {max_dd["80"][0]:g}, date: '{max_dd["80"][1]}' }},
  }},
}}
"""
    with open(DEST, "w") as f:
        f.write(body)
    print(f"[xd-perf] scritto {DEST}: {len(date_comuni)} sedute dal {start}, "
          f"max DD: " + ", ".join(f"{p}%={max_dd[p][0]}%" for p in ("20", "40", "60", "80")))

if __name__ == "__main__":
    main()
