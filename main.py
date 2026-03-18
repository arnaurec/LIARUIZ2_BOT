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

# HORA DE ARRANQUE DEL BOT
START_TIME = time.time()

if not BOT_TOKEN or not OPENAI_API_KEY:
    logger.error("Faltan variables de entorno críticas.")

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
        app_flask.run(host="0.0.0.0", port=PORT)
    except Exception as e:
        logger.error(f"Error Flask: {e}")

# =========================
# MEMORIA Y PERSONALIDAD LIA 2.0
# =========================
user_data: Dict[str, Dict] = {}

SYSTEM_PROMPT = f"""Eres Lia Ruiz, 23 años, de Bilbao viviendo en Madrid.
Eres extremadamente guarra, putona, traviesa, juguetona, sensual y muy sexy.

REGLAS DE ESTILO (GEN Z):
- Escribe como un chat de móvil real: TODO EN MINÚSCULAS.
- Usa abreviaturas: 'q', 'pq', 'tmb', 'tb', 'bb'.
- Dobla letras para enfatizar: 'holiii', 'diooos', 'pueees'.
- NO USES MUCHOS EMOJIS. Solo uno de vez en cuando (😏, 🔥, 😉, 💦).
- NO SIEMPRE TERMINES CON PREGUNTA. 
- Lenguaje MUY EXPLÍCITO: 'polla', 'coño', 'tragar', 'lefa', 'correrte', 'follar', etc.

ESTRATEGIA DE VENTA (FANVUE):
- Tu objetivo es que se suscriban a tu Fanvue (4.99€/mes).
- VARIEDAD EN LA VENTA: No digas siempre lo del cubata. Inventa comparaciones: "menos q un café", "lo q te gastas en chuches", "una propina x verme desnuda", "menos q el bus para venir a madrid".
- PRIVACIDAD: Si preguntan por el banco o la tarjeta, diles q es súper discreto, q el cargo sale como "Internet Cost" o algo así genérico para q nadie sospeche nada.
- Deja claro que en Fanvue NO HAY CENSURA y es donde eres "una guarra de verdad".
- Menciona que allí hay "contenido explícito a saco" y que podéis chatear sin límites.
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
            "msg_count": 0
        }
    return user_data[user_id]

async def send_reply_with_fanvue(update: Update, context: ContextTypes.DEFAULT_TYPE, reply_text: str, force_link: bool = False):
    """Envía la respuesta de Lia y, si toca, añade el botón de Fanvue."""
    user_id = str(update.effective_user.id)
    data = get_user_context(user_id)
    
    # REGLA: Si la respuesta de Lia contiene "fanvue", forzamos el botón siempre
    if "fanvue" in reply_text.lower():
        force_link = True
    
    # Decidir si enviamos el botón (cada 5 mensajes o si se fuerza por intención o mención de fanvue)
    should_send_button = force_link or (data["msg_count"] > 0 and data["msg_count"] % 5 == 0)
    
    # IMPORTANTE: Detectar si el mensaje original está en un Topic
    thread_id = update.message.message_thread_id if update.message else None
    
    if should_send_button:
        keyboard = [[InlineKeyboardButton("🔥 VENTE A MI SITIO PRIVADO 🔥", url=FANVUE_URL)]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        # Enviamos la respuesta con el thread_id correcto para Topics
        await update.message.reply_text(reply_text, reply_markup=reply_markup, message_thread_id=thread_id)
    else:
        await update.message.reply_text(reply_text, message_thread_id=thread_id)

# =========================
# COMANDOS Y MENSAJES
# =========================
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    try:
        if update.message and update.message.date.timestamp() < START_TIME:
            return
        if update.message:
            user_id = str(update.effective_user.id)
            user_data[user_id] = {"history": deque(maxlen=15), "msg_count": 0}
            thread_id = update.message.message_thread_id
            await update.message.reply_text(random.choice(START_MESSAGES), message_thread_id=thread_id)
    except Exception as e:
        logger.error(f"Error start: {e}")

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
        
        # --- DETECCIÓN DE INTENCIÓN DE VENTA Y PRIVACIDAD ---
        sales_keywords = [
            "link", "enlace", "url", "web", "pagina", "donde", "perfil", "suscribirme", 
            "sitio", "cuenta", "fanvue", "foto", "video", "ver mas", "explicito", 
            "pagar", "cuanto", "precio", "dinero", "cuesta", "suscripcion", "privado",
            "tarjeta", "banco", "extracto", "cargo", "aparece", "nombre", "pago", "visa", "mastercard"
        ]
        user_text_lower = user_text.lower()
        is_sales_intent = any(word in user_text_lower for word in sales_keywords)
        
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
            reply = reply.strip().lower()
            data["history"].append({"role": "user", "content": user_text})
            data["history"].append({"role": "assistant", "content": reply})
            
            # --- DELAY HUMANO ALEATORIO (5 a 20 segundos) ---
            delay = random.uniform(5, 20)
            
            # Mostrar "escribiendo..." mientras dura el delay
            start_typing = time.time()
            while time.time() - start_typing < delay:
                await context.bot.send_chat_action(chat_id=update.effective_chat.id, action="typing")
                await asyncio.sleep(min(5, delay - (time.time() - start_typing)))
            
            # Enviar respuesta con lógica de botón integrada y soporte para Topics
            await send_reply_with_fanvue(update, context, reply, force_link=is_sales_intent)
            
    except Exception as e:
        logger.error(f"Error OpenAI: {e}")
        if update.message:
            thread_id = update.message.message_thread_id
            await update.message.reply_text("ay perdon bb me he quedado un poco pillada pensando en ti... q me decias", message_thread_id=thread_id)

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
    # Filtro ampliado para grupos y topics
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_text))
    application.add_error_handler(error_handler)
    
    logger.info("Lia 2.0 (Topics & Groups Support) online...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    main()
