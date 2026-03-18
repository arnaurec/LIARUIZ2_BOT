
import os
import logging
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from openai import OpenAI

# Configuración de logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# Variables de entorno
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
FANVUE_PROFILE_URL = os.getenv("FANVUE_PROFILE_URL", "https://fanvue.com/your_profile")
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

# Inicializar cliente OpenAI
openai_client = OpenAI(api_key=OPENAI_API_KEY)

# Diccionario para almacenar el contexto de la conversación y el "heat score" por usuario
# En un entorno de producción, esto debería ser una base de datos persistente.
user_data = {}

# Umbral de "heat score" para redirigir a Fanvue
HEAT_SCORE_THRESHOLD = 5

# --- Funciones del Bot ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Envía un mensaje de bienvenida cuando se inicia el bot."""
    user_id = update.effective_user.id
    user_data[user_id] = {"history": [], "heat_score": 0}
    await update.message.reply_text(
        "¡Hola! Soy tu asistente personal. ¿En qué puedo ayudarte hoy? 😉"
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Maneja los mensajes de texto del usuario."""
    user_id = update.effective_user.id
    user_message = update.message.text

    if user_id not in user_data:
        user_data[user_id] = {"history": [], "heat_score": 0}

    current_user_data = user_data[user_id]
    current_user_data["history"].append({"role": "user", "content": user_message})

    # Lógica para incrementar el "heat score"
    # Esto es una simplificación. En un bot real, se usaría NLP más avanzado.
    if any(keyword in user_message.lower() for keyword in ["sexy", "caliente", "explícito", "foto", "video", "privado"]):
        current_user_data["heat_score"] += 2
    elif any(keyword in user_message.lower() for keyword in ["interesante", "curioso", "dime más"]):
        current_user_data["heat_score"] += 1
    else:
        # Reducir el heat_score si la conversación se enfría
        current_user_data["heat_score"] = max(0, current_user_data["heat_score"] - 0.5)

    logger.info(f"User {user_id} heat score: {current_user_data['heat_score']}")

    # Comprobar si se alcanza el umbral de monetización
    if current_user_data["heat_score"] >= HEAT_SCORE_THRESHOLD:
        await redirect_to_fanvue(update, context)
        return

    # Preparar el historial para OpenAI (limitando para evitar tokens excesivos)
    # Mantener un historial corto para simular conversación móvil y evitar costos altos
    conversation_history = current_user_data["history"][-5:] # Últimos 5 intercambios

    # Añadir un mensaje de sistema para guiar el tono del bot
    system_message = {"role": "system", "content": (
        "Eres una persona real, amigable y un poco coqueta. "
        "Mantén las respuestas breves, naturales y con un tono de chat móvil. "
        "Evita sonar como una IA. Genera engagement emocional/sexual progresivo. "
        "No ofrezcas contenido explícito directamente, pero insinúa la posibilidad de un "espacio privado"."
    )}

    messages = [system_message] + conversation_history

    try:
        response = openai_client.chat.completions.create(
            model="gpt-4.1-mini", # Usar un modelo adecuado para el tono y costo
            messages=messages,
            max_tokens=100, # Respuestas breves
            temperature=0.9, # Para respuestas más creativas y "humanas"
        )
        bot_response = response.choices[0].message.content.strip()
    except Exception as e:
        logger.error(f"Error al comunicarse con OpenAI: {e}")
        bot_response = "Disculpa, tuve un pequeño problema. ¿Podrías repetirlo?"

    current_user_data["history"].append({"role": "assistant", "content": bot_response})
    await update.message.reply_text(bot_response)

async def redirect_to_fanvue(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Redirige al usuario a Fanvue cuando se alcanza el umbral de "heat score"."""
    keyboard = [
        [InlineKeyboardButton("¡Vamos a mi Fanvue! 😉", url=FANVUE_PROFILE_URL)]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text(
        "¡Uhm, la conversación se está poniendo interesante! "
        "Para continuar en un espacio más... privado, te invito a mi Fanvue. "
        "Allí podemos hablar sin límites y tengo contenido exclusivo para ti. ¿Vienes?",
        reply_markup=reply_markup
    )
    # Resetear el heat_score después de la redirección para evitar spam
    user_id = update.effective_user.id
    if user_id in user_data:
        user_data[user_id]["heat_score"] = 0

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Loggea los errores causados por las actualizaciones."""
    logger.error(f"Update {update} causó error {context.error}")

def main() -> None:
    """Inicia el bot."""
    if not TELEGRAM_BOT_TOKEN or not OPENAI_API_KEY or not WEBHOOK_URL:
        logger.error("Faltan variables de entorno. Asegúrate de configurar TELEGRAM_BOT_TOKEN, OPENAI_API_KEY y WEBHOOK_URL.")
        return

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # Comandos
    application.add_handler(CommandHandler("start", start))

    # Mensajes
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    # Errores
    application.add_error_handler(error_handler)

    # Configuración de Webhook para Railway
    application.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
        url_path=TELEGRAM_BOT_TOKEN,
        webhook_url=f"{WEBHOOK_URL}/{TELEGRAM_BOT_TOKEN}"
    )

if __name__ == "__main__":
    main()
