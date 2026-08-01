#!/usr/bin/env python3
"""Estrae per posizione la torta 'Esposizione geografica' di ogni fondo/trimestre.
- Rilevamento pagina-dettaglio: un solo fondo nell'intestazione.
- USA = unico valore in [40,68] sulla pagina (blindato).
- Vettore-paesi completo: clustering per distanza dal centro delle due torte, con
  validazione somma~100 e confronto con i valori letti a vista.
"""
import os, re, glob, json, math
import pdfplumber

ARCHIVE = os.path.expanduser("~/Desktop/rebalix-lifestrategy-archivio")
NUM = re.compile(r"^-?\d{1,2},\d$")
FUND_HEADER = re.compile(r"Vanguard LifeStrategy (\d{2})% Equity UCITS ETF")

def num(s): return float(s.replace(",", "."))

def detail_fund(text):
    """Ritorna l'equity ('60') se la pagina è il dettaglio di UN solo fondo, altrimenti None."""
    found = set(FUND_HEADER.findall(text))
    return found.pop() if len(found) == 1 else None

def analyze(pg):
    words = pg.extract_words()
    hdr = {w["text"]: (w["x0"], w["top"]) for w in words if w["text"] in ("geografica","settoriale")}
    if "geografica" not in hdr or "settoriale" not in hdr:
        return None
    gx = hdr["geografica"][0]; sx = hdr["settoriale"][0]
    gtop = hdr["geografica"][1]
    # banda verticale delle torte: sotto le intestazioni, sopra le legende
    leg_top = min([w["top"] for w in words if w["text"] in ("Stati","Tecnologia")] or [gtop+210])
    nums = [(w["x0"], w["top"], num(w["text"])) for w in words
            if NUM.match(w["text"]) and w["x0"] > gx-30 and gtop+6 < w["top"] < leg_top-4]
    # USA blindato = unico valore in [40,68]
    us_candidates = [v for (_,_,v) in nums if 40 <= v <= 68]
    us = max(us_candidates) if us_candidates else None
    # centri stimati delle due torte
    gc = gx + 62; scn = sx + 62
    geo, sec = [], []
    for (x, t, v) in nums:
        (geo if abs(x-gc) <= abs(x-scn) else sec).append(v)
    geo.sort(reverse=True); sec.sort(reverse=True)
    return {"us": us, "geo": geo, "geo_sum": round(sum(geo),1),
            "sec_sum": round(sum(sec),1), "n_us_cand": len(us_candidates)}

def main():
    manual_us = {("2024-09-30","60"):57.5, ("2025-06-30","60"):57.5}
    known = {("2022-12-31","60"):55.1, ("2026-03-31","60"):57.7}
    pdfs = sorted(glob.glob(os.path.join(ARCHIVE, "*", "*.pdf")))
    print(f"{'file':<22}{'US%':>7}{'#US':>5}{'geoΣ':>7}{'secΣ':>7}   geo (LS60)")
    for path in pdfs:
        with pdfplumber.open(path) as pdf:
            for pg in pdf.pages:
                t = pg.extract_text() or ""
                eq = detail_fund(t)
                if eq != "60":
                    continue
                r = analyze(pg)
                fn = os.path.relpath(path, ARCHIVE)
                if not r:
                    print(f"{fn:<22}  (immagine, no text)")
                    continue
                flag = ""
                if r["n_us_cand"] != 1: flag += " ⚠US-ambiguo"
                if not (95 <= r["geo_sum"] <= 105): flag += f" ⚠geoΣ={r['geo_sum']}"
                print(f"{fn:<22}{str(r['us']):>7}{r['n_us_cand']:>5}{r['geo_sum']:>7}{r['sec_sum']:>7}   {r['geo']}{flag}")

if __name__ == "__main__":
    main()
