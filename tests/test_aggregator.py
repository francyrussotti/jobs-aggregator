import unittest

from aggregator.filters import CONTROLLARE, ESCLUSO, MATCH, Filtro, deduplica
from aggregator.main import carica_config
from aggregator.models import Email, Offerta
from aggregator.parsers import parse_aziende_target, parse_big4, parse_paris
from aggregator.gmail_reader import LettoreGmail
from aggregator.weekly import chiave_fonte

CFG = carica_config()

# Estratti della struttura reale delle newsletter (novembre 2026)
BIG4 = """
<tr><td id="f-ntt-data-italia" style="padding:28px 32px 0;"><table><tr><td style="padding:0 0 10px;">
<table><tr><td style="font-size:13px;"><span style="display:inline-block;width:10px;height:10px;
background:#FF0033;"></span>NTT DATA Italia</td><td align="right">1 nuova</td></tr></table></td></tr>
<tr><td style="padding:14px 0;"><a href="https://careers.example/net-developer" style="font-family:Georgia;font-size:18px;
line-height:1.35;">.NET Developer</a><div style="margin-top:6px;"><strong style="color:#111827;">NTT DATA Italia · Milano</strong>
&nbsp;·&nbsp; 2 giorni fa</div></td></tr></table></td></tr>
<tr><td id="f-deloitte-paesi-bassi"><table><tr><td><table><tr><td><span style="width:10px;"></span>Deloitte Paesi Bassi</td>
<td>1 nuova</td></tr></table></td></tr><tr><td><a href="https://werkenbijdeloitte.nl/x" style="font-size:18px;">Consultant</a>
<div><strong>Deloitte Paesi Bassi</strong> · oggi</div></td></tr></table></td></tr>"""

PARIS = """PARIS JOB NEWSLETTER — 4 novembre 2026

ATTENZIONE - fonti con problemi oggi:
- Welcome to the Jungle: 0 annunci oggi (di solito ~14).

== Ashby (1) ==
- Dust — User Researcher [ruolo target]
  Paris · 2026-11-03
  https://jobs.ashbyhq.com/dust/1

== Portfolio VC (1) ==
- Revolut (via Balderton) — Operations Manager (Banking)
  Paris, France · 2021-12-08
  https://www.revolut.com/x
"""

TARGET = """
<tr><td id="s-IT" style="font-size:13px;">Italia <span>· 1</span></td></tr>
<tr><td style="padding:18px 32px 0;">
<div style="font-family:sans-serif;font-size:15px;font-weight:700;color:#111827;">Thales</div>
<div style="font-size:11px;">open innovation · sede Parigi</div><table>
<tr><td><a href="https://thales.example/R1" style="font-family:Georgia;font-size:16px;line-height:1.35;">Maintenance Technician</a>
<div style="margin-top:3px;font-size:12px;">Firenze &nbsp;·&nbsp; oggi</div></td></tr></table></td></tr>
<tr><td id="s-PAR">Parigi</td></tr><tr><td>
<div style="font-size:15px;font-weight:700;">Utac France</div><table>
<tr><td><a href="https://utac.example/1" style="font-size:16px;">Head of Digital Mobility</a>
<div>TBD, , France &nbsp;·&nbsp; ieri &nbsp;·&nbsp; <span style="padding:0 6px;">Manager</span></div></td></tr>
<tr><td style="padding:6px 0 6px 12px;font-size:12px;">+ altre 3 offerte</td></tr></table></td></tr>"""


def offerta(ruolo, sede="Milano", fonte="Big4 Jobs", azienda="EY", **kw):
    return Offerta(data="2026-11-04", azienda=azienda, ruolo=ruolo, sede=sede, link="https://x",
                   fonte=fonte, **kw)


