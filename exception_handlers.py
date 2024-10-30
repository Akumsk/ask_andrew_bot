# exception_handlers.py
import os
import logging
import traceback  # Added missing import
from telegram import Update
from telegram.ext import ContextTypes

from datetime import datetime
from dotenv import load_dotenv
from db_service import DatabaseService

# Initialize the DatabaseService
db_service = DatabaseService()

async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Log the error and send a message to notify the developer."""
    # Log the error before we do anything else
    logging.error(msg="Exception while handling an update:", exc_info=context.error)

    # Gather exception information
    exception_type = type(context.error).__name__
    exception_message = str(context.error)
    stack_trace = ''.join(traceback.format_exception(None, context.error, context.error.__traceback__))
    occurred_at = datetime.now()
    user_id = update.effective_user.id if update and update.effective_user else None
    data_context = str(update.to_dict()) if update else "No update available"
    resolved = False

    # Log the exception to the database
    db_service.log_exception(
        exception_type=exception_type,
        exception_message=exception_message,
        stack_trace=stack_trace,
        occurred_at=occurred_at,
        user_id=user_id,
        data_context=data_context,
        resolved=resolved,
    )

    # Notify the user
    if update and update.message:
        await update.message.reply_text("An unexpected error occurred. The support team has been notified.")

def handle_telegram_context_length_exceeded_error(error, user_id, data_context):
    exception_type = "ContextLengthExceededError"
    exception_message = str(error)
    stack_trace = "No stack trace available for context length exceeded."
    occurred_at = datetime.now()
    resolved = False

    # Log the exception to the database
    db_service.log_exception(
        exception_type=exception_type,
        exception_message=exception_message,
        stack_trace=stack_trace,
        occurred_at=occurred_at,
        user_id=user_id,
        data_context=data_context,
        resolved=resolved,
    )
