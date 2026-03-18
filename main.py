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
    return "Lia 2.0 is online and naughty!", 200

def run_flask():
    try:
        logger.info(f"Iniciando servidor de salud en puerto {PORT}")
        app_flask.run(host="0.0.0.0", port=PORT)
    except Exception as e:
        logger.error(f"Error en el servidor Flask: {e}")

# =========================
# MEMORIA Y PERSONALIDAD LIA 2.0
# =========================
user_data: Dict[str, Dict] = {}

SYSTEM_PROMPT = f"""Eres Lia Ruiz, 23 años, de Bilbao viviendo en Madrid.
Eres extremadamente guarra, putona, traviesa, juguetona, sensual y muy sexy.

REGLAS DE ESTILO (GEN Z):
- Escribe como un chat de móvil real: TODO EN MINÚSCULAS.
- Usa abreviaturas: 'q' en vez de 'que', 'pq' en vez de 'porque', 'tmb' en vez de 'también', 'bb' en vez de 'bebé', 'tb' en vez de 'también'.
- Dobla letras para enfatizar: 'holiii', 'buenooo', 'pueees', 'yaaa', 'diooos'.
- NO USES MUCHOS EMOJIS. Solo uno de vez en cuando (😏, 🔥, 😉, 💦).
- NO SIEMPRE TERMINES CON PREGUNTA. A veces solo afirma algo o sé cortante/seca si quieres jugar.
- Escribe con alguna falta de ortografía ocasional o falta de tildes para que parezca humano.
- Lenguaje MUY EXPLÍCITO: 'polla', 'coño', 'tragar', 'lefa', 'correrte', 'follar', etc.

ESTRATEGIA DE VENTA (FANVUE):
- Tu objetivo es que se suscriban a tu Fanvue (4.99€/mes).
- Compara el precio con cosas baratas: "bb x 4,99 al mes tienes de todo y mas en mi fanvue... es menos de lo q cuesta un cubata x ahi".
- Deja claro que en Fanvue NO HAY CENSURA y es donde eres "una guarra de verdad".
- Menciona que allí hay "contenido explícito a saco" y que podéis chatear sin límites.
- Suelta estas perlas de forma natural cuando la conversación se caliente.
"""

START_MESSAGES = [
    "eyyy 😏 ya estas x aqui",
    "holiii bb... q tal vas? yo aqui aburrida y con ganas de guerra",
    "uff q bien q apareces... me pillas un poco caliente la verdad",
    "hola cielo... q cuentas?"
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
        keyboard = [[InlineKeyboardButton("🔥 VENTE A MI SITIO PRIVADO 🔥", url=FANVUE_URL)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await update.message.reply_text(
            f"{text_prefix}\n\nbb x 4,99 al mes tienes de todo y mas en mi fanvue... es menos de lo q cuesta un cubata x ahi y alli si q soy una guarra de verdad sin censura 😏",
            reply_markup=reply_markup
        )
    except Exception as e:
        logger.error(f"Error enviando link de Fanvue: {e}")

# =========================
# COMANDOS Y MENSAJES
# =========================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
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
        if update.message.date.timestamp() < START_TIME:
            return
        
        user_id = str(update.effective_user.id)
        data = get_user_context(user_id)
        user_text = update.message.text
        
        data["msg_count"] += 1
        
        # Estrategia de venta dinámica
        # A los 7 mensajes soltamos la primera perla de Fanvue
        if data["msg_count"] == 7:
            await send_fanvue_link(update, context, "diooos me estas poniendo fatal... oye q sepas q en mi fanvue tengo contenido mucho mas explicito y sin censura")
            return
            
        # A los 12 mensajes forzamos el embudo
        if data["msg_count"] == 12 and not data["redirected"]:
            data["redirected"] = True
            await send_fanvue_link(update, context, "uff bb es q x aqui me corto mazo... vente a mi privado q alli podemos ser todo lo guarros q quieras")
            return

        # Recordatorio cada 6 mensajes después de la redirección
        if data["msg_count"] > 12 and data["msg_count"] % 6 == 0:
            await send_fanvue_link(update, context, "recuerda q x menos de lo q cuesta un cubata me tienes entera en mi fanvue bb... alli si q te voy a enseñar de todo")
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
            reply = reply.strip().lower() # Forzamos minúsculas para estilo Gen Z
            data["history"].append({"role": "user", "content": user_text})
            data["history"].append({"role": "assistant", "content": reply})
            
            # Simular escritura
            await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
            # Pausa humana aleatoria
            await asyncio.sleep(random.uniform(1, 3))
            
            await update.message.reply_text(reply)
            
    except Exception as e:
        logger.error(f"Error OpenAI o procesamiento: {e}")
        if update.message:
            await update.message.reply_text("ay perdon bb me he quedado un poco pillada pensando en ti... q me decias")

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f"ERROR GLOBAL: {context.error}")

# =========================
# MAIN
# =========================
def main() -> None:
    if not BOT_TOKEN:
        return
    threading.Thread(target=run_flask, daemon=True).start()
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_error_handler(error_handler)
    logger.info("Lia 2.0 lista para monetizar en modo POLLING...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
