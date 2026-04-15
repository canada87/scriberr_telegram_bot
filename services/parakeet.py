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

    def _upload():
        try:
            requests.post(
                f"{PARAKEET_URL}/v1/audio/transcriptions",
                files={"file": (filename, io.BytesIO(file_bytes), mime)},
                data={"model": PARAKEET_MODEL, "response_format": "verbose_json"},
                verify=False,
                timeout=5,  # timeout corto: il proxy chiude prima del completamento, è atteso
            )
        except Exception:
            pass  # 504 dal proxy è normale — il job è comunque avviato
        finally:
            upload_done.set()

    threading.Thread(target=_upload, daemon=True).start()
    upload_done.wait()

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
