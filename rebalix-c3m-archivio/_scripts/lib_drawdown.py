"""Drawdown «raccontabili» dai dati, senza interventi umani (Linus 19/9/2026: «pensa a una
soluzione che non sia un intervento umano»). Condivisa da gen_c3m_performance.py e
gen_c3m_xeon_compare.py (sulla VPS: _scripts/lib_drawdown.py).

Il problema: una prosa che racconta UN episodio («picco 2014 → minimo 2022, erosione dei tassi
negativi») con numeri liberi di descriverne un altro. La soluzione:
  1. l'EPISODIO DEI TASSI NEGATIVI è DEFINITO, non scelto: la finestra in cui l'INDICE del fondo
     rende ≤ 0 su 3 mesi (tratti uniti se separati da meno di 12 mesi; la più lunga), e dentro
     la finestra il drawdown più profondo (picco precedente → minimo → recupero). La prosa
     «erosione lenta nell'era dei tassi negativi» è vera per costruzione: descrive quella finestra;
  2. il MASSIMO DI SEMPRE è un secondo numero; se non coincide con l'episodio storico, il testo
     lo dice e lo CLASSIFICA (erosione / shock / altro) da tre proprietà misurabili — profondità,
     durata picco→minimo, velocità (caduta peggiore in 20 sedute) — senza pretendere di spiegarlo;
  3. nessuna sentinella che chieda una persona per pubblicare: restano solo le guardie sul dato
     rotto (serie vuota, finestra non trovata), che lasciano in piedi l'ultimo modulo buono.
"""
import datetime

SEDUTE_3M = 63
GAP_UNIONE_GIORNI = 365
SHOCK_PCT, SHOCK_SEDUTE = 0.5, 20          # ≥ 0,5 % perso in ≤ 20 sedute = shock (scala di un monetario: un −0,5 % in un mese è un crollo)
EROSIONE_MESI, EROSIONE_MAX_20 = 24, 0.3   # ≥ 24 mesi picco→minimo e mai più di 0,3 % in 20 sedute = erosione
SOGLIE = {"shockPct": SHOCK_PCT, "shockSedute": SHOCK_SEDUTE, "erosioneMesi": EROSIONE_MESI, "erosioneMax20": EROSIONE_MAX_20}   # emesse nel modulo: il testo le legge, mai duplicate


def ordina(serie):
    return sorted((d, float(v)) for d, v in serie.items() if v is not None and v > 0)


class DatoRotto(Exception):
    """La finestra non è calcolabile in modo onesto: il chiamante non scrive il modulo."""


def finestra_tassi_negativi(indice):
    """→ {da, a, aperta} del tratto più lungo in cui il rendimento a 3 mesi dell'indice è ≤ 0, oppure None.
    DatoRotto se la finestra è TRONCA IN TESTA (parte alla prima seduta calcolabile: l'indice non copre
    l'inizio dell'era → una finestra dipendente dalla copertura sarebbe un cambio muto). Una finestra
    ancora aperta in coda (era in corso) è legittima: viene dichiarata `aperta` e il testo lo dice."""
    p = ordina(indice)
    if len(p) < SEDUTE_3M + 50:
        return None
    tratti, cur = [], None
    for i in range(SEDUTE_3M, len(p)):
        if p[i][1] / p[i - SEDUTE_3M][1] - 1 <= 0:
            cur = cur or [p[i][0], p[i][0]]
            cur[1] = p[i][0]
        elif cur:
            tratti.append(cur); cur = None
    if cur:
        tratti.append(cur)
    if not tratti:
        return None
    uniti = [tratti[0]]
    for t in tratti[1:]:   # parentesi brevi (BOT nel giugno 2020) non spezzano l'era
        if (t[0] - uniti[-1][1]).days <= GAP_UNIONE_GIORNI:
            uniti[-1][1] = t[1]
        else:
            uniti.append(t)
    da, a = max(uniti, key=lambda t: (t[1] - t[0]).days)
    if da <= p[SEDUTE_3M + 5][0]:
        raise DatoRotto(f"finestra dei tassi negativi tronca in testa ({da}): l'indice parte dal {p[0][0]}, non copre l'inizio dell'era")
    return {"da": da, "a": a, "aperta": a == p[-1][0]}


