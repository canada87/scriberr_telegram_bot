import asyncio
import io
import logging
import os
import time

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, MessageHandler, filters

load_dotenv()

import db
from services import parakeet, scriberr

logger = logging.getLogger(__name__)

TELEGRAM_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]

# Coda dei job di trascrizione — processati uno alla volta dal worker
_queue: asyncio.Queue = asyncio.Queue()
_processing = False  # True mentre il worker sta elaborando un job


def _chat_name(chat) -> str | None:
    if chat is None:
        return None
    if chat.title:
        return chat.title
    parts = [chat.first_name, chat.last_name]
    return " ".join(p for p in parts if p) or None


async def _run_transcription(job: dict) -> None:
    """Esegue la trascrizione per un singolo job e risponde all'utente."""
    message = job["message"]
    active_service = job["service"]

    start_time = time.time()
    status = "error"
    error_message = None
    text = None

    try:
        if active_service == "parakeet":
            text = await asyncio.to_thread(
                parakeet.transcribe, job["file_bytes"], filename=job["filename"]
            )
        else:
            text = await asyncio.to_thread(
                scriberr.transcribe, job["file_bytes"], filename=job["filename"]
            )
        status = "success"
    except Exception as exc:
        logger.exception("Errore nella trascrizione")
        error_message = str(exc)

    processing_time = round(time.time() - start_time, 1)
    user = job["user"]
    chat = job["chat"]

    db.log_transcription(
        user_id=user.id if user else None,
        username=user.username if user else None,
        full_name=user.full_name if user else None,
        chat_id=chat.id if chat else None,
        chat_title=_chat_name(chat),
        audio_duration=job["audio_duration"],
        service=active_service,
        status=status,
        processing_time=processing_time,
        error_message=error_message,
    )

    if status == "success":
        await message.reply_text(f"📝 Trascrizione:\n\n{text}")
    else:
        await message.reply_text(f"❌ Errore: {error_message}")


async def _worker() -> None:
    """Processa i job dalla coda uno alla volta."""
    global _processing
    while True:
        job = await _queue.get()
        _processing = True
        try:
            await _run_transcription(job)
        except Exception:
            logger.exception("Errore imprevisto nel worker")
        finally:
            _processing = False
            _queue.task_done()


async def audio_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    tg_audio = message.voice or message.audio
    if not tg_audio:
        return

    user = message.from_user
    chat = message.chat

    tg_file = await context.bot.get_file(tg_audio.file_id)
    bio = io.BytesIO()
    await tg_file.download_to_memory(out=bio)
    bio.seek(0)

    # Legge posizione coda PRIMA di accodare (no await in mezzo → stato consistente)
    waiting = _queue.qsize()
    in_progress = _processing

    job = {
        "message": message,
        "file_bytes": bio.read(),
        "filename": getattr(tg_audio, "file_name", None) or "audio.ogg",
        "user": user,
        "chat": chat,
        "audio_duration": getattr(tg_audio, "duration", None),
        "service": db.get_setting("service", "scriberr"),
    }
    await _queue.put(job)

    if not in_progress and waiting == 0:
        await message.reply_text("🎧 Audio ricevuto, sto trascrivendo...")
    else:
        ahead = waiting + (1 if in_progress else 0)
        await message.reply_text(f"⏳ In coda — {ahead} audio davanti al tuo.")


async def servizio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        current = db.get_setting("service", "scriberr")
        queue_info = ""
        if _processing or _queue.qsize() > 0:
            total = _queue.qsize() + (1 if _processing else 0)
            queue_info = f"\n⏳ {total} audio in elaborazione/coda."
        await update.message.reply_text(
            f"Servizio attivo: *{current}*{queue_info}", parse_mode="Markdown"
        )
        return

    name = args[0].lower()
    if name not in db.VALID_SERVICES:
        await update.message.reply_text(
            f"Servizi disponibili: {', '.join(db.VALID_SERVICES)}"
        )
        return

    db.set_setting("service", name)
    logger.info("Servizio cambiato a %s da %s", name, update.effective_user)
    await update.message.reply_text(f"✅ Servizio impostato: *{name}*", parse_mode="Markdown")


async def _post_init(application) -> None:
    asyncio.create_task(_worker())


def run_bot():
    db.init_db()
    app = (
        ApplicationBuilder()
        .token(TELEGRAM_TOKEN)
        .post_init(_post_init)
        .build()
    )
    app.add_handler(CommandHandler("servizio", servizio_command))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, audio_handler))
    logger.info("Bot in ascolto (servizio: %s)", db.get_setting("service", "scriberr"))
    app.run_polling()
