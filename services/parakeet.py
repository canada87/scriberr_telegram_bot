import io
import logging
import os
import threading
import time

import requests
import urllib3

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

PARAKEET_URL = os.environ.get("PARAKEET_URL", "").rstrip("/")
PARAKEET_MODEL = os.environ.get("PARAKEET_MODEL", "istupakov/parakeet-tdt-0.6b-v3-onnx")

POLL_INTERVAL = 3
TIMEOUT = 600

_MIME_MAP = {
    ".ogg": "audio/ogg",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
}


def _get_mime(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    return _MIME_MAP.get(ext, "application/octet-stream")


def transcribe(file_bytes: bytes, filename: str = "audio.ogg") -> str:
    """Invia l'audio a Parakeet e restituisce il testo trascritto."""
    if not PARAKEET_URL:
        raise EnvironmentError("PARAKEET_URL deve essere configurato nel .env")

    mime = _get_mime(filename)
    upload_response = [None]
    upload_done = threading.Event()

    def _upload():
        try:
            resp = requests.post(
                f"{PARAKEET_URL}/v1/audio/transcriptions",
                files={"file": (filename, io.BytesIO(file_bytes), mime)},
                data={"model": PARAKEET_MODEL, "response_format": "verbose_json"},
                verify=False,
                # connect timeout 10s, read timeout = TIMEOUT: per audio brevi/medi il
                # server risponde direttamente senza bisogno del polling
                timeout=(10, TIMEOUT),
            )
            if resp.ok:
                upload_response[0] = resp
                logger.debug("Parakeet POST response: %s", resp.text[:200])
        except requests.exceptions.Timeout:
            logger.debug("Parakeet POST timeout (atteso se il proxy chiude la connessione)")
        except Exception as exc:
            logger.warning("Parakeet POST error: %s", exc)
        finally:
            upload_done.set()

    # Avvia upload in background e inizia subito il polling (come AudioVault).
    # Non aspettiamo upload_done: il ritardo extra (timeout + poll_interval)
    # farebbe perdere i job che finiscono prima del primo poll.
    threading.Thread(target=_upload, daemon=True).start()

    start = time.time()
    final_text = ""
    job_seen = False

    while True:
        if time.time() - start > TIMEOUT:
            raise TimeoutError(f"Parakeet: timeout dopo {TIMEOUT}s")

        time.sleep(POLL_INTERVAL)

        # Fast path: se l'upload è già tornato con il testo (server risponde direttamente)
        if upload_response[0] is not None:
            try:
                text = upload_response[0].json().get("text", "")
                if text:
                    logger.info("Parakeet: trascrizione dalla risposta POST diretta")
                    return text
            except Exception:
                pass

        try:
            resp = requests.get(f"{PARAKEET_URL}/status", verify=False, timeout=10)
            data = resp.json()
        except Exception as e:
            logger.warning("Parakeet polling error: %s", e)
            continue

        job_id = data.get("job_id", "")
        partial = data.get("partial_text", "")
        status = data.get("status", "")

        logger.debug(
            "Parakeet /status: status=%r job_id=%r partial_len=%d chunk=%s/%s",
            status, job_id, len(partial),
            data.get("current_chunk"), data.get("total_chunks"),
        )

        if job_id:
            job_seen = True

        # Teniamo il testo più lungo visto finora
        if partial and len(partial) >= len(final_text):
            final_text = partial

        # Server idle senza job e senza averlo mai visto: upload ancora in corso
        if status == "idle" and not job_id and not job_seen:
            continue

        # Job completato: server tornato idle dopo che il job era visibile
        if status == "idle" and not job_id and job_seen:
            break

    # Grace-period poll: il server potrebbe ancora svuotare il partial_text
    # dell'ultimo chunk proprio mentre transisce a idle
    time.sleep(min(POLL_INTERVAL, 2))
    try:
        resp = requests.get(f"{PARAKEET_URL}/status", verify=False, timeout=10)
        data = resp.json()
        partial = data.get("partial_text", "")
        if partial and len(partial) > len(final_text):
            logger.debug("Parakeet grace-period: recuperati %d caratteri", len(partial))
            final_text = partial
    except Exception:
        pass

    if not final_text:
        # Fallback: attende che l'upload thread finisca e usa la risposta POST
        remaining = max(0, TIMEOUT - (time.time() - start))
        logger.info("Parakeet: partial_text vuoto, attendo risposta POST (%.0fs rimasti)", remaining)
        upload_done.wait(timeout=remaining)
        if upload_response[0] is not None:
            try:
                text = upload_response[0].json().get("text", "")
                if text:
                    logger.info("Parakeet: testo recuperato dalla risposta POST (fallback)")
                    return text
            except Exception:
                pass
        raise ValueError("Parakeet: job completato ma nessun testo restituito")

    return final_text
