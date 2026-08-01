#!/usr/bin/env python3
"""Rigenera il modulo versionato `lib/blog/xd-lookthrough.ts`: la radiografia
paesi/settori dei 4 Xtrackers Diversified Portfolio, calcolata DA NOI aggregando
le posizioni complete dei mattoncini (archivio lookthrough/, fonte DWS).

METODOLOGIA (decisa 14-15 lug 2026 — trappola verificata sul campo):
- Mattoncini FISICI: distribuzione reale delle loro posizioni.
- Mattoncini SWAP: il paniere in pancia e' il COLLATERALE, non l'indice (il MSCI USA
  Swap deteneva 5,8% Germania e perfino Brasile!) -> si usa l'esposizione dell'INDICE:
    · MSCI USA Swap   -> 100% Stati Uniti (per costruzione); settori = proxy MSCI USA fisico
    · MSCI EM Swap    -> proxy = MSCI Emerging Markets fisico (IE00BTJRMP35)
    · MSCI World Swap -> paesi = ACWI Screened fisico MENO i paesi emergenti (lista presa
      dal fisico EM), rinormalizzato; settori = ACWI Screened tal quale
  Ogni proxy e' dichiarato nel campo `metodologia` del modulo.
- Falda azionaria e falda obbligazionaria SEPARATE (il "paese" di un bond e' l'emittente).
- Oro e liquidita' esclusi (gia' mostrati nell'aggregato per classe di xd-holdings).
Sanita' (fail-loud): pesi falda ~100 dopo rinormalizzazione, dati non piu' vecchi di 10
giorni, quota 'sconosciuta' <8% per falda. Scrive solo se esiste la cartella del repo.
"""
import json, os, sys, datetime

ARCHIVE = os.path.expanduser("~/backups/rebalix-xtrackers-archivio")
REPO = os.path.expanduser("~/progetti/rebalix")
DEST = os.path.join(REPO, "lib", "blog", "xd-lookthrough.ts")

PROFILI = {"20": "xeq2", "40": "xeq4", "60": "xeq6", "80": "xeq8"}
FISICO_EM = "IE00BTJRMP35"      # MSCI Emerging Markets (proxy per EM Swap + lista paesi EM)
FISICO_USA = "IE00BJ0KDR00"     # MSCI USA (proxy settori per USA Swap)
FISICO_ACWI = "IE00BGHQ0G80"    # MSCI AC World Screened (base proxy World Swap)
TOP_N = 12
MAX_ETA_GIORNI = 10
MAX_SCONOSCIUTA = 8.0
IGNORA = {"sconosciuta", "n.d.", "--", ""}

def ultimo(path):
    with open(path) as f:
        righe = f.read().splitlines()
    return json.loads(righe[-1])

def lookthrough(isin):
    return ultimo(os.path.join(ARCHIVE, "lookthrough", isin + ".jsonl"))

def normalizza(dist):
    """Toglie le voci ignote e rinormalizza a 100."""
    pulita = {k: v for k, v in dist.items() if k not in IGNORA and v > 0}
    tot = sum(pulita.values())
    return {k: v / tot * 100 for k, v in pulita.items()} if tot else {}

def dist_mattoncino(isin, nome):
    """(paesi, settori, proxy_usato) per un mattoncino azionario, con le regole swap."""
    if "Swap" not in (nome or ""):
        r = lookthrough(isin)
        return (normalizza(r["aggregati"].get("paese", {})),
                normalizza(r["aggregati"].get("industria", {})), None)
    n = nome.lower()
    if "msci usa swap" in n:
        settori = normalizza(lookthrough(FISICO_USA)["aggregati"].get("industria", {}))
        return {"Stati Uniti d'America": 100.0}, settori, "indice (100% USA); settori: proxy MSCI USA fisico"
    if "emerging markets swap" in n:
        r = lookthrough(FISICO_EM)
        return (normalizza(r["aggregati"].get("paese", {})),
                normalizza(r["aggregati"].get("industria", {})), "proxy MSCI Emerging Markets fisico")
    if "msci world swap" in n:
        acwi = lookthrough(FISICO_ACWI)
        # paesi EM = solo quelli con peso significativo nel fondo EM (>=1%): il fondo EM
        # tiene anche briciole di titoli USA/sviluppati che NON vanno tolte dall'ACWI
        paesi_em = {k for k, v in normalizza(lookthrough(FISICO_EM)["aggregati"].get("paese", {})).items()
                    if v >= 1.0} - {"Stati Uniti d'America"}
        paesi = normalizza({k: v for k, v in normalizza(acwi["aggregati"].get("paese", {})).items()
                            if k not in paesi_em})
        return (paesi, normalizza(acwi["aggregati"].get("industria", {})),
                "proxy ACWI Screened fisico senza paesi emergenti (paesi); ACWI tal quale (settori)")
    sys.exit(f"!! mattoncino swap non riconosciuto: {nome} — modulo NON scritto")

