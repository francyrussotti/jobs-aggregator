"""Lettura delle tre newsletter nel formato comune.

Ogni parser riceve una Email e restituisce le offerte più gli avvisi che la
newsletter stessa riporta (fonti rotte, offerte tagliate...). Gli avvisi
finiscono solo nel log: questo progetto non ripara le altre newsletter.
"""
import re

from bs4 import BeautifulSoup

from .models import EsitoParsing, Offerta

PAESI_BIG4 = ("Italia", "Belgio", "Lussemburgo", "Irlanda", "Paesi Bassi")
# "EY Italia", "Deloitte Paesi Bassi"... davanti alla città nel campo sede
RE_ENTE_BIG4 = re.compile(
    r"^(EY|PwC|Deloitte|KPMG|Accenture|NTT DATA|Capgemini|Bip|Digital360|Roland Berger|"
    r"Simon-Kucher|Oliver Wyman|Gartner|Grant Thornton)( (" + "|".join(PAESI_BIG4) + r"))?$")
RE_DATA_ISO = re.compile(r"^\d{4}-\d{2}-\d{2}$")
RE_QUANDO = re.compile(r"^(oggi|ieri|\d+ giorni fa|\d{1,2}/\d{2}|\d{1,2} [a-z]{3})$", re.I)


def _testo(el):
    return re.sub(r"\s+", " ", el.get_text(" ", strip=True)).strip() if el else ""


def _stile(el, *pezzi):
    s = (el.get("style") or "").replace(" ", "").replace("\n", "")
    return all(p in s for p in pezzi)


def _azienda_big4(sezione):
    for paese in PAESI_BIG4:
        if sezione.endswith(" " + paese):
            return sezione[: -len(paese) - 1].strip()
    return sezione


# --------------------------------------------------------------------------
# Big4 Jobs: sezioni <td id="f-...">, titolo in <a> a 18px, sede in <strong>
# --------------------------------------------------------------------------
def parse_big4(email):
    soup = BeautifulSoup(email.html, "html.parser")
    offerte, avvisi = [], []

    box = soup.find(string=re.compile("Controllo automatico"))
    if box:
        for d in box.find_parent("div").find_all("div"):
            avvisi.append(_testo(d).lstrip("🔴🟠 \xa0"))

    for sez in soup.find_all("td", id=re.compile(r"^f-")):
        quadrato = sez.find("span", style=re.compile(r"width:\s*10px"))
        sezione = _testo(quadrato.parent) if quadrato else _testo(sez.find("td"))
        paese = next((p for p in PAESI_BIG4 if sezione.endswith(" " + p)), "")
        for a in sez.find_all("a"):
            if not _stile(a, "font-size:18px"):
                continue
            meta = a.find_next_sibling("div")
            sede = ""
            if meta and meta.find("strong"):
                parti = [p.strip() for p in _testo(meta.find("strong")).split("·")]
                sede = ", ".join(p for p in parti if p and not RE_ENTE_BIG4.match(p))
                if not sede:          # solo "Bip Italia": resta il paese dell'ente
                    m = next((RE_ENTE_BIG4.match(p) for p in parti if RE_ENTE_BIG4.match(p)), None)
                    paese = paese or (m.group(3) if m and m.group(3) else "")
            if not sede and paese:
                sede = paese          # la fonte non indica la città: resta il paese
            offerte.append(Offerta(
                data=email.data, azienda=_azienda_big4(sezione), ruolo=_testo(a),
                sede=sede, link=a.get("href", ""), fonte=email.fonte, sottofonte=sezione))

    if not offerte and "nuov" in email.oggetto and not re.search(r"nessuna", email.oggetto, re.I):
        avvisi.append("email Big4 senza offerte leggibili: struttura HTML cambiata?")
    return EsitoParsing(offerte, avvisi)


