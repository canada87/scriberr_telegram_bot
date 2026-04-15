# CLAUDE.md

## Architettura

Il processo è unico: `main.py` avvia Flask in un thread daemon e il bot Telegram nel thread principale tramite asyncio (`run_polling()` blocca).

```
main.py
├── thread daemon  →  web.py  (Flask, porta WEB_PORT)
└── main thread    →  bot.py  (asyncio, python-telegram-bot)
                       └── db.py  (SQLite, condiviso tra i due thread)
```

## File chiave

| File | Ruolo |
|------|-------|
| `main.py` | Entry point, avvio parallelo bot + web |
| `bot.py` | Handler Telegram: download audio → servizio STT → risposta + log |
| `db.py` | Audit log su SQLite. Connessioni aperte e chiuse per operazione (`check_same_thread=False`) |
| `web.py` | Flask: `GET /` (HTML), `POST /api/service`, `GET /api/logs`, `GET /api/stats` |
| `services/scriberr.py` | Upload → job_id → polling status endpoint |
| `services/parakeet.py` | Upload in thread separato (timeout 5s atteso) → polling `/status` globale |
| `templates/index.html` | Dashboard Bootstrap 5 dark, Jinja2 |

## Selezione del servizio

Il servizio attivo è salvato nella tabella `settings` del DB (chiave `service`). Viene inizializzato al primo avvio dal valore di `TRANSCRIPTION_SERVICE` nel `.env`, ma può essere cambiato a runtime senza restart:

- **Web UI**: toggle Scriberr/Parakeet nell'header → `POST /api/service`
- **Telegram**: `/servizio` (mostra attivo), `/servizio scriberr` o `/servizio parakeet` (cambia)

La lettura avviene a ogni trascrizione (`db.get_setting("service")` in `audio_handler`).

## Parakeet — comportamento non ovvio

- L'upload va in un thread separato con `timeout=5`: il proxy risponde 504 prima del completamento, ma il job è già avviato — questo è il comportamento atteso.
- Il polling usa un singolo endpoint `/status` globale (non per-job). La condizione di fine è: `status=="idle"` **e** `job_id` assente **e** `job_seen==True` (per non uscire prima che il job parta).
- SSL self-signed: `verify=False` + `urllib3.disable_warnings`.

## Database

Tabella `transcriptions` in `data/audit.db`. Non salva il testo trascritto — solo metadati: timestamp, user_id, username, full_name, chat_id, chat_title, audio_duration, service, status, processing_time, error_message.

## Dipendenze

`python-telegram-bot`, `requests`, `flask`, `python-dotenv`. Nessuna altra dipendenza necessaria.
