"""CSV per il tracker, log delle escluse ed email finale (neutra: fonte → azienda)."""
import csv
import html as html_lib
from pathlib import Path

from .filters import CONTROLLARE, MATCH

COLONNE_TRACKER = ["data", "azienda", "ruolo", "sede", "link", "fonte", "sezione"]
COLONNE_ESCLUSE = ["data", "azienda", "ruolo", "sede", "link", "fonte", "motivo"]


def ordina(offerte, ordine_fonti):
    """Per fonte (ordine di config.yaml), poi azienda, poi ruolo. Nessuna rilevanza."""
    rango = {f: i for i, f in enumerate(ordine_fonti)}
    return sorted(offerte, key=lambda o: (rango.get(o.fonte, 99), o.azienda.lower(),
                                          o.ruolo.lower(), o.data))


def scrivi_csv(percorso, offerte, colonne):
    Path(percorso).parent.mkdir(parents=True, exist_ok=True)
    with open(percorso, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        w.writerow(colonne)
        for o in offerte:
            w.writerow([getattr(o, c) for c in colonne])


def _gruppi(offerte):
    """[(fonte, [(azienda, [offerte])])] mantenendo l'ordine già dato."""
    out = []
    for o in offerte:
        if not out or out[-1][0] != o.fonte:
            out.append((o.fonte, []))
        aziende = out[-1][1]
        if not aziende or aziende[-1][0] != o.azienda:
            aziende.append((o.azienda, []))
        aziende[-1][1].append(o)
    return out


def _sezione_html(titolo, offerte, con_motivo):
    esc = html_lib.escape
    sans = "font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;"
    h = (f'<h2 style="{sans}font-size:18px;margin:28px 0 4px;border-bottom:2px solid #111827;'
         f'padding-bottom:4px;">{esc(titolo)} <span style="color:#9ca3af;font-weight:400;">· '
         f'{len(offerte)}</span></h2>')
    if not offerte:
        return h + f'<p style="{sans}font-size:14px;color:#6b7280;">Nessuna offerta.</p>'
    for fonte, aziende in _gruppi(offerte):
        h += (f'<h3 style="{sans}font-size:12px;letter-spacing:2px;text-transform:uppercase;'
              f'color:#6b7280;margin:18px 0 6px;">{esc(fonte)}</h3>')
        for azienda, lista in aziende:
            h += f'<div style="{sans}font-size:15px;font-weight:700;margin:10px 0 2px;">{esc(azienda)}</div>'
            for o in lista:
                nota = (f'<div style="font-size:12px;color:#92400e;">{esc(o.motivo)}</div>'
                        if con_motivo else "")
                h += (f'<div style="{sans}font-size:14px;line-height:1.5;padding:4px 0 4px 10px;'
                      f'border-left:2px solid #e5e7eb;"><a href="{esc(o.link or "#")}" '
                      f'style="color:#111827;">{esc(o.ruolo)}</a>'
                      f'<span style="color:#6b7280;"> · {esc(o.sede or "sede non indicata")}</span>'
                      f'{nota}</div>')
    return h


def _sezione_testo(titolo, offerte, con_motivo):
    righe = [f"== {titolo} ({len(offerte)}) =="]
    for fonte, aziende in _gruppi(offerte):
        righe.append(f"\n[{fonte}]")
        for azienda, lista in aziende:
            for o in lista:
                righe.append(f"- {azienda} — {o.ruolo} · {o.sede or 'sede non indicata'}")
                if con_motivo:
                    righe.append(f"  ({o.motivo})")
                righe.append(f"  {o.link}")
    return "\n".join(righe)


def componi_email(giorno_txt, match, controllare, n_escluse, mancanti, lunedi=None, quando="oggi"):
    """→ (html, testo)"""
    sans = "font-family:-apple-system,'Segoe UI',Helvetica,Arial,sans-serif;"
    esc = html_lib.escape
    avviso = ""
    if mancanti:
        avviso = (f'<p style="{sans}font-size:13px;color:#92400e;border-left:3px solid #f59e0b;'
                  f'padding-left:10px;">Newsletter non arrivata {quando}: {esc(", ".join(mancanti))}.</p>')
    corpo_lunedi, testo_lunedi = "", ""
    if lunedi:
        corpo_lunedi, testo_lunedi = lunedi
    html = (f'<!DOCTYPE html><html lang="it"><head><meta charset="utf-8"></head>'
            f'<body style="margin:0;padding:16px;background:#fff;"><div style="max-width:640px;margin:auto;">'
            f'<div style="{sans}font-size:12px;letter-spacing:3px;font-weight:700;">JOBS AGGREGATOR</div>'
            f'<div style="{sans}font-size:13px;color:#6b7280;">{esc(giorno_txt)} · '
            f'{len(match)} match · {len(controllare)} da controllare · {n_escluse} escluse</div>'
            f'{avviso}'
            f'{_sezione_html(MATCH, match, False)}'
            f'{_sezione_html(CONTROLLARE, controllare, True)}'
            f'{corpo_lunedi}'
            f'<p style="{sans}font-size:11px;color:#9ca3af;margin-top:32px;">Ordine: fonte, poi azienda. '
            f'Nessun punteggio. Le escluse, con il motivo, sono in excluded_log.csv.</p>'
            f'</div></body></html>')
    testo = "\n\n".join(x for x in [
        f"JOBS AGGREGATOR — {giorno_txt}",
        f"{len(match)} match · {len(controllare)} da controllare · {n_escluse} escluse",
        f"Newsletter non arrivata {quando}: {', '.join(mancanti)}" if mancanti else "",
        _sezione_testo(MATCH, match, False),
        _sezione_testo(CONTROLLARE, controllare, True),
        testo_lunedi] if x)
    return html, testo
