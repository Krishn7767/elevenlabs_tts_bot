import logging
import os
import requests
from io import BytesIO

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, constants
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
    CallbackQueryHandler,
)

# --- Configuration ---
# Load from environment variables
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ELEVENLABS_API_KEY = os.getenv("ELEVENLABS_API_KEY")
# Default voice if user hasn't selected one or if API call for voices fails
DEFAULT_ELEVENLABS_VOICE_ID = os.getenv("DEFAULT_ELEVENLABS_VOICE_ID", "21m00Tcm4TlvDq8ikWAM") # Rachel

ELEVENLABS_API_BASE_URL = "https://api.elevenlabs.io/v1"

# --- Logging Setup ---
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logger = logging.getLogger(__name__)

# --- ElevenLabs API Functions ---
async def fetch_elevenlabs_voices(api_key: str) -> list | None:
    """Fetches available voices from ElevenLabs."""
    voices_url = f"{ELEVENLABS_API_BASE_URL}/voices"
    headers = {"Accept": "application/json", "xi-api-key": api_key}
    try:
        response = requests.get(voices_url, headers=headers, timeout=10)
        response.raise_for_status()
        voices_data = response.json()
        # We only care about predefined voices usually, filter if necessary
        # For simplicity, taking all for now.
        # Filter out non-premade voices if too many:
        # available_voices = [
        #     {"name": voice["name"], "voice_id": voice["voice_id"]}
        #     for voice in voices_data.get("voices", [])
        #     if voice.get("category") == "premade" # or other criteria
        # ]
        available_voices = [
            {"name": voice["name"], "voice_id": voice["voice_id"]}
            for voice in voices_data.get("voices", [])
        ]
        logger.info(f"Fetched {len(available_voices)} voices from ElevenLabs.")
        return available_voices
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"ElevenLabs HTTP error fetching voices: {http_err} - Response: {response.text if 'response' in locals() else 'N/A'}")
        return None
    except requests.exceptions.RequestException as req_err:
        logger.error(f"ElevenLabs Request error fetching voices: {req_err}")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching ElevenLabs voices: {e}")
        return None

def generate_tts_elevenlabs(text: str, voice_id: str, api_key: str) -> bytes | None:
    """
    Generates speech from text using ElevenLabs API.
    Returns audio content as bytes, or None if an error occurs.
    """
    tts_url = f"{ELEVENLABS_API_BASE_URL}/text-to-speech/{voice_id}"
    headers = {
        "Accept": "audio/mpeg",
        "Content-Type": "application/json",
        "xi-api-key": api_key,
    }
    data = {
        "text": text,
        "model_id": "eleven_multilingual_v2",
        "voice_settings": {"stability": 0.5, "similarity_boost": 0.75},
    }

    try:
        response = requests.post(tts_url, json=data, headers=headers, timeout=60)
        response.raise_for_status()
        return response.content
    except requests.exceptions.HTTPError as http_err:
        logger.error(f"ElevenLabs TTS HTTP error: {http_err} - Response: {response.text}")
        if response.status_code == 401:
            logger.error("ElevenLabs API Key is invalid or missing for TTS.")
        return None
    except requests.exceptions.RequestException as req_err:
        logger.error(f"ElevenLabs TTS Request error: {req_err}")
        return None
    except Exception as e:
        logger.error(f"An unexpected error occurred with ElevenLabs TTS API: {e}")
        return None

# --- Telegram Bot Handlers ---
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a more attractive welcome message."""
    user_name = update.effective_user.first_name
    welcome_message = (
        f"Hi {user_name}! 👋 Welcome to the ElevenLabs TTS Bot! ✨\n\n"
        "I can turn your text into super realistic speech using ElevenLabs AI.\n\n"
        "Here's how to get started:\n"
        "1.  Simply send me any text message.\n"
        "2.  Use /voices to see available voices and choose your favorite.\n"
        "3.  I'll send back an audio message 🗣️🎶\n\n"
        "Type /help for more commands and info."
    )
    await update.message.reply_html(welcome_message)

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Sends a help message."""
    current_voice_id = context.user_data.get("voice_id", DEFAULT_ELEVENLABS_VOICE_ID)
    current_voice_name = context.user_data.get("voice_name", "Default") # You might want to fetch name for default ID too

    help_text = (
        "🤖 **Bot Commands & Info** 🤖\n\n"
        "Simply send me any text, and I'll convert it to speech!\n\n"
        "🔹 /start - Display the welcome message.\n"
        "🔹 /help - Show this help message.\n"
        "🔹 /voices - List available ElevenLabs voices and let you choose one.\n\n"
        f"🗣️ Your current selected voice: **{current_voice_name}** (ID: `{current_voice_id}`).\n\n"
        "This bot uses the ElevenLabs API. Ensure the API key is valid and has enough quota."
    )
    await update.message.reply_html(help_text)

