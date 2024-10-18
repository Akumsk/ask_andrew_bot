from telegram.ext import Updater, MessageHandler, Filters

# Replace 'YOUR_TELEGRAM_BOT_TOKEN' with your actual token
TELEGRAM_BOT_TOKEN = 'YOUR_TELEGRAM_BOT_TOKEN'

# In-memory storage for chat history
chat_histories = {}

def chat_retriever(update, context):
    chat_id = update.effective_chat.id
    user_message = update.message.text

    # Initialize chat history for new chats
    if chat_id not in chat_histories:
        chat_histories[chat_id] = []

    # Append the message to the chat history
    chat_histories[chat_id].append({'user': user_message})

    # Echo the message back (or process it as needed)
    reply = f"You said: {user_message}"
    update.message.reply_text(reply)

    # Append the bot's reply to the chat history
    chat_histories[chat_id].append({'bot': reply})

    # Print the chat history for debugging
    print(f"Chat history for chat_id {chat_id}: {chat_histories[chat_id]}")

def main():
        updater = Updater(TELEGRAM_BOT_TOKEN, use_context=True)
        dp = updater.dispatcher

        # Add a handler for text messages
        dp.add_handler(MessageHandler(Filters.text & ~Filters.command, handle_message))

        # Start the bot
        updater.start_polling()
        updater.idle()

    if __name__ == '__main__':
        main()