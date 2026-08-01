#!/usr/bin/env python3
"""Rigenera `lib/blog/c3m-composition.ts`: fotografia del paniere C3M dall'ULTIMO
snapshot archiviato (Top 10 titoli fondo/indice, paesi, rating, scadenze + NAV/AUM/TER).

⚠️ Amundi NON pubblica il paniere completo (54 titoli): espone Top 10 + spaccati
aggregati — l'articolo lo dichiara. I pesi usano `adjustedWeight` (per i Top 10 il
campo `weight` arriva a 0 dall'API; per gli spaccati i due campi coincidono).

Golden (fail-loud, altrimenti NON scrive): dato ≤ 10 giorni; Top 10 fondo = 10 voci;
somma pesi paesi in [98, 102]%; NAV > 0; il primo paese non sfora il tetto del 34,5%
dell'indice di più di 1,5 punti (capping delle ground rules FTSE: se lo sfora davvero,
qualcosa è rotto nei dati — o nel fondo, e allora è una NOTIZIA, non un dato da
pubblicare in automatico).
"""
import json, os, sys, datetime

ARCHIVE = os.path.expanduser("~/backups/rebalix-c3m-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "c3m-composition.ts")

FRESCHEZZA_GIORNI = 10
TETTO_CAPPING = 34.5  # % — ground rules FTSE (issuer cap della variante Capped)


def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print("[c3m-composition] repo non trovato — salto."); return
    raws = sorted(os.listdir(os.path.join(ARCHIVE, "raw")))
    if not raws:
        sys.exit("[c3m-composition] nessun raw in archivio — NON scrivo")
    asof = raws[-1].replace(".json", "")
    eta = (datetime.date.today() - datetime.date.fromisoformat(asof)).days
    if eta > FRESCHEZZA_GIORNI:
        sys.exit(f"[c3m-composition] ultimo snapshot {asof} ({eta}gg): fonte ferma — NON scrivo")
    p = json.load(open(os.path.join(ARCHIVE, "raw", raws[-1])))
    car = p.get("characteristics") or {}
    bds = {b["aggregationField"]: b.get("breakDownData") or [] for b in p.get("breakDowns") or []}
    # paniere COMPLETO (dal 29/7, scovato da Linus): conteggio + golden sulla somma pesi
    comp_rows = (p.get("composition") or {}).get("compositionData") or []
    full_count = (p.get("composition") or {}).get("totalNumberOfInstruments") or 0
    if comp_rows:
        somma_full = sum(r["compositionCharacteristics"]["weight"] for r in comp_rows)
        if not (0.99 <= somma_full <= 1.01):
            sys.exit(f"[c3m-composition] GOLDEN FALLITO: somma pesi paniere completo {somma_full:.4f} — NON scrivo")
        if len(comp_rows) != full_count:
            sys.exit(f"[c3m-composition] GOLDEN FALLITO: {len(comp_rows)} righe vs {full_count} dichiarati — NON scrivo")

    def voci(campo, limite=None):
        out = [{"name": v["aggregationName"], "pct": round(float(v.get("adjustedWeight") or 0) * 100, 2)}
               for v in bds.get(campo, [])]
        out.sort(key=lambda x: -x["pct"])
        return out[:limite] if limite else out

    top10 = voci("FUND_TOP10", 10)
    paesi = voci("FUND_COUNTRIES")
    rating = voci("FUND_RATINGS")
    scadenze = voci("FUND_MATURITIES")
    top10_idx = voci("INDEX_TOP10", 10)

    if len(top10) != 10:
        sys.exit(f"[c3m-composition] GOLDEN FALLITO: Top10 fondo con {len(top10)} voci — NON scrivo")
    somma_paesi = sum(v["pct"] for v in paesi)
    if not (98 <= somma_paesi <= 102):
        sys.exit(f"[c3m-composition] GOLDEN FALLITO: somma paesi {somma_paesi:.1f}% — NON scrivo")
    nav = car.get("NAV")
    if not nav or nav <= 0:
        sys.exit("[c3m-composition] GOLDEN FALLITO: NAV assente — NON scrivo")
    if paesi and paesi[0]["pct"] > TETTO_CAPPING + 1.5:
        sys.exit(f"[c3m-composition] GOLDEN FALLITO: {paesi[0]['name']} al {paesi[0]['pct']}% "
                 f"sfora il tetto {TETTO_CAPPING}% — dati rotti o notizia: occhio umano, NON scrivo")

    # primi 10 dal paniere INTEGRALE (con ISIN: alimenta la tabella «paper» stile
    # articolo replica — appunto Linus 29/7); nomi bill = "EMITTENTE % ggMmmAA"
    top10_full = []
    if comp_rows:
        ordinati = sorted(comp_rows, key=lambda r: -(r["compositionCharacteristics"].get("weight") or 0))
        for r in ordinati[:10]:
            c = r["compositionCharacteristics"]
            top10_full.append({"name": (c.get("name") or "").strip(), "isin": c.get("isin") or "",
                               "country": c.get("countryOfRisk") or c.get("country") or "",
                               "pct": round((c.get("weight") or 0) * 100, 2)})
        if len(top10_full) < 10 or any(not v["isin"] for v in top10_full):
            sys.exit("[c3m-composition] GOLDEN FALLITO: top10 dal paniere integrale incompleto — NON scrivo")

    # autorizzazione alla vendita (passporting) — appunto di Linus 29/7: va distinta
    # dalle PIAZZE di quotazione (3 borse), che si derivano dai ticker Bloomberg unici
    IT_NAMES = {"Switzerland": "Svizzera", "Germany": "Germania", "Finland": "Finlandia",
                "France": "Francia", "United Kingdom": "Regno Unito", "Italy": "Italia",
                "Netherlands": "Paesi Bassi"}
    passported = []
    for c in car.get("PASSPORTED_COUNTRIES") or []:
        en = c.get("passportingCountryName") or ""
        passported.append({"en": en, "it": IT_NAMES.get(en, en),
                           "retail": (c.get("distributionProfil") or "") != "Institutionnal Only"})
    passported.sort(key=lambda x: x["en"])
    if len(passported) < 5:
        sys.exit(f"[c3m-composition] GOLDEN FALLITO: {len(passported)} paesi autorizzati (<5) — NON scrivo")
    EXCHANGES = {"GY": "Xetra (Francoforte)", "FP": "Euronext Paris", "IM": "Borsa Italiana"}
    tickers = sorted({v for v in (car.get("MAIN_LISTINGS") or {}).values()})
    listings = [{"exchange": EXCHANGES[t.split()[-1]], "ticker": t.split()[0]}
                for t in tickers if t.split()[-1] in EXCHANGES]

    def js(arr):
        return "[\n    " + ",\n    ".join(
            f"{{ name: {json.dumps(v['name'], ensure_ascii=False)}, pct: {v['pct']} }}" for v in arr) + ",\n  ]"

    oggi = datetime.date.today().isoformat()
    aum_mln = round((car.get("AUM") or 0) / 1e6, 1)
    ts = f"""/**
 * Fotografia del paniere C3M dall'ultimo snapshot dell'archiviatore (API Amundi).
 * ⚠️ Amundi non pubblica il paniere completo ({car.get('BENCHMARK_NUMBER_OF_COMPONENTS', '~54')} titoli
 * nell'indice): espone Top 10 + spaccati aggregati — l'articolo lo dichiara.
 * Il primo paese viaggia a ridosso del tetto del {TETTO_CAPPING}% (capping ground rules FTSE):
 * il golden lo sorveglia — uno sforamento = dati rotti o notizia, mai pubblicazione muta.
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_c3m_composition.py`
 * (archivio C3M). Non modificare a mano.
 */
export type C3mVoce = {{ name: string; pct: number }}
export type C3mComposition = {{
  updated: string
  asOf: string // data-dato della posizione (POSITION_AS_OF_DATE)
  nav: number
  navDate: string
  aumMln: number
  ter: number
  benchComponents: number
  fundInstruments: number // strumenti nel paniere COMPLETO pubblicato dall'emittente
  top10Full: {{ name: string; isin: string; country: string; pct: number }}[] // dal paniere integrale
  top10Fund: C3mVoce[]
  top10Index: C3mVoce[]
  countries: C3mVoce[]
  ratings: C3mVoce[]
  maturities: C3mVoce[]
  passported: {{ en: string; it: string; retail: boolean }}[] // autorizzazione alla vendita
  listings: {{ exchange: string; ticker: string }}[] // piazze di quotazione effettive
}}

export const C3M_COMPOSITION: C3mComposition = {{
  updated: '{asof}', // data di POSIZIONE (data-derivata: niente freschezza finta)
  asOf: '{asof}',
  nav: {nav},
  navDate: '{datetime.datetime.utcfromtimestamp(car["NAV_DATE_DISPLAYED"] / 1000).date().isoformat() if car.get("NAV_DATE_DISPLAYED") else asof}',
  aumMln: {aum_mln},
  ter: {car.get('TER', 0)},
  benchComponents: {car.get('BENCHMARK_NUMBER_OF_COMPONENTS', 0)},
  fundInstruments: {full_count},
  top10Full: {json.dumps(top10_full, ensure_ascii=False)},
  top10Fund: {js(top10)},
  top10Index: {js(top10_idx)},
  countries: {js(paesi)},
  ratings: {js(rating)},
  maturities: {js(scadenze)},
  passported: {json.dumps(passported, ensure_ascii=False)},
  listings: {json.dumps(listings, ensure_ascii=False)},
}}
"""
    with open(DEST, "w") as f:
        f.write(ts)
    print(f"[c3m-composition] scritto: asof {asof}, NAV {nav}, AUM {aum_mln}M, "
          f"{paesi[0]['name']} {paesi[0]['pct']}% (tetto {TETTO_CAPPING}), somma paesi {somma_paesi:.1f}%")


if __name__ == "__main__":
    main()
