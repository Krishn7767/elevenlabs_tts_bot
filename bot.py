import logging
import os
import requests
from io import BytesIO

from telegram import Update, constants
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- Configuration ---
# Load from environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
ELEVENLABS_VOICE_ID = os.getenv("ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM") # Default: Rachel
# You can find more voice IDs here: https://api.elevenlabs.io/v1/voices

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ElevenLabs API Function ---
def generate_tts_elevenlabs(text: str, voice_id: str, api_key: str) -> bytes | None:
    """
    Generates speech from text using ElevenLabs API.
    Returns audio content as bytes, or None if an error occurs.
    """
    tts_url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2", # Or "eleven_monolingual_v1" for English only
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    try:
        response = requests.post(tts_url, json=data, headers=headers, timeout=60) # Added timeout
        response.raise_for_status() # Raises HTTPError for bad responses (4XX or 5XX)
        return response.content
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"ElevenLabs HTTP error: {http_err} - Response: {response.text}")
        if response.status_code == 401:
            logger.error("ElevenLabs API Key is invalid or missing.")
        return None
    except requests.exceptions.RequestException as req_err:
        logger.error(f"ElevenLabs Request error: {req_err}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred with ElevenLabs API: {e}")
        return None

# --- Telegram Bot Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a welcome message when the /start command is issued."""
    user_name = update.effective_user.first_name
    await update.message.reply_html(
        rf"Hi {user_name}! 👋 Send me any text, and I'll convert it to speech using ElevenLabs.",
        reply_markup=None, # No buttons for now
    )
    await update.message.reply_text(
        f"I'm currently configured to use voice ID: {ELEVENLABS_VOICE_ID}. "
        "You can find more voices and their IDs on the ElevenLabs website."
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message when the /help command is issued."""
    await update.message.reply_text(
        "How to use this bot:\n"
        "1. Simply send me any text message.\n"
        "2. I will convert it to an audio voice message using ElevenLabs.\n\n"
        "Current voice ID: " + ELEVENLABS_VOICE_ID + "\n"
        "This can be changed by the bot administrator via an environment variable."
    )

async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles regular text messages and converts them to speech."""
    user_text = update.message.text
    if not user_text:
        return

    chat_id = update.effective_chat.id
    logger.info(f"Received text from chat {chat_id}: '{user_text[:50]}...'")

    # Indicate bot is working
    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.RECORD_VOICE)

    audio_content = generate_tts_elevenlabs(user_text, ELEVENLABS_VOICE_ID, ELEVENLABS_API_KEY)

    if audio_content:
        audio_file = BytesIO(audio_content)
        audio_file.name = "voice.mp3" # Telegram needs a name, even for BytesIO
        try:
            await update.message.reply_voice(voice=audio_file)
            logger.info(f"Sent voice message to chat {chat_id}")
        except Exception as e:
            logger.error(f"Error sending voice message: {e}")
            await update.message.reply_text("Sorry, I encountered an error while sending the audio.")
    else:
        logger.warning(f"Failed to generate audio for text from chat {chat_id}")
        await update.message.reply_text(
            "Sorry, I couldn't convert your text to speech. "
            "This might be due to an issue with the ElevenLabs API, an invalid API key, "
            "or the service might be temporarily unavailable. Please try again later."
        )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(f"Update {update} caused error {context.error}")
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("An unexpected error occurred. The developers have been notified.")


def main() -> None:
    """Start the bot."""
    # --- Pre-run Checks ---
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
        return
    if not ELEVENLABS_API_KEY:
        logger.critical("ELEVENLABS_API_KEY environment variable not set. Exiting.")
        return

    logger.info("Starting bot...")

    # Create the Application and pass it your bot's token.
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    # --- Command Handlers ---
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))

    # --- Message Handler ---
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))

    # --- Error Handler ---
    application.add_error_handler(error_handler)

    # Run the bot until the user presses Ctrl-C
    logger.info("Bot is polling for updates...")
    application.run_polling()

if __name__ == "__main__":
    main()