# --------------------------------------------------------------------------
# Paris Jobs: parte di testo semplice, molto regolare
#   == Ashby (4) ==
#   - Dust — User Researcher
#     Paris · 2026-11-03
#     https://...
# --------------------------------------------------------------------------
def parse_paris(email):
    if not email.testo.strip():
        return _parse_paris_html(email)
    offerte, avvisi = [], []
    sottofonte, corrente, in_avvisi = "", None, False

    def chiudi():
        if corrente:
            offerte.append(corrente)

    for riga in email.testo.splitlines():
        r = riga.rstrip()
        m = re.match(r"^== (.+?) \(\d+\) ==$", r.strip())
        if m:
            chiudi(); corrente = None
            sottofonte, in_avvisi = m.group(1), False
            continue
        if r.startswith("ATTENZIONE"):
            in_avvisi = True
            continue
        if in_avvisi:
            if r.startswith("- "):
                avvisi.append(r[2:].strip())
            continue
        if r.startswith("- ") and sottofonte:
            chiudi()
            testa = r[2:]
            azienda, _, ruolo = testa.partition(" — ")
            azienda = re.sub(r"\s*\(via [^)]*\)\s*$", "", azienda).strip()
            ruolo = re.sub(r"\s*\[ruolo target\]\s*$", "", ruolo).strip()
            corrente = Offerta(data=email.data, azienda=azienda, ruolo=ruolo, sede="",
                               link="", fonte=email.fonte, sottofonte=sottofonte)
            continue
        if corrente and r.startswith("  "):
            s = r.strip()
            if s.startswith("http"):
                corrente.link = s
            else:
                parti = [p.strip() for p in s.split(" · ")]
                if parti and RE_DATA_ISO.match(parti[-1]):
                    corrente.pubblicata = parti.pop()
                corrente.sede = " · ".join(parti)
    chiudi()
    return EsitoParsing(offerte, avvisi)


def _parse_paris_html(email):
    soup = BeautifulSoup(email.html, "html.parser")
    offerte, avvisi = [], []
    for li in soup.select("div ul li"):
        avvisi.append(_testo(li))
    for blocco in soup.find_all("div", style=re.compile("margin-bottom:24px")):
        tds = blocco.find("table").find_all("td")
        sottofonte = _testo(tds[0]) if tds else ""
        for cella in blocco.find_all("td", style=re.compile("border-bottom")):
            a = cella.find("a")
            if not a:
                continue
            testa = cella.find("div")
            via = testa.find("span")
            if via:
                via.extract()
            spans = [_testo(s) for s in cella.find_all("span")]
            sede = next((s.lstrip("📍 ") for s in spans if s.startswith("📍")), "")
            pub = next((s.lstrip("📅 ") for s in spans if s.startswith("📅")), "")
            offerte.append(Offerta(data=email.data, azienda=_testo(testa).lstrip("🏢 ").strip(),
                                   ruolo=_testo(a), sede=sede, link=a.get("href", ""),
                                   fonte=email.fonte, pubblicata=pub, sottofonte=sottofonte))
    return EsitoParsing(offerte, avvisi)


# --------------------------------------------------------------------------
# Aziende Target: sezioni <td id="s-PAR|IT|REMOTO|EU...">, azienda in un div
# a 15px grassetto, titolo in <a> a 16px, sede/quando/etichette nel div dopo
# --------------------------------------------------------------------------
def parse_aziende_target(email):
    soup = BeautifulSoup(email.html, "html.parser")
    offerte, avvisi = [], []
    zona, azienda = "", ""

    box = soup.find(string=re.compile("Fonti da controllare"))
    if box:
        for d in box.find_parent("div").find_all("div"):
            avvisi.append(_testo(d).lstrip("· "))

    for el in soup.find_all(["td", "div", "a"]):
        if el.name == "td" and (el.get("id") or "").startswith("s-"):
            zona = el["id"][2:]
        elif el.name == "td" and _testo(el).startswith("+ altre") and not el.find("td"):
            avvisi.append(f"{azienda} ({zona}): l'email mostra solo una parte delle offerte "
                          f"— {_testo(el)}")
        elif el.name == "div" and _stile(el, "font-size:15px", "font-weight:700"):
            azienda = _testo(el)
        elif el.name == "a" and _stile(el, "font-size:16px"):
            meta = el.find_next_sibling("div")
            etichette = [_testo(s) for s in meta.find_all("span")] if meta else []
            if meta:
                for s in meta.find_all("span"):
                    s.extract()
            parti = [p.strip() for p in _testo(meta).split("·")] if meta else []
            parti = [p for p in parti if p]
            sede = parti[0] if parti and not RE_QUANDO.match(parti[0]) else ""
            offerte.append(Offerta(data=email.data, azienda=azienda, ruolo=_testo(el), sede=sede,
                                   link=el.get("href", ""), fonte=email.fonte,
                                   etichette=etichette, sottofonte=zona))
    return EsitoParsing(offerte, avvisi)


PARSER = {"big4": parse_big4, "paris": parse_paris, "aziende_target": parse_aziende_target}
