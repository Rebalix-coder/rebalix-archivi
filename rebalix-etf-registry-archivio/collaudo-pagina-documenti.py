#!/usr/bin/env python3
# collaudo-pagina-documenti.py — collaudo PUBBLICO della sezione «Documenti» di una scheda salvata, dopo il COMMIT di un lotto del giro
# documentale automatico (rev. 2, 28 ott 2026; riesame dell'auditor: le attese derivano dal COMPORTAMENTO EFFETTIVO della pagina per
# classe, come nei copioni approvati). Uso: collaudo-pagina-documenti.py --html <file> --lang it|en --http <codice> --attese <json>
#   attese = {"pubblica": bool, "voci": [{"tipo": "kid_it"|…, "href": "<href atteso nella scheda>", "lingua": "it"|…|null,
#             "invalidata": bool, "via_pagina": bool}]}
#   · classe NON pubblica (is_etf falso e non ETC/ETP/ETN): atteso HTTP 404 e nessun altro controllo (la scheda non esiste per scelta);
#   · classe pubblica: HTTP 200 e sezione <section id="documenti"> presente; per ogni voce una scheda con href ESATTO = href atteso
#     (per il factsheet in anomalia definitiva l'href atteso è la PAGINA DEL FONDO dell'emittente, non il PDF: «via_pagina»);
#   · lingua SCRITTA (lingua non nulla, non invalidata, non via_pagina): la scheda mostra «PDF in <lingua>» (IT: italiano/inglese/
#     tedesco/francese; EN: Italian/English/German/French) oppure l'alternativa «in <lingua>», e MAI «non verificata»;
#   · INVALIDATA: solo l'href (la pagina può ricadere sulla lingua dedotta dall'URL: la verifica dell'invalidazione sta nel registro);
#   · solo URL scritto: solo l'href. Esce 0 = superato · 1 = non superato (motivi a video) · 2 = argomenti.
import argparse, html, json, re, sys

NOMI = {'it': {'it': 'italiano', 'en': 'inglese', 'de': 'tedesco', 'fr': 'francese'}, 'en': {'it': 'Italian', 'en': 'English', 'de': 'German', 'fr': 'French'}}
NON_VERIFICATA = {'it': 'non verificata', 'en': 'not verified'}

def sezione(src):
    m = re.search(r'<section id="documenti".*?</section>', src, re.S)
    return m.group(0) if m else None

def schede(sez):
    inizi = [m.start() for m in re.finditer(r'<a href="[^"]+" target="_blank"[^>]*style="display:flex', sez)]
    parti = [sez[i:(inizi[k + 1] if k + 1 < len(inizi) else len(sez))] for k, i in enumerate(inizi)]
    out = []
    for p in parti:
        hrefs = [html.unescape(h) for h in re.findall(r'href="([^"]+)"', p)]
        testo = re.sub(r'\s+', ' ', html.unescape(re.sub(r'<[^>]+>', ' ', p))).strip()
        out.append((hrefs, testo))
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--html', required=True); ap.add_argument('--lang', choices=['it', 'en'], required=True)
    ap.add_argument('--http', required=True); ap.add_argument('--attese', required=True)
    a = ap.parse_args()
    try:
        attese = json.load(open(a.attese))
        src = open(a.html, encoding='utf-8', errors='replace').read()
    except Exception as e:
        print(f'argomenti: {e}'); sys.exit(2)
    if not isinstance(attese, dict) or 'voci' not in attese: print('attese: serve un oggetto con «pubblica» e «voci»'); sys.exit(2)
    motivi = []
    if not attese.get('pubblica', True):
        if a.http == '404': print(f'  ✓ {a.lang}: classe non pubblica, HTTP 404 come atteso'); sys.exit(0)
        print(f'  ✗ classe non pubblica ma HTTP {a.http} (atteso 404)'); sys.exit(1)
    if a.http != '200': motivi.append(f'HTTP {a.http} (atteso 200)')
    sez = sezione(src)
    if not sez:
        motivi.append('sezione «documenti» assente')
        for m in motivi: print(f'  ✗ {m}')
        sys.exit(1)
    sc = schede(sez)
    for att in attese['voci']:
        href = att['href']; k = att['tipo']
        mie = [(h, t) for h, t in sc if href in h]
        if not mie:
            motivi.append(f'{k}: nessuna scheda con href = {href[-70:]}' + (' (atteso il rimando alla pagina del fondo)' if att.get('via_pagina') else '')); continue
        if att.get('invalidata') or att.get('via_pagina'): continue
        lingua = att.get('lingua')
        if lingua:
            nome = NOMI[a.lang].get(lingua, lingua)
            ok = any((f'PDF in {nome}' in t or f' in {nome}' in t) and NON_VERIFICATA[a.lang] not in t for _, t in mie)
            if not ok: motivi.append(f'{k}: lingua «{lingua}» scritta ma la scheda non mostra «PDF in {nome}»/«in {nome}» senza «{NON_VERIFICATA[a.lang]}» (testo: {mie[0][1][:120]})')
    if motivi:
        for m in motivi: print(f'  ✗ {m}')
        sys.exit(1)
    print(f'  ✓ {a.lang}: sezione presente, {len(attese["voci"])} attese superate')
    sys.exit(0)

if __name__ == '__main__':
    main()
