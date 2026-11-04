"""Riepilogo del lunedì: 10 aziende della lista Aziende Target senza annunci
aperti, con 2-3 titoli da cercare su LinkedIn.

Legge in sola lettura i file pubblici del repo aziende-target-jobs-newsletter.
"Senza annunci aperti" vuol dire: l'azienda ha una fonte e l'ultima lettura ha
trovato 0 offerte, oppure non ha nessuna fonte monitorata (annunci sconosciuti).
Scelta neutra: ordine della lista, a rotazione settimanale (niente punteggi).
"""
import html as html_lib
import re
from urllib.parse import quote_plus, urlparse

import requests

RE_LINGUA = re.compile(r"[a-z]{2}(-[A-Z]{2})?", re.I)

SEDE = {"PAR": "Parigi", "IT": "Italia", "IT+PAR": "Italia + Parigi"}


def chiave_fonte(f):
    """Stessa chiave usata da aziende-target-jobs-newsletter (fonti.chiave_fonte)."""
    if f.get("tipo") == "workday":
        u = urlparse(f.get("url", ""))
        parti = [p for p in u.path.split("/") if p and not RE_LINGUA.fullmatch(p)]
        return f"workday:{u.netloc.lower()}/{'/'.join(parti[:1])}"
    return f["tipo"] + ":" + str(f.get("slug") or f.get("url"))


def titoli_suggeriti(a):
    """2-3 titoli da cercare, dedotti dal tipo di azienda (campi della lista)."""
    nome = a["n"].lower()
    italia = "IT" in (a.get("k") or "") and "PAR" not in (a.get("k") or "")
    titoli = []
    if a.get("o"):
        titoli += ["Open Innovation Analyst", "Startup Scouting Associate"]
    if re.search(r"energ|hydrogen|idrogen|power|solar|wind|renew", nome):
        titoli.append("Energy Transition Analyst")
    if re.search(r"space|spazi|aero|satell", nome):
        titoli.append("Space Business Development Associate")
    if a.get("np"):
        titoli.append("Progettista bandi europei" if italia else "EU Project Officer")
        titoli.append("Consulente finanza agevolata" if italia else "Grant Consultant")
    titoli.append("Innovation Consultant")
    titoli.append("Business Development Associate")
    return list(dict.fromkeys(titoli))[:3]


def _leggi(url):
    r = requests.get(url, timeout=30)
    r.raise_for_status()
    return r.json()


def aziende_senza_annunci(cfg, settimana):
    c = cfg["lunedi"]
    aziende = _leggi(c["url_aziende"])["aziende"]
    fonti = _leggi(c["url_fonti"]).get("fonti", {})
    manuali = {k: v for k, v in _leggi(c["url_fonti_manuali"]).items() if not k.startswith("_")}
    fonti = {**fonti, **manuali}
    storico = _leggi(c["url_seen"]).get("storico", [])
    ultimi = storico[-1]["conteggi"] if storico else {}

    zone = set(c.get("zone") or [])
    candidate = []
    for a in aziende:
        if zone and (a.get("k") or "") not in zone:
            continue
        sue = fonti.get(a["id"]) or []
        if sue:
            conteggi = [ultimi.get(chiave_fonte(f)) for f in sue]
            if any(n for n in conteggi if n):
                continue           # ha annunci aperti
            stato = "fonte monitorata: 0 annunci all'ultima lettura"
        else:
            stato = "nessuna fonte monitorata: annunci non verificabili"
        candidate.append((a, stato))
    if not candidate:
        return []
    n = c.get("quante_aziende", 10)
    inizio = (settimana * n) % len(candidate)
    giro = candidate[inizio:] + candidate[:inizio]
    return giro[:n]


def link_linkedin(titolo, azienda):
    return "https://www.linkedin.com/jobs/search/?keywords=" + quote_plus(f'{titolo} "{azienda}"')


def componi(scelte):
    """→ (html, testo) da aggiungere all'email del lunedì."""
    esc = html_lib.escape
    sans = "font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;"
    h = (f'<h2 style="{sans}font-size:18px;margin:32px 0 4px;border-bottom:2px solid #111827;'
         f'padding-bottom:4px;">Lunedì: aziende target senza annunci aperti</h2>'
         f'<p style="{sans}font-size:12px;color:#6b7280;">Ordine della lista Aziende Target, a '
         f'rotazione settimanale. I titoli sono suggerimenti da cercare su LinkedIn.</p>')
    t = ["== Lunedì: aziende target senza annunci aperti =="]
    for a, stato in scelte:
        sede = SEDE.get(a.get("k"), a.get("k") or a.get("p", ""))
        titoli = titoli_suggeriti(a)
        link = " · ".join(f'<a href="{esc(link_linkedin(x, a["n"]))}" style="color:#111827;">'
                          f'{esc(x)}</a>' for x in titoli)
        h += (f'<div style="{sans}font-size:14px;line-height:1.5;margin:10px 0;">'
              f'<strong>{esc(a["n"])}</strong> <span style="color:#6b7280;">· {esc(sede)} · '
              f'{esc(stato)}</span><br>Cerca: {link}</div>')
        t.append(f"- {a['n']} · {sede} · {stato}\n  Cerca su LinkedIn: " + " / ".join(titoli))
    return h, "\n".join(t)