def falda(posizioni, classe):
    """Aggrega paesi (e settori se azionaria) della falda richiesta, pesata e rinormalizzata."""
    voci = [p for p in posizioni if p["classe"] == classe and p["isin"]]
    tot_falda = sum(p["peso"] for p in voci)
    paesi, settori, proxy_note = {}, {}, []
    for p in voci:
        if classe == "azioni":
            dp, ds, proxy = dist_mattoncino(p["isin"], p["nome"])
            if proxy:
                proxy_note.append(f"{p['nome']}: {proxy}")
        else:
            r = lookthrough(p["isin"])
            dp, ds = normalizza(r["aggregati"].get("paese", {})), {}
        quota = p["peso"] / tot_falda
        for k, v in dp.items():
            paesi[k] = paesi.get(k, 0) + v * quota
        for k, v in ds.items():
            settori[k] = settori.get(k, 0) + v * quota
    for nome_dist, dist in (("paesi", paesi), ("settori", settori)):
        if dist and abs(sum(dist.values()) - 100) > 1.0:
            sys.exit(f"!! falda {classe}/{nome_dist}: somma {sum(dist.values()):.1f} ≠ 100 — modulo NON scritto")
    return paesi, settori, proxy_note

def paesi_em_bond():
    """Paesi del blocco J.P. Morgan EM Bond (>=0,1% nel blocco): la lista 'ufficiale'
    degli emittenti emergenti, presa dai dati stessi — serve a spacchettare la coda."""
    r = lookthrough("LU0321462953")
    return {k for k, v in normalizza(r["aggregati"].get("paese", {})).items() if v >= 0.1}

def top_altri(dist, em_set=None):
    """Top-N + coda. La coda NON e' un blob opaco: per i bond (em_set) si spacca in
    'altri emergenti' / 'altri sviluppati' (token ALTRI_EM/ALTRI_DEV + conteggio paesi),
    per le azioni resta un solo ALTRI col conteggio. Il client localizza le etichette."""
    voci = sorted(dist.items(), key=lambda kv: -kv[1])
    testa = [{"nome": k, "pct": round(v, 2)} for k, v in voci[:TOP_N]]
    coda = voci[TOP_N:]
    if not coda:
        return testa
    if em_set is None:
        testa.append({"nome": "ALTRI", "pct": round(sum(v for _, v in coda), 2), "n": len(coda)})
        return testa
    em = [(k, v) for k, v in coda if k in em_set]
    dev = [(k, v) for k, v in coda if k not in em_set]
    if em:
        testa.append({"nome": "ALTRI_EM", "pct": round(sum(v for _, v in em), 2), "n": len(em)})
    if dev:
        testa.append({"nome": "ALTRI_DEV", "pct": round(sum(v for _, v in dev), 2), "n": len(dev)})
    return testa

