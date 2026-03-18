import logging
import os

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("lia-bot")

BOT_TOKEN = os.getenv("BOT_TOKEN")
PUBLIC_URL = os.getenv("PUBLIC_URL")
PORT = int(os.getenv("PORT", "8080"))

if not BOT_TOKEN or not PUBLIC_URL:
    raise RuntimeError("Faltan env vars: BOT_TOKEN, PUBLIC_URL")


async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("COMANDO /start RECIBIDO")
    await update.message.reply_text("bot vivo")


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info(f"UPDATE RECIBIDO: {update}")

    msg = update.effective_message
    if not msg or not msg.text:
        return

    text = msg.text.strip()
    if not text:
        return

    send_kwargs = {}

    # soporte para direct messages topics de canal
    if getattr(msg, "direct_messages_topic", None):
        send_kwargs["direct_messages_topic_id"] = msg.direct_messages_topic.topic_id

    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="te leo",
        **send_kwargs,
    )


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"ERROR GLOBAL: {context.error}", exc_info=True)


def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    app.add_error_handler(error_handler)

    webhook_url = f"{PUBLIC_URL}/telegram/webhook"
    logger.info(f"Bot iniciado en {webhook_url}")

    app.run_webhook(
        listen="0.0.0.0",
        port=PORT,
        url_path="telegram/webhook",
        webhook_url=webhook_url,
        allowed_updates=Update.ALL_TYPES,
    )


if __name__ == "__main__":
    main()