def _episodio(p, trough_i):
    """Dal minimo (indice in p) ricostruisce picco precedente, recupero, durata e velocità."""
    picco_i = max(range(trough_i + 1), key=lambda i: (p[i][1], i))   # a parità di valore l'ULTIMO giorno al massimo: «sotto il picco» = strettamente sotto
    picco_v, picco_d, trough_d = p[picco_i][1], p[picco_i][0], p[trough_i][0]
    rec = next((p[i][0] for i in range(trough_i + 1, len(p)) if p[i][1] >= picco_v), None)
    peggiore, peggiore_d = 0.0, trough_d
    for i in range(picco_i + 1, trough_i + 1):   # caduta peggiore su una finestra di ≤ 20 sedute dentro la discesa
        r = (p[i][1] / p[max(picco_i, i - SHOCK_SEDUTE)][1] - 1) * 100
        if r < peggiore:
            peggiore, peggiore_d = r, p[i][0]
    mesi_discesa = (trough_d - picco_d).days / 30.4375
    dd = round((p[trough_i][1] / picco_v - 1) * 100, 2)
    if -peggiore >= SHOCK_PCT:
        classe = "shock"
    elif mesi_discesa >= EROSIONE_MESI and -peggiore <= EROSIONE_MAX_20:
        classe = "erosione"
    else:
        classe = "altro"
    fine = rec or p[-1][0]
    if dd == 0:
        raise DatoRotto("serie senza alcun calo: nessun episodio di drawdown da raccontare")
    return {"maxDdPct": dd, "peakYm": picco_d.isoformat()[:7], "peakDate": picco_d.isoformat(),
            "troughYm": trough_d.isoformat()[:7], "troughDate": trough_d.isoformat(),
            "recoveryDate": rec.isoformat() if rec else None,
            "monthsUnderwater": round((fine - picco_d).days / 30.4375),
            "monthsToTrough": round(mesi_discesa),
            "worst20Pct": round(peggiore, 2), "worst20Date": peggiore_d.isoformat(), "classe": classe}


def drawdown_massimo(nav):
    """Episodio del massimo drawdown di sempre (giornaliero, come la FAQ della scheda)."""
    p = ordina(nav)
    picco, min_dd, trough_i = -1e9, 0.0, 0
    for i, (d, v) in enumerate(p):
        picco = max(picco, v)
        dd = v / picco - 1
        if dd < min_dd:
            min_dd, trough_i = dd, i
    ep = _episodio(p, trough_i)
    # caduta peggiore in ≤ 20 sedute su TUTTA la storia (non solo nell'episodio massimo): «qui non vedrai crolli»
    # deve cadere anche per un crollo che poi recupera e non diventa il massimo di sempre
    peggiore, peggiore_d = 0.0, p[0][0]
    for i in range(1, len(p)):
        r = (p[i][1] / p[max(0, i - SHOCK_SEDUTE)][1] - 1) * 100
        if r < peggiore:
            peggiore, peggiore_d = r, p[i][0]
    ep.update({"firstYm": p[0][0].isoformat()[:7], "lastYm": p[-1][0].isoformat()[:7],
               "worst20Ever": round(peggiore, 2), "worst20EverDate": peggiore_d.isoformat()})
    return ep


def episodio_tassi_negativi(nav, indice):
    """Drawdown più profondo con il MINIMO dentro la finestra dei tassi negativi, oppure None."""
    fin = finestra_tassi_negativi(indice)
    if not fin:
        return None
    p = ordina(nav)
    picco, min_dd, trough_i = -1e9, 0.0, None
    for i, (d, v) in enumerate(p):
        picco = max(picco, v)
        dd = v / picco - 1
        if fin["da"] <= d <= fin["a"] and dd < min_dd:
            min_dd, trough_i = dd, i
    if trough_i is None:
        return None
    return {"finestra": {"da": fin["da"].isoformat(), "a": fin["a"].isoformat(), "aperta": fin["aperta"]}, **_episodio(p, trough_i)}


def racconto(nav, indice, finestra_precedente=None):
    """→ {massimo, tassiNegativi, coincide, soglie}: tutto ciò che serve ai template dell'articolo.
    DatoRotto (o tassiNegativi None) = il chiamante NON scrive. `finestra_precedente` = la finestra del modulo
    già committato: se cambia, lo si dice nel log (cambio non muto, ma nemmeno bloccante: il testo resta
    vero per costruzione, e una seconda era di tassi negativi più lunga è un fatto, non un guasto)."""
    massimo = drawdown_massimo(nav)
    tn = episodio_tassi_negativi(nav, indice)
    if tn and finestra_precedente and (tn["finestra"]["da"], tn["finestra"]["a"]) != tuple(finestra_precedente):
        print(f"   ⚠ finestra dei tassi negativi CAMBIATA: {finestra_precedente[0]} → {finestra_precedente[1]} diventa "
              f"{tn['finestra']['da']} → {tn['finestra']['a']} (l'episodio storico raccontato cambia con lei)")
    coincide = bool(tn) and tn["troughDate"] == massimo["troughDate"]
    return {"massimo": massimo, "tassiNegativi": tn, "coincide": coincide, "soglie": SOGLIE}


def finestra_nel_file(percorso):
    """Legge la finestra dei tassi negativi dal modulo TS già committato (per dire nel log se cambia); None se assente."""
    import os, re
    if not os.path.exists(percorso):
        return None
    m = re.search(r'"finestra":\s*\{"da":\s*"(\d{4}-\d{2}-\d{2})",\s*"a":\s*"(\d{4}-\d{2}-\d{2})"', open(percorso).read())
    return (m.group(1), m.group(2)) if m else None
