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


def _chat_name(chat) -> str | None:
    if chat is None:
        return None
    if chat.title:
        return chat.title
    parts = [chat.first_name, chat.last_name]
    return " ".join(p for p in parts if p) or None


async def audio_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message:
        return

    tg_audio = message.voice or message.audio
    if not tg_audio:
        return

    user = message.from_user
    chat = message.chat
    audio_duration = getattr(tg_audio, "duration", None)
    filename = getattr(tg_audio, "file_name", None) or "audio.ogg"

    tg_file = await context.bot.get_file(tg_audio.file_id)
    bio = io.BytesIO()
    await tg_file.download_to_memory(out=bio)
    bio.seek(0)
    file_bytes = bio.read()

    await message.reply_text("🎧 Audio ricevuto, sto trascrivendo...")

    start_time = time.time()
    status = "error"
    error_message = None
    text = None

    active_service = db.get_setting("service", "scriberr")

    try:
        if active_service == "parakeet":
            text = parakeet.transcribe(file_bytes, filename=filename)
        else:
            text = scriberr.transcribe(file_bytes, filename=filename)
        status = "success"
    except Exception as exc:
        logger.exception("Errore nella trascrizione")
        error_message = str(exc)

    processing_time = round(time.time() - start_time, 1)

    db.log_transcription(
        user_id=user.id if user else None,
        username=user.username if user else None,
        full_name=user.full_name if user else None,
        chat_id=chat.id if chat else None,
        chat_title=_chat_name(chat),
        audio_duration=audio_duration,
        service=active_service,
        status=status,
        processing_time=processing_time,
        error_message=error_message,
    )

    if status == "success":
        await message.reply_text(f"📝 Trascrizione:\n\n{text}")
    else:
        await message.reply_text(f"❌ Errore: {error_message}")


async def servizio_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        current = db.get_setting("service", "scriberr")
        await update.message.reply_text(f"Servizio attivo: *{current}*", parse_mode="Markdown")
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


def run_bot():
    db.init_db()
    app = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("servizio", servizio_command))
    app.add_handler(MessageHandler(filters.VOICE | filters.AUDIO, audio_handler))
    logger.info("Bot in ascolto (servizio: %s)", db.get_setting("service", "scriberr"))
    app.run_polling()
