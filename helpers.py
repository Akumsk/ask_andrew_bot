from datetime import datetime
import re
from telegram import Update, InlineKeyboardMarkup
from telegram.ext import ContextTypes
from langchain.schema import Document, HumanMessage, AIMessage


def messages_to_langchain_messages(chat_history_texts):

    # Convert chat_history_texts to list of HumanMessage and AIMessage
    chat_history = []
    for msg in chat_history_texts:
        if msg.startswith("HumanMessage:"):
            content = msg[len("HumanMessage:") :].strip()
            chat_history.append(HumanMessage(content=content))
        elif msg.startswith("AIMessage:"):
            content = msg[len("AIMessage:") :].strip()
            chat_history.append(AIMessage(content=content))

    return chat_history

def current_timestamp():
    date_time = (
            datetime.now().date().strftime("%Y-%m-%d")
            + ", "
            + datetime.now().time().strftime("%H:%M:%S")
    )
    return date_time




def escape_markdown_v2(text: str) -> str:
    """
    Escapes special characters for MarkdownV2 formatting in Telegram messages.

    Args:
        text (str): The text to escape.

    Returns:
        str: The escaped text.
    """
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return re.sub(r'([%s])' % re.escape(escape_chars), r'\\\1', text)

async def send_formatted_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    text: str,
    reply_markup: InlineKeyboardMarkup = None,
    parse_mode: str = 'Markdown'
):
    """
    Sends a formatted message to the user, handling both regular messages and callback queries.

    Args:
        update (Update): The incoming update.
        context (ContextTypes.DEFAULT_TYPE): The context of the update.
        text (str): The message text to send.
        reply_markup (InlineKeyboardMarkup, optional): Inline keyboard markup. Defaults to None.
        parse_mode (str, optional): The parse mode for formatting. Defaults to 'Markdown'.
    """
    if parse_mode == 'MarkdownV2':
        text = escape_markdown_v2(text)

    if update.message:
        await update.message.reply_text(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )
    elif update.callback_query:
        await update.callback_query.message.reply_text(
            text,
            parse_mode=parse_mode,
            reply_markup=reply_markup
        )