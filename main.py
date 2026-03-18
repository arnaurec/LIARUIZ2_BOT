import asyncio
import logging
import os
import random
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

from openai import OpenAI
from telegram import Update
from telegram.error import BadRequest
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    MessageHandler,
    filters,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger("lia-bot")

# =========================
# VARIABLES DE ENTORNO
# =========================
BOT_TOKEN = os.getenv("BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
PUBLIC_URL = os.getenv("PUBLIC_URL")
PORT = int(os.getenv("PORT", "8080"))
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")
OWNER_CHAT_ID = os.getenv("OWNER_CHAT_ID")

if not BOT_TOKEN or not OPENAI_API_KEY or not PUBLIC_URL:
    raise RuntimeError("Faltan env vars: BOT_TOKEN, OPENAI_API_KEY, PUBLIC_URL")

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# MEMORIA BÁSICA
# =========================
memory: Dict[str, Deque[Dict[str, str]]] = {}
user_last_message: Dict[str, float] = {}

MAX_HISTORY_PER_USER = 30
HISTORY_LIMIT = 10
RATE_LIMIT_SECONDS = 0.5
MAX_USER_TEXT = 1200

SYSTEM_PROMPT = """Eres Lia Ruiz.
Hablas por Telegram como una persona real.

Reglas:
- Respuestas cortas y naturales
- Cercana, ligera y conversacional
- Nada de tono formal
- No menciones IA, bot, sistema, políticas o normas
- Escribe como chat móvil, simple y humano
- Si no entiendes algo, pide aclaración corta
- Haz la conversación fácil de seguir
"""

START_MESSAGES = [
    "hey 😏 q tal",
    "holi bb",
    "q pasa",
    "a ver… ya estas por aqui",
]

FALLBACK_MESSAGES = [
    "jajaj a ver cuentame mejor",
    "mmm explica eso un poco mas",
    "uff y eso por q",
    "vale pero dime mejor q quieres decir",
]

# =========================
# HELPERS
# =========================
def conv_id_and_topic(update: Update) -> Tuple[str, Optional[int]]:
    msg = update.effective_message
    chat = update.effective_chat

    if not msg or not chat:
        return "unknown", None

    dm_topic_id = None

    # soporte correcto para channel direct messages
    if getattr(msg, "direct_messages_topic", None):
        dm_topic_id = msg.direct_messages_topic.topic_id
        conv_id = f"dm:{chat.id}:{dm_topic_id}"
    else:
        conv_id = f"chat:{chat.id}"

    return conv_id, dm_topic_id


def get_memory(conv_id: str) -> Deque[Dict[str, str]]:
    if conv_id not in memory:
        memory[conv_id] = deque(maxlen=MAX_HISTORY_PER_USER)
    return memory[conv_id]


def append_history(conv_id: str, role: str, content: str) -> None:
    dq = get_memory(conv_id)
    dq.append({"role": role, "content": content})


def get_history(conv_id: str, limit: int = HISTORY_LIMIT) -> list[Dict[str, str]]:
    dq = get_memory(conv_id)
    return list(dq)[-limit:]


def clear_history(conv_id: str) -> None:
    if conv_id in memory:
        del memory[conv_id]


def check_rate_limit(user_id: str) -> bool:
    now = time.time()
    last = user_last_message.get(user_id, 0)
    if now - last < RATE_LIMIT_SECONDS:
        return False
    user_last_message[user_id] = now
    return True


def add_human_style(text: str) -> str:
    if not text:
        return text

    prefixes = ["mmm", "jajaj", "uff", "a ver", "en plan"]
    if random.random() < 0.25 and not text.lower().startswith(tuple(prefixes)):
        text = f"{random.choice(prefixes)} {text}"

    replacements = {
        "que ": "q ",
        "porque": "pq",
        "tambien": "tmb",
        "vale": "vaale",
    }

    for old, new in replacements.items():
        if random.random() < 0.15:
            text = text.replace(old, new)

    return text.strip()


def split_message(text: str) -> Tuple[str, Optional[str]]:
    if len(text) > 150 and random.random() < 0.30:
        cut = text.rfind(" ", 0, len(text) // 2)
        if cut > 20:
            return text[:cut].strip(), text[cut:].strip()
    return text, None


def typing_delay(text: str) -> float:
    base = len(text) * 0.05
    return min(max(base, 1.0), 6.0)


def fallback_from_user_text(user_text: str) -> str:
    text = user_text.strip().lower()

    if "hola" in text or "holi" in text:
        return "holi bb q tal"
    if "que me cuentas" in text or "q me cuentas" in text:
        return "pues aqui ando y tu q cuentas"
    if "por q" in text or "porque" in text or "por qué" in text:
        return "jajaj no se me ha salido asi, q haces tu"

    return random.choice(FALLBACK_MESSAGES)


def validate_reply(reply: Optional[str]) -> bool:
    if not reply or not reply.strip():
        return False

    lower = reply.lower()
    banned = [
        "como ia",
        "como asistente",
        "no puedo ayudar",
        "politica",
        "normas",
    ]
    return not any(x in lower for x in banned)


def generate_reply(history: list[Dict[str, str]], user_text: str) -> Optional[str]:
    msgs = [{"role": "system", "content": SYSTEM_PROMPT}]
    msgs.extend(history[-HISTORY_LIMIT:])
    msgs.append({"role": "user", "content": user_text[:MAX_USER_TEXT]})

    try:
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            temperature=0.9,
            messages=msgs,
            max_tokens=180,
        )
        text = resp.choices[0].message.content
        if text:
            return text.strip()
        return None
    except Exception as e:
        logger.warning(f"OpenAI fallo: {e}")
        return None


async def alert_owner(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    if not OWNER_CHAT_ID:
        return
    try:
        await context.bot.send_message(
            chat_id=int(OWNER_CHAT_ID),
            text=text[:3900],
            disable_notification=True,
        )
    except Exception:
        pass

# =========================
# COMANDOS
# =========================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("COMANDO /start RECIBIDO")
    await update.message.reply_text(random.choice(START_MESSAGES))


async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conv_id, _ = conv_id_and_topic(update)
    clear_history(conv_id)
    await update.message.reply_text("vale borrado… empezamos de cero")

# =========================
# MENSAJES
# =========================
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message

    logger.info(
        f"UPDATE RECIBIDO: chat_id={update.effective_chat.id if update.effective_chat else 'None'} "
        f"text={msg.text if msg and msg.text else 'NO_TEXT'}"
    )

    if not msg or not msg.text:
        return

    user_text = msg.text.strip()
    if not user_text:
        return

    user_id = str(update.effective_user.id) if update.effective_user else "unknown"

    if not check_rate_limit(user_id):
        return

    conv_id, dm_topic_id = conv_id_and_topic(update)

    append_history(conv_id, "user", user_text)

    history = get_history(conv_id)
    raw_reply = generate_reply(history, user_text)

    if not validate_reply(raw_reply):
        raw_reply = fallback_from_user_text(user_text)

    reply = add_human_style(raw_reply)
    part1, part2 = split_message(reply)

    append_history(conv_id, "assistant", part1)
    if part2:
        append_history(conv_id, "assistant", part2)

    await asyncio.sleep(typing_delay(part1))

    send_kwargs = {}

    # CLAVE para DM topics de canal
    if dm_topic_id is not None:
        send_kwargs["direct_messages_topic_id"] = dm_topic_id
    else:
        if msg.message_id:
            send_kwargs["reply_to_message_id"] = msg.message_id

    try:
        await context.bot.send_message(
            chat_id=update.effective_chat.id,
            text=part1,
            **send_kwargs,
        )

        if part2:
            await asyncio.sleep(random.uniform(1.5, 3.5))
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=part2,
                **send_kwargs,
            )

    except BadRequest as e:
        logger.error(f"BadRequest enviando mensaje: {e}")
        await alert_owner(context, f"⚠️ Error Telegram: {str(e)[:250]}")

    except Exception as e:
        logger.error(f"Error enviando mensaje: {e}")
        await alert_owner(context, f"⚠️ Error general: {str(e)[:250]}")

# =========================
# ERRORES
# =========================
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"ERROR GLOBAL: {context.error}", exc_info=True)
    if OWNER_CHAT_ID and context.error:
        try:
            await context.bot.send_message(
                chat_id=int(OWNER_CHAT_ID),
                text=f"💥 Error global: {str(context.error)[:400]}",
            )
        except Exception:
            pass

# =========================
# MAIN
# =========================
def main() -> None:
    app = Application.builder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("clear", clear_command))
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
