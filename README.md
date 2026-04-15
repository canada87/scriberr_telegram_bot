# Transcription Bot

Telegram bot che riceve messaggi audio/voice e li trascrive tramite un servizio STT (Scriberr o Parakeet). Include una web UI per l'audit log delle trascrizioni.

## Funzionamento

1. Un utente invia un audio nella chat Telegram
2. Il bot scarica il file, lo manda al servizio STT configurato e aspetta la trascrizione
3. La trascrizione viene postata nella stessa chat come risposta
4. Ogni chiamata viene registrata nel database per audit (nessun testo salvato, solo metadati)

## Servizi supportati

| Servizio | Auth | Note |
|----------|------|-------|
| **Scriberr** | API key | polling su job ID |
| **Parakeet** | nessuna | self-hosted, SSL self-signed, polling `/status` globale |

## Configurazione

Copia e adatta il file `.env`:

```env
TELEGRAM_BOT_TOKEN=...

# Scriberr
SCRIBERR_API_KEY=...
SCRIBERR_BASE_URL=https://scriberr.example.com/

# Parakeet
PARAKEET_URL=https://parakeet.example.com
# PARAKEET_MODEL=istupakov/parakeet-tdt-0.6b-v3-onnx   # opzionale

# Servizio attivo
TRANSCRIPTION_SERVICE=scriberr   # oppure: parakeet

# Web UI
WEB_PORT=8080
DB_PATH=data/audit.db
```

## Deploy con Docker (raccomandato)

```bash
docker compose up --build -d
```

Il database SQLite è persistito nel volume `bot_data` (`/app/data` nel container).

La web UI è disponibile su `http://server:8080`.

## Avvio locale

```bash
pip install -r requirements.txt
python main.py
```

## Comandi Telegram

| Comando | Descrizione |
|---------|-------------|
| _(audio / voice message)_ | Avvia la trascrizione con il servizio attivo |
| `/servizio` | Mostra il servizio attualmente attivo |
| `/servizio scriberr` | Imposta Scriberr come servizio attivo |
| `/servizio parakeet` | Imposta Parakeet come servizio attivo |

Il servizio può essere cambiato anche dalla web UI senza riavviare il bot.

## Web UI

Dashboard di audit accessibile via browser. Mostra per ogni trascrizione:
- Timestamp
- Utente Telegram (nome + username)
- Chat
- Durata audio
- Servizio usato
- Stato (ok / errore)
- Tempo di elaborazione

Auto-refresh ogni 30 secondi. Paginazione da 50 righe.
