# bot.py

import logging
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    ConversationHandler,
    filters,
    CallbackQueryHandler,
)
from telegram.error import BadRequest
from oauth2callback import start_server

from settings import TELEGRAM_TOKEN
from llm_service import LLMService
from db_service import DatabaseService
from handlers import (
    BotHandlers,
    WAITING_FOR_FOLDER_PATH,
    WAITING_FOR_QUESTION,
    WAITING_FOR_PROJECT_SELECTION,
)
from exception_handlers import (
    error_handler,
    handle_telegram_context_length_exceeded_error,
)


def main():
    logging.basicConfig(level=logging.INFO)

    handlers = BotHandlers()

    application = (
        ApplicationBuilder().token(TELEGRAM_TOKEN).post_init(handlers.post_init).build()
    )

    # Existing handlers
    folder_conv_handler = ConversationHandler(
        entry_points=[
            CommandHandler("folder", handlers.folder),
            CommandHandler("start", handlers.start),
        ],
        states={
            WAITING_FOR_FOLDER_PATH: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.set_folder)
            ],
        },
        fallbacks=[],
    )

    ask_conv_handler = ConversationHandler(
        entry_points=[CommandHandler("ask", handlers.ask)],
        states={
            WAITING_FOR_QUESTION: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.ask_question)
            ],
        },
        fallbacks=[],
    )

    conversation_handler = ConversationHandler(
        entry_points=[CommandHandler('gdrive_folder', bot_handlers.gdrive_folder)],
        states={
            WAITING_FOR_GDRIVE_FOLDER_ID: [
                MessageHandler(filters.TEXT & ~filters.COMMAND, bot_handlers.set_gdrive_folder)
            ],
            # ... other states
        },
        fallbacks=[],
    )

    application.add_handler(CommandHandler("status", handlers.status))
    application.add_handler(CommandHandler("knowledge_base", handlers.knowledge_base))
    application.add_handler(folder_conv_handler)
    application.add_handler(ask_conv_handler)
    application.add_handler(project_conv_handler)
    application.add_handler(
        CallbackQueryHandler(handlers.handle_question_callback, pattern=r'^ask_question:')
    )

    # Handler for file download
    application.add_handler(CallbackQueryHandler(handlers.send_file, pattern=r'^get_file:'))

    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, handlers.handle_message)
    )

    application.add_error_handler(error_handler)

    application.run_polling()


if __name__ == "__main__":
    start_server()
    main()
