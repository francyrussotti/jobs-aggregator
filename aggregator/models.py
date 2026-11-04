from dataclasses import dataclass, field


@dataclass
class Offerta:
    """Formato comune a tutte le fonti."""
    data: str            # giorno della newsletter (YYYY-MM-DD)
    azienda: str
    ruolo: str
    sede: str
    link: str
    fonte: str           # Big4 Jobs / Paris Jobs / Aziende Target
    # Dettagli utili al filtro, non esportati nel CSV del tracker
    pubblicata: str = ""     # data di pubblicazione dichiarata dalla fonte, se c'è
    etichette: list = field(default_factory=list)   # es. "francese fluente" (Aziende Target)
    sottofonte: str = ""     # es. "Deloitte Paesi Bassi", "Greenhouse", "IT"
    # Esito del filtro
    sezione: str = ""        # Match / Da controllare / Escluso
    motivo: str = ""
    citta: str = ""          # sede ammessa riconosciuta (es. "Milano")


@dataclass
class Email:
    """Una newsletter ricevuta."""
    id: str
    data: str            # YYYY-MM-DD (fuso orario italiano)
    fonte: str
    oggetto: str
    html: str = ""
    testo: str = ""


@dataclass
class EsitoParsing:
    offerte: list
    avvisi: list         # problemi segnalati dalla newsletter stessa (solo log)
