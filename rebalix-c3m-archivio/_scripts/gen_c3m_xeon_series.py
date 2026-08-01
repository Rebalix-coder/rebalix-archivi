#!/usr/bin/env python3
"""Serie NAV MENSILE di XEON per il bottone «Confronta» del grafico cumulato C3M
(deciso con Linus 29/7: confronto NAV/NAV, mai NAV-contro-prezzi).
Fonte: API DWS performancechart (NAV ufficiale, la stessa triangolata al centesimo
il 28/7). Livelli mensili (ultimo NAV del mese): il componente ribasa alla prima
data mostrata e deflaziona in modalità reale — i livelli sono la forma flessibile.
Generatore SEPARATO da gen_c3m_performance: un guasto DWS non deve bloccare
l'aggiornamento dei dati C3M (fail-soft di sistema, fail-loud di file).

GOLDEN (fail-loud): rendimenti per anno solare dalla serie mensile vs dichiarati
DWS validati (2023 +3,27 / 2024 +3,79 / 2025 +2,23) entro 0,1 pt; freschezza ≤10gg.
"""
import json, os, sys, datetime, urllib.request, urllib.error

REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "c3m-xeon-series.ts")
URL = "https://etf.dws.com/api/pdp/it-it/etf/LU0290358497/performancechart"
ATTESI = {"2023": 3.27, "2024": 3.79, "2025": 2.23}  # dichiarati DWS, triangolati 28/7
SOGLIA = 0.1
FRESCHEZZA_GIORNI = 10

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


def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print("[c3m-xeon-series] repo non trovato — salto."); return
    req = urllib.request.Request(URL, headers={"User-Agent": "Mozilla/5.0"})
    def _go():
        with urllib.request.urlopen(req, timeout=60) as r:
            return json.load(r)
    d = net_retry(_go)
    vals = d["values"]
    mensile = {}
    for ts, row in vals:
        dt = datetime.datetime.utcfromtimestamp(ts / 1000).date()
        if row[0][0] is not None:
            mensile[dt.isoformat()[:7]] = float(row[0][0])  # ultimo del mese vince
    yms = sorted(mensile)
    ultimo_ym = yms[-1]
    # freschezza: l'ultimo mese deve essere quello corrente o il precedente
    oggi = datetime.date.today()
    eta_mesi = (oggi.year * 12 + oggi.month) - (int(ultimo_ym[:4]) * 12 + int(ultimo_ym[5:7]))
    if eta_mesi > 1:
        sys.exit(f"[c3m-xeon-series] serie ferma a {ultimo_ym}: fonte DWS ferma — NON scrivo")
    # golden: annuali dalla serie mensile vs dichiarati
    for anno, atteso in ATTESI.items():
        prev = f"{int(anno)-1}-12"
        if prev not in mensile or f"{anno}-12" not in mensile:
            sys.exit(f"[c3m-xeon-series] manca {anno} nella serie — NON scrivo")
        r = (mensile[f"{anno}-12"] / mensile[prev] - 1) * 100
        if abs(r - atteso) > SOGLIA:
            sys.exit(f"[c3m-xeon-series] GOLDEN FALLITO {anno}: {r:.2f} vs atteso {atteso} — NON scrivo")

    ts_out = f"""/**
 * NAV MENSILE di XEON (Xtrackers II EUR Overnight Rate Swap, LU0290358497) per il
 * bottone «Confronta» del cumulato C3M: livelli di fine mese dal NAV ufficiale DWS.
 * Regola di parità (29/7/2026): confronto NAV/NAV — il componente ribasa alla prima
 * data mostrata. Golden: annuali dalla serie vs dichiarati DWS entro {SOGLIA} pt.
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_c3m_xeon_series.py`
 * (archivio C3M). Non modificare a mano.
 */
export const XEON_NAV_MONTHLY: {{ updated: string; months: string[]; nav: number[] }} = {{
  updated: '{ultimo_ym}-01', // ultimo mese in serie (data-derivata)
  months: {json.dumps(yms)},
  nav: {json.dumps([round(mensile[m], 4) for m in yms])},
}}
"""
    with open(DEST, "w") as f:
        f.write(ts_out)
    print(f"[c3m-xeon-series] scritto: {len(yms)} mesi {yms[0]}→{ultimo_ym}, golden ok")


if __name__ == "__main__":
    main()
