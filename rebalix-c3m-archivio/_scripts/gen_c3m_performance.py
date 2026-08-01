#!/usr/bin/env python3
"""Rigenera `lib/blog/c3m-performance.ts`: cumulato, drawdown e tracking difference di
C3M (Amundi Euro Government Bond 0-6M, FR0010754200) dal NAV UFFICIALE Amundi e
dall'indice ribasato (adjustedBenchPrice), archiviati ogni giorno alle 10:45.

PERCHE' IL NAV e non il prezzo di borsa (stessa decisione Xtrackers/LS): il NAV è il
valore vero del paniere e combacia con la controprova che i lettori faranno su altri
siti (che usano il NAV). La serie Yahoo Milano su C3M restituisce solo ~9 mesi recenti:
buona per la controprova, inservibile come fonte.
⚠️ adjustedBenchPrice è RIBASATO (livello ~110 vs NAV ~127): si confrontano SOLO
rendimenti, mai livelli.

GOLDEN TEST (fail-loud), TRE controlli — se uno fallisce il modulo NON viene scritto:
  a) DICHIARATO: i rendimenti per anno solare calcolati da noi devono combaciare con le
     performance DICHIARATE da Amundi (metrics nel raw dello snapshot) entro 0,05 punti —
     è la controprova più forte, verificata al centesimo il 28/07/2026 su 8 anni;
  b) YAHOO: cumulato end-to-end sulla finestra sovrapposta prezzo-di-borsa vs NAV ≤ 1,5
     punti + livello massimo ≤ 3% (split non gestiti impossibili da mancare);
  c) FRESCHEZZA: ultimo NAV in archivio ≤ 7 giorni.
Regole metriche: serie >1 anno → annualizzato ammesso; acc = total return; TD per anno
solare = rendimento fondo − rendimento indice sull'ultima seduta comune dell'anno.
"""
import json, os, sys, datetime, statistics, urllib.request, urllib.error