def main():
    if not os.path.isdir(os.path.dirname(DEST)):
        print(f"[xd-look] repo non trovato ({DEST}) — salto."); return
    # freschezza dei lookthrough usati
    for f_ in os.listdir(os.path.join(ARCHIVE, "lookthrough")):
        r = ultimo(os.path.join(ARCHIVE, "lookthrough", f_))
        eta = (datetime.date.today() - datetime.date.fromisoformat(r["asof"])).days
        if eta > MAX_ETA_GIORNI:
            sys.exit(f"!! lookthrough {f_}: dato del {r['asof']} ({eta} gg) — stantio, modulo NON scritto")
    # composizioni correnti dai history
    profili_out, note_proxy = {}, []
    for prof, key in PROFILI.items():
        h = None
        with open(os.path.join(ARCHIVE, "history", key + ".jsonl")) as f:
            for line in f:
                r = json.loads(line)
                if r.get("kind") == "full":
                    h = r
        pos = [{"isin": p["isin"], "nome": p["nome"], "peso": p["peso"] or 0,
                "classe": {"Azionari": "azioni", "Obbligazionari": "obbligazioni"}.get(p.get("classe"), "altro")}
               for p in h["posizioni"]]
        az_p, az_s, proxy = falda(pos, "azioni")
        ob_p, _, _ = falda(pos, "obbligazioni")
        note_proxy = proxy or note_proxy
        scon = sum(v for k, v in az_p.items() if k in IGNORA) + sum(v for k, v in ob_p.items() if k in IGNORA)
        if scon > MAX_SCONOSCIUTA:
            sys.exit(f"!! {key}: quota ignota {scon:.1f}% — modulo NON scritto")
        em_set = paesi_em_bond()
        profili_out[prof] = {"asof": h["asof"], "azioni_paesi": top_altri(az_p),
                             "azioni_settori": top_altri(az_s), "bond_paesi": top_altri(ob_p, em_set)}
    def arr(voci):
        out = []
        for v in voci:
            nome = v["nome"].replace(chr(39), chr(92) + chr(39))
            extra = f", n: {v['n']}" if "n" in v else ""
            out.append(f"{{ nome: '{nome}', pct: {v['pct']:g}{extra} }}")
        return "[" + ", ".join(out) + "]"
    oggi = datetime.date.today().isoformat()
    blocchi = []
    for prof, d in profili_out.items():
        blocchi.append(f"""  '{prof}': {{
    asof: '{d["asof"]}',
    azioniPaesi: {arr(d["azioni_paesi"])},
    azioniSettori: {arr(d["azioni_settori"])},
    bondPaesi: {arr(d["bond_paesi"])},
  }}""")
    metodologia = "; ".join(note_proxy)
    body = f"""/**
 * Radiografia paesi/settori dei 4 Xtrackers Diversified Portfolio, calcolata da Rebalix
 * aggregando le posizioni complete dei mattoncini (fonte DWS, archivio quotidiano).
 * Falda azionaria e obbligazionaria SEPARATE (il "paese" di un bond è l'emittente).
 * Mattoncini swap: esposizione dell'INDICE, non del paniere-collaterale (vedi metodologia).
 *
 * FILE VERSIONATO E AGGIORNATO AUTOMATICAMENTE da `_scripts/gen_xd_lookthrough.py`
 * (archivio Xtrackers). Non modificare a mano.
 */
export type XdVoce = {{ nome: string; pct: number; n?: number }} // n = paesi raggruppati nei token ALTRI*
export type XdRadiografia = {{
  asof: string
  azioniPaesi: XdVoce[] // % della falda azionaria
  azioniSettori: XdVoce[] // % della falda azionaria
  bondPaesi: XdVoce[] // % della falda obbligazionaria (paese dell'emittente)
}}
export type XdLookthrough = {{
  updated: string
  metodologia: string // trattamento dei mattoncini a replica sintetica
  profili: Record<'20' | '40' | '60' | '80', XdRadiografia>
}}

export const XD_LOOKTHROUGH: XdLookthrough = {{
  updated: '{oggi}',
  metodologia: '{metodologia.replace(chr(39), chr(92)+chr(39))}',
  profili: {{
{(",{}".format(chr(10))).join(blocchi)},
  }},
}}
"""
    with open(DEST, "w") as f:
        f.write(body)
    p80 = profili_out["80"]
    print(f"[xd-look] scritto {DEST}")
    print(f"  controllo 80%: paesi az. top3 {p80['azioni_paesi'][:3]}")
    print(f"                 settori top3 {p80['azioni_settori'][:3]}")
    print(f"                 bond top3 {p80['bond_paesi'][:3]}")

if __name__ == "__main__":
    main()
