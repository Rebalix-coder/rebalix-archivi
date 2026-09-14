#!/usr/bin/env python3
"""Archiviatore SETTIMANALE dell'articolo «ETF a replica fisica o sintetica».

Onora le promesse della tabella «Quando si aggiorna questa pagina»:
  1. panieri sostitutivi vs indici (XSPU S&P 500, XMWO MSCI World) dagli export
     ufficiali DWS → rigenera lib/blog/repl-baskets.ts (conteggi, non-USA,
     top-10, titoli in comune, active share, righe-highlight);
  2. scarto sintetico-vs-fisico (I500 vs CSPX) dalle serie di performance
     incorporate nelle pagine prodotto iShares (CH, USD) → repl-td.ts;
  3. quota white-list XEON dai documenti fiscali semestrali DWS → se compare
     un semestre nuovo, repl-xeon-whitelist.ts;
  4. paniere fisico del fondo ibrido SCWX (Scalable MSCI AC World) dall'export
     DWS → repl-hybrid.ts (conteggio titoli, quota USA fisica, primi paesi).

Il rendimento da dividendo (repl-withholding.ts) resta a revisione manuale:
la fonte (scheda DWS «Index key facts») è una SPA senza endpoint noto.

Fail-soft per fonte (pattern broker-zero): se una fonte non risponde o i
numeri sono anomali si TIENE il modulo precedente e si segnala nel battito —
mai pubblicare un crollo che è solo un cambio di formato. Prima del deploy:
`npx tsc --noEmit` sui moduli rigenerati; se fallisce, revert e allarme.

Uso: python3 _archiver.py [--dry-run] [--force] [--no-deploy]
Cadenza: launchd lunedì 07:40 (RunAtLoad recupera se il Mac era spento;
lo stato in _state.json evita doppi giri nella stessa settimana ISO).
"""
import os, re, sys, json, math, shutil, zipfile, tempfile, datetime, subprocess, urllib.request
import xml.etree.ElementTree as ET

os.environ["PATH"] = "/usr/local/bin:/opt/homebrew/bin:" + os.environ.get("PATH", "")

