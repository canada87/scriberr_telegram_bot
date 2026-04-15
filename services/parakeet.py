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
    upload_done = threading.Event()
    upload_response = [None]  # cattura la risposta se arriva entro il timeout

    def _upload():
        try:
            resp = requests.post(
                f"{PARAKEET_URL}/v1/audio/transcriptions",
                files={"file": (filename, io.BytesIO(file_bytes), mime)},
                data={"model": PARAKEET_MODEL, "response_format": "verbose_json"},
                verify=False,
                timeout=5,
            )
            if resp.ok:
                upload_response[0] = resp
        except requests.exceptions.Timeout:
            pass  # atteso per audio lunghi — il proxy chiude prima, il job è avviato
        except Exception:
            pass
        finally:
            upload_done.set()

    threading.Thread(target=_upload, daemon=True).start()
    upload_done.wait()

    # Fast path: audio breve → la trascrizione è già nella risposta dell'upload
    if upload_response[0] is not None:
        try:
            text = upload_response[0].json().get("text", "")
            if text:
                logger.info("Parakeet: trascrizione ottenuta dalla risposta diretta (audio breve)")
                return text
        except Exception:
            pass

    # Slow path: audio lungo → upload scaduto per timeout, si usa polling su /status
    start = time.time()
    final_text = ""
    job_seen = False

    while True:
        if time.time() - start > TIMEOUT:
            raise TimeoutError(f"Parakeet: timeout dopo {TIMEOUT}s")

        time.sleep(POLL_INTERVAL)

        try:
            resp = requests.get(f"{PARAKEET_URL}/status", verify=False, timeout=10)
            data = resp.json()
        except Exception as e:
            logger.warning("Parakeet polling error: %s", e)
            continue

        job_id = data.get("job_id", "")
        partial = data.get("partial_text", "")

        if job_id:
            job_seen = True
        if partial:
            final_text = partial

        if data.get("status") == "idle" and not job_id and job_seen:
            break

    if not final_text:
        raise ValueError("Parakeet: job completato ma nessun testo restituito")

    return final_text
