#!/usr/bin/env python3
"""Registro delle VARIAZIONI SIGNIFICATIVE del paniere C3M (idea di Linus, 29/7):
l'archivio quotidiano da solo è muto — il valore per il lettore è un registro di
eventi sopra-soglia, con le soglie DICHIARATE in pagina (pattern «mai cambi muti»
dei bond). Il roll settimanale dei singoli bill è fisiologico e NON è un evento.

MECCANICA (stato-di-riferimento, non giorno-su-giorno: le derive lente non sfuggono):
- `history/variazioni-stato.json` = ultimo stato SEGNALATO (pesi paesi/scadenze/rating
  + insieme dei paesi). Primo giro: baseline dal primo snapshot col paniere completo,
  nessun evento.
- ogni giro: confronto snapshot più recente vs stato; sopra soglia → evento in
  `history/variazioni.jsonl` + aggiornamento dello stato PER QUELLA VOCE.
- eventi STRUTTURATI {date, kind, name, from, to}: le frasi le compone il componente
  (bilingue). Modulo `lib/blog/c3m-changes.ts` = baseline + eventi.

SOGLIE (concordate con Linus, dichiarate nell'articolo):
- paese che ENTRA/ESCE dal paniere: sempre segnalato (kind country-in/country-out)
- peso di un paese: |Δ| ≥ 2,0 punti (kind country-weight)
- fascia di scadenza: |Δ| ≥ 5,0 punti (kind maturity)
- fascia di rating: |Δ| ≥ 5,0 punti (kind rating)
"""
import json, os, sys, datetime

ARCHIVE = os.path.expanduser("~/backups/rebalix-c3m-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "c3m-changes.ts")
STATO = os.path.join(ARCHIVE, "history", "variazioni-stato.json")
EVENTI = os.path.join(ARCHIVE, "history", "variazioni.jsonl")

SOGLIA_PAESE = 2.0
SOGLIA_SCADENZE = 5.0
SOGLIA_RATING = 5.0


def pesi(bds, campo):
    return {v["aggregationName"]: round(float(v.get("adjustedWeight") or 0) * 100, 2)
            for v in bds.get(campo, [])}


def snapshot_stato(p):
    bds = {b["aggregationField"]: b.get("breakDownData") or [] for b in p.get("breakDowns") or []}
    return {"countries": pesi(bds, "FUND_COUNTRIES"),
            "maturities": pesi(bds, "FUND_MATURITIES"),
            "ratings": pesi(bds, "FUND_RATINGS")}


def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print("[c3m-changes] repo non trovato — salto."); return
    raws = sorted(os.listdir(os.path.join(ARCHIVE, "raw")))
    if not raws:
        sys.exit("[c3m-changes] nessun raw — NON scrivo")
    ultimo = json.load(open(os.path.join(ARCHIVE, "raw", raws[-1])))
    if not (ultimo.get("composition") or {}).get("compositionData"):
        sys.exit("[c3m-changes] ultimo raw senza paniere completo — NON scrivo")
    asof = raws[-1].replace(".json", "")
    corrente = snapshot_stato(ultimo)
    if not corrente["countries"]:
        sys.exit("[c3m-changes] snapshot senza spaccato paesi — NON scrivo")

    # baseline al primo giro
    if not os.path.exists(STATO):
        json.dump({"asof": asof, **corrente}, open(STATO, "w"), ensure_ascii=False)
        print(f"[c3m-changes] baseline creata ({asof}); nessun evento")
    stato = json.load(open(STATO))

    nuovi = []
    def evento(kind, name, da, a):
        nuovi.append({"date": asof, "kind": kind, "name": name,
                      "from": da, "to": a})

    # paesi: ingressi/uscite + pesi sopra soglia
    for paese in sorted(set(stato["countries"]) | set(corrente["countries"])):
        prima = stato["countries"].get(paese)
        dopo = corrente["countries"].get(paese)
        if prima is None and dopo is not None:
            evento("country-in", paese, 0, dopo); stato["countries"][paese] = dopo
        elif dopo is None and prima is not None:
            evento("country-out", paese, prima, 0); del stato["countries"][paese]
        elif prima is not None and dopo is not None and abs(dopo - prima) >= SOGLIA_PAESE:
            evento("country-weight", paese, prima, dopo); stato["countries"][paese] = dopo

    for campo, kind, soglia in (("maturities", "maturity", SOGLIA_SCADENZE),
                                ("ratings", "rating", SOGLIA_RATING)):
        for nome in sorted(set(stato[campo]) | set(corrente[campo])):
            prima = stato[campo].get(nome, 0)
            dopo = corrente[campo].get(nome, 0)
            if abs(dopo - prima) >= soglia:
                evento(kind, nome, prima, dopo); stato[campo][nome] = dopo

    if nuovi:
        with open(EVENTI, "a") as f:
            for e in nuovi:
                f.write(json.dumps(e, ensure_ascii=False) + "\n")
        stato["asof"] = asof
        json.dump(stato, open(STATO, "w"), ensure_ascii=False)

    # modulo solo se c'è qualcosa di nuovo (o manca): il rilevamento gira ogni giorno
    # dall'archiviatore e un rewrite quotidiano sporcherebbe il repo senza motivo
    if not nuovi and os.path.exists(DEST):
        print("[c3m-changes] nessun evento nuovo, modulo invariato"); return

    # modulo dai soli eventi confermati (append-only; dedup per chiave completa)
    eventi = []
    visti = set()
    if os.path.exists(EVENTI):
        for l in open(EVENTI):
            e = json.loads(l)
            k = (e["date"], e["kind"], e["name"])
            if k not in visti:
                visti.add(k); eventi.append(e)
    eventi.sort(key=lambda e: e["date"], reverse=True)

    baseline = json.load(open(STATO)).get("asof", asof)
    prima_baseline = json.load(open(STATO))
    # data-derivata: ultimo evento registrato, o baseline se il registro è vuoto
    ultimo_evento = eventi[0]["date"] if eventi else min(raws).replace(".json", "")
    ts = f"""/**
 * Registro delle variazioni SIGNIFICATIVE del paniere C3M, con soglie dichiarate
 * (paese entra/esce: sempre; peso paese ±{SOGLIA_PAESE} pt; scadenze/rating ±{SOGLIA_RATING} pt),
 * confrontate con l'ULTIMO STATO SEGNALATO (le derive lente non sfuggono).
 * Il roll settimanale dei singoli bill è fisiologico e non è un evento.
 * Prima osservazione (baseline): {min(raws).replace('.json', '')}.
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_c3m_changes.py`
 * (archivio C3M, registro append-only). Non modificare a mano.
 */
export type C3mChange = {{
  date: string
  kind: 'country-in' | 'country-out' | 'country-weight' | 'maturity' | 'rating'
  name: string
  from: number
  to: number
}}

export const C3M_CHANGES: {{
  updated: string
  baselineDate: string
  thresholds: {{ countryPt: number; maturityPt: number; ratingPt: number }}
  events: C3mChange[]
}} = {{
  updated: '{ultimo_evento}',
  baselineDate: '{min(raws).replace(".json", "")}',
  thresholds: {{ countryPt: {SOGLIA_PAESE}, maturityPt: {SOGLIA_SCADENZE}, ratingPt: {SOGLIA_RATING} }},
  events: {json.dumps(eventi, ensure_ascii=False)},
}}
"""
    with open(DEST, "w") as f:
        f.write(ts)
    print(f"[c3m-changes] scritto: {len(eventi)} eventi registrati "
          f"({len(nuovi)} nuovi in questo giro), stato al {prima_baseline.get('asof')}")


if __name__ == "__main__":
    main()
