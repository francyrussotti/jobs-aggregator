# Jobs Aggregator

Legge ogni giorno da Gmail (solo lettura) le tre newsletter di offerte
— **Big4 Jobs**, **Paris Jobs**, **Aziende Target** — le porta in un formato
comune, toglie i doppioni, le filtra e invia un'unica email con due sezioni:
**Match** e **Da controllare**. Nessun punteggio, nessun ordinamento per
rilevanza: l'ordine è sempre fonte → azienda → ruolo.

I repository che generano le newsletter non vengono toccati: questo progetto
legge solo le email e, il lunedì, alcuni file pubblici di
`aziende-target-jobs-newsletter` (sola lettura via HTTPS).

## Cosa produce

| File | Contenuto |
|---|---|
| email | Match + Da controllare (azienda, ruolo, sede, link, fonte); il lunedì anche 10 aziende target senza annunci aperti con 2-3 titoli da cercare su LinkedIn |
| `output/jobs_YYYY-MM-DD.csv` | `data, azienda, ruolo, sede, link, fonte, sezione` (per il tracker) |
| `output/excluded_log.csv` | ogni offerta scartata con il motivo |
| `output/log_YYYY-MM-DD.txt` | log della run, compresi gli avvisi che le newsletter stesse riportano (fonti rotte, offerte tagliate) |

I due CSV sono allegati all'email e restano 30 giorni tra gli artifact della
run su GitHub Actions. Il repo è pubblico, quindi i dati non vengono mai
salvati nel repository.

## Regole

Tutte in [`config.yaml`](config.yaml): sedi ammesse, sedi vicine, parole che
includono (ambiti) ed escludono (stage, senior/manager, tecnici, sales puri,
aree non cercate). Ogni offerta finisce in uno di tre stati:

- **Match**: sede ammessa, ambito cercato nel titolo, nessuna esclusione.
- **Da controllare**: casi dubbi, sempre con il motivo (sede solo "Italia" o
  "Paesi Bassi", comune vicino come Amstelveen, titolo generico "Consultant",
  manager in un ambito cercato, Parigi con francese richiesto, annuncio vecchio…).
- **Escluso**: con il motivo, in `excluded_log.csv`.

Doppioni: stessa azienda + ruolo + sede nello stesso giorno; vince la fonte che
viene prima in `config.yaml`.

## Configurazione (una volta)

Secret del repository (Settings → Secrets and variables → Actions):

| Secret | Cos'è |
|---|---|
| `GMAIL_CLIENT_ID`, `GMAIL_CLIENT_SECRET`, `GMAIL_REFRESH_TOKEN` | accesso Gmail **in sola lettura** all'account che riceve le newsletter: vedi `scripts/ottieni_refresh_token.py` |
| `GMAIL_MITTENTE`, `GMAIL_PASSWORD` | account che invia l'email finale (App Password Gmail, come le altre newsletter) |

## Esecuzione

- Automatica: `.github/workflows/daily.yml` parte alle 13:37, 15:37 e 18:07 UTC.
  Se manca una newsletter aspetta la run successiva; dalle 18 UTC invia comunque,
  indicando quale manca. Una sola email al giorno.
- A mano: Actions → "Jobs Aggregator" → Run workflow (opzione "forza").
- In locale:

```bash
pip install -r requirements.txt
python -m aggregator.main --no-email                          # oggi, senza inviare
python -m aggregator.main --data 2026-11-04 --giorni 7 --no-email   # ultimi 7 giorni
python -m aggregator.main --cartella email_salvate/ --giorni 7 --no-email
python -m unittest -v tests.test_aggregator
```

`--cartella` legge email salvate in JSON (`{id, date, subject, html, text}`)
invece di Gmail.
