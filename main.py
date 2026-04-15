import logging
import os
import threading

from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

from bot import run_bot
from web import app as flask_app


def _run_web():
    port = int(os.environ.get("WEB_PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port, use_reloader=False, threaded=True)


if __name__ == "__main__":
    web_thread = threading.Thread(target=_run_web, daemon=True, name="web")
    web_thread.start()
    run_bot()  # blocks — asyncio event loop runs here
