"""Filtro delle offerte: Match / Da controllare / Escluso, sempre con un motivo.

Nessun punteggio e nessun ordinamento: ogni regola dice solo se un'offerta
entra, esce o va controllata a mano. Le regole sono tutte in config.yaml.
"""
import re
import unicodedata
from datetime import date

MATCH, CONTROLLARE, ESCLUSO = "Match", "Da controllare", "Escluso"


def normalizza(testo):
    """Minuscolo, senza accenti, spazi compattati."""
    t = unicodedata.normalize("NFKD", testo or "")
    t = "".join(c for c in t if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", t.lower()).strip()


def _compila(lista):
    return re.compile("|".join(f"(?:{e})" for e in lista), re.I) if lista else None


def _trova(regex, testo):
    m = regex.search(testo) if regex else None
    return m.group(0).strip() if m else ""


class Filtro:
    def __init__(self, config):
        r = config["ruoli"]
        s = config["sedi"]
        self.vuoti = _compila(r["titoli_vuoti"])
        self.escludi = {motivo: _compila(lst) for motivo, lst in r["escludi"].items()}
        self.manager = re.compile(r["manager"], re.I)
        self.manager_ok = _compila(r["manager_ammessi"])
        self.manager_dubbi = _compila(r["manager_da_controllare"])
        self.includi = {ambito: _compila(lst) for ambito, lst in r["includi"].items()}
        self.non_pertinenti = _compila(r["aree_non_pertinenti"])
        self.generici = _compila(r["generici"])
        self.francese = _compila(r["titolo_francese"])
        self.citta = {c: _compila([rf"\b{re.escape(normalizza(a).replace('-', ' '))}\b" for a in alias])
                      for c, alias in s["ammesse"].items()}
        self.vicine = {c: _compila([rf"\b{re.escape(normalizza(a).replace('-', ' '))}\b" for a in alias])
                       for c, alias in (s.get("vicine") or {}).items()}
        self.paesi = [normalizza(p) for p in s["paesi_da_controllare"]]
        self.giorni_vecchio = config.get("giorni_annuncio_vecchio")

    # ---------------------------------------------------------------- sede
    def valuta_sede(self, sede):
        """→ (città ammessa | "", motivo esclusione | "", motivo dubbio | "")"""
        s = normalizza(sede).replace("-", " ")
        if not s:
            return "", "", "sede non indicata"
        if re.match(r"^(sedi:\s*\d+|\d+ locations?|multi ?locations?)$", s):
            return "", "", f"più sedi non elencate ({sede})"
        trovate = [c for c, rx in self.citta.items() if rx.search(s)]
        if trovate:
            return trovate[0], "", ""
        for c, rx in self.vicine.items():
            m = _trova(rx, s)
            if m:
                return "", "", f"sede vicina a {c} ({m})"
        # Solo paese / remoto / sede da definire in un paese di interesse
        pezzi = [p.strip() for p in re.split(r"[,;/()·|-]+", s) if p.strip()]
        parole = {w for x in self.paesi for w in x.split()}
        if pezzi and all(len(p) <= 2 or all(w in parole for w in p.split()) for p in pezzi):
            return "", "", f"sede non precisa ({sede})"
        return "", f"sede fuori elenco ({sede})", ""

    # --------------------------------------------------------------- ruolo
    def valuta(self, o):
        """Imposta o.sezione, o.motivo, o.citta e restituisce l'offerta."""
        titolo = normalizza(o.ruolo)
        if self.vuoti.search(titolo) or titolo in ("n/d", "nd"):
            return self._esito(o, ESCLUSO, ["titolo vuoto o N/D"])

        esclusioni, dubbi = [], []
        citta, fuori, dubbio_sede = self.valuta_sede(o.sede)
        o.citta = citta
        if fuori:
            esclusioni.append(fuori)
        if dubbio_sede:
            dubbi.append(dubbio_sede)

        ambiti = [a for a, rx in self.includi.items() if rx.search(titolo)]

        for motivo, rx in self.escludi.items():
            m = _trova(rx, titolo)
            if m:
                esclusioni.append(f"{motivo} («{m}»)")

        if self.manager.search(titolo) and not _trova(self.manager_ok, titolo):
            m = _trova(self.manager_dubbi, titolo)
            if m:
                dubbi.append(f"«{m}»: verificare il livello")
            elif ambiti:
                dubbi.append("ruolo manager in un ambito cercato: verificare il livello")
            else:
                esclusioni.append("ruolo manager")

        area = _trova(self.non_pertinenti, titolo)
        if ambiti:
            if area:
                dubbi.append(f"ambito {', '.join(ambiti)} ma area «{area}»")
        elif area:
            esclusioni.append(f"area non cercata («{area}»)")
        else:
            g = _trova(self.generici, titolo)
            if g:
                dubbi.append(f"titolo generico («{g}»): ambito non chiaro")
            else:
                esclusioni.append("nessun ambito cercato nel titolo")

        if citta == "Parigi":
            if any("francese" in normalizza(e) for e in o.etichette):
                dubbi.append("Parigi: l'annuncio chiede francese fluente")
            m = _trova(self.francese, titolo)
            if m:
                dubbi.append(f"Parigi: titolo in francese («{m}»)")

        if o.pubblicata and self.giorni_vecchio:
            try:
                eta = (date.fromisoformat(o.data) - date.fromisoformat(o.pubblicata[:10])).days
                if eta > self.giorni_vecchio:
                    dubbi.append(f"pubblicata il {o.pubblicata[:10]}: annuncio vecchio?")
            except ValueError:
                pass

        if esclusioni:
            return self._esito(o, ESCLUSO, esclusioni)
        if dubbi:
            return self._esito(o, CONTROLLARE, dubbi)
        return self._esito(o, MATCH, [f"ambito: {', '.join(ambiti)}"])

    @staticmethod
    def _esito(o, sezione, motivi):
        o.sezione = sezione
        o.motivo = "; ".join(motivi)
        return o


def chiave_dedup(o):
    """Azienda + ruolo + sede, normalizzati (la città riconosciuta vale come sede)."""
    az = re.sub(r"\b(spa|s\.p\.a\.|srl|sas|sa|bv|nv|ltd|inc|gmbh)\b", "", normalizza(o.azienda))
    ruolo = re.sub(r"[^a-z0-9]+", " ", normalizza(o.ruolo))
    sede = o.citta or re.sub(r"[^a-z0-9]+", " ", normalizza(o.sede))
    return (re.sub(r"[^a-z0-9]+", " ", az).strip(), ruolo.strip(), sede.strip())


def deduplica(offerte, ordine_fonti):
    """Tiene la prima per chiave, nell'ordine delle fonti di config.yaml.
    → (uniche, doppioni) dove i doppioni hanno già il motivo."""
    rango = {f: i for i, f in enumerate(ordine_fonti)}
    viste, uniche, doppioni = {}, [], []
    for o in sorted(offerte, key=lambda x: (x.data, rango.get(x.fonte, 99))):
        k = (o.data,) + chiave_dedup(o)
        if k in viste:
            o.sezione, o.motivo = ESCLUSO, f"duplicato (già presente da {viste[k].fonte})"
            doppioni.append(o)
        else:
            viste[k] = o
            uniche.append(o)
    return uniche, doppioni
