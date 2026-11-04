"""Da eseguire UNA volta sul tuo computer per ottenere il refresh token Gmail
in SOLA LETTURA (scope gmail.readonly).

1. Google Cloud Console → nuovo progetto → abilita "Gmail API".
2. Schermata consenso OAuth: tipo "Esterno", aggiungi il tuo indirizzo come
   utente di test, poi "Pubblica app" (In produzione): in modalità "Test" il
   token scade dopo 7 giorni.
3. Credenziali → Crea ID client OAuth → "App desktop" → scarica il JSON come
   client_secret.json nella stessa cartella di questo script.
4. pip install google-auth-oauthlib && python scripts/ottieni_refresh_token.py
5. Accedi con l'account che RICEVE le newsletter e copia i tre valori stampati
   nei secret del repo (GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN).
"""
import json
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow

SCOPE = ["https://www.googleapis.com/auth/gmail.readonly"]
file = Path(__file__).with_name("client_secret.json")
flow = InstalledAppFlow.from_client_secrets_file(str(file), SCOPE)
cred = flow.run_local_server(port=0, prompt="consent", access_type="offline")
dati = json.loads(file.read_text())["installed"]
print("\nGMAIL_CLIENT_ID     =", dati["client_id"])
print("GMAIL_CLIENT_SECRET =", dati["client_secret"])
print("GMAIL_REFRESH_TOKEN =", cred.refresh_token)
