# handlers.py

import logging
import os
import uuid
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from settings import PROJECT_PATHS, MAX_TOKENS_IN_CONTEXT, KNOWLEDGE_BASE_PATH, CHAT_HISTORY_LEVEL, FOLLOWING_QUESTIONS
from db_service import DatabaseService
from llm_service import LLMService
from helpers import messages_to_langchain_messages, send_formatted_message, escape_markdown_v2
from auth.auth import AuthService

# Decorators:
def authorized_only(func):
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        user = update.effective_user
        user_id = user.id
        user_name = user.full_name
        language_code = user.language_code

        # Initialize db_service in context if not already present
        if 'db_service' not in context.user_data:
            context.user_data['db_service'] = DatabaseService()

        # Save or update user info
        self.auth_service.save_user_info(user_id, user_name, language_code)

        # Check if user has access
        if not self.auth_service.check_user_access(user_id):
            if update.message:
                await update.message.reply_text("You do not have access, please make the /request_access.")
            elif update.callback_query:
                await update.callback_query.answer("You do not have access, please make the /request_access.", show_alert=True)
            return
        else:
            # Update last_active
            self.auth_service.update_last_active(user_id)

        return await func(self, update, context, *args, **kwargs)
    return wrapper

def initialize_services(func):
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if 'db_service' not in context.user_data:
            context.user_data['db_service'] = DatabaseService()
        if 'llm_service' not in context.user_data:
            context.user_data['llm_service'] = LLMService()
        if 'user_id' not in context.user_data:
            context.user_data['user_id'] = update.effective_user.id
        if 'user_name' not in context.user_data:
            context.user_data['user_name'] = update.effective_user.full_name
        if 'language_code' not in context.user_data:
            context.user_data['language_code'] = update.effective_user.language_code
        return await func(self, update, context, *args, **kwargs)
    return wrapper

def ensure_documents_indexed(func):
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
        if not context.user_data.get("vector_store_loaded", False):
            system_response = "Documents are not indexed yet. Use /folder or /knowledge_base first."
            await update.message.reply_text(system_response)
            return ConversationHandler.END
        valid_files_in_folder = context.user_data.get("valid_files_in_folder", [])
        if not valid_files_in_folder:
            system_response = "No valid documents found in the folder. Please add documents to the folder."
            await update.message.reply_text(system_response)
            return ConversationHandler.END
        return await func(self, update, context, *args, **kwargs)
    return wrapper

def log_event(event_type):
    def decorator(func):
        async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args, **kwargs):
            # Before executing the handler function
            user_id = update.effective_user.id
            user_message = update.message.text if update.message else ''
            conversation_id = str(uuid.uuid4())

            # Execute the handler function
            result = await func(self, update, context, *args, **kwargs)

            # After executing the handler function
            # Retrieve system_response from context.user_data
            system_response = context.user_data.get('system_response', '')

            # Access db_service
            db_service = context.user_data.get('db_service')
            if db_service:
                db_service.save_event_log(
                    user_id=user_id,
                    event_type=event_type,
                    user_message=user_message,
                    system_response=system_response,
                    conversation_id=conversation_id,
                )
            else:
                logging.error("db_service not found in context.user_data")

            return result
        return wrapper
    return decorator

WAITING_FOR_FOLDER_PATH, WAITING_FOR_QUESTION, WAITING_FOR_PROJECT_SELECTION = range(3)

class BotHandlers:
    def __init__(self):
        self.auth_service = AuthService()

    async def post_init(self, application):
        commands = [
            BotCommand("start", "Display introduction message"),
            BotCommand("folder", "Set folder path for documents"),
            BotCommand("projects", "Select a project from predefined options"),
            BotCommand("ask", "Ask a question about documents"),
            BotCommand("status", "Display current status and information"),
            BotCommand("knowledge_base", "Set context to knowledge base"),
            BotCommand("request_access", "Request access to the bot"),
            BotCommand("grant_access", "Grant access to a user (Admin only)"),
        ]
        await application.bot.set_my_commands(commands)

    @initialize_services
    @log_event(event_type='command')
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = context.user_data['user_id']
        user_name = context.user_data['user_name']
        language_code = context.user_data['language_code']

        # Save or update user info
        self.auth_service.save_user_info(user_id, user_name, language_code)

        db_service = context.user_data["db_service"]
        llm_service = context.user_data["llm_service"]

        # Try to get the last folder from the database for the user
        last_folder = db_service.get_last_folder(user_id)

        if last_folder and os.path.isdir(last_folder):
            context.user_data["folder_path"] = last_folder
            valid_files_in_folder = [
                f
                for f in os.listdir(last_folder)
                if f.endswith((".pdf", ".docx", ".xlsx"))
            ]
            context.user_data["valid_files_in_folder"] = valid_files_in_folder

            if valid_files_in_folder:
                index_status = llm_service.load_and_index_documents(last_folder)
                if index_status != "Documents successfully indexed.":
                    logging.error(
                        f"Error during load_and_index_documents: {index_status}"
                    )
                    await update.message.reply_text(
                        "An error occurred while loading and indexing your documents. Please try again later."
                    )
                    return

                context.user_data["vector_store_loaded"] = True

                # Evaluate token count
                token_count = llm_service.count_tokens_in_context(last_folder)
                percentage_full = (
                    (token_count / MAX_TOKENS_IN_CONTEXT) * 100
                    if MAX_TOKENS_IN_CONTEXT
                    else 0
                )
                percentage_full = min(percentage_full, 100)

                system_response = (
                    f"Welcome back, {user_name}! I have loaded your previous folder for context:\n\n"
                    f"{last_folder}\n\n"
                    f"Context storage is {percentage_full:.2f}% full.\n\n"
                    "You can specify any folder using /folder or select a project using /projects.\n"
                    "/start - Display this introduction message.\n"
                    "/ask - Ask a question about your documents.\n"
                    "/status - Display your current settings.\n"
                    "/knowledge_base - Set the context to the knowledge base.\n"
                    "Send any message without a command to ask a question."
                )
                await update.message.reply_text(system_response)
            else:
                system_response = f"Welcome back, {user_name}! However, no valid files were found in your last folder: {last_folder}."
                await update.message.reply_text(system_response)
        else:
            system_response = (
                "Welcome to the AI document assistant bot! This bot generates responses using documents "
                "in a specified folder. You can interact with the bot using the following commands:\n\n"
                "/start - Display this introduction message.\n"
                "/folder - Set the folder path where your documents are located.\n"
                "/projects - Select a project folder from predefined options.\n"
                "/ask - Ask a question about the documents.\n"
                "/status - Display your current settings.\n"
                "/knowledge_base - Set the context to the knowledge base.\n"
                "Send any message without a command to ask a question."
            )
            await update.message.reply_text(system_response)

        # Store system_response in context.user_data
        context.user_data['system_response'] = system_response

    @authorized_only
    @initialize_services
    @log_event(event_type='command')
    async def projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /projects command."""

        user_id = context.user_data['user_id']
        conversation_id = str(uuid.uuid4())
        user_message = '/projects'

        keyboard = [
            [InlineKeyboardButton(project_name, callback_data=project_name)]
            for project_name in PROJECT_PATHS.keys()
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        system_response = "Please select a project:"

        await update.message.reply_text(system_response, reply_markup=reply_markup)

        # Store system_response in context.user_data
        context.user_data['system_response'] = system_response

        return WAITING_FOR_PROJECT_SELECTION

    @authorized_only
    @initialize_services
    @log_event(event_type='command')
    async def handle_project_selection_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle project selection via callback data after /projects command."""

        db_service = context.user_data["db_service"]
        llm_service = context.user_data["llm_service"]

        query = update.callback_query
        await query.answer()
        user_choice = query.data
        user_id = query.from_user.id
        user_name = query.from_user.full_name

        folder_path = PROJECT_PATHS.get(user_choice)

        if folder_path:
            # Check if the folder path exists
            if not os.path.isdir(folder_path):
                system_response = "The selected project's folder path does not exist."
                await query.edit_message_text(system_response)
                context.user_data['system_response'] = system_response
                return ConversationHandler.END

            # Check for valid files
            valid_files_in_folder = [
                f
                for f in os.listdir(folder_path)
                if f.endswith((".pdf", ".docx", ".xlsx"))
            ]
            if not valid_files_in_folder:
                system_response = "No valid files found in the selected project's folder."
                await query.edit_message_text(system_response)

                context.user_data['system_response'] = system_response

                return ConversationHandler.END

            # Set user-specific folder path and process the documents
            context.user_data["folder_path"] = folder_path
            context.user_data["valid_files_in_folder"] = valid_files_in_folder
            index_status = llm_service.load_and_index_documents(folder_path)
            if index_status != "Documents successfully indexed.":
                logging.error(f"Error during load_and_index_documents: {index_status}")
                system_response = "An error occurred while loading and indexing the project documents. Please try again later."
                await query.edit_message_text(system_response)
                context.user_data['system_response'] = system_response
                return ConversationHandler.END

            context.user_data["vector_store_loaded"] = True

            # Evaluate token count
            token_count = llm_service.count_tokens_in_context(folder_path)
            percentage_full = (
                (token_count / MAX_TOKENS_IN_CONTEXT) * 100
                if MAX_TOKENS_IN_CONTEXT
                else 0
            )
            percentage_full = min(percentage_full, 100)

            system_response = (
                f"Project folder path set to: {folder_path}\n\nValid files have been indexed.\n\n"
                f"Context storage is {percentage_full:.2f}% full."
            )
            await query.edit_message_text(system_response)

            # Save user info in database
            db_service.save_folder(
                user_id=user_id, user_name=user_name, folder=folder_path
            )

            # Prepare buttons with the three questions
            questions = FOLLOWING_QUESTIONS
            keyboard = [[InlineKeyboardButton(q, callback_data=f"ask_question:{q}")] for q in questions]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(
                "You can ask the following questions about the project:",
                reply_markup=reply_markup
            )

        else:
            system_response = "Invalid selection or project is not available. Please select a valid project."
            await query.edit_message_text(system_response)

            context.user_data['system_response'] = system_response

            return ConversationHandler.END

        return ConversationHandler.END

    @authorized_only
    @initialize_services
    @log_event(event_type='ai_conversation')
    async def handle_question_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the question buttons after project selection."""
        query = update.callback_query
        await query.answer()
        data = query.data
        if data.startswith("ask_question:"):
            question = data[len("ask_question:"):]
            # Now, process the question as if the user asked it

            user_id = context.user_data["user_id"]
            conversation_id = str(uuid.uuid4())

            db_service = context.user_data["db_service"]
            db_service.save_message(conversation_id, "user", user_id, question)

            chat_history_texts = db_service.get_chat_history(CHAT_HISTORY_LEVEL, user_id)
            # Convert chat_history_texts to list of HumanMessage and AIMessage
            chat_history = messages_to_langchain_messages(chat_history_texts)

            llm_service = context.user_data["llm_service"]

            try:
                response, source_files = llm_service.generate_response(
                    question, chat_history=chat_history
                )
            except Exception as e:
                logging.error(f"Error during generate_response: {e}")
                system_response = "An error occurred while processing your question. Please try again later."
                await query.message.reply_text(system_response)

                context.user_data['system_response'] = system_response
                return

            # Prepare the bot's response
            bot_message = f"{response}\n\nReferences:"

            if source_files:
                # Initialize or retrieve the file ID mapping
                file_id_mapping = context.user_data.get('file_id_mapping', {})
                keyboard = []
                for file in source_files:
                    # Generate a short unique ID
                    file_id = str(uuid.uuid4())[:8]
                    file_id_mapping[file_id] = file
                    keyboard.append([InlineKeyboardButton(file, callback_data=f"get_file:{file_id}")])

                context.user_data['file_id_mapping'] = file_id_mapping
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.message.reply_text(bot_message, reply_markup=reply_markup)
            else:
                await query.message.reply_text(response)

            # Save the bot's message
            db_service.save_message(conversation_id, "bot", None, bot_message)
            context.user_data['system_response'] = bot_message

    @authorized_only
    @initialize_services
    @log_event(event_type='command')
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /status command."""
        llm_service = context.user_data["llm_service"]
        user_name = update.effective_user.full_name
        user_id = context.user_data["user_id"]
        user_message = '/status'
        conversation_id = str(uuid.uuid4())
        folder_path = context.user_data.get("folder_path", "")
        valid_files_in_folder = context.user_data.get("valid_files_in_folder", [])

        if not folder_path:
            system_response = (
                f"Status Information:\n\n"
                f"Name: {user_name}\n"
                "No folder path has been set yet. Please set it using the /folder command."
            )
            await update.message.reply_text(system_response)
        else:
            if valid_files_in_folder:
                file_list = "\n".join(valid_files_in_folder)
                folder_info = (
                    f"The folder path is currently set to: {folder_path}\n\n"
                    f"Valid Files:\n{file_list}"
                )

                # Evaluate token count
                token_count = llm_service.count_tokens_in_context(folder_path)
                percentage_full = (
                    (token_count / MAX_TOKENS_IN_CONTEXT) * 100
                    if MAX_TOKENS_IN_CONTEXT
                    else 0
                )
                percentage_full = min(percentage_full, 100)

                system_response = (
                    f"Status Information:\n\n"
                    f"Name: {user_name}\n"
                    f"{folder_info}\n\n"
                    f"Context storage is {percentage_full:.2f}% full."
                )
                await update.message.reply_text(system_response)
            else:
                system_response = (
                    f"Status Information:\n\n"
                    f"Name: {user_name}\n"
                    f"The folder path is currently set to: {folder_path}, but no valid files were found."
                )
                await update.message.reply_text(system_response)

            # Save event log
        db_service = context.user_data.get("db_service")
        context.user_data['system_response'] = system_response

    @authorized_only
    @initialize_services
    @log_event(event_type='command')
    async def folder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /folder command."""
        user_id = update.effective_user.id
        user_message = '/folder'
        conversation_id = str(uuid.uuid4())
        system_response = "Please provide the folder path for your documents:"
        await update.message.reply_text(system_response)

        # Save event log
        db_service = context.user_data["db_service"]
        context.user_data['system_response'] = system_response

        return WAITING_FOR_FOLDER_PATH

    @authorized_only
    @initialize_services
    @log_event(event_type='command')
    async def set_folder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set the folder path after receiving it from the user."""
        db_service = context.user_data["db_service"]
        llm_service = context.user_data["llm_service"]

        folder_path = update.message.text.strip()
        user_id = context.user_data["user_id"]
        user_name = update.effective_user.full_name
        user_message = folder_path
        conversation_id = str(uuid.uuid4())

        # Check if the folder path exists
        if not os.path.isdir(folder_path):
            system_response = "Invalid folder path. Please provide a valid path."
            await update.message.reply_text(system_response)
            # Save event log
            context.user_data['system_response'] = system_response
            return ConversationHandler.END

        # Check for valid files
        valid_files_in_folder = [
            f for f in os.listdir(folder_path) if f.endswith((".pdf", ".docx", ".xlsx"))
        ]
        if not valid_files_in_folder:
            system_response = "No valid files found in the folder. Please provide a folder containing valid documents."
            await update.message.reply_text(system_response)
            # Save event log
            context.user_data['system_response'] = system_response
            return ConversationHandler.END

        # Set user-specific folder path and process the documents
        context.user_data["folder_path"] = folder_path
        context.user_data["valid_files_in_folder"] = valid_files_in_folder
        index_status = llm_service.load_and_index_documents(folder_path)
        if index_status != "Documents successfully indexed.":
            logging.error(f"Error during load_and_index_documents: {index_status}")
            system_response = "An error occurred while loading and indexing your documents. Please try again later."
            await update.message.reply_text(system_response)
            # Save event log
            context.user_data['system_response'] = system_response
            return ConversationHandler.END

        context.user_data["vector_store_loaded"] = True

        # Evaluate token count
        token_count = llm_service.count_tokens_in_context(folder_path)
        percentage_full = (
            (token_count / MAX_TOKENS_IN_CONTEXT) * 100 if MAX_TOKENS_IN_CONTEXT else 0
        )
        percentage_full = min(percentage_full, 100)

        system_response = (
            f"Folder path successfully set to: {folder_path}\n\nValid files have been indexed.\n\n"
            f"Context storage is {percentage_full:.2f}% full."
        )
        await update.message.reply_text(system_response)

        # Save user info in database
        db_service.save_folder(
            user_id=user_id, user_name=user_name, folder=folder_path
        )

        # Save event log
        context.user_data['system_response'] = system_response

        return ConversationHandler.END

    @authorized_only
    @initialize_services
    @log_event(event_type='command')
    async def knowledge_base(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /knowledge_base command."""

        db_service = context.user_data["db_service"]
        llm_service = context.user_data["llm_service"]

        folder_path = KNOWLEDGE_BASE_PATH
        user_id = context.user_data["user_id"]
        user_name = update.effective_user.full_name
        user_message = '/knowledge_base'
        conversation_id = str(uuid.uuid4())

        # Check if the folder path exists
        if not os.path.isdir(folder_path):
            system_response = "The knowledge base folder path does not exist."
            await update.message.reply_text(system_response)
            # Save event log
            context.user_data['system_response'] = system_response
            return

        # Check for valid files
        valid_files_in_folder = [
            f for f in os.listdir(folder_path) if f.endswith((".pdf", ".docx", ".xlsx"))
        ]
        if not valid_files_in_folder:
            system_response = "No valid files found in the knowledge base folder."
            await update.message.reply_text(system_response)
            # Save event log
            context.user_data['system_response'] = system_response
            return

        # Set user-specific folder path and process the documents
        context.user_data["folder_path"] = folder_path
        context.user_data["valid_files_in_folder"] = valid_files_in_folder
        index_status = llm_service.load_and_index_documents(folder_path)
        if index_status != "Documents successfully indexed.":
            logging.error(f"Error during load_and_index_documents: {index_status}")
            system_response = "An error occurred while loading and indexing the knowledge base documents. Please try again later."
            await update.message.reply_text(system_response)
            # Save event log
            context.user_data['system_response'] = system_response
            return

        context.user_data["vector_store_loaded"] = True

        # Evaluate token count
        token_count = llm_service.count_tokens_in_context(folder_path)
        percentage_full = (
            (token_count / MAX_TOKENS_IN_CONTEXT) * 100 if MAX_TOKENS_IN_CONTEXT else 0
        )
        percentage_full = min(percentage_full, 100)

        system_response = (
            f"Knowledge base folder path set to: {folder_path}\n\nValid files have been indexed.\n\n"
            f"Context storage is {percentage_full:.2f}% full."
        )
        await update.message.reply_text(system_response)

        # Save user info in database
        db_service.save_folder(
            user_id=user_id, user_name=user_name, folder=folder_path
        )

        # Save event log
        context.user_data['system_response'] = system_response

    @authorized_only
    @initialize_services
    @ensure_documents_indexed
    @log_event(event_type='command')
    async def ask(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /ask command."""

        system_response = "Please provide the question you want to ask about the documents:"
        await update.message.reply_text(system_response)

        # Save event log
        user_id = update.effective_user.id
        user_message = '/ask'
        conversation_id = str(uuid.uuid4())
        db_service = context.user_data.get("db_service")
        if not db_service:
            db_service = DatabaseService()
            context.user_data["db_service"] = db_service

        context.user_data['system_response'] = system_response

        return WAITING_FOR_QUESTION

    @authorized_only
    @initialize_services
    @ensure_documents_indexed
    @log_event(event_type='ai_conversation')
    async def ask_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        user_prompt = update.message.text
        user_id = context.user_data["user_id"]
        conversation_id = str(uuid.uuid4())

        db_service = context.user_data["db_service"]
        db_service.save_message(conversation_id, "user", user_id, user_prompt)

        chat_history_texts = db_service.get_chat_history(CHAT_HISTORY_LEVEL, user_id)
        # Convert chat_history_texts to list of HumanMessage and AIMessage
        chat_history = messages_to_langchain_messages(chat_history_texts)

        llm_service = context.user_data["llm_service"]

        try:
            response, source_files = llm_service.generate_response(
                user_prompt, chat_history=chat_history
            )
        except Exception as e:
            logging.error(f"Error during generate_response: {e}")
            system_response = "An error occurred while processing your question. Please try again later."
            await update.message.reply_text(system_response)
            # Save event log
            context.user_data['system_response'] = system_response
            return ConversationHandler.END

        # Prepare the bot's response
        bot_message = f"{response}\n\nReferences:"

        if source_files:
            # Create buttons for each source file
            keyboard = [
                [InlineKeyboardButton(file, callback_data=f"get_file:{file}")]
                for file in source_files
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await update.message.reply_text(bot_message, reply_markup=reply_markup)
        else:
            await update.message.reply_text(response)

        # Save the bot's message
        db_service.save_message(conversation_id, "bot", None, bot_message)

        # Save event log
        context.user_data['system_response'] = bot_message

        return ConversationHandler.END

    @authorized_only
    @initialize_services
    @ensure_documents_indexed
    @log_event(event_type='ai_conversation')
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle any text message sent by the user."""

        db_service = context.user_data["db_service"]
        llm_service = context.user_data["llm_service"]
        user_message = update.message.text
        user_id = context.user_data["user_id"]
        conversation_id = str(uuid.uuid4())

        # Save the user's message
        db_service.save_message(conversation_id, "user", user_id, user_message)

        chat_history_texts = db_service.get_chat_history(CHAT_HISTORY_LEVEL, user_id)
        # Convert chat_history_texts to list of HumanMessage and AIMessage
        chat_history = messages_to_langchain_messages(chat_history_texts)

        try:
            response, source_files = llm_service.generate_response(user_message, chat_history=chat_history)
        except Exception as e:
            logging.error(f"Error during generate_response: {e}")
            system_response = "An error occurred while processing your message. Please try again later."
            await send_formatted_message(update, context, system_response, parse_mode='MarkdownV2')
            # Save event log
            context.user_data['system_response'] = system_response
            return ConversationHandler.END

            # Prepare the bot's response
        bot_message = f"{response}"

        if source_files:
            # Initialize or retrieve the file ID mapping
            file_id_mapping = context.user_data.get('file_id_mapping', {})
            keyboard = []
            for file in source_files:
                # Generate a short unique ID
                file_id = str(uuid.uuid4())[:8]
                file_id_mapping[file_id] = file
                keyboard.append([InlineKeyboardButton(file, callback_data=f"get_file:{file_id}")])

            context.user_data['file_id_mapping'] = file_id_mapping
            reply_markup = InlineKeyboardMarkup(keyboard)
            await send_formatted_message(update, context, bot_message, reply_markup=reply_markup, parse_mode='MarkdownV2')
        else:
            await send_formatted_message(update, context, response, parse_mode='MarkdownV2')

        # Save the bot's message
        db_service.save_message(conversation_id, "bot", None, bot_message)

        context.user_data['system_response'] = bot_message

    @authorized_only
    @initialize_services
    async def send_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        if data.startswith("get_file:"):
            file_id = data[len("get_file:"):]
            file_id_mapping = context.user_data.get('file_id_mapping', {})
            file_name = file_id_mapping.get(file_id)
            if not file_name:
                await query.message.reply_text("File not found.")
                return
            folder_path = context.user_data.get("folder_path")
            if folder_path:
                file_path = os.path.join(folder_path, file_name)
                if os.path.isfile(file_path):
                    try:
                        with open(file_path, 'rb') as f:
                            await query.message.reply_document(document=f, filename=file_name)
                    except Exception as e:
                        logging.error(f"Error sending file: {e}")
                        await query.message.reply_text("An error occurred while sending the file.")
                else:
                    await query.message.reply_text("File not found.")
            else:
                await query.message.reply_text("Folder path not set.")
        else:
            await query.message.reply_text("Unknown command.")

    @log_event(event_type='command')
    async def request_access(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        user_id = user.id
        user_name = user.full_name
        username = user.username
        language_code = user.language_code

        # Initialize db_service in context if not already present
        if 'db_service' not in context.user_data:
            context.user_data['db_service'] = DatabaseService()

        # Save or update user info
        self.auth_service.save_user_info(user_id, user_name, language_code)

        # Send a notification to the admin
        admin_id = os.getenv("ADMIN_TELEGRAM_ID")
        message = f"Access request from {user_name} (@{username}), ID: {user_id}"
        await context.bot.send_message(chat_id=admin_id, text=message)

        # Inform the user
        system_response = "Your access request has been sent to the admin."
        await update.message.reply_text(system_response)
        context.user_data['system_response'] = system_response

    async def grant_access(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        admin_id = update.effective_user.id
        if str(admin_id) != os.getenv("ADMIN_TELEGRAM_ID"):
            await update.message.reply_text("You are not authorized to perform this action.")
            return

        try:
            user_id_to_grant = int(context.args[0])
            self.auth_service.grant_access(user_id_to_grant)
            await update.message.reply_text(f"User {user_id_to_grant} has been granted access.")
        except (IndexError, ValueError):
            await update.message.reply_text("Usage: /grant_access <user_id>")