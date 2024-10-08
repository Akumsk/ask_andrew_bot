# exception_handlers.py

import logging
from telegram import Update
from telegram.ext import ContextTypes

async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle exceptions that occur during update processing."""
    logging.error(msg="Exception while handling an update:", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "An unexpected error occurred. Please try again later."
        )