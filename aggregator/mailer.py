"""Invio dell'email finale via SMTP Gmail (App Password).

Mittente: GMAIL_MITTENTE + GMAIL_PASSWORD se impostati, altrimenti l'account di
lettura (config.yaml → lettura.account) con GMAIL_LETTURA_PASSWORD.
"""
import os
import smtplib
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path


def invia(cfg, oggetto, html, testo, allegati=()):
    mittente = os.environ.get("GMAIL_MITTENTE", "").strip()
    password = "".join(os.environ.get("GMAIL_PASSWORD", "").split())
    if not mittente or not password:
        # Senza un mittente dedicato si invia dall'account che legge (a se stessi)
        mittente = cfg["lettura"]["account"]
        password = "".join(os.environ.get("GMAIL_LETTURA_PASSWORD", "").split())
    if not password:
        raise RuntimeError("Nessuna password per l'invio (GMAIL_LETTURA_PASSWORD)")
    e = cfg["email"]
    msg = MIMEMultipart("mixed")
    msg["Subject"], msg["From"], msg["To"] = oggetto, mittente, e["destinatario"]
    corpo = MIMEMultipart("alternative")
    corpo.attach(MIMEText(testo, "plain", "utf-8"))
    corpo.attach(MIMEText(html, "html", "utf-8"))
    msg.attach(corpo)
    for p in allegati:
        parte = MIMEApplication(Path(p).read_bytes(), Name=Path(p).name)
        parte["Content-Disposition"] = f'attachment; filename="{Path(p).name}"'
        msg.attach(parte)
    with smtplib.SMTP_SSL(e["smtp_host"], e["smtp_porta"], timeout=60) as s:
        s.login(mittente, password)
        s.sendmail(mittente, [e["destinatario"]], msg.as_string())
