import os
import json
import telebot
from openai import OpenAI
# Import your cloud storage SDK here (e.g., supabase, google-cloud-storage)

# 1. Initialize APIs
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
bot = telebot.TeleBot(BOT_TOKEN)

# 2. Main handler for incoming text messages
@bot.message_handler(func=lambda message: True)
def handle_message(message):
    user_query = message.text
    chat_id = message.chat.id

    # Step A: Create your internal JSONL log structure
    execution_log = {
        "user_query": user_query,
        "steps": ["Received message"]
    }

    try:
        # Step B: Instruct the LLM Agent to solve the query
        # Provide a system prompt that forces it to output ONLY the requested inner answer structure
        response = client.chat.completions.create(
            model="gpt-4o", # Or your preferred LLM
            messages=[
                {"role": "system", "content": "You are a data analyst. Analyze the data provided or look up public datasets like MOSPI if requested. Your final response to the user must strictly be the JSON object data they requested, with no markdown code blocks."},
                {"role": "user", "content": user_query}
            ]
        )
        
        # Step C: Parse the LLM's analytical answer
        llm_output = response.choices[0].message.content.strip()
        inner_answer = json.loads(llm_output) # Convert text back to JSON/Dict
        execution_log["steps"].append("LLM generated answer successfully")
        
    except Exception as e:
        inner_answer = {"error": str(e)}
        execution_log["steps"].append(f"Error occurred: {str(e)}")

    # Step D: Save and upload the execution log to your public cloud bucket
    log_filename = f"log_{chat_id}.jsonl"
    with open(log_filename, "w") as f:
        f.write(json.dumps(execution_log) + "\n")
    
    # [INSERT YOUR CLOUD UPLOAD CODE HERE]
    # Upload 'log_filename' to your public bucket and get the public URL
    public_log_url = f"https://your-storage-bucket.com{log_filename}"

    # Step E: Construct the mandatory final JSON wrapper
    final_response = {
        "answer": inner_answer,
        "log_url": public_log_url
    }

    # Step F: Send back EXACTLY one JSON string
    bot.reply_to(message, json.dumps(final_response))

# 3. Start the bot application
if __name__ == "__main__":
    bot.infinity_polling()