ARCHIVE = os.path.expanduser("~/backups/rebalix-replica-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
BASKETS_REL = "lib/blog/repl-baskets.ts"
TD_REL = "lib/blog/repl-td.ts"
XEON_REL = "lib/blog/repl-xeon-whitelist.ts"
HYBRID_REL = "lib/blog/repl-hybrid.ts"
GIT = shutil.which("git") or "/usr/bin/git"
NPX = shutil.which("npx") or "/usr/local/bin/npx"

DRY = "--dry-run" in sys.argv
FORCE = "--force" in sys.argv
NO_DEPLOY = "--no-deploy" in sys.argv
TODAY = datetime.date.today()
YW = f"{TODAY.isocalendar()[0]}-W{TODAY.isocalendar()[1]:02d}"
SNAPDIR = os.path.join(ARCHIVE, "snapshots", TODAY.isoformat())

UA = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Safari/605.1.15"}
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"

XSPU, XWORLD, XEON_ISIN = "LU0490618542", "LU0274208692", "LU0290358497"
SCWX = "LU2903252349"  # Scalable MSCI AC World Xtrackers 1C — il fondo a replica ibrida
# Endpoint dati della SPA DWS (scovato dal traffico di rete, 26/7/2026): serve lo
# SLUG COMPLETO, non il solo ISIN. Restituisce NAV del fondo E indice, giornalieri.
SCWX_PERFCHART = "https://etf.dws.com/api/pdp/en-lu/etf/LU2903252349-scalable-msci-ac-world-xtrackers-ucits-etf-1c/performancechart"
# Il termine di paragone fisico sullo stesso indice (serie NAV incorporata nella pagina CH).
SSAC_URL = "https://www.ishares.com/ch/individual/en/products/251850/ishares-msci-acwi-ucits-etf"
DWS_BASKET = "https://etf.dws.com/etfdata/export/GBR/ENG/excel/product/constituent/{isin}/"
DWS_INDEX = "https://etf.dws.com/etfdata/export/GBR/ENG/excel/index/constituent/{isin}/"
DWS_FISC = "https://etf.dws.com/it-it/informativa-prodotti/etf-documenti/fiscalita-degli-etf/"
DWS_ASSET = "https://etf.dws.com/download/asset/{uid}"
ISHARES_I500 = "https://www.ishares.com/ch/individual/en/products/314989/ishares-s-p-500-swap-ucits-etf-fund"
ISHARES_CSPX = "https://www.ishares.com/ch/individual/en/products/253743/ishares-sp-500-b-ucits-etf-acc-fund"


def log(msg):
    line = f"{datetime.datetime.now():%Y-%m-%d %H:%M}  {msg}"
    print(line)
    with open(os.path.join(ARCHIVE, "_archiver.log"), "a") as f:
        f.write(line + "\n")


def fetch(url, dest=None, min_size=500, timeout=120):
    req = urllib.request.Request(url, headers=UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        data = r.read()
    if len(data) < min_size:
        raise RuntimeError(f"risposta sospetta ({len(data)}B) da {url}")
    if dest:
        with open(dest, "wb") as f:
            f.write(data)
    return data


# ── XLSX minimale (niente dipendenze) ────────────────────────────────────────

def xlsx_rows(path):
    z = zipfile.ZipFile(path)
    sheet = [n for n in z.namelist() if n.startswith("xl/worksheets/")][0]
    shared = []
    if "xl/sharedStrings.xml" in z.namelist():
        root = ET.fromstring(z.read("xl/sharedStrings.xml"))
        for si in root.findall(f"{NS}si"):
            shared.append("".join(t.text or "" for t in si.iter(f"{NS}t")))
    root = ET.fromstring(z.read(sheet))
    rows = []
    for row in root.iter(f"{NS}row"):
        vals = []
        for c in row.findall(f"{NS}c"):
            v = c.find(f"{NS}v")
            t = c.get("t")
            if v is None:
                vals.append("")
            elif t == "s":
                vals.append(shared[int(v.text)])
            elif t == "inlineStr":
                vals.append("".join(x.text or "" for x in c.iter(f"{NS}t")))
            else:
                vals.append(v.text)
        rows.append(vals)
    return rows


def norm_name(s):
    s = s.upper()
    s = re.sub(r"[^A-Z0-9 ]", " ", s)
    s = re.sub(r"\b(INC|CORP|CORPORATION|CO|PLC|LTD|SA|AG|NV|SE|GROUP|HOLDINGS?|COMPANY|THE|N)\b", "", s)
    return re.sub(r"\s+", " ", s).strip()


# ── 1) Panieri vs indici ─────────────────────────────────────────────────────

def parse_basket(path):
    """Righe a 11 colonne: [n, Name, ISIN, Country, Currency, …, Industry, Weight]."""
    recs = []
    for r in xlsx_rows(path):
        if len(r) == 11 and str(r[0]).isdigit():
            try:
                recs.append({"name": r[1], "country": r[3], "w": float(r[10])})
            except ValueError:
                pass
    return recs


def parse_index(path):
    """Righe [n, Name, Currency, Weighting] + 'As of' nell'intestazione."""
    recs, asof = [], None
    for r in xlsx_rows(path):
        if len(r) == 2 and r[0] == "As of":
            m = re.match(r"(\d{2})\.(\d{2})\.(\d{4})", r[1])
            if m:
                asof = f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        if len(r) == 4 and str(r[0]).isdigit():
            try:
                recs.append({"name": r[1], "w": float(r[3])})
            except ValueError:
                pass
    return recs, asof


HIGHLIGHT_XSPU = ["NVIDIA", "APPLE", "MICROSOFT", "SEAGATE TECHNOLOGY", "EDP", "RWE", "KIOXIA"]
HL_LABEL = {"NVIDIA": "NVIDIA", "APPLE": "Apple", "MICROSOFT": "Microsoft",
            "SEAGATE TECHNOLOGY": "Seagate Technology", "EDP": "EDP (Portogallo)",
            "RWE": "RWE (Germania)", "KIOXIA": "Kioxia (Giappone)"}
COUNTRY_IT = {"Japan": "Giappone", "Germany": "Germania", "Portugal": "Portogallo",
              "Canada": "Canada", "United Kingdom": "Regno Unito", "Switzerland": "Svizzera",
              "France": "Francia", "Netherlands": "Paesi Bassi", "Australia": "Australia",
              "Spain": "Spagna", "Italy": "Italia", "Sweden": "Svezia"}


def analyze_pair(basket, index):
    wb, wi = {}, {}
    for x in basket:
        wb[norm_name(x["name"])] = wb.get(norm_name(x["name"]), 0.0) + x["w"]
    for x in index:
        wi[norm_name(x["name"])] = wi.get(norm_name(x["name"]), 0.0) + x["w"]
    sum_b, sum_i = sum(wb.values()), sum(wi.values())
    if not (0.99 < sum_b < 1.01 and 0.99 < sum_i < 1.01):
        raise RuntimeError(f"somme pesi anomale: paniere {sum_b:.4f}, indice {sum_i:.4f}")
    common = set(wb) & set(wi)
    active = 0.5 * sum(abs(wb.get(k, 0) - wi.get(k, 0)) for k in set(wb) | set(wi))
    only_i = {k: wi[k] for k in set(wi) - set(wb)}
    top_b = sorted(wb.values(), reverse=True)
    top_i = sorted(wi.values(), reverse=True)
    return {
        "wb": wb, "wi": wi,
        "basketCount": len(basket), "indexCount": len(index),
        "top10BasketPct": round(100 * sum(top_b[:10]), 1),
        "top10IndexPct": round(100 * sum(top_i[:10]), 1),
        "commonCount": len(common),
        "commonWeightBasketPct": round(100 * sum(wb[k] for k in common), 1),
        "commonWeightIndexPct": round(100 * sum(wi[k] for k in common), 1),
        "indexOnlyCount": len(only_i),
        "indexOnlyWeightPct": round(100 * sum(only_i.values()), 1),
        "activeSharePct": round(100 * active, 1),
    }


def src_baskets(snapdir, prev):
    out = {}
    for key, isin, name, ticker, idxname in [
        ("xspu", XSPU, "Xtrackers S&P 500 Swap UCITS ETF 1C", "XSPU", "S&P 500"),
        ("world", XWORLD, "Xtrackers MSCI World Swap UCITS ETF 1C", "XMWO", "MSCI World (net total return)"),
    ]:
        bpath = os.path.join(snapdir, f"basket-{key}.xlsx")
        ipath = os.path.join(snapdir, f"index-{key}.xlsx")
        fetch(DWS_BASKET.format(isin=isin), bpath, min_size=5000)
        fetch(DWS_INDEX.format(isin=isin), ipath, min_size=5000)
        basket = parse_basket(bpath)
        index, idx_asof = parse_index(ipath)
        if not idx_asof:
            raise RuntimeError(f"[{key}] data indice non trovata")
        p = prev.get(key, {})
        if p and (len(basket) < 0.6 * p.get("basketCount", 0) or len(index) < 0.6 * p.get("indexCount", 0)):
            raise RuntimeError(f"[{key}] conteggi anomali: {len(basket)}/{len(index)} (prima {p.get('basketCount')}/{p.get('indexCount')})")
        a = analyze_pair(basket, index)
        if not (20 <= a["activeSharePct"] <= 90):
            raise RuntimeError(f"[{key}] active share fuori range: {a['activeSharePct']}")
        a.update({"isin": isin, "fundName": name, "ticker": ticker, "indexName": idxname,
                  "basketAsOf": TODAY.isoformat(), "indexAsOf": idx_asof})
        # dettagli solo per XSPU (tabella principale)
        if key == "xspu":
            by_c = {}
            for x in basket:
                c = x["country"]
                by_c.setdefault(c, [0.0, 0])
                by_c[c][0] += x["w"]; by_c[c][1] += 1
            non_us = {c: v for c, v in by_c.items() if "United States" not in c}
            a["nonUsCount"] = sum(v[1] for v in non_us.values())
            a["nonUsWeightPct"] = round(100 * sum(v[0] for v in non_us.values()), 1)
            top3 = sorted(non_us.items(), key=lambda kv: -kv[1][0])[:3]
            a["nonUsTop"] = [{"country": COUNTRY_IT.get(c, c), "weightPct": round(100 * v[0], 1), "holdings": v[1]} for c, v in top3]
            # highlight: pesi e ranking per i nomi-simbolo
            rank_b = {k: i + 1 for i, (k, _) in enumerate(sorted(a["wb"].items(), key=lambda kv: -kv[1]))}
            rank_i = {k: i + 1 for i, (k, _) in enumerate(sorted(a["wi"].items(), key=lambda kv: -kv[1]))}
            hl = []
            for probe in HIGHLIGHT_XSPU:
                kb = next((k for k in a["wb"] if k.startswith(norm_name(probe))), None)
                ki = next((k for k in a["wi"] if k.startswith(norm_name(probe))), None)
                b_w = a["wb"].get(kb) if kb else None
                i_w = a["wi"].get(ki) if ki else None
                b_rank = rank_b.get(kb) if kb else None
                i_rank = rank_i.get(ki) if ki else None
                hl.append({
                    "name": HL_LABEL[probe],
                    "basketPct": round(100 * b_w, 2) if (b_w and b_rank and b_rank <= 15) else None,
                    "indexPct": round(100 * i_w, 2) if (i_w and i_rank and i_rank <= 15) else None,
                    "basketRank": b_rank if (b_rank and b_rank <= 15) else None,
                    "indexRank": i_rank if (i_rank and i_rank <= 15) else None,
                })
            a["highlights"] = hl
        del a["wb"], a["wi"]
        out[key] = a
        log(f"[baskets:{key}] ok — {a['basketCount']}/{a['indexCount']} titoli, active share {a['activeSharePct']}%")
    return out


def render_baskets_ts(x, w):
    def hl_row(h):
        f = lambda v: "null" if v is None else (str(v))
        parts = [f"name: '{h['name']}'", f"basketPct: {f(h['basketPct'])}", f"indexPct: {f(h['indexPct'])}"]
        if h["basketRank"]:
            parts.append(f"basketRank: {h['basketRank']}")
        if h["indexRank"]:
            parts.append(f"indexRank: {h['indexRank']}")
        return "    { " + ", ".join(parts) + " },"
    hl = "\n".join(hl_row(h) for h in x["highlights"])
    top = "\n".join(
        f"      {{ country: '{r['country']}', weightPct: {r['weightPct']}, holdings: {r['holdings']} }},"
        for r in x["nonUsTop"])
    return f"""/**
 * Confronto paniere-sostitutivo vs indice per ETF sintetici (articolo
 * «ETF a replica fisica o sintetica»).
 *
 * FILE RIGENERATO AUTOMATICAMENTE da ~/backups/rebalix-replica-archivio/_archiver.py
 * (settimanale, lunedì). NON MODIFICARE A MANO.
 * Fonte: export ufficiali DWS (product/constituent e index/constituent per ISIN);
 * active share = ½·Σ|Δpeso| per denominazione normalizzata.
 */

export type ReplHighlightRow = {{
  name: string
  basketPct: number | null
  indexPct: number | null
  basketRank?: number
  indexRank?: number
}}

export type ReplFundComparison = {{
  fundName: string
  ticker: string
  isin: string
  indexName: string
  basketAsOf: string
  indexAsOf: string
  basketCount: number
  indexCount: number
  top10BasketPct: number
  top10IndexPct: number
  commonCount: number
  commonWeightBasketPct: number
  commonWeightIndexPct: number
  indexOnlyCount: number
  indexOnlyWeightPct: number
  indexOnlyExamples: string[]
  activeSharePct: number
  nonIndexCountry?: {{
    count: number
    weightPct: number
    top: {{ country: string; weightPct: number; holdings?: number }}[]
  }}
  highlights: ReplHighlightRow[]
}}

export const REPL_XSPU: ReplFundComparison = {{
  fundName: '{x["fundName"]}',
  ticker: '{x["ticker"]}',
  isin: '{x["isin"]}',
  indexName: '{x["indexName"]}',
  basketAsOf: '{x["basketAsOf"]}',
  indexAsOf: '{x["indexAsOf"]}',
  basketCount: {x["basketCount"]},
  indexCount: {x["indexCount"]},
  top10BasketPct: {x["top10BasketPct"]},
  top10IndexPct: {x["top10IndexPct"]},
  commonCount: {x["commonCount"]},
  commonWeightBasketPct: {x["commonWeightBasketPct"]},
  commonWeightIndexPct: {x["commonWeightIndexPct"]},
  indexOnlyCount: {x["indexOnlyCount"]},
  indexOnlyWeightPct: {x["indexOnlyWeightPct"]},
  indexOnlyExamples: ['JPMorgan', 'Exxon Mobil', 'Visa', 'Costco', 'Netflix'],
  activeSharePct: {x["activeSharePct"]},
  nonIndexCountry: {{
    count: {x["nonUsCount"]},
    weightPct: {x["nonUsWeightPct"]},
    top: [
{top}
    ],
  }},
  highlights: [
{hl}
  ],
}}

export const REPL_XWORLD: ReplFundComparison = {{
  fundName: '{w["fundName"]}',
  ticker: '{w["ticker"]}',
  isin: '{w["isin"]}',
  indexName: '{w["indexName"]}',
  basketAsOf: '{w["basketAsOf"]}',
  indexAsOf: '{w["indexAsOf"]}',
  basketCount: {w["basketCount"]},
  indexCount: {w["indexCount"]},
  top10BasketPct: {w["top10BasketPct"]},
  top10IndexPct: {w["top10IndexPct"]},
  commonCount: {w["commonCount"]},
  commonWeightBasketPct: {w["commonWeightBasketPct"]},
  commonWeightIndexPct: {w["commonWeightIndexPct"]},
  indexOnlyCount: {w["indexOnlyCount"]},
  indexOnlyWeightPct: {w["indexOnlyWeightPct"]},
  indexOnlyExamples: ['JPMorgan', 'Exxon Mobil', 'Eli Lilly', 'ASML', 'Visa'],
  activeSharePct: {w["activeSharePct"]},
  highlights: [],
}}

/** Il precedente storico: case study Vanguard Research (dic. 2020). */
export const REPL_VANGUARD_2019 = {{
  basketAsOf: '2019-05-31',
  basketCount: 354,
  indexCount: 1607,
  top10BasketPct: 39.7,
  top10IndexPct: 17.3,
  francePctBasket: 18.0,
  francePctIndex: 3.3,
  ukPctBasket: 0.0,
  ukPctIndex: 4.1,
  teExAntePct: 4.62,
}} as const

export const REPL_BASKETS_UPDATED = '{TODAY.isoformat()}'
"""


# ── 1-bis) Paniere fisico del fondo ibrido (SCWX) ────────────────────────────

def src_hybrid(snapdir, prev):
    """La firma dell'ibrido è il paniere quasi tutto ex-USA: conta i titoli
    detenuti fisicamente, misura la quota USA fisica e i primi paesi.
    L'esposizione USA/emergenti arriva via swap, quindi NON compare qui."""
    bpath = os.path.join(snapdir, "basket-hybrid.xlsx")
    fetch(DWS_BASKET.format(isin=SCWX), bpath, min_size=5000)
    recs = []
    for r in xlsx_rows(bpath):
        if len(r) == 11 and str(r[0]).isdigit() and r[6] == "Equities":
            try:
                recs.append({"country": r[3], "w": float(r[10])})
            except ValueError:
                pass
    tot = sum(x["w"] for x in recs)
    if not (0.90 < tot < 1.10):
        raise RuntimeError(f"somma pesi anomala: {tot:.4f}")
    if prev.get("basketCount") and len(recs) < 0.6 * prev["basketCount"]:
        raise RuntimeError(f"conteggio anomalo: {len(recs)} (prima {prev['basketCount']})")
    us = round(100 * sum(x["w"] for x in recs if x["country"] == "United States"), 1)
    if us > 10:
        # La prosa dice «quasi tutte fuori dagli USA»: se non è più vero, il
        # gestore ha cambiato dosaggio (il prospetto glielo consente) → serve
        # revisione redazionale, non un aggiornamento muto.
        raise RuntimeError(f"quota USA fisica {us}% — struttura cambiata, serve revisione redazionale")
    by_c = {}
    for x in recs:
        by_c[x["country"]] = by_c.get(x["country"], 0.0) + x["w"]
    top = sorted(by_c.items(), key=lambda kv: -kv[1])[:3]

    # ── scarto misurato: NAV SCWX + indice (endpoint DWS) vs fisico iShares ──
    raw = fetch(SCWX_PERFCHART, os.path.join(snapdir, "scwx-perfchart.json"), min_size=5000)
    perf = json.loads(raw)
    cfg = perf.get("seriesConfiguration", [])
    if len(cfg) < 2 or cfg[0].get("chartType") != "Nav" or cfg[1].get("chartType") != "Index":
        raise RuntimeError(f"performancechart: serie inattese {[c.get('chartType') for c in cfg]}")
    nav, idx = {}, {}
    for ts, vals in perf["values"]:
        day = datetime.datetime.fromtimestamp(ts / 1000, datetime.timezone.utc).date().isoformat()
        if len(vals) >= 1 and vals[0] and vals[0][0]:
            nav[day] = vals[0][0]
        if len(vals) >= 2 and vals[1] and vals[1][0]:
            idx[day] = vals[1][0]
    html = fetch(SSAC_URL, os.path.join(snapdir, "ssac-ch.html"), min_size=100_000).decode("utf-8", "replace")
    ssac = {str(k): v for k, v in ishares_series(html).items()}
    common = sorted(set(nav) & set(idx) & set(ssac))
    if len(common) < 300:
        raise RuntimeError(f"scarto: solo {len(common)} sedute comuni")
    if prev.get("tdPoints") and len(common) < prev["tdPoints"]:
        raise RuntimeError(f"scarto: la finestra si accorcia ({len(common)} < {prev['tdPoints']})")
    a, b = common[0], common[-1]
    years = (datetime.date.fromisoformat(b) - datetime.date.fromisoformat(a)).days / 365.25
    cum = lambda s: round((s[b] / s[a] - 1) * 100, 2)
    annf = lambda s: ((s[b] / s[a]) ** (1 / years) - 1) * 100
    gap_bp = round((annf(nav) - annf(ssac)) * 100)
    if abs(gap_bp) > 300:
        raise RuntimeError(f"scarto anomalo: {gap_bp} pb/anno — verifica le serie prima di pubblicare")
    td = {
        "from": a, "to": b, "points": len(common),
        "hybridCumPct": cum(nav), "physicalCumPct": cum(ssac), "indexCumPct": cum(idx),
        "hybridAnnPct": round(annf(nav), 2), "physicalAnnPct": round(annf(ssac), 2),
        "indexAnnPct": round(annf(idx), 2), "gapVsPhysicalBp": gap_bp,
    }
    log(f"[hybrid] ok — {len(recs)} titoli fisici, USA {us}%; scarto vs fisico {gap_bp:+d} pb/a su {len(common)} sedute")
    return {
        "basketCount": len(recs), "usPhysicalPct": us, "asof": TODAY.isoformat(),
        "top": [{"en": c, "it": COUNTRY_IT.get(c, c), "pct": round(100 * w, 1)} for c, w in top],
        "td": td,
    }


def render_hybrid_ts(h):
    top = "\n".join(
        f"    {{ it: '{r['it']}', en: '{r['en']}', pct: {r['pct']} }},"
        for r in h["top"])
    return f"""/**
 * La «terza via»: il fondo a replica dichiaratamente ibrida (articolo
 * «ETF a replica fisica o sintetica», sezione 10).
 *
 * FILE RIGENERATO AUTOMATICAMENTE da ~/backups/rebalix-replica-archivio/_archiver.py
 * (settimanale, lunedì). NON MODIFICARE A MANO.
 * Fonte: export ufficiale DWS (product/constituent per ISIN); prospetto e KID
 * correnti sono sempre depositati sulla scheda Borsa Italiana del fondo.
 */

export type ReplHybridCountry = {{ it: string; en: string; pct: number }}

/** Scarto misurato da Rebalix: NAV SCWX e indice (endpoint DWS) vs NAV del
 *  fisico iShares MSCI ACWI (serie incorporata nella pagina prodotto), USD. */
export type ReplHybridTd = {{
  from: string
  to: string
  points: number
  hybridCumPct: number
  physicalCumPct: number
  indexCumPct: number
  hybridAnnPct: number
  physicalAnnPct: number
  indexAnnPct: number
  gapVsPhysicalBp: number
  physical: {{ name: string; ticker: string; isin: string; terPct: number }}
}}

export type ReplHybridFund = {{
  fundName: string
  ticker: string
  isin: string
  indexName: string
  /** Anno di lancio del comparto (prospetto). */
  launchYear: number
  /** Data della nostra rilevazione del paniere (export ufficiale DWS). */
  basketAsOf: string
  /** Titoli detenuti fisicamente (solo azioni, esclusa la liquidità). */
  basketCount: number
  /** Peso % delle azioni USA detenute fisicamente (l'esposizione USA arriva via swap). */
  usPhysicalPct: number
  /** Primi paesi del paniere fisico, in % del patrimonio. */
  topCountries: ReplHybridCountry[]
  /** Link stabili ai documenti sempre aggiornati (scheda BI = ultimo prospetto/KID depositati). */
  links: {{ borsaItaliana: string; dws: string }}
  /** Scarto ibrido-vs-fisico misurato sui NAV ufficiali. */
  td: ReplHybridTd
}}

export const REPL_HYBRID: ReplHybridFund = {{
  fundName: 'Scalable MSCI AC World Xtrackers UCITS ETF 1C',
  ticker: 'SCWX',
  isin: '{SCWX}',
  indexName: 'MSCI ACWI',
  launchYear: 2024,
  basketAsOf: '{h["asof"]}',
  basketCount: {h["basketCount"]},
  usPhysicalPct: {h["usPhysicalPct"]},
  topCountries: [
{top}
  ],
  links: {{
    borsaItaliana: 'https://www.borsaitaliana.it/borsa/etf/scheda/{SCWX}.html',
    dws: 'https://etf.dws.com/en-lu/{SCWX}-scalable-msci-ac-world-xtrackers-ucits-etf-1c/',
  }},
  td: {{
    from: '{h["td"]["from"]}',
    to: '{h["td"]["to"]}',
    points: {h["td"]["points"]},
    hybridCumPct: {h["td"]["hybridCumPct"]},
    physicalCumPct: {h["td"]["physicalCumPct"]},
    indexCumPct: {h["td"]["indexCumPct"]},
    hybridAnnPct: {h["td"]["hybridAnnPct"]},
    physicalAnnPct: {h["td"]["physicalAnnPct"]},
    indexAnnPct: {h["td"]["indexAnnPct"]},
    gapVsPhysicalBp: {h["td"]["gapVsPhysicalBp"]},
    physical: {{ name: 'iShares MSCI ACWI UCITS ETF (Acc)', ticker: 'SSAC', isin: 'IE00B6R52259', terPct: 0.2 }},
  }},
}}

/** Data di generazione di questo modulo (rilevazione del paniere). */
export const REPL_HYBRID_UPDATED = '{h["asof"]}'
"""


# ── 2) Scarto I500 vs CSPX ───────────────────────────────────────────────────

def ishares_series(html_text):
    pts = re.findall(r"Date\.UTC\((\d+),(\d+),(\d+)\),y:Number\(\(([\d.]+)\)", html_text)
    out = {}
    for y, m, d, v in pts:
        out[datetime.date(int(y), int(m) + 1, int(d))] = float(v)
    return out


def src_td(snapdir, prev):
    h_syn = fetch(ISHARES_I500, os.path.join(snapdir, "i500.html"), min_size=100_000).decode("utf-8", "ignore")
    h_phy = fetch(ISHARES_CSPX, os.path.join(snapdir, "cspx.html"), min_size=100_000).decode("utf-8", "ignore")
    syn, phy = ishares_series(h_syn), ishares_series(h_phy)
    common = sorted(set(syn) & set(phy))
    if len(common) < 1400 or (prev and len(common) < prev.get("commonPoints", 0) - 30):
        raise RuntimeError(f"serie sospette: {len(common)} punti comuni (prima {prev.get('commonPoints')})")
    end = common[-1]
    if (TODAY - end).days > 15:
        raise RuntimeError(f"serie ferma al {end} — fonte non aggiornata")

    def ann(s, a, b):
        yrs = (b - a).days / 365.25
        return (s[b] / s[a]) ** (1 / yrs) - 1

    def nearest(t):
        return min(common, key=lambda d: abs((d - t).days))

    windows = []
    for years in (1, 3, 5):
        start = nearest(datetime.date(end.year - years, end.month, end.day))
        s, p = ann(syn, start, end), ann(phy, start, end)
        windows.append({"years": years, "start": start.isoformat(),
                        "synPct": round(100 * s, 2), "phyPct": round(100 * p, 2),
                        "gapBp": round(10000 * (s - p))})
    start = common[0]
    s, p = ann(syn, start, end), ann(phy, start, end)
    windows.append({"years": None, "start": start.isoformat(),
                    "synPct": round(100 * s, 2), "phyPct": round(100 * p, 2),
                    "gapBp": round(10000 * (s - p))})
    for w in windows:
        if abs(w["gapBp"]) > 100:
            raise RuntimeError(f"scarto anomalo {w['gapBp']} pb sulla finestra {w['years']}")
    log(f"[td] ok — {len(common)} punti comuni, fine {end}, scarti " +
        ", ".join(f"{w['gapBp']:+d}pb" for w in windows))
    return {"endDate": end.isoformat(), "commonPoints": len(common), "windows": windows}


def render_td_ts(d):
    rows = "\n".join(
        f"    {{ years: {w['years'] if w['years'] is not None else 'null'}, start: '{w['start']}', "
        f"synPct: {w['synPct']}, phyPct: {w['phyPct']}, gapBp: {w['gapBp']} }},"
        for w in d["windows"])
    return f"""/**
 * Scarto di rendimento misurato tra S&P 500 sintetico e fisico — I500 (swap)
 * vs CSPX (fisico), stesso emittente iShares, serie di performance ufficiali
 * (pagine prodotto CH, valuta base USD).
 *
 * FILE RIGENERATO AUTOMATICAMENTE da ~/backups/rebalix-replica-archivio/_archiver.py
 * (settimanale, lunedì). NON MODIFICARE A MANO.
 */

export type ReplTdWindow = {{
  years: number | null
  start: string
  synPct: number
  phyPct: number
  gapBp: number
}}

export const REPL_TD = {{
  updated: '{TODAY.isoformat()}',
  endDate: '{d["endDate"]}',
  currency: 'USD',
  commonPoints: {d["commonPoints"]},
  physical: {{ name: 'iShares Core S&P 500 UCITS ETF', ticker: 'CSPX', isin: 'IE00B5BMR087', terPct: 0.07 }},
  synthetic: {{ name: 'iShares S&P 500 Swap UCITS ETF', ticker: 'I500', isin: 'IE00BMTX1Y45', terPct: 0.05 }},
  windows: [
{rows}
  ] satisfies ReplTdWindow[],
}} as const
"""


# ── 3) Quota white-list XEON ─────────────────────────────────────────────────

def excel_serial_to_date(n):
    return datetime.date(1899, 12, 30) + datetime.timedelta(days=int(n))


def src_xeon(snapdir, prev_series):
    page = fetch(DWS_FISC, min_size=50_000).decode("utf-8", "ignore")
    uids = list(dict.fromkeys(re.findall(r"download/asset/([0-9a-f-]{36})", page)))
    if len(uids) < len(prev_series) - 2:
        raise RuntimeError(f"pagina fiscalità sospetta: {len(uids)} documenti")
    series = {}
    for uid in uids:
        dest = os.path.join(snapdir, f"fisc-{uid[:8]}.xlsx")
        try:
            fetch(DWS_ASSET.format(uid=uid), dest, min_size=5000)
            for r in xlsx_rows(dest):
                if len(r) >= 9 and r[0] == XEON_ISIN:
                    frm = excel_serial_to_date(float(r[4])).isoformat()
                    to = excel_serial_to_date(float(r[5])).isoformat()
                    series[frm] = {"from": frm, "to": to, "pct": round(float(r[2]), 2)}
        except Exception as e:
            log(f"!! [xeon] documento {uid[:8]}: {e} — salto")
    if len(series) < max(3, len(prev_series) - 2):
        raise RuntimeError(f"serie XEON troppo corta: {len(series)} semestri")
    # la storia non si accorcia mai: unione con la serie già pubblicata
    # (un documento vecchio sparito dalla pagina NON deve cancellare la riga)
    merged = {r["from"]: dict(r) for r in prev_series}
    merged.update(series)
    rows = [merged[k] for k in sorted(merged)]
    for r in rows:
        if not (30 <= r["pct"] <= 100):
            raise RuntimeError(f"percentuale XEON fuori range: {r}")
    log(f"[xeon] ok — {len(rows)} semestri, ultimo {rows[-1]['from']} → {rows[-1]['pct']}%")
    return rows


def render_xeon_ts(rows):
    body = "\n".join(f"  {{ from: '{r['from']}', to: '{r['to']}', pct: {r['pct']} }}," for r in rows)
    return f"""/**
 * Quota «titoli pubblici» (white list, 12,5%) certificata da DWS per XEON —
 * Xtrackers II EUR Overnight Rate Swap UCITS ETF (LU0290358497).
 *
 * FILE RIGENERATO AUTOMATICAMENTE da ~/backups/rebalix-replica-archivio/_archiver.py
 * (settimanale; la fonte cambia ogni semestre). NON MODIFICARE A MANO.
 * Fonte: documenti semestrali «Fiscalità degli ETF» di DWS (mercato italiano).
 */

export type XeonWhitelistRow = {{
  from: string
  to: string
  pct: number
}}

export const XEON_WHITELIST_SERIES: XeonWhitelistRow[] = [
{body}
]

export const XEON_WHITELIST = {{
  isin: 'LU0290358497',
  fundName: 'Xtrackers II EUR Overnight Rate Swap UCITS ETF 1C',
  ticker: 'XEON',
  updated: '{TODAY.isoformat()}',
  current: XEON_WHITELIST_SERIES[XEON_WHITELIST_SERIES.length - 1],
}} as const
"""


# ── battito + deploy (pattern broker-zero) ───────────────────────────────────

def send_heartbeat(errori, modules, data_date):
    if DRY:
        log(f"[heartbeat] (dry) errori={errori} moduli={modules}")
        return
    try:
        secret = None
        with open(os.path.join(REPO, ".env.local")) as f:
            for line in f:
                if line.startswith("CRON_SECRET="):
                    secret = line.split("=", 1)[1].strip().strip('"').strip("'")
                    break
        if not secret:
            log("!! [heartbeat] CRON_SECRET non trovato — salto")
            return
        payload = json.dumps({"name": "replica-articolo", "ok": errori == 0, "errors_count": errori,
                              "metrics": {"host": os.uname().nodename, "modules": modules, "data_date": data_date}}).encode()
        req = urllib.request.Request("https://rebalix.com/api/heartbeat", data=payload, method="POST",
                                     headers={"Authorization": f"Bearer {secret}",
                                              "Content-Type": "application/json"})
        urllib.request.urlopen(req, timeout=30).read()
        log(f"[heartbeat] inviato (errori={errori})")
    except Exception as e:
        log(f"!! [heartbeat] {e}")


def tsc_ok():
    r = subprocess.run([NPX, "tsc", "--noEmit"], cwd=REPO, capture_output=True, text=True, timeout=600)
    if r.returncode != 0:
        log("!! tsc fallito sui moduli rigenerati:\n" + (r.stdout or r.stderr)[:800])
        return False
    return True


def autodeploy(files):
    if DRY or NO_DEPLOY:
        log("[deploy] saltato (dry/no-deploy)")
        return True
    branch = subprocess.run([GIT, "-C", REPO, "rev-parse", "--abbrev-ref", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    if branch != "main":
        log(f"[deploy] branch {branch} ≠ main — moduli scritti, commit+deploy al prossimo giro su main")
        return True
    try:
        subprocess.run([GIT, "-C", REPO, "add", "--"] + files, check=True)
        if subprocess.run([GIT, "-C", REPO, "diff", "--cached", "--quiet", "--"] + files).returncode == 0:
            log("[deploy] moduli invariati — nessun deploy")
            return True
        msg = ("data(blog-replica): refresh automatico panieri, active share, scarto TD e ibrido\n\n"
               "Rigenerati dall'archiviatore settimanale dell'articolo replica\n"
               "fisica/sintetica (DWS constituent + serie performance iShares\n"
               "+ paniere fisico SCWX).\n\n"
               "Co-Authored-By: Claude Fable 5 <noreply@anthropic.com>")
        subprocess.run([GIT, "-C", REPO, "commit", "-m", msg, "--"] + files, check=True)
        # ANTI-RETROCESSIONE (lezione 13 ago 2026): con più macchine che pushano, deployare
        # una base non allineata a origin/main retrocede in prod il lavoro delle altre.
        # Rebase + push obbligatori: se una delle due fallisce, deploy ANNULLATO (False → guardiano).
        if subprocess.run([GIT, "-C", REPO, "fetch", "origin", "main"]).returncode != 0:
            log("!! [deploy] fetch origin fallito — deploy ANNULLATO (base non verificabile)"); return False
        if subprocess.run([GIT, "-C", REPO, "rebase", "-X", "theirs", "origin/main"]).returncode != 0:
            subprocess.run([GIT, "-C", REPO, "rebase", "--abort"])
            log("!! [deploy] rebase su origin/main fallito — deploy ANNULLATO (risolvere a mano)"); return False
        if subprocess.run([GIT, "-C", REPO, "push", "origin", "main"]).returncode != 0:
            log("!! [deploy] push fallito DOPO il rebase — deploy ANNULLATO (mai deployare una base non pushata)"); return False
        head = subprocess.run([GIT, "-C", REPO, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()
        wt = tempfile.mkdtemp(prefix="rebalix-deploy-")
        try:
            subprocess.run([GIT, "-C", REPO, "worktree", "add", "--detach", wt, head], check=True)
            vsrc = os.path.join(REPO, ".vercel")
            if os.path.isdir(vsrc):
                shutil.copytree(vsrc, os.path.join(wt, ".vercel"))
            vercel = shutil.which("vercel") or "/usr/local/bin/vercel"
            for attempt in range(1, 4):
                r = subprocess.run([vercel, "--prod", "--yes"], cwd=wt, capture_output=True, text=True, timeout=900)
                if r.returncode == 0:
                    log("[deploy] produzione aggiornata")
                    return True
                log(f"!! [deploy] tentativo {attempt} fallito: {(r.stderr or r.stdout)[:300]}")
        finally:
            subprocess.run([GIT, "-C", REPO, "worktree", "remove", "--force", wt], capture_output=True)
        return False
    except Exception as e:
        log(f"!! [deploy] {e}")
        return False


# ── main ─────────────────────────────────────────────────────────────────────

def read_prev():
    """Numeri chiave dei moduli attuali (per le soglie di sanità)."""
    prev = {"xspu": {}, "world": {}, "td": {}, "xeon": [], "hybrid": {}}
    try:
        t = open(os.path.join(REPO, BASKETS_REL)).read()
        for key, var in [("xspu", "REPL_XSPU"), ("world", "REPL_XWORLD")]:
            m = re.search(var + r"[^=]*=\s*\{(.*?)\n\}", t, re.S)
            if m:
                seg = m.group(1)
                prev[key] = {k: int(v) for k, v in re.findall(r"(basketCount|indexCount):\s*(\d+)", seg)}
    except OSError:
        pass
    try:
        t = open(os.path.join(REPO, TD_REL)).read()
        m = re.search(r"commonPoints:\s*(\d+)", t)
        if m:
            prev["td"] = {"commonPoints": int(m.group(1))}
    except OSError:
        pass
    try:
        t = open(os.path.join(REPO, XEON_REL)).read()
        prev["xeon"] = [
            {"from": f, "to": to, "pct": float(pc)}
            for f, to, pc in re.findall(r"from: '(\d{4}-\d{2}-\d{2})', to: '(\d{4}-\d{2}-\d{2})', pct: ([\d.]+)", t)
        ]
    except OSError:
        pass
    try:
        t = open(os.path.join(REPO, HYBRID_REL)).read()
        m = re.search(r"basketCount:\s*(\d+)", t)
        if m:
            prev["hybrid"] = {"basketCount": int(m.group(1))}
        m = re.search(r"points:\s*(\d+)", t)
        if m:
            prev["hybrid"]["tdPoints"] = int(m.group(1))
    except OSError:
        pass
    return prev


def main():
    state_path = os.path.join(ARCHIVE, "_state.json")
    state = json.load(open(state_path)) if os.path.exists(state_path) else {}
    if not FORCE and state.get("last_ok_week") == YW:
        log(f"giro {YW} già completato — niente da fare (usa --force per rifare)")
        return
    os.makedirs(SNAPDIR, exist_ok=True)
    log(f"=== giro {YW} avviato (dry={DRY}) ===")
    prev = read_prev()
    modules, errori, files = {}, 0, []

    try:
        b = src_baskets(SNAPDIR, prev)
        modules["baskets-xspu"] = modules["baskets-world"] = True
        if not DRY:
            open(os.path.join(REPO, BASKETS_REL), "w").write(render_baskets_ts(b["xspu"], b["world"]))
            files.append(BASKETS_REL)
    except Exception as e:
        log(f"!! [baskets] {e} — TENGO il modulo precedente")
        modules["baskets-xspu"] = modules["baskets-world"] = False
        errori += 1

    try:
        d = src_td(SNAPDIR, prev.get("td", {}))
        modules["td"] = True
        if not DRY:
            open(os.path.join(REPO, TD_REL), "w").write(render_td_ts(d))
            files.append(TD_REL)
    except Exception as e:
        log(f"!! [td] {e} — TENGO il modulo precedente")
        modules["td"] = False
        errori += 1

    try:
        rows = src_xeon(SNAPDIR, prev.get("xeon", []))
        modules["xeon-whitelist"] = True
        if not DRY and rows != prev.get("xeon", []):
            open(os.path.join(REPO, XEON_REL), "w").write(render_xeon_ts(rows))
            files.append(XEON_REL)
    except Exception as e:
        log(f"!! [xeon] {e} — TENGO il modulo precedente")
        modules["xeon-whitelist"] = False
        errori += 1

    try:
        h = src_hybrid(SNAPDIR, prev.get("hybrid", {}))
        modules["hybrid"] = True
        if not DRY:
            open(os.path.join(REPO, HYBRID_REL), "w").write(render_hybrid_ts(h))
            files.append(HYBRID_REL)
    except Exception as e:
        log(f"!! [hybrid] {e} — TENGO il modulo precedente")
        modules["hybrid"] = False
        errori += 1

    deploy_ok = True
    if files:
        if tsc_ok():
            deploy_ok = autodeploy(files)
        else:
            subprocess.run([GIT, "-C", REPO, "checkout", "--"] + files)
            log("!! moduli rigenerati NON compilano — revert eseguito")
            deploy_ok = False
            errori += 1
    modules["deploy"] = deploy_ok
    if not deploy_ok:
        errori += 1

    if not DRY and errori == 0:
        state["last_ok_week"] = YW
        state["last_ok"] = TODAY.isoformat()
        json.dump(state, open(state_path, "w"))
    send_heartbeat(errori, modules, TODAY.isoformat())
    log(f"=== giro completato ({errori} errori) ===")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        log(f"!!! ERRORE FATALE: {e}")
        send_heartbeat(99, {"fatal": True}, None)
        raise