class TestParser(unittest.TestCase):
    def test_big4(self):
        r = parse_big4(Email("1", "2026-11-04", "Big4 Jobs", "Big4 Jobs — 2 nuove", html=BIG4))
        self.assertEqual(len(r.offerte), 2)
        o = r.offerte[0]
        self.assertEqual((o.azienda, o.ruolo, o.sede), ("NTT DATA", ".NET Developer", "Milano"))
        self.assertEqual(r.offerte[1].sede, "Paesi Bassi")     # niente città: resta il paese

    def test_paris(self):
        r = parse_paris(Email("2", "2026-11-04", "Paris Jobs", "Paris Jobs", testo=PARIS))
        self.assertEqual([(o.azienda, o.ruolo) for o in r.offerte],
                         [("Dust", "User Researcher"), ("Revolut", "Operations Manager (Banking)")])
        self.assertEqual(r.offerte[0].pubblicata, "2026-11-03")
        self.assertEqual(r.offerte[0].link, "https://jobs.ashbyhq.com/dust/1")
        self.assertIn("Welcome to the Jungle", r.avvisi[0])

    def test_aziende_target(self):
        r = parse_aziende_target(Email("3", "2026-11-04", "Aziende Target", "x", html=TARGET))
        self.assertEqual([(o.azienda, o.ruolo, o.sede, o.sottofonte) for o in r.offerte],
                         [("Thales", "Maintenance Technician", "Firenze", "IT"),
                          ("Utac France", "Head of Digital Mobility", "TBD, , France", "PAR")])
        self.assertEqual(r.offerte[1].etichette, ["Manager"])
        self.assertTrue(any("altre 3" in a for a in r.avvisi))


class TestFiltro(unittest.TestCase):
    f = Filtro(CFG)

    def esito(self, *a, **kw):
        o = self.f.valuta(offerta(*a, **kw))
        return o.sezione, o.motivo

    def test_match(self):
        for ruolo, sede in [("Junior EU Consultant - Space Technology", "Diegem"),
                            ("Consulente Finanza Agevolata", "Roma"),
                            ("Business Developer Open Innovation", "Torino"),
                            ("Platform Manager", "Paris, France"),
                            ("Energy Transition Analyst", "Amsterdam")]:
            self.assertEqual(self.esito(ruolo, sede)[0], MATCH, ruolo)

    def test_esclusi(self):
        casi = {"Innovation Intern": "stage", "Tesi - Innovazione": "stage",
                "Senior Innovation Consultant": "senior", "Head of Partnerships": "senior",
                "Junior Developer": "tecnico", "Cybersecurity Analyst": "tecnico",
                "Account Executive - SMB": "sales", "SDR Italy": "sales", "N/D": "vuoto",
                "Audit Associate": "area non cercata", "Product Designer": "nessun ambito"}
        for ruolo, atteso in casi.items():
            sez, motivo = self.esito(ruolo)
            self.assertEqual(sez, ESCLUSO, ruolo)
            self.assertIn(atteso, motivo, ruolo)

    def test_sedi(self):
        self.assertIn("fuori elenco", self.esito("Innovation Consultant", "Dublin")[1])
        self.assertEqual(self.esito("Innovation Consultant", "Amstelveen")[0], CONTROLLARE)
        self.assertEqual(self.esito("Innovation Consultant", "Paesi Bassi")[0], CONTROLLARE)
        self.assertEqual(self.esito("Innovation Consultant", "Remote, France")[0], CONTROLLARE)
        self.assertEqual(self.esito("Innovation Consultant", "Sedi: 5")[0], CONTROLLARE)
        self.assertIn("fuori elenco", self.esito("Innovation Consultant", "Remote Ireland")[1])
        self.assertEqual(self.esito("Innovation Consultant", "Le Plessis Robinson")[0], CONTROLLARE)

    def test_dubbi(self):
        self.assertEqual(self.esito("Strategy Consultant", "Milano")[0], CONTROLLARE)
        self.assertEqual(self.esito("EU Funding Project Manager", "Roma")[0], CONTROLLARE)
        self.assertEqual(self.esito("Junior Consultant CFO Services", "Diegem")[0], CONTROLLARE)
        o = self.f.valuta(offerta("Innovation Analyst", "Paris", fonte="Aziende Target",
                                  etichette=["francese fluente"]))
        self.assertEqual(o.sezione, CONTROLLARE)
        o = self.f.valuta(offerta("Startup Partnerships Associate", "Paris", pubblicata="2021-12-08"))
        self.assertIn("vecchio", o.motivo)