ARCHIVE = os.path.expanduser("~/backups/rebalix-c3m-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "c3m-performance.ts")

SOGLIA_DICHIARATO = 0.05   # punti: |nostro anno solare − dichiarato Amundi|
SOGLIA_CUMULATO = 1.5      # punti: Yahoo vs NAV sulla finestra sovrapposta
SOGLIA_LIVELLO = 3.0       # %: scarto massimo di livello Yahoo vs NAV
FRESCHEZZA_GIORNI = 7

NET_ERR = (urllib.error.URLError, OSError)


def net_retry(fn):
    import time
    for i, pausa in enumerate((5, 20, 0)):
        try:
            return fn()
        except NET_ERR as e:
            if i == 2:
                raise
            print(f"   rete instabile ({type(e).__name__}) — ritento tra {pausa}s")
            time.sleep(pausa)


def serie(path):
    punti = json.load(open(os.path.join(ARCHIVE, "nav", path)))
    out = {}
    for p in punti:
        d = datetime.datetime.utcfromtimestamp(p["date"] / 1000).date()
        if p.get("data") is not None:
            out[d] = float(p["data"])
    return out


def yahoo_serie(sym):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{sym}?range=2y&interval=1d"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    def _go():
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    d = net_retry(_go)["chart"]["result"][0]
    ts, close = d["timestamp"], d["indicators"]["quote"][0]["close"]
    return {datetime.datetime.utcfromtimestamp(t).date(): c for t, c in zip(ts, close) if c}


def dd_storico_completo():
    """Drawdown sull'INTERO storico (Parigi mensile dal 2009, stessa fonte della rotta
    live): numeri per la prosa della sez. 6. SENTINELLA sull'episodio raccontato: la
    narrativa dell'articolo descrive il picco 2014-15 → minimo estate 2022; se un
    nuovo episodio lo supera, i numeri nuovi sotto la vecchia storia sarebbero una
    bugia → fail-loud, riscrittura umana (pattern «mai cambi muti»)."""
    EPISODIO_RACCONTATO = {"trough": "2022-08", "max_dd_circa": -4.9, "tolleranza_pt": 0.5}
    url = "https://query1.finance.yahoo.com/v8/finance/chart/C3M.PA?range=max&interval=1mo"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    def _go():
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    d = net_retry(_go)["chart"]["result"][0]
    ts, close = d["timestamp"], d["indicators"]["quote"][0]["close"]
    mesi = {}
    for t, c in zip(ts, close):
        if c is not None:
            mesi[datetime.datetime.utcfromtimestamp(t).date().isoformat()[:7]] = c
    yms = sorted(mesi)
    picco, picco_ym = -1e9, yms[0]
    min_dd, trough_ym, peak_of_trough = 0.0, yms[0], yms[0]
    streak, longest = 0, 0
    for ym in yms:
        v = mesi[ym]
        if v >= picco:
            picco, picco_ym, streak = v, ym, 0
        else:
            streak += 1
            longest = max(longest, streak)
        dd = (v / picco - 1) * 100
        if dd < min_dd:
            min_dd, trough_ym, peak_of_trough = dd, ym, picco_ym
    min_dd = round(min_dd, 2)
    if (trough_ym != EPISODIO_RACCONTATO["trough"]
            or abs(min_dd - EPISODIO_RACCONTATO["max_dd_circa"]) > EPISODIO_RACCONTATO["tolleranza_pt"]):
        sys.exit(f"[c3m-performance] SENTINELLA EPISODIO: max drawdown ora {min_dd}% ({trough_ym}), "
                 f"raccontato {EPISODIO_RACCONTATO['max_dd_circa']}% ({EPISODIO_RACCONTATO['trough']}) — "
                 f"la NARRATIVA della sez. 6 va riscritta a mano, NON scrivo")
    return {"maxDdPct": min_dd, "troughYm": trough_ym, "peakYm": peak_of_trough,
            "monthsUnderwater": longest, "firstYm": yms[0], "lastYm": yms[-1]}


def dichiarate_da_raw():
    """Ultimo snapshot raw → metriche dichiarate Amundi {(indicatore, periodo): valore%}."""
    raws = sorted(os.listdir(os.path.join(ARCHIVE, "raw")))
    if not raws:
        return {}, None
    p = json.load(open(os.path.join(ARCHIVE, "raw", raws[-1])))
    out = {}
    for m in p.get("metrics") or []:
        if m.get("value") is not None:
            out[(m["indicator"], m["period"])] = float(m["value"]) * 100
    return out, raws[-1]


def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print("[c3m-performance] repo non trovato — salto."); return
    nav, idx = serie("officialNav.json"), serie("adjustedBenchPrice.json")
    comuni = sorted(set(nav) & set(idx))
    if len(comuni) < 500:
        sys.exit(f"[c3m-performance] solo {len(comuni)} date comuni: archivio rotto?")

    # freschezza
    ultimo = max(nav)
    eta = (datetime.date.today() - ultimo).days
    if eta > FRESCHEZZA_GIORNI:
        sys.exit(f"[c3m-performance] NAV fermo a {ultimo} ({eta}gg): fonte ferma, NON scrivo")

    # rendimenti per anno solare (ultima seduta comune di ogni anno) + TD
    per_anno = {}
    fine_anno = {}
    for d in comuni:
        fine_anno[d.year] = d
    anni = sorted(fine_anno)
    for prev, anno in zip(anni, anni[1:]):
        d0, d1 = fine_anno[prev], fine_anno[anno]
        rf = nav[d1] / nav[d0] - 1
        ri = idx[d1] / idx[d0] - 1
        per_anno[anno] = {"fund": round(rf * 100, 2), "index": round(ri * 100, 2),
                          "tdBp": round((rf - ri) * 10000)}

    # GOLDEN a) — dichiarato Amundi vs nostro, solo anni pieni
    dich, raw_usato = dichiarate_da_raw()
    confrontati = 0
    oggi_anno = datetime.date.today().year
    for anno, v in per_anno.items():
        if anno >= oggi_anno:
            continue
        for indicatore, chiave in (("shareCalendarPerformance", "fund"),
                                   ("benchmarkCalendarPerformance", "index")):
            atteso = dich.get((indicatore, str(anno)))
            if atteso is None:
                continue
            scarto = abs(v[chiave] - atteso)
            if scarto > SOGLIA_DICHIARATO:
                sys.exit(f"[c3m-performance] GOLDEN a) FALLITO {anno} {chiave}: "
                         f"nostro {v[chiave]} vs dichiarato {atteso:.2f} (Δ{scarto:.2f}pt) — NON scrivo")
            confrontati += 1
    if confrontati < 8:
        sys.exit(f"[c3m-performance] GOLDEN a): solo {confrontati} confronti col dichiarato (<8): raw senza metriche?")

    # GOLDEN b) — Yahoo sulla finestra sovrapposta
    yh = yahoo_serie("C3M.MI")
    overlap = sorted(set(yh) & set(nav))
    if len(overlap) >= 60:
        y0, y1 = overlap[0], overlap[-1]
        cum_y = (yh[y1] / yh[y0] - 1) * 100
        cum_n = (nav[y1] / nav[y0] - 1) * 100
        if abs(cum_y - cum_n) > SOGLIA_CUMULATO:
            sys.exit(f"[c3m-performance] GOLDEN b) FALLITO: cumulato Yahoo {cum_y:.2f} vs NAV {cum_n:.2f} — NON scrivo")
        liv = max(abs(yh[d] / nav[d] - 1) * 100 for d in overlap)
        if liv > SOGLIA_LIVELLO:
            sys.exit(f"[c3m-performance] GOLDEN b) FALLITO: scarto di livello max {liv:.1f}% — NON scrivo")
        golden_yahoo = f"cumulato Δ{abs(cum_y - cum_n):.2f}pt, livello max {liv:.2f}% su {len(overlap)} sedute"
    else:
        golden_yahoo = f"finestra Yahoo insufficiente ({len(overlap)} sedute): saltato, fa fede il dichiarato"

    # serie cumulato + drawdown (dal primo giorno comune)
    base_n, base_i = nav[comuni[0]], idx[comuni[0]]
    dates, cum_f, cum_i, dd = [], [], [], []
    picco = 0.0
    max_dd, max_dd_date = 0.0, comuni[0]
    for d in comuni:
        cf = (nav[d] / base_n - 1) * 100
        ci = (idx[d] / base_i - 1) * 100
        picco = max(picco, cf)
        # drawdown dal massimo, in % dal picco del VALORE (non dei punti percentuali)
        v = (1 + cf / 100) / (1 + picco / 100) - 1
        ddv = round(v * 100, 3)
        if ddv < max_dd:
            max_dd, max_dd_date = ddv, d
        dates.append(d.isoformat())
        cum_f.append(round(cf, 3))
        cum_i.append(round(ci, 3))
        dd.append(ddv)

    full_dd = dd_storico_completo()

    # annualizzato intero periodo (serie ≫ 1 anno)
    anni_tot = (comuni[-1] - comuni[0]).days / 365.25
    ann_f = ((nav[comuni[-1]] / base_n) ** (1 / anni_tot) - 1) * 100
    ann_i = ((idx[comuni[-1]] / base_i) ** (1 / anni_tot) - 1) * 100

    oggi = datetime.date.today().isoformat()
    anni_righe = ",\n    ".join(
        f"'{a}': {{ fund: {v['fund']}, index: {v['index']}, tdBp: {v['tdBp']} }}"
        for a, v in sorted(per_anno.items()))
    ts = f"""/**
 * Performance C3M (Amundi Euro Government Bond 0-6M): cumulato, drawdown e tracking
 * difference dal NAV UFFICIALE Amundi + indice ribasato (adjustedBenchPrice), serie
 * archiviate ogni giorno alle 10:45. La TD per anno solare = fondo − indice.
 *
 * QUALITÀ: i rendimenti per anno solare COMBACIANO con le performance dichiarate da
 * Amundi entro {SOGLIA_DICHIARATO} punti ({confrontati} confronti, raw {raw_usato});
 * controprova Borsa Italiana via Yahoo: {golden_yahoo}.
 * Se una verifica fallisce, questo file semplicemente non viene rigenerato.
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_c3m_performance.py`
 * (archivio C3M). Non modificare a mano.
 */
export type C3mPerformance = {{
  updated: string
  start: string // prima seduta comune NAV/indice (base = 0%)
  dates: string[]
  cumFund: number[] // rendimento cumulato fondo %
  cumIndex: number[] // rendimento cumulato indice %
  dd: number[] // drawdown % dal massimo (fondo)
  maxDd: {{ pct: number; date: string }}
  // drawdown sull'INTERO storico (prezzi Parigi mensili dal 2009, fonte della rotta live);
  // una SENTINELLA nel generatore blocca la riscrittura se l'episodio raccontato cambia
  fullDd: {{ maxDdPct: number; troughYm: string; peakYm: string; monthsUnderwater: number; firstYm: string; lastYm: string }}
  annualized: {{ fund: number; index: number; tdBp: number; years: number }}
  byYear: Record<string, {{ fund: number; index: number; tdBp: number }}> // anno solare
}}

export const C3M_PERFORMANCE: C3mPerformance = {{
  updated: '{dates[-1]}', // ultima seduta NAV (data-derivata: niente freschezza finta)
  start: '{dates[0]}',
  dates: {json.dumps(dates)},
  cumFund: {json.dumps(cum_f)},
  cumIndex: {json.dumps(cum_i)},
  dd: {json.dumps(dd)},
  maxDd: {{ pct: {max_dd}, date: '{max_dd_date.isoformat()}' }},
  fullDd: {json.dumps(full_dd)},
  annualized: {{ fund: {ann_f:.3f}, index: {ann_i:.3f}, tdBp: {round((ann_f - ann_i) * 100)}, years: {anni_tot:.1f} }},
  byYear: {{
    {anni_righe},
  }},
}}
"""
    with open(DEST, "w") as f:
        f.write(ts)
    print(f"[c3m-performance] scritto: {len(dates)} sedute {dates[0]}→{dates[-1]}, "
          f"TD {round((ann_f - ann_i) * 100)}bp/a, maxDD {max_dd}% ({max_dd_date}), golden ok ({confrontati} vs dichiarato)")


if __name__ == "__main__":
    main()
