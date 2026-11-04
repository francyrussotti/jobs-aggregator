"""Esecuzione: python -m aggregator.main [--data YYYY-MM-DD] [--giorni N] [--cartella DIR] [--no-email]

- senza opzioni: newsletter di oggi da Gmail, email inviata (una volta al giorno)
- --giorni N: rielabora gli N giorni che finiscono con --data (nessuna email)
- --cartella DIR: legge email salvate in JSON invece di Gmail
"""
import argparse
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import yaml

from . import report
from .filters import CONTROLLARE, ESCLUSO, MATCH, Filtro, deduplica
from .parsers import PARSER

RADICE = Path(__file__).resolve().parent.parent


def carica_config(percorso=None):
    with open(percorso or RADICE / "config.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)


def elabora_giorno(cfg, lettore, filtro, giorno, log):
    """→ (offerte valutate e deduplicate, doppioni, fonti mancanti)"""
    tutte, mancanti = [], []
    for voce in cfg["newsletter"]:
        email = lettore.newsletter_del_giorno(voce, giorno)
        if not email:
            mancanti.append(voce["fonte"])
            log(f"[{giorno}] {voce['fonte']}: newsletter non trovata")
            continue
        for e in email:
            esito = PARSER[voce["parser"]](e)
            log(f"[{giorno}] {voce['fonte']}: {len(esito.offerte)} offerte lette ({e.oggetto})")
            for a in esito.avvisi:
                log(f"[{giorno}]   avviso dalla fonte: {a}")
            tutte.extend(esito.offerte)
    for o in tutte:
        filtro.valuta(o)
    uniche, doppioni = deduplica(tutte, [v["fonte"] for v in cfg["newsletter"]])
    return uniche, doppioni, mancanti


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--data", help="giorno (YYYY-MM-DD), default oggi")
    ap.add_argument("--giorni", type=int, default=1)
    ap.add_argument("--cartella", help="email salvate in JSON (al posto di Gmail)")
    ap.add_argument("--uscita", default=str(RADICE / "output"))
    ap.add_argument("--no-email", action="store_true")
    ap.add_argument("--forza", action="store_true", help="invia anche se già inviata oggi")
    ap.add_argument("--config")
    args = ap.parse_args(argv)

    cfg = carica_config(args.config)
    fuso = cfg["fuso_orario"]
    oggi = date.fromisoformat(args.data) if args.data else datetime.now(ZoneInfo(fuso)).date()
    uscita = Path(args.uscita)
    uscita.mkdir(parents=True, exist_ok=True)
    righe_log = []

    def log(msg):
        print(msg)
        righe_log.append(msg)

    if args.cartella:
        from .gmail_reader import LettoreCartella
        lettore = LettoreCartella(args.cartella, fuso)
    else:
        from .gmail_reader import LettoreGmail
        lettore = LettoreGmail(fuso)

    invio = args.giorni == 1 and not args.no_email
    data_it = oggi.strftime("%d/%m/%Y")
    base_oggetto = f"{cfg['email']['oggetto']} {data_it}"
    if invio and not args.forza and lettore.gia_inviata(base_oggetto):
        log(f"Email di oggi ({data_it}) già inviata: niente da fare.")
        return 0

    filtro = Filtro(cfg)
    giorni = [oggi - timedelta(days=i) for i in range(args.giorni - 1, -1, -1)]
    valutate, escluse_log, mancanti_oggi = [], [], []
    for g in giorni:
        uniche, doppioni, mancanti = elabora_giorno(cfg, lettore, filtro, g, log)
        mancanti_oggi = mancanti
        ordinate = report.ordina(uniche, [v["fonte"] for v in cfg["newsletter"]])
        report.scrivi_csv(uscita / f"jobs_{g.isoformat()}.csv",
                          [o for o in ordinate if o.sezione != ESCLUSO], report.COLONNE_TRACKER)
        valutate.extend(uniche)
        escluse_log.extend([o for o in uniche if o.sezione == ESCLUSO] + doppioni)

    ordine = [v["fonte"] for v in cfg["newsletter"]]
    escluse_log = report.ordina(escluse_log, ordine)
    report.scrivi_csv(uscita / "excluded_log.csv", escluse_log, report.COLONNE_ESCLUSE)

    match = report.ordina([o for o in valutate if o.sezione == MATCH], ordine)
    controllare = report.ordina([o for o in valutate if o.sezione == CONTROLLARE], ordine)
    log(f"Totale: {len(valutate) + len(escluse_log) - sum(1 for o in valutate if o.sezione == ESCLUSO)}"
        f" offerte lette · {len(match)} match · {len(controllare)} da controllare · "
        f"{len(escluse_log)} escluse (di cui {sum(1 for o in escluse_log if o.motivo.startswith('duplicato'))} doppioni)")

    if invio and mancanti_oggi and not args.forza:
        limite = cfg["attesa"]["invia_comunque_dopo_ora_utc"]
        if datetime.now(timezone.utc).hour < limite:
            log(f"Mancano {', '.join(mancanti_oggi)}: aspetto la prossima run (invio comunque "
                f"dalle {limite}:00 UTC).")
            (uscita / f"log_{oggi.isoformat()}.txt").write_text("\n".join(righe_log), encoding="utf-8")
            return 0

    lunedi = None
    if oggi.weekday() == 0 and cfg.get("lunedi", {}).get("attivo") and args.giorni == 1:
        from . import weekly
        try:
            scelte = weekly.aziende_senza_annunci(cfg, oggi.isocalendar()[1])
            lunedi = weekly.componi(scelte)
            log(f"Riepilogo del lunedì: {len(scelte)} aziende")
        except Exception as e:   # il riepilogo non deve bloccare l'email del giorno
            log(f"Riepilogo del lunedì non disponibile: {e}")

    titolo_giorno = data_it if args.giorni == 1 else \
        f"{giorni[0].strftime('%d/%m')}–{data_it} ({args.giorni} giorni)"
    html, testo = report.componi_email(titolo_giorno, match, controllare, len(escluse_log),
                                       mancanti_oggi if args.giorni == 1 else [], lunedi)
    (uscita / f"email_{oggi.isoformat()}.html").write_text(html, encoding="utf-8")
    (uscita / f"log_{oggi.isoformat()}.txt").write_text("\n".join(righe_log), encoding="utf-8")

    if invio:
        from .mailer import invia
        oggetto = f"{base_oggetto} — {len(match)} match, {len(controllare)} da controllare"
        allegati = [uscita / f"jobs_{oggi.isoformat()}.csv", uscita / "excluded_log.csv"] \
            if cfg["email"].get("allega_csv") else []
        invia(cfg, oggetto, html, testo, allegati)
        log(f"Email inviata: {oggetto}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
