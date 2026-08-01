#!/usr/bin/env python3
"""Estrae la serie storica dei report trimestrali Vanguard LifeStrategy dai PDF.
Output: un JSON con, per ogni trimestre e per ogni fondo (LS20/40/60/80),
strato-1 (ETF sottostanti + pesi), metriche chiave, credito, geografia, settori, performance.
"""
import os, re, json, glob, sys

import pdfplumber

ARCHIVE = os.path.expanduser("~/backups/rebalix-lifestrategy-archivio")

MONTHS = {
    "gennaio": "01", "febbraio": "02", "marzo": "03", "aprile": "04",
    "maggio": "05", "giugno": "06", "luglio": "07", "agosto": "08",
    "settembre": "09", "ottobre": "10", "novembre": "11", "dicembre": "12",
}

def quarter_date(year, month_num):
    # data di riferimento = ultimo giorno del mese del report
    last = {"03": "31", "06": "30", "09": "30", "12": "31"}[month_num]
    return f"{year}-{month_num}-{last}"

def num(s):
    """'19,4' -> 19.4 ; '-15,69' -> -15.69 ; '--' -> None"""
    s = s.strip()
    if s in ("--", "-", "", "—"):
        return None
    return float(s.replace(".", "").replace(",", ".")) if s.count(",") else float(s.replace(",", "."))

FUND_HEADER = re.compile(r"Vanguard LifeStrategy (\d{2})% Equity UCITS ETF")
HOLDING = re.compile(r"(Vanguard .+?UCITS ETF(?: EUR Hedged)?)\s+(\d{1,2},\d)\s*$")
ISIN = re.compile(r"\b(IE[0-9A-Z]{10})\b")

def parse_fund_page(text):
    d = {}
    m = ISIN.search(text)
    if m: d["isin"] = m.group(1)
    # metriche chiave
    for key, pat in [
        ("aum_eur_m", r"AUM \(EUR M\)\s+([\d\.,]+)"),
        ("ter", r"OCF/TER \(%\)\s+([\d,]+)"),
        ("durata_modificata", r"Durata modificata \(anni\)\s+([\d,]+)"),
        ("rendimento_scadenza", r"Rendimento a scadenza \(%\)\s+([\d,]+)"),
        ("pe", r"Rapporto P/E \(x\)\s+([\d,]+)"),
        ("dividend_yield", r"Rendimento da dividendi \(%\)\s+([\d,]+)"),
        ("perf_ytd", r"Performance da inizio anno\s+(-?[\d,]+)"),
    ]:
        mm = re.search(pat, text)
        if mm:
            d[key] = num(mm.group(1))
    # strato-1: ETF sottostanti
    holdings = []
    for line in text.splitlines():
        hm = HOLDING.search(line.strip())
        if hm:
            holdings.append({"etf": hm.group(1).strip(), "peso": num(hm.group(2))})
    d["holdings"] = holdings
    # credito
    credit = {}
    for label, key in [("AAA","AAA"),("AA","AA"),("A","A"),("BBB","BBB"),
                       ("NR","NR"),("Senza rating","NR")]:
        cm = re.search(rf"^{re.escape(label)}\s+([\d,]+)\s*$", text, re.MULTILINE)
        if cm: credit[key] = num(cm.group(1))
    d["credito"] = credit
    return d

def parse_pdf(path, year):
    fname = os.path.basename(path)
    base = re.sub(r"\.pdf$", "", fname, flags=re.I)
    base = re.sub(r"_\d{4}$", "", base).strip().lower()
    month_num = MONTHS.get(base)
    if not month_num:
        print(f"  ! mese non riconosciuto: {fname}", file=sys.stderr)
        return None
    ref = quarter_date(year, month_num)
    result = {"data_riferimento": ref, "file": os.path.relpath(path, ARCHIVE), "fondi": {}}
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            text = page.extract_text() or ""
            hm = FUND_HEADER.search(text)
            if not hm:
                continue
            equity = hm.group(1)  # '20','40','60','80'
            result["fondi"][equity] = parse_fund_page(text)
    return result

def main():
    out = []
    pdfs = sorted(glob.glob(os.path.join(ARCHIVE, "*", "*.pdf")))
    for path in pdfs:
        year = os.path.basename(os.path.dirname(path))
        rec = parse_pdf(path, year)
        if rec:
            out.append(rec)
            nfondi = len(rec["fondi"])
            nh = {k: len(v.get("holdings", [])) for k, v in rec["fondi"].items()}
            print(f"{rec['data_riferimento']}  fondi={nfondi}  holdings={nh}")
    out.sort(key=lambda r: r["data_riferimento"])
    dest = os.path.join(os.path.dirname(__file__), "ls_timeseries.json")
    with open(dest, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n-> {len(out)} trimestri scritti in {dest}")

if __name__ == "__main__":
    main()
