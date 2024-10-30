# helpers.py

import os
from datetime import datetime
from functools import wraps
from telegram import Update
from telegram.ext import ContextTypes, ConversationHandler
from langchain.schema import HumanMessage, AIMessage

from settings import MAX_TOKENS_IN_CONTEXT


def ensure_services(func):
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if "db_service" not in context.user_data:
            from db_service import DatabaseService
            context.user_data["db_service"] = DatabaseService()
        if "llm_service" not in context.user_data:
            from llm_service import LLMService
            context.user_data["llm_service"] = LLMService()
        if "user_id" not in context.user_data:
            context.user_data["user_id"] = update.effective_user.id
        return await func(self, update, context, *args, **kwargs)
    return wrapper


def check_vector_store_loaded(func):
    @wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not context.user_data.get("vector_store_loaded", False):
            system_response = "Documents are not indexed yet. Use /folder or /knowledge_base first."
            await update.message.reply_text(system_response)
            return ConversationHandler.END
        return await func(self, update, context, *args, **kwargs)
    return wrapper


def messages_to_langchain_messages(chat_history_texts):
    # Convert chat_history_texts to list of HumanMessage and AIMessage
    chat_history = []
    for msg in chat_history_texts:
        if msg.startswith("HumanMessage:"):
            content = msg[len("HumanMessage:"):].strip()
            chat_history.append(HumanMessage(content=content))
        elif msg.startswith("AIMessage:"):
            content = msg[len("AIMessage:"):].strip()
            chat_history.append(AIMessage(content=content))
    return chat_history


def current_timestamp():
    date_time = (
        datetime.now().date().strftime("%Y-%m-%d")
        + ", "
        + datetime.now().time().strftime("%H:%M:%S")
    )
    return date_time
