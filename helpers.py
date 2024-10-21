from datetime import datetime

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