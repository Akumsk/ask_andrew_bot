# handlers.py

import logging
import os
import uuid
import urllib.parse
from telegram import Update, BotCommand, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler

from settings import (
    PROJECT_PATHS,
    MAX_TOKENS_IN_CONTEXT,
    KNOWLEDGE_BASE_PATH,
    CHAT_HISTORY_LEVEL,
    FOLLOWING_QUESTIONS,
)
from helpers import (
    messages_to_langchain_messages,
    ensure_services,
    check_vector_store_loaded,
    calculate_percentage_full,
    get_valid_files_in_folder,
)

from gdrive_service import get_flow, save_credentials, build_service


WAITING_FOR_FOLDER_PATH, WAITING_FOR_QUESTION, WAITING_FOR_PROJECT_SELECTION = range(3)
WAITING_FOR_GDRIVE_FOLDER_ID = 4


class BotHandlers:
    def __init__(self):
        pass

    async def post_init(self, application):
        commands = [
            BotCommand("start", "Display introduction message"),
            BotCommand("folder", "Set folder path for documents"),
            BotCommand("projects", "Select a project from predefined options"),
            BotCommand("ask", "Ask a question about documents"),
            BotCommand("status", "Display current status and information"),
            BotCommand("knowledge_base", "Set context to knowledge base"),
        ]
        await application.bot.set_my_commands(commands)

    @ensure_services
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_name = update.effective_user.full_name
        user_message = "/start"
        conversation_id = str(uuid.uuid4())

        db_service = context.user_data["db_service"]
        llm_service = context.user_data["llm_service"]

        # Try to get the last folder from the database for the user
        last_folder = db_service.get_last_folder(user_id)

        if last_folder and os.path.isdir(last_folder):
            context.user_data["folder_path"] = last_folder
            valid_files_in_folder = get_valid_files_in_folder(last_folder)
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
                percentage_full = calculate_percentage_full(
                    token_count, MAX_TOKENS_IN_CONTEXT
                )

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
                system_response = (
                    f"Welcome back, {user_name}! However, no valid files were found in your last folder: {last_folder}."
                )
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
        # Save event log
        db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)

    @ensure_services
    async def projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /projects command."""
        user_id = update.effective_user.id
        conversation_id = str(uuid.uuid4())
        user_message = "/projects"

        keyboard = [
            [InlineKeyboardButton(project_name, callback_data=project_name)]
            for project_name in PROJECT_PATHS.keys()
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        system_response = "Please select a project:"
        await update.message.reply_text(system_response, reply_markup=reply_markup)

        # Save event log
        db_service = context.user_data.get("db_service")
        db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)

        return WAITING_FOR_PROJECT_SELECTION

    @ensure_services
    async def handle_project_selection_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle project selection via callback data after /projects command."""

        query = update.callback_query
        await query.answer()
        user_choice = query.data
        user_id = query.from_user.id
        conversation_id = str(uuid.uuid4())
        user_message = user_choice

        folder_path = PROJECT_PATHS.get(user_choice)

        db_service = context.user_data.get("db_service")
        llm_service = context.user_data.get("llm_service")

        if folder_path:
            user_id = update.effective_user.id
            user_name = update.effective_user.full_name

            # Check if the folder path exists
            if not os.path.isdir(folder_path):
                system_response = "The selected project's folder path does not exist."
                await query.edit_message_text(system_response)
                # Save event log
                db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id,
                )
                return ConversationHandler.END

            # Check for valid files
            valid_files_in_folder = get_valid_files_in_folder(folder_path)
            if not valid_files_in_folder:
                system_response = (
                    "No valid files found in the selected project's folder."
                )
                await query.edit_message_text(system_response)
                # Save event log
                db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
                return ConversationHandler.END

            # Set user-specific folder path and process the documents
            context.user_data["folder_path"] = folder_path
            context.user_data["valid_files_in_folder"] = valid_files_in_folder
            index_status = llm_service.load_and_index_documents(folder_path)
            if index_status != "Documents successfully indexed.":
                logging.error(
                    f"Error during load_and_index_documents: {index_status}"
                )
                system_response = (
                    "An error occurred while loading and indexing the project documents. Please try again later."
                )
                await query.edit_message_text(system_response)
                # Save event log
                db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
                return ConversationHandler.END

            context.user_data["vector_store_loaded"] = True

            # Evaluate token count
            token_count = llm_service.count_tokens_in_context(folder_path)
            percentage_full = calculate_percentage_full(
                token_count, MAX_TOKENS_IN_CONTEXT
            )

            system_response = (
                f"Project folder path set to: {folder_path}\n\nValid files have been indexed.\n\n"
                f"Context storage is {percentage_full:.2f}% full."
            )
            await query.edit_message_text(system_response)

            # Save user info in database
            db_service.save_folder(user_id, user_name, folder_path)

            # Prepare buttons with the three questions
            questions = FOLLOWING_QUESTIONS
            keyboard = [
                [InlineKeyboardButton(q, callback_data=f"ask_question:{q}")]
                for q in questions
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await query.message.reply_text(
                "Ask any project-related question by messaging the bot or use the suggested questions below:",
                reply_markup=reply_markup,
            )

        else:
            system_response = (
                "Invalid selection or project is not available. Please select a valid project."
            )
            await query.edit_message_text(system_response)
            # Save event log
            db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
            return ConversationHandler.END

        # Save event log
        db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)

        return ConversationHandler.END

    @ensure_services
    async def handle_question_callback(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle the question buttons after project selection."""
        query = update.callback_query
        await query.answer()
        data = query.data
        if data.startswith("ask_question:"):
            question = data[len("ask_question:") :]
            # Now, process the question as if the user asked it

            user_id = context.user_data.get("user_id")
            if not user_id:
                user_id = update.effective_user.id
                context.user_data["user_id"] = user_id

            conversation_id = str(uuid.uuid4())

            db_service = context.user_data.get("db_service")
            db_service.save_message(conversation_id, "user", user_id, question)

            chat_history_texts = db_service.get_chat_history(
                CHAT_HISTORY_LEVEL, user_id
            )
            # Convert chat_history_texts to list of HumanMessage and AIMessage
            chat_history = messages_to_langchain_messages(chat_history_texts)

            llm_service = context.user_data.get("llm_service")

            try:
                response, source_files = llm_service.generate_response(
                    question, chat_history=chat_history
                )
            except Exception as e:
                logging.error(f"Error during generate_response: {e}")
                system_response = (
                    "An error occurred while processing your question. Please try again later."
                )
                await query.message.reply_text(system_response)
                # Save event log
                db_service.save_event_log(user_id, "ai_conversation", question, system_response, conversation_id)
                return

            # Prepare the bot's response
            bot_message = f"{response}\n\nReferences:"

            if source_files:
                # Create buttons for each source file
                keyboard = [
                    [InlineKeyboardButton(file, callback_data=f"get_file:{file}")]
                    for file in source_files
                ]
                reply_markup = InlineKeyboardMarkup(keyboard)
                await query.message.reply_text(
                    bot_message, reply_markup=reply_markup
                )
            else:
                await query.message.reply_text(response)

            # Save the bot's message
            db_service.save_message(conversation_id, "bot", None, bot_message)

            # Save event log
            db_service.save_event_log(user_id, "ai_conversation", question, bot_message, conversation_id)

    @ensure_services
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /status command."""
        llm_service = context.user_data.get("llm_service")

        user_name = update.effective_user.full_name
        user_id = update.effective_user.id
        user_message = "/status"
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
                percentage_full = calculate_percentage_full(
                    token_count, MAX_TOKENS_IN_CONTEXT
                )

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
        db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)

    async def folder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /folder command."""
        user_id = update.effective_user.id
        user_message = "/folder"
        conversation_id = str(uuid.uuid4())
        system_response = "Please provide the folder path for your documents:"
        await update.message.reply_text(system_response)

        # Save event log
        db_service = context.user_data.get("db_service")
        db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)

        return WAITING_FOR_FOLDER_PATH

    @ensure_services
    async def set_folder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set the folder path after receiving it from the user."""
        db_service = context.user_data.get("db_service")
        llm_service = context.user_data.get("llm_service")

        folder_path = update.message.text.strip()
        user_id = update.effective_user.id
        user_name = update.effective_user.full_name
        user_message = folder_path
        conversation_id = str(uuid.uuid4())

        # Check if the folder path exists
        if not os.path.isdir(folder_path):
            system_response = (
                "Invalid folder path. Please provide a valid path."
            )
            await update.message.reply_text(system_response)
            # Save event log
            db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
            return ConversationHandler.END

        # Check for valid files
        valid_files_in_folder = get_valid_files_in_folder(folder_path)
        if not valid_files_in_folder:
            system_response = (
                "No valid files found in the folder. Please provide a folder containing valid documents."
            )
            await update.message.reply_text(system_response)
            # Save event log
            db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
            return ConversationHandler.END

        # Set user-specific folder path and process the documents
        context.user_data["folder_path"] = folder_path
        context.user_data["valid_files_in_folder"] = valid_files_in_folder
        index_status = llm_service.load_and_index_documents(folder_path)
        if index_status != "Documents successfully indexed.":
            logging.error(
                f"Error during load_and_index_documents: {index_status}"
            )
            system_response = (
                "An error occurred while loading and indexing your documents. Please try again later."
            )
            await update.message.reply_text(system_response)
            # Save event log
            db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
            return ConversationHandler.END

        context.user_data["vector_store_loaded"] = True

        # Evaluate token count
        token_count = llm_service.count_tokens_in_context(folder_path)
        percentage_full = calculate_percentage_full(
            token_count, MAX_TOKENS_IN_CONTEXT
        )

        system_response = (
            f"Folder path successfully set to: {folder_path}\n\nValid files have been indexed.\n\n"
            f"Context storage is {percentage_full:.2f}% full."
        )
        await update.message.reply_text(system_response)

        # Save user info in database
        db_service.save_folder(user_id, user_name, folder_path)

        # Save event log
        db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)

        return ConversationHandler.END

    @ensure_services
    async def knowledge_base(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /knowledge_base command."""

        db_service = context.user_data.get("db_service")
        llm_service = context.user_data.get("llm_service")

        folder_path = KNOWLEDGE_BASE_PATH
        user_id = update.effective_user.id
        user_name = update.effective_user.full_name
        user_message = "/knowledge_base"
        conversation_id = str(uuid.uuid4())

        # Check if the folder path exists
        if not os.path.isdir(folder_path):
            system_response = "The knowledge base folder path does not exist."
            await update.message.reply_text(system_response)
            # Save event log
            db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
            return

        # Check for valid files
        valid_files_in_folder = get_valid_files_in_folder(folder_path)
        if not valid_files_in_folder:
            system_response = (
                "No valid files found in the knowledge base folder."
            )
            await update.message.reply_text(system_response)
            # Save event log
            db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
            return

        # Set user-specific folder path and process the documents
        context.user_data["folder_path"] = folder_path
        context.user_data["valid_files_in_folder"] = valid_files_in_folder
        index_status = llm_service.load_and_index_documents(folder_path)
        if index_status != "Documents successfully indexed.":
            logging.error(
                f"Error during load_and_index_documents: {index_status}"
            )
            system_response = (
                "An error occurred while loading and indexing the knowledge base documents. Please try again later."
            )
            await update.message.reply_text(system_response)
            # Save event log
            db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
            return

        context.user_data["vector_store_loaded"] = True

        # Evaluate token count
        token_count = llm_service.count_tokens_in_context(folder_path)
        percentage_full = calculate_percentage_full(
            token_count, MAX_TOKENS_IN_CONTEXT
        )

        system_response = (
            f"Knowledge base folder path set to: {folder_path}\n\nValid files have been indexed.\n\n"
            f"Context storage is {percentage_full:.2f}% full."
        )
        await update.message.reply_text(system_response)

        # Save user info in database
        db_service.save_folder(user_id, user_name, folder_path)

        # Save event log
        db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)

    @ensure_services
    @check_vector_store_loaded
    async def ask(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /ask command."""

        valid_files_in_folder = context.user_data.get("valid_files_in_folder", [])
        if not valid_files_in_folder:
            system_response = (
                "No valid documents found in the folder. Please add documents to the folder."
            )
            await update.message.reply_text(system_response)
            return ConversationHandler.END

        system_response = (
            "Please provide the question you want to ask about the documents:"
        )
        await update.message.reply_text(system_response)

        # Save event log
        user_id = update.effective_user.id
        user_message = "/ask"
        conversation_id = str(uuid.uuid4())
        db_service = context.user_data.get("db_service")
        db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)

        return WAITING_FOR_QUESTION

    @ensure_services
    @check_vector_store_loaded
    async def ask_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):

        user_prompt = update.message.text
        user_id = context.user_data.get("user_id")

        if not user_id:
            user_id = update.effective_user.id
            context.user_data["user_id"] = user_id

        conversation_id = str(uuid.uuid4())

        db_service = context.user_data.get("db_service")
        db_service.save_message(conversation_id, "user", user_id, user_prompt)

        chat_history_texts = db_service.get_chat_history(CHAT_HISTORY_LEVEL, user_id)
        # Convert chat_history_texts to list of HumanMessage and AIMessage
        chat_history = messages_to_langchain_messages(chat_history_texts)

        llm_service = context.user_data.get("llm_service")

        try:
            response, source_files = llm_service.generate_response(
                user_prompt, chat_history=chat_history
            )
        except Exception as e:
            logging.error(f"Error during generate_response: {e}")
            system_response = (
                "An error occurred while processing your question. Please try again later."
            )
            await update.message.reply_text(system_response)
            # Save event log
            db_service.save_event_log(user_id, "ai_conversation", user_prompt, system_response, conversation_id)
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
        db_service.save_event_log(user_id, "ai_conversation", user_prompt, bot_message, conversation_id)

        return ConversationHandler.END

    @ensure_services
    @check_vector_store_loaded
    async def handle_message(
        self, update: Update, context: ContextTypes.DEFAULT_TYPE
    ):
        """Handle any text message sent by the user."""

        db_service = context.user_data.get("db_service")
        llm_service = context.user_data.get("llm_service")

        if not context.user_data.get("vector_store_loaded", False):
            system_response = (
                "Documents are not indexed yet. Use /folder or /knowledge_base first."
            )
            await update.message.reply_text(system_response)
            return

        valid_files_in_folder = context.user_data.get("valid_files_in_folder", [])
        if not valid_files_in_folder:
            system_response = (
                "No valid documents found in the folder. Please add documents to the folder."
            )
            await update.message.reply_text(system_response)
            return

        user_message = update.message.text
        user_id = update.effective_user.id
        conversation_id = str(uuid.uuid4())

        # Save the user's message
        db_service.save_message(conversation_id, "user", user_id, user_message)

        chat_history_texts = db_service.get_chat_history(CHAT_HISTORY_LEVEL, user_id)
        # Convert chat_history_texts to list of HumanMessage and AIMessage
        chat_history = messages_to_langchain_messages(chat_history_texts)

        try:
            response, source_files = llm_service.generate_response(user_message, chat_history)
        except Exception as e:
            logging.error(f"Error during generate_response: {e}")
            system_response = (
                "An error occurred while processing your message. Please try again later."
            )
            await update.message.reply_text(system_response)
            # Save event log
            db_service.save_event_log(user_id, "ai_conversation", user_message, system_response, conversation_id)
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
        db_service.save_event_log(user_id, "ai_conversation", user_message, bot_message, conversation_id)

    @ensure_services
    async def send_file(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        if data.startswith("get_file:"):
            file_name = data[len("get_file:") :]
            folder_path = context.user_data.get("folder_path")
            if folder_path:
                file_path = os.path.join(folder_path, file_name)
                if os.path.isfile(file_path):
                    try:
                        with open(file_path, "rb") as f:
                            await query.message.reply_document(
                                document=f, filename=file_name
                            )
                    except Exception as e:
                        logging.error(f"Error sending file: {e}")
                        await query.message.reply_text(
                            "An error occurred while sending the file."
                        )
                else:
                    await query.message.reply_text("File not found.")
            else:
                await query.message.reply_text("Folder path not set.")
        else:
            await query.message.reply_text("Unknown command.")

    @ensure_services
    async def gdrive_folder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /gdrive_folder command."""
        user_id = update.effective_user.id
        user_message = "/gdrive_folder"
        conversation_id = str(uuid.uuid4())
        system_response = "Please authorize access to your Google Drive by clicking the link below."

        flow = get_flow(str(user_id))
        auth_url, _ = flow.authorization_url(prompt='consent', include_granted_scopes='true')

        await update.message.reply_text(f"{system_response}\n{auth_url}")

        # Save the flow in context to retrieve later
        context.user_data['flow'] = flow

        # Save event log
        db_service = context.user_data.get("db_service")
        db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)

        return WAITING_FOR_GDRIVE_FOLDER_ID

    @ensure_services
    async def set_gdrive_folder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set the Google Drive folder after receiving the folder ID from the user."""
        db_service = context.user_data.get("db_service")
        llm_service = context.user_data.get("llm_service")

        folder_id = update.message.text.strip()
        user_id = str(update.effective_user.id)
        user_name = update.effective_user.full_name
        user_message = folder_id
        conversation_id = str(uuid.uuid4())

        # Build the service using user's credentials
        service = build_service(user_id)
        if not service:
            system_response = "Authorization not completed or failed. Please try /gdrive_folder again."
            await update.message.reply_text(system_response)
            db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
            return ConversationHandler.END

        # Local folder to store the downloaded files
        local_folder = os.path.join('/tmp', 'gdrive_files', user_id, folder_id)

        # Download all files in the folder
        try:
            download_all_files_in_folder(service, folder_id, local_folder)
        except Exception as e:
            logging.error(f"Failed to download files from Google Drive: {e}")
            system_response = "Failed to download files from Google Drive. Please check the folder ID."
            await update.message.reply_text(system_response)
            db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
            return ConversationHandler.END

        # Now proceed as you do with local folders
        valid_files_in_folder = get_valid_files_in_folder(local_folder)
        if not valid_files_in_folder:
            system_response = (
                "No valid files found in the Google Drive folder. Please provide a folder containing valid documents."
            )
            await update.message.reply_text(system_response)
            db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
            return ConversationHandler.END

        # Set user-specific folder path and process the documents
        context.user_data["folder_path"] = local_folder
        context.user_data["valid_files_in_folder"] = valid_files_in_folder
        index_status = llm_service.load_and_index_documents(local_folder)
        if index_status != "Documents successfully indexed.":
            logging.error(f"Error during load_and_index_documents: {index_status}")
            system_response = (
                "An error occurred while loading and indexing your documents. Please try again later."
            )
            await update.message.reply_text(system_response)
            db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)
            return ConversationHandler.END

        context.user_data["vector_store_loaded"] = True

        # Evaluate token count
        token_count = llm_service.count_tokens_in_context(local_folder)
        percentage_full = calculate_percentage_full(token_count, MAX_TOKENS_IN_CONTEXT)

        system_response = (
            f"Google Drive folder successfully set. Valid files have been downloaded and indexed.\n\n"
            f"Context storage is {percentage_full:.2f}% full."
        )
        await update.message.reply_text(system_response)

        # Save user info in database
        db_service.save_folder(user_id, user_name, local_folder)

        # Save event log
        db_service.save_event_log(user_id, "command", user_message, system_response, conversation_id)

        return ConversationHandler.END