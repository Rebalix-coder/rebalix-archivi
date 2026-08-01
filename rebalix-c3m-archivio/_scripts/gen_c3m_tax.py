#!/usr/bin/env python3
"""Rigenera `lib/blog/c3m-tax.ts`: quote white list e aliquote effettive di C3M E XEON
DAL DB `etf_whitelist` — quota corrente + STORICO COMPLETO dei semestri di entrambi.

Lo storico serve al pezzo esclusivo dell'articolo: «quanto ti rimane se lo vendi» —
l'aliquota che conta è quella del semestre della VENDITA, e per XEON balla parecchio
(12,87% H1-2023 → 15,46% H2-2026: dipende dal collaterale dello swap) mentre C3M è
inchiodata (~12,6-12,7%: paniere di titoli di Stato). Registro del passato, MAI
consiglio di timing (non-inducement).

Golden (fail-loud, altrimenti NON scrive): entrambi gli ISIN presenti; quote in [0,100];
storia C3M ≥ 4 semestri CONTIGUI (il buco H1-2026 è stato riparato il 28/07/2026 e non
deve riaprirsi in silenzio); storia XEON ≥ 10 semestri.
Aliquota effettiva = 12,5%·q + 26%·(1−q) (DM 13/12/2011 + Circ. AE 11/E/2012).
"""
import os, re, sys, json, datetime, urllib.request, urllib.error

REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "c3m-tax.ts")
ISINS = {"c3m": "FR0010754200", "xeon": "LU0290358497"}
MIN_SEMESTRI = {"c3m": 4, "xeon": 10}

NET_ERR = (urllib.error.URLError, OSError)


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


def aliquota(q):
    return round(12.5 * q / 100 + 26 * (1 - q / 100), 2)


def semestre_label(valid_to):
    y, m = valid_to[:4], valid_to[5:7]
    return f"{'1°' if m <= '06' else '2°'} sem. {y}"


def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print("[c3m-tax] repo non trovato — salto."); return
    env = load_env()
    base = env.get("NEXT_PUBLIC_SUPABASE_URL")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY") or env.get("SUPABASE_SECRET_KEY")
    if not base or not key:
        print("[c3m-tax] env DB assente — salto."); return

    storici = {}
    for nome, isin in ISINS.items():
        url = (f"{base}/rest/v1/etf_whitelist?isin=eq.{isin}"
               f"&order=valid_from.asc&select=valid_from,valid_to,whitelist_pct")
        req = urllib.request.Request(url, headers={"apikey": key, "Authorization": f"Bearer {key}"})
        def _go(req=req):
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)
        righe = net_retry(_go)
        if len(righe) < MIN_SEMESTRI[nome]:
            sys.exit(f"[c3m-tax] GOLDEN FALLITO: {nome} ha {len(righe)} semestri (<{MIN_SEMESTRI[nome]}) — NON scrivo")
        for r in righe:
            q = float(r["whitelist_pct"])
            if not (0 <= q <= 100):
                sys.exit(f"[c3m-tax] GOLDEN FALLITO: quota {nome} fuori range: {q} — NON scrivo")
        storici[nome] = righe

    # contiguità C3M: ogni semestre attacca al precedente (il buco H1-2026 non deve riaprirsi)
    c3m = storici["c3m"]
    for prev, cur in zip(c3m, c3m[1:]):
        d_prev = datetime.date.fromisoformat(prev["valid_to"])
        d_cur = datetime.date.fromisoformat(cur["valid_from"])
        if (d_cur - d_prev).days != 1:
            sys.exit(f"[c3m-tax] GOLDEN FALLITO: buco C3M tra {prev['valid_to']} e {cur['valid_from']} — NON scrivo")

    def blocco(nome):
        righe = storici[nome]
        hist = ",\n    ".join(
            f"{{ from: '{r['valid_from']}', to: '{r['valid_to']}', label: '{semestre_label(r['valid_to'])}', "
            f"pct: {float(r['whitelist_pct']):.3f}, aliquota: {aliquota(float(r['whitelist_pct']))} }}"
            for r in righe)
        cur = righe[-1]
        return (f"{{\n  current: {{ from: '{cur['valid_from']}', to: '{cur['valid_to']}', "
                f"label: '{semestre_label(cur['valid_to'])}', pct: {float(cur['whitelist_pct']):.3f}, "
                f"aliquota: {aliquota(float(cur['whitelist_pct']))} }},\n  history: [\n    {hist},\n  ],\n}}")

    # data-derivata: inizio del semestre più recente (mai run-date → output deterministico)
    ultimo_semestre = max(s[-1]["valid_from"] for s in storici.values())
    ts = f"""/**
 * Fiscalità white list di C3M (FR0010754200) e XEON (LU0290358497) DAL DB
 * `etf_whitelist`: quota corrente + storico completo dei semestri di entrambi.
 * Aliquota effettiva = 12,5%·q + 26%·(1−q) (DM 13/12/2011 + Circ. AE 11/E/2012).
 * Conta la quota del semestre della VENDITA: lo storico alimenta il grafico
 * «quanto ti rimane se vendi» (registro del passato, mai consiglio di timing).
 * Fonte quote: documenti fiscali ufficiali degli emittenti, ingeriti semestralmente
 * (archivio dei documenti in ~/backups/rebalix-whitelist-docs, audit a ogni ingest).
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_c3m_tax.py`
 * (archivio C3M). Non modificare a mano.
 */
export type WlSemestre = {{ from: string; to: string; label: string; pct: number; aliquota: number }}
export type WlTax = {{ current: WlSemestre; history: WlSemestre[] }}

export const C3M_TAX_UPDATED = '{ultimo_semestre}' // inizio del semestre più recente

export const C3M_TAX: WlTax = {blocco('c3m')}

export const XEON_TAX_HISTORY: WlTax = {blocco('xeon')}
"""
    with open(DEST, "w") as f:
        f.write(ts)
    c_cur, x_cur = storici["c3m"][-1], storici["xeon"][-1]
    print(f"[c3m-tax] scritto: C3M {len(c3m)} semestri (corrente {float(c_cur['whitelist_pct']):.2f}% → "
          f"{aliquota(float(c_cur['whitelist_pct']))}%), XEON {len(storici['xeon'])} semestri "
          f"(corrente {float(x_cur['whitelist_pct']):.2f}% → {aliquota(float(x_cur['whitelist_pct']))}%)")


if __name__ == "__main__":
    main()
