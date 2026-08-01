#!/usr/bin/env python3
"""Rigenera `lib/blog/c3m-aum.ts`: patrimonio (AUM) mensile di C3M dal 2017 e
RACCOLTA NETTA per anno — entrambi dalle serie ufficiali Amundi (idea Linus 29/7,
ispirata dagli aggregatori ma fatta meglio: fonte emittente, non vendor).

La raccolta netta separa i flussi veri dall'effetto mercato: quote in circolazione
= AUM/NAV (giorno per giorno), flusso del giorno = Δquote × NAV del giorno.
Un AUM che sale può essere mercato (NAV su) o raccolta (quote su): qui si vede quale.

Golden (fail-loud, altrimenti NON scrive): AUM in [50, 5000] mln; ultimo dato ≤7gg;
ultimo AUM entro il 3% di quello del modulo composizione (stessa fonte, altra via);
|raccolta 12 mesi| < AUM corrente (sanità). updated = ultima data AUM (data-derivata).
"""
import json, os, sys, datetime

ARCHIVE = os.path.expanduser("~/backups/rebalix-c3m-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "c3m-aum.ts")
FRESCHEZZA_GIORNI = 7


def serie(nome):
    punti = json.load(open(os.path.join(ARCHIVE, "nav", nome)))
    out = {}
    for p in punti:
        d = datetime.datetime.utcfromtimestamp(p["date"] / 1000).date()
        if p.get("data") is not None:
            out[d] = float(p["data"])
    return out


def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print("[c3m-aum] repo non trovato — salto."); return
    aum, nav = serie("shareAumInMCcy.json"), serie("officialNav.json")
    if len(aum) < 500:
        sys.exit(f"[c3m-aum] solo {len(aum)} punti AUM: archivio rotto? NON scrivo")
    ultimo = max(aum)
    if (datetime.date.today() - ultimo).days > FRESCHEZZA_GIORNI:
        sys.exit(f"[c3m-aum] AUM fermo a {ultimo}: fonte ferma — NON scrivo")
    for d, v in aum.items():
        if not (50e6 <= v <= 5000e6):
            sys.exit(f"[c3m-aum] AUM fuori range il {d}: {v:.0f} — NON scrivo")

    # controprova: ultimo AUM vs modulo composizione (stessa fonte, altra chiamata)
    comp = open(os.path.join(REPO, "lib", "blog", "c3m-composition.ts")).read()
    import re
    m = re.search(r"aumMln: ([0-9.]+)", comp)
    if m:
        scarto = abs(aum[ultimo] / 1e6 - float(m.group(1))) / float(m.group(1))
        if scarto > 0.03:
            sys.exit(f"[c3m-aum] GOLDEN FALLITO: AUM serie {aum[ultimo]/1e6:.0f}M vs snapshot {m.group(1)}M — NON scrivo")

    # mensile per il grafico (ultimo valore del mese, in milioni)
    per_mese = {}
    for d in sorted(aum):
        per_mese[d.isoformat()[:7]] = round(aum[d] / 1e6, 1)
    mesi = sorted(per_mese)

    # raccolta netta: quote = AUM/NAV sui giorni comuni; flusso = Δquote × NAV
    comuni = sorted(set(aum) & set(nav))
    per_anno = {}
    prev_q = None
    for d in comuni:
        q = aum[d] / nav[d]
        if prev_q is not None:
            per_anno[d.year] = per_anno.get(d.year, 0.0) + (q - prev_q) * nav[d]
        prev_q = q
    flussi_anno = {str(a): round(v / 1e6, 1) for a, v in sorted(per_anno.items())}

    # ultimi 12 mesi (sanità + numero citabile)
    un_anno_fa = ultimo - datetime.timedelta(days=365)
    f12 = 0.0
    prev_q = None
    for d in comuni:
        if d < un_anno_fa:
            prev_q = aum[d] / nav[d]
            continue
        q = aum[d] / nav[d]
        if prev_q is not None:
            f12 += (q - prev_q) * nav[d]
        prev_q = q
    f12_mln = round(f12 / 1e6, 1)
    if abs(f12_mln) > aum[ultimo] / 1e6:
        sys.exit(f"[c3m-aum] GOLDEN FALLITO: raccolta 12m {f12_mln}M > AUM — NON scrivo")

    anno_corrente = str(datetime.date.today().year)
    ts = f"""/**
 * Patrimonio (AUM) mensile di C3M dal 2017 e raccolta netta per anno, dalle serie
 * UFFICIALI Amundi (shareAumInMCcy + officialNav). Raccolta = Δquote × NAV: separa
 * i flussi veri dall'effetto mercato — un AUM che sale può essere l'uno o l'altro,
 * qui si vede quale. L'anno in corso ({anno_corrente}) è parziale.
 * Golden: range, freschezza, controprova vs snapshot composizione, sanità 12 mesi.
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_c3m_aum.py`
 * (archivio C3M). Non modificare a mano.
 */
export const C3M_AUM: {{
  updated: string
  months: string[]
  aumMln: number[]
  flowsByYear: Record<string, number> // raccolta netta, milioni €
  flows12mMln: number
  partialYear: string
}} = {{
  updated: '{ultimo.isoformat()}',
  months: {json.dumps(mesi)},
  aumMln: {json.dumps([per_mese[m] for m in mesi])},
  flowsByYear: {json.dumps(flussi_anno)},
  flows12mMln: {f12_mln},
  partialYear: '{anno_corrente}',
}}
"""
    with open(DEST, "w") as f:
        f.write(ts)
    print(f"[c3m-aum] scritto: {len(mesi)} mesi {mesi[0]}→{mesi[-1]}, AUM {per_mese[mesi[-1]]:.0f}M, "
          f"raccolta 12m {f12_mln:+.0f}M, anni flussi: {list(flussi_anno)[:1]}…{list(flussi_anno)[-1:]}")


if __name__ == "__main__":
    main()
