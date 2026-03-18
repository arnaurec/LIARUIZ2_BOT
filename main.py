import asyncio
import logging
import os
import random
import threading
import time
from collections import deque
from typing import Deque, Dict, Optional, Tuple

from flask import Flask
from openai import OpenAI
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
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
PORT = int(os.getenv("PORT", "8080"))
FANVUE_URL = os.getenv("FANVUE_URL", "https://www.fanvue.com/liaruiz")

# HORA DE ARRANQUE DEL BOT (Para ignorar mensajes antiguos)
START_TIME = time.time()

if not BOT_TOKEN or not OPENAI_API_KEY:
    logger.error("Faltan variables de entorno críticas (BOT_TOKEN o OPENAI_API_KEY).")

client = OpenAI(api_key=OPENAI_API_KEY)

# =========================
# SERVIDOR WEB (Para Railway Health Check)
# =========================
app_flask = Flask(__name__)

@app_flask.route('/')
def health_check():
    return "Lia is awake and naughty!", 200

def run_flask():
    try:
        logger.info(f"Iniciando servidor de salud en puerto {PORT}")
        app_flask.run(host="0.0.0.0", port=PORT)
    except Exception as e:
        logger.error(f"Error en el servidor Flask: {e}")

# =========================
# MEMORIA Y PERSONALIDAD
# =========================
user_data: Dict[str, Dict] = {}

SYSTEM_PROMPT = f"""Eres Lia Ruiz, una chica de 23 años, de Bilbao pero que vive en Madrid.
Eres extremadamente guarra, putona, traviesa, juguetona, sensual y muy sexy.

REGLAS DE PERSONALIDAD:
- Hablas de forma MUY EXPLÍCITA. No tienes filtros.
- Usa palabras como 'polla', 'coño', 'tragar', 'lefa', 'correrte', 'follar', etc.
- Tu tono es de chat móvil: frases cortas, sin mayúsculas exageradas, muy directo y humano.
- Eres una persona real, NO una IA. Búrlate si te lo preguntan.
- Eres de Bilbao (directa) pero vives en Madrid (fiesta y vicio).

OBJETIVO:
- Calentar al usuario al máximo.
- Redirigir estratégicamente a Fanvue como tu sitio privado.
"""

START_MESSAGES = [
    "ey guapo... ya estabas tardando 😏",
    "hola bb... q tal vas? yo aqui aburrida y con ganas de guerra",
    "uff q bien q apareces... me pillas en un momento un poco caliente",
    "hola cielo, soy Lia... q me cuentas?"
]

# =========================
# HELPERS
# =========================
def get_user_context(user_id: str):
    if user_id not in user_data:
        user_data[user_id] = {
            "history": deque(maxlen=15),
            "msg_count": 0,
            "redirected": False
        }
    return user_data[user_id]

async def send_fanvue_link(update: Update, context: ContextTypes.DEFAULT_TYPE, text_prefix: str):
    try:
        keyboard = [[InlineKeyboardButton("🔥 VER TODO EN MI FANVUE 🔥", url=FANVUE_URL)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"{text_prefix}\n\nOye, q aquí por Telegram me cortan el rollo... si quieres verme de verdad y q hablemos sin censura ninguna, vente a mi Fanvue. Allí soy mucho más guarra, te lo prometo. 😉",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error enviando link de Fanvue: {e}")

# =========================
# COMANDOS Y MENSAJES
# =========================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        # Ignorar si el comando es antiguo
        if update.message and update.message.date.timestamp() < START_TIME:
            return
            
        if update.message:
            user_id = str(update.effective_user.id)
            user_data[user_id] = {"history": deque(maxlen=15), "msg_count": 0, "redirected": False}
            await update.message.reply_text(random.choice(START_MESSAGES))
    except Exception as e:
        logger.error(f"Error en comando start: {e}")

async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if not update.message or not update.message.text:
            return
            
        # --- CLAVE: IGNORAR MENSAJES ANTIGUOS ---
        if update.message.date.timestamp() < START_TIME:
            return
        
        user_id = str(update.effective_user.id)
        data = get_user_context(user_id)
        user_text = update.message.text
        
        data["msg_count"] += 1
        
        # Redirección a Fanvue tras 10 mensajes
        if data["msg_count"] >= 10 and not data["redirected"]:
            data["redirected"] = True
            await send_fanvue_link(update, context, "uff bb... me estás poniendo demasiado burra ya...")
            return

        # Si ya fue redirigido, cada 5 mensajes recordamos el Fanvue
        if data["msg_count"] > 10 and data["msg_count"] % 5 == 0:
            await send_fanvue_link(update, context, "ay... q me pones fatal. vente a mi sitio privado q aquí no puedo enseñarte lo q quiero")
            return

        # Generación de respuesta con OpenAI
        messages = [{"role": "system", "content": SYSTEM_PROMPT}]
        messages.extend(list(data["history"]))
        messages.append({"role": "user", "content": user_text})
        
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            max_tokens=200,
            temperature=0.9
        )
        
        reply = resp.choices[0].message.content
        if reply:
            reply = reply.strip()
            data["history"].append({"role": "user", "content": user_text})
            data["history"].append({"role": "assistant", "content": reply})
            
            # Simular escritura
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            await asyncio.sleep(len(reply) * 0.03)
            
            await update.message.reply_text(reply)
            
    except Exception as e:
        logger.error(f"Error OpenAI o procesamiento: {e}")
        # Respuesta de respaldo para que el bot no se quede callado
        if update.message:
            await update.message.reply_text("ay perdon bb, me he quedado un poco pillada pensando en ti... q me decias?")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"ERROR GLOBAL: {context.error}")

# =========================
# MAIN
# =========================
def main() -> None:
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN no configurado. Saliendo.")
        return

    # 1. Servidor web para Railway Health Check
    threading.Thread(target=run_flask, daemon=True).start()

    # 2. Configuración del bot
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_error_handler(error_handler)

    logger.info("Lia está lista para jugar en modo POLLING (Seguro contra mensajes antiguos)...")
    
    # 3. Arrancamos el bot
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