class TestDedup(unittest.TestCase):
    def test_vince_la_prima_fonte(self):
        f = Filtro(CFG)
        a = f.valuta(offerta("Innovation Consultant", "Milano, IT", fonte="Aziende Target"))
        b = f.valuta(offerta("Innovation  consultant", "Milano", fonte="Big4 Jobs"))
        uniche, doppi = deduplica([a, b], ["Big4 Jobs", "Paris Jobs", "Aziende Target"])
        self.assertEqual([o.fonte for o in uniche], ["Big4 Jobs"])
        self.assertIn("duplicato", doppi[0].motivo)


class TestLunedi(unittest.TestCase):
    def test_chiave_fonte(self):
        self.assertEqual(chiave_fonte({"tipo": "lever", "slug": "novaspace"}), "lever:novaspace")
        self.assertEqual(chiave_fonte({"tipo": "workday",
                                       "url": "https://thales.wd3.myworkdayjobs.com/fr-FR/Careers"}),
                         "workday:thales.wd3.myworkdayjobs.com/Careers")


class ImapFinto:
    """Registra i comandi: niente rete, e si verifica che siano solo di lettura."""

    def __init__(self, grezzo):
        self.grezzo, self.comandi = grezzo, []

    def list(self):
        return "OK", [b'(\\HasNoChildren) "/" "INBOX"',
                      b'(\\All \\HasNoChildren) "/" "[Gmail]/Tutti i messaggi"']

    def select(self, cartella, readonly=False):
        self.comandi.append(("select", cartella, readonly))
        return "OK", [b"1"]

    def uid(self, comando, *args):
        self.comandi.append((comando,) + args)
        if comando == "SEARCH":
            return "OK", [b"42"]
        return "OK", [(b"42 (BODY[] {10}", self.grezzo), b")"]


class TestImap(unittest.TestCase):
    def test_sola_lettura(self):
        grezzo = (b"Subject: =?utf-8?q?Paris_Jobs_04/11?=\r\nDate: Wed, 04 Nov 2026 10:06:28 +0000\r\n"
                  b"MIME-Version: 1.0\r\nContent-Type: multipart/alternative; boundary=X\r\n\r\n"
                  b"--X\r\nContent-Type: text/plain; charset=utf-8\r\n\r\n" + PARIS.encode() +
                  b"\r\n--X\r\nContent-Type: text/html; charset=utf-8\r\n\r\n<p>x</p>\r\n--X--\r\n")
        imap = ImapFinto(grezzo)
        lettore = LettoreGmail(CFG, conn=imap)
        from datetime import date
        email = lettore.newsletter_del_giorno(CFG["newsletter"][1], date(2026, 11, 4))
        self.assertEqual(imap.comandi[0], ("select", '"[Gmail]/Tutti i messaggi"', True))
        self.assertEqual(imap.comandi[1][:2], ("SEARCH", "X-GM-RAW"))
        self.assertIn('subject:\\"Paris Jobs\\"', imap.comandi[1][2])
        self.assertEqual(imap.comandi[2], ("FETCH", b"42", "(BODY.PEEK[])"))
        self.assertTrue(all(c[0] in ("select", "SEARCH", "FETCH") for c in imap.comandi))
        self.assertEqual((email[0].data, email[0].oggetto), ("2026-11-04", "Paris Jobs 04/11"))
        self.assertEqual(len(parse_paris(email[0]).offerte), 2)


if __name__ == "__main__":
    unittest.main()
