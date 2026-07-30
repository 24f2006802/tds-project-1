
import os
import json
import telebot
import threading
from groq import Groq
from flask import Flask
from supabase import create_client, Client

# =====================================================================
# 1. API INITIALIZATION & SETUP
# =====================================================================
# Load secrets from Render environment variables
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")

# Create connection instances
bot = telebot.TeleBot(BOT_TOKEN)
groq_client = Groq(api_key=GROQ_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# An in-memory dictionary to store conversation history per chat room.
# Required because the assignment explicitly tests multi-turn sequences.
chat_history = {}


# =====================================================================
# 2. LOG UPLOADER FUNCTION (SUPABASE)
# =====================================================================
def upload_log_to_cloud(local_file_path, storage_filename):
    """Uploads the local .jsonl file directly to your public Supabase bucket"""
    try:
        with open(local_file_path, 'rb') as f:
            supabase.storage.from_('bot-logs').upload(
                file=f,
                path=storage_filename,
                file_options={"content-type": "application/x-jsonlines", "x-upsert": "true"}
            )
        # Construct the explicit public path URL that wget will download
        public_url = f"{SUPABASE_URL}/storage/v1/object/public/bot-logs/{storage_filename}"
        return public_url
    except Exception as e:
        print(f"Log upload failure: {e}")
        return "https://fallback-url/failed-to-upload-log.jsonl"


# =====================================================================
# 3. TELEGRAM MESSAGE HANDLER
# =====================================================================
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_query = message.text
    chat_id = message.chat.id

    # Initialize chat history if this is a first-time user
    if chat_id not in chat_history:
        chat_history[chat_id] = [
            {
                "role": "system", 
                "content": (
                    "You are a professional data analyst. Analyze data provided inline or query public "
                    "datasets like MOSPI to provide direct answers. The user's query text contains an explicit "
                    "instruction asking for a specific JSON data structure outcome. Read that constraint carefully. "
                    "Your response must strictly contain ONLY that inner JSON data dictionary format. "
                    "Do NOT use markdown text formatting, wrapping code blocks (```json), or introductory/trailing filler text."
                )
            }
        ]

    # Append the incoming question into the persistent thread
    chat_history[chat_id].append({"role": "user", "content": user_query})

    # Prepare local log container tracking steps for the JSONL document evaluation
    execution_log = {
        "chat_id": chat_id,
        "received_query": user_query,
        "history_depth": len(chat_history[chat_id]),
        "steps": ["Parsed inbound multi-turn context"]
    }

    try:
        # Request completion payload from Groq
        # Using 'llama-3.3-70b-versatile' as a highly reliable option for reasoning/JSON structural tasks
        response = groq_client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=chat_history[chat_id],
            temperature=0.1  # Kept minimal to force accurate format compliance
        )
        
        # Capture raw completion output
        llm_output = response.choices[0].message.content.strip()
        execution_log["steps"].append("Groq inference computation succeeded")
        
        # Safely convert textual output back to a dictionary structure to verify parsing validation 
        inner_answer = json.loads(llm_output)
        
        # Append the successfully parsed bot answer back into the model chat string history
        chat_history[chat_id].append({"role": "assistant", "content": llm_output})

    except Exception as e:
        # Fallback error mapping handling inside the expected structure 
        inner_answer = {"error": f"Failed to compute/parse query response cleanly: {str(e)}"}
        execution_log["steps"].append(f"Processing structural anomaly: {str(e)}")

    # Create the local log file
    log_filename = f"run_{chat_id}.jsonl"
    with open(log_filename, "w", encoding="utf-8") as f:
        f.write(json.dumps(execution_log) + "\n")
    
    # Push log up to your running Supabase bucket and fetch its live URL
    public_log_url = upload_log_to_cloud(log_filename, log_filename)

    # Clean up local runtime disk asset
    if os.path.exists(log_filename):
        os.remove(log_filename)

    # Construct the exact outermost wrapper required by the grader pipeline
    final_response = {
        "answer": inner_answer,
        "log_url": public_log_url
    }

    # Transmit exactly one stringified JSON layout payload token back to the testing pipeline account
    bot.reply_to(message, json.dumps(final_response))


# ... Keep all your existing bot code, handlers, and logic exactly the same above ...

# 1. Create a tiny fake web app to keep Render happy
app = Flask(__name__)

@app.route('/')
def home():
    return "Data Analyst Bot is running safely!", 200

def run_bot():
    print("Telegram bot polling started...")
    bot.infinity_polling()

# 2. Modify the execution block to run both simultaneously
if __name__ == "__main__":
    # Launch your Telegram bot thread in the background
    bot_thread = threading.Thread(target=run_bot)
    bot_thread.daemon = True
    bot_thread.start()
    
    # Run the web server on the port Render dynamically assigns
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)


