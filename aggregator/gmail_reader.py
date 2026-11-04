"""Lettura delle newsletter da Gmail, SOLO LETTURA (scope gmail.readonly).

Credenziali dalle variabili d'ambiente (secret di GitHub):
  GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN
Il refresh token si ottiene una volta sola con scripts/ottieni_refresh_token.py.
"""
import base64
import json
import os
from datetime import datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from .models import Email

SCOPE = "https://www.googleapis.com/auth/gmail.readonly"


def _servizio():
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    mancanti = [k for k in ("GMAIL_CLIENT_ID", "GMAIL_CLIENT_SECRET", "GMAIL_REFRESH_TOKEN")
                if not os.environ.get(k, "").strip()]
    if mancanti:
        raise RuntimeError("Credenziali Gmail mancanti: " + ", ".join(mancanti))
    cred = Credentials(
        token=None, refresh_token=os.environ["GMAIL_REFRESH_TOKEN"].strip(),
        client_id=os.environ["GMAIL_CLIENT_ID"].strip(),
        client_secret=os.environ["GMAIL_CLIENT_SECRET"].strip(),
        token_uri="https://oauth2.googleapis.com/token", scopes=[SCOPE])
    return build("gmail", "v1", credentials=cred, cache_discovery=False)


def _decodifica(dati):
    return base64.urlsafe_b64decode(dati + "=" * (-len(dati) % 4)).decode("utf-8", "replace")


def _corpi(payload):
    """→ (html, testo) cercando nelle parti MIME."""
    html, testo = "", ""
    pila = [payload]
    while pila:
        p = pila.pop()
        pila.extend(p.get("parts") or [])
        dati = (p.get("body") or {}).get("data")
        if not dati:
            continue
        if p.get("mimeType") == "text/html" and not html:
            html = _decodifica(dati)
        elif p.get("mimeType") == "text/plain" and not testo:
            testo = _decodifica(dati)
    return html, testo


def limiti_giorno(giorno, fuso):
    tz = ZoneInfo(fuso)
    inizio = datetime.combine(giorno, time.min, tz)
    return int(inizio.timestamp()), int((inizio + timedelta(days=1)).timestamp())


class LettoreGmail:
    def __init__(self, fuso):
        self.fuso = fuso
        self.svc = _servizio()

    def cerca(self, query, giorno):
        dopo, prima = limiti_giorno(giorno, self.fuso)
        q = f"{query} after:{dopo} before:{prima}"
        res = self.svc.users().messages().list(userId="me", q=q, maxResults=20).execute()
        return [m["id"] for m in res.get("messages", [])]

    def leggi(self, msg_id, fonte):
        m = self.svc.users().messages().get(userId="me", id=msg_id, format="full").execute()
        intestazioni = {h["name"].lower(): h["value"] for h in m["payload"].get("headers", [])}
        html, testo = _corpi(m["payload"])
        quando = datetime.fromtimestamp(int(m["internalDate"]) / 1000, ZoneInfo(self.fuso))
        return Email(id=m["id"], data=quando.date().isoformat(), fonte=fonte,
                     oggetto=intestazioni.get("subject", ""), html=html, testo=testo)

    def newsletter_del_giorno(self, voce, giorno):
        """Le email di una newsletter in un giorno (di solito una)."""
        return [self.leggi(i, voce["fonte"]) for i in self.cerca(voce["query"], giorno)]

    def gia_inviata(self, oggetto):
        res = self.svc.users().messages().list(userId="me", q=f'subject:"{oggetto}"',
                                               maxResults=1).execute()
        return bool(res.get("messages"))


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
        parola = voce["query"].split('subject:"', 1)[1].split('"', 1)[0]
        return [Email(id=d["id"], data=g, fonte=voce["fonte"], oggetto=d["subject"],
                      html=d.get("html", ""), testo=d.get("text", ""))
                for g, d in self.email
                if g == giorno.isoformat() and parola in d["subject"]
                and "riepilogo" not in d["subject"].lower()]

    def gia_inviata(self, oggetto):
        return False