async def voices_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Lists available voices and allows selection."""
    if not ELEVENLABS_API_KEY:
        await update.message.reply_text("Sorry, the ElevenLabs API key is not configured by the admin.")
        return

    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=constants.ChatAction.TYPING)
    voices = await fetch_elevenlabs_voices(ELEVENLABS_API_KEY)

    if not voices:
        await update.message.reply_text(
            "Could not fetch voices from ElevenLabs at the moment. Please try again later or contact the admin."
        )
        return

    if not voices: # Double check after potential modification in fetch_elevenlabs_voices
        await update.message.reply_text("No voices found or an error occurred.")
        return

    keyboard = []
    row = []
    # Limit to a reasonable number of buttons or implement pagination if many voices
    # For ElevenLabs default voices, the number is usually manageable (around 10-30)
    for voice in voices[:20]: # Displaying up to 20 voices for now
        button = InlineKeyboardButton(voice["name"], callback_data=f"voice_{voice['voice_id']}_{voice['name']}")
        row.append(button)
        if len(row) == 2: # 2 buttons per row
            keyboard.append(row)
            row = []
    if row: # Add remaining buttons if any
        keyboard.append(row)

    if not keyboard:
        await update.message.reply_text("No voices available to display.")
        return

    reply_markup = InlineKeyboardMarkup(keyboard)
    await update.message.reply_text("Choose your desired voice:", reply_markup=reply_markup)

async def voice_selection_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles voice selection from inline keyboard."""
    query = update.callback_query
    await query.answer() # Acknowledge callback

    try:
        # callback_data is "voice_VOICEID_VOICENAME"
        parts = query.data.split("_", 2)
        if len(parts) < 3 or parts[0] != "voice":
            logger.warning(f"Invalid callback data format: {query.data}")
            await query.edit_message_text(text="Error processing selection. Invalid data.")
            return

        voice_id = parts[1]
        voice_name = parts[2].replace("_", " ") # Reconstruct name if it had underscores

        context.user_data["voice_id"] = voice_id
        context.user_data["voice_name"] = voice_name
        logger.info(f"User {update.effective_user.id} selected voice: {voice_name} ({voice_id})")
        await query.edit_message_text(text=f"✨ Voice set to: **{voice_name}** ✨\nSend me some text to try it out!")

    except Exception as e:
        logger.error(f"Error in voice_selection_callback: {e}")
        await query.edit_message_text(text="An error occurred while setting the voice. Please try again.")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handles regular text messages and converts them to speech."""
    user_text = update.message.text
    if not user_text:
        return

    chat_id = update.effective_chat.id
    logger.info(f"Received text from chat {chat_id}: '{user_text[:50]}...'")

    await context.bot.send_chat_action(chat_id=chat_id, action=constants.ChatAction.RECORD_VOICE)

    selected_voice_id = context.user_data.get("voice_id", DEFAULT_ELEVENLABS_VOICE_ID)
    selected_voice_name = context.user_data.get("voice_name", "Default")

    if not ELEVENLABS_API_KEY:
        await update.message.reply_text("Admin alert: ElevenLabs API key is not set. Cannot process TTS.")
        return

    audio_content = generate_tts_elevenlabs(user_text, selected_voice_id, ELEVENLABS_API_KEY)

    if audio_content:
        audio_file = BytesIO(audio_content)
        audio_file.name = "voice.mp3"
        try:
            await update.message.reply_voice(voice=audio_file, caption=f"🎙️ Voice: {selected_voice_name}")
            logger.info(f"Sent voice message to chat {chat_id} using voice {selected_voice_name}")
        except Exception as e:
            logger.error(f"Error sending voice message: {e}")
            await update.message.reply_text("Sorry, I encountered an error while sending the audio.")
    else:
        logger.warning(f"Failed to generate audio for text from chat {chat_id}")
        await update.message.reply_text(
            "Sorry, I couldn't convert your text to speech. 😔\n"
            "This might be due to:\n"
            "- An issue with the ElevenLabs API.\n"
            "- Invalid or exhausted API key quota.\n"
            "- The selected voice might be unavailable.\n\n"
            "Please try again later or select a different voice using /voices."
        )

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log Errors caused by Updates."""
    logger.error(f"Update {update} caused error {context.error}", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        try:
            await update.effective_message.reply_text("An unexpected error occurred. The bot admin has been notified. Please try again later.")
        except Exception as e:
            logger.error(f"Failed to send error message to user: {e}")


def main() -> None:
    """Start the bot."""
    if not TELEGRAM_BOT_TOKEN:
        logger.critical("FATAL: TELEGRAM_BOT_TOKEN environment variable not set. Exiting.")
        return
    if not ELEVENLABS_API_KEY:
        # Bot can still start, but TTS and voice listing will fail.
        logger.warning("WARNING: ELEVENLABS_API_KEY environment variable not set. TTS features will be disabled.")

    logger.info("🚀 Starting ElevenLabs TTS Bot...")

    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("voices", voices_command))
    application.add_handler(CallbackQueryHandler(voice_selection_callback, pattern="^voice_"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    application.add_error_handler(error_handler)

    logger.info("Bot is now polling for updates... 📡")
    application.run_polling()

if __name__ == "__main__":
    main()