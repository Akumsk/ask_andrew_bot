# exception_handlers.py
import os
import logging
from telegram import Update
from telegram.ext import ContextTypes

from datetime import datetime
from dotenv import load_dotenv
from db_service import DatabaseService

# Initialize the DatabaseService
db_service = DatabaseService()


async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    """Handle exceptions that occur during update processing."""
    logging.error(msg="Exception while handling an update:", exc_info=context.error)
    if update and update.effective_message:
        await update.effective_message.reply_text(
            "An unexpected error occurred. Please try again later."
        )


def handle_telegram_context_length_exceeded_error(error, user_id, data_context):
    exception_id = "context_length_exceeded"
    exception_type = type(error).__name__
    exception_message = str(error)
    stack_trace = "No stack trace available for context length exceeded."
    occurred_at = (
        datetime.now().date().strftime("%Y-%m-%d")
        + ", "
        + datetime.now().time().strftime("%H:%M:%S")
    )
    resolved = False

    db_service.log_exception(
        exception_id=exception_id,
        exception_type=exception_type,
        exception_message=exception_message,
        stack_trace=stack_trace,
        occurred_at=occurred_at,
        user_id=user_id,
        data_context=data_context,
        resolved=resolved,
    )
