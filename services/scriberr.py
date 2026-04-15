import io
import json
import os
import time

import requests

SCRIBERR_API_KEY = os.environ.get("SCRIBERR_API_KEY", "")
SCRIBERR_BASE_URL = os.environ.get("SCRIBERR_BASE_URL", "").rstrip("/")

_QUICK_ENDPOINT = f"{SCRIBERR_BASE_URL}/api/v1/transcription/quick"
_STATUS_ENDPOINT = f"{SCRIBERR_BASE_URL}/api/v1/transcription/quick/{{id}}"

POLL_INTERVAL = 5
TIMEOUT = 600


def transcribe(file_bytes: bytes, filename: str = "audio.ogg") -> str:
    """Invia l'audio a Scriberr e restituisce il testo trascritto."""
    if not SCRIBERR_API_KEY or not SCRIBERR_BASE_URL:
        raise EnvironmentError(
            "SCRIBERR_API_KEY e SCRIBERR_BASE_URL devono essere configurati nel .env"
        )

    headers = {"X-API-Key": SCRIBERR_API_KEY}
    files = {"audio": (filename, io.BytesIO(file_bytes))}
    resp = requests.post(_QUICK_ENDPOINT, headers=headers, files=files, timeout=60)
    resp.raise_for_status()

    job_id = resp.json().get("id")
    if not job_id:
        raise ValueError(f"Scriberr non ha restituito un job_id. Risposta: {resp.text}")

    return _poll(job_id, headers)


def _poll(job_id: str, headers: dict) -> str:
    url = _STATUS_ENDPOINT.format(id=job_id)
    start = time.time()
    while True:
        resp = requests.get(url, headers=headers, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        transcript = data.get("transcript")
        if transcript and transcript.strip():
            return json.loads(transcript)["text"]
        if time.time() - start > TIMEOUT:
            raise TimeoutError(f"Scriberr: timeout dopo {TIMEOUT}s")
        time.sleep(POLL_INTERVAL)
