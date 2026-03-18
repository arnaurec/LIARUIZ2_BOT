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

# Configuración de logging
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
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini")

if not BOT_TOKEN or not OPENAI_API_KEY:
    logger.error(f"Faltan variables de entorno críticas. BOT_TOKEN: {bool(BOT_TOKEN)}, OPENAI_API_KEY: {bool(OPENAI_API_KEY)}")

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
    try:
        if hasattr(msg, "message_thread_id") and msg.message_thread_id:
            dm_topic_id = msg.message_thread_id
            conv_id = f"topic:{chat.id}:{dm_topic_id}"
        else:
            conv_id = f"chat:{chat.id}"
    except:
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
    replacements = {"que ": "q ", "porque": "pq", "tambien": "tmb", "vale": "vaale"}
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
    banned = ["como ia", "como asistente", "no puedo ayudar", "politica", "normas"]
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

# =========================
# COMANDOS Y MENSAJES
# =========================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message:
        await update.message.reply_text(random.choice(START_MESSAGES))

async def clear_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    conv_id, _ = conv_id_and_topic(update)
    clear_history(conv_id)
    if update.message:
        await update.message.reply_text("vale borrado… empezamos de cero")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = update.effective_message
    if not msg or not msg.text:
        return
    user_text = msg.text.strip()
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
    if dm_topic_id is not None:
        send_kwargs["message_thread_id"] = dm_topic_id
    try:
        await context.bot.send_message(chat_id=update.effective_chat.id, text=part1, **send_kwargs)
        if part2:
            await asyncio.sleep(random.uniform(1.5, 3.5))
            await context.bot.send_message(chat_id=update.effective_chat.id, text=part2, **send_kwargs)
    except Exception as e:
        logger.error(f"Error enviando mensaje: {e}")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"ERROR GLOBAL: {context.error}")

# =========================
# MAIN
# =========================
def main() -> None:
    if not BOT_TOKEN:
        logger.error("No se encontró BOT_TOKEN.")
        return
    
    # Cambiamos a modo POLLING para máxima estabilidad en Railway
    # Esto elimina la necesidad de configurar PUBLIC_URL y puertos
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("clear", clear_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_error_handler(error_handler)

    logger.info("Iniciando bot en modo POLLING (Máxima estabilidad)...")
    
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
