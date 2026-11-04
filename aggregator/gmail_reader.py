"""Lettura delle newsletter da Gmail via IMAP con una App Password.

Solo lettura: la cartella si apre in modalità read-only (EXAMINE) e i messaggi
si scaricano con BODY.PEEK, quindi non cambia nulla nella casella (nemmeno lo
stato "letto"). Le ricerche usano la sintassi di Gmail (estensione X-GM-RAW).

Variabile d'ambiente (secret di GitHub): GMAIL_LETTURA_PASSWORD
L'account è in config.yaml (lettura.account).
"""
import email
import imaplib
import json
import os
import re
from datetime import datetime, time, timedelta
from email.policy import default as POLICY
from email.utils import parsedate_to_datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Email


def limiti_giorno(giorno, fuso):
    inizio = datetime.combine(giorno, time.min, ZoneInfo(fuso))
    return int(inizio.timestamp()), int((inizio + timedelta(days=1)).timestamp())


def corpi(msg):
    """→ (html, testo) da un messaggio email."""
    html, testo = "", ""
    for parte in msg.walk():
        if parte.get_content_maintype() == "multipart" or parte.get_filename():
            continue
        tipo = parte.get_content_type()
        if tipo == "text/html" and not html:
            html = parte.get_content()
        elif tipo == "text/plain" and not testo:
            testo = parte.get_content()
    return html, testo


def _cartella_tutti(conn):
    """La cartella "Tutti i messaggi" (nome diverso per lingua: si cerca il flag \\All)."""
    tipo, righe = conn.list()
    for r in righe or []:
        r = r.decode("utf-8", "replace")
        if "\\All" in r:
            return r.rsplit(' "/" ', 1)[-1].strip()
    return "INBOX"


class LettoreGmail:
    def __init__(self, cfg, conn=None):
        lettura = cfg["lettura"]
        self.fuso = cfg["fuso_orario"]
        if conn is None:
            password = "".join(os.environ.get("GMAIL_LETTURA_PASSWORD", "").split())
            if not password:
                raise RuntimeError("Secret GMAIL_LETTURA_PASSWORD mancante")
            conn = imaplib.IMAP4_SSL(lettura.get("imap_host", "imap.gmail.com"))
            conn.login(lettura["account"], password)
        self.conn = conn
        stato, _ = self.conn.select(_cartella_tutti(self.conn), readonly=True)
        if stato != "OK":
            raise RuntimeError("Impossibile aprire la casella in sola lettura")

    def cerca(self, query):
        q = query.replace("\\", "\\\\").replace('"', '\\"')
        stato, dati = self.conn.uid("SEARCH", "X-GM-RAW", f'"{q}"')
        return dati[0].split() if stato == "OK" and dati and dati[0] else []

    def leggi(self, uid, fonte):
        stato, dati = self.conn.uid("FETCH", uid, "(BODY.PEEK[])")
        grezzo = next(p[1] for p in dati if isinstance(p, tuple))
        msg = email.message_from_bytes(grezzo, policy=POLICY)
        quando = parsedate_to_datetime(msg["Date"]).astimezone(ZoneInfo(self.fuso))
        html, testo = corpi(msg)
        return Email(id=uid.decode(), data=quando.date().isoformat(), fonte=fonte,
                     oggetto=str(msg["Subject"] or ""), html=html, testo=testo)

    def newsletter_del_giorno(self, voce, giorno):
        dopo, prima = limiti_giorno(giorno, self.fuso)
        uids = self.cerca(f"{voce['query']} after:{dopo} before:{prima}")
        return [self.leggi(u, voce["fonte"]) for u in uids]

    def gia_inviata(self, oggetto):
        return bool(self.cerca(f'subject:"{oggetto}"'))


class LettoreCartella:
    """Legge email salvate in JSON ({id, date, sender, subject, html, text}).
    Serve per i test e per rieseguire giorni passati senza Gmail."""

    def __init__(self, cartella, fuso):
        self.fuso = fuso
        self.email = []
        for f in sorted(Path(cartella).glob("*.json")):
            d = json.loads(f.read_text(encoding="utf-8"))
            quando = datetime.fromisoformat(d["date"].replace("Z", "+00:00"))
            self.email.append((quando.astimezone(ZoneInfo(fuso)).date().isoformat(), d))

    def newsletter_del_giorno(self, voce, giorno):
        parola = re.search(r'subject:"([^"]+)"', voce["query"]).group(1)
        return [Email(id=d["id"], data=g, fonte=voce["fonte"], oggetto=d["subject"],
                      html=d.get("html", ""), testo=d.get("text", ""))
                for g, d in self.email
                if g == giorno.isoformat() and parola in d["subject"]
                and "riepilogo" not in d["subject"].lower()]

    def gia_inviata(self, oggetto):
        return False
