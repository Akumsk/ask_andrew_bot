# handlers.py

import logging
import os
from telegram import Update, BotCommand
from telegram.ext import ContextTypes, ConversationHandler

from settings import PROJECT_PATHS, MAX_TOKENS_IN_CONTEXT, KNOWLEDGE_BASE_PATH
from db_service import DatabaseService
from llm_service import LLMService

WAITING_FOR_FOLDER_PATH, WAITING_FOR_QUESTION, WAITING_FOR_PROJECT_SELECTION = range(3)


class BotHandlers:
    def __init__(self, llm_service: LLMService, db_service: DatabaseService):
        self.llm_service = llm_service
        self.db_service = db_service

    async def post_init(self, application):
        commands = [
            BotCommand("start", "Display introduction message"),
            BotCommand("folder", "Set folder path for documents"),
            BotCommand("projects", "Select a project from predefined options"),
            BotCommand("ask", "Ask a question about documents"),
            BotCommand("status", "Display current status and information"),
            BotCommand("knowledge_base", "Set context to knowledge base")
        ]
        await application.bot.set_my_commands(commands)

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = update.effective_user.id
        user_name = update.effective_user.full_name

        context.user_data['folder_path'] = ""
        context.user_data['vector_store_loaded'] = False
        context.user_data['valid_files_in_folder'] = []

        # Try to get the last folder from the database for the user
        last_folder = self.db_service.get_last_folder(user_id)

        if last_folder and os.path.isdir(last_folder):
            context.user_data['folder_path'] = last_folder
            valid_files_in_folder = [
                f for f in os.listdir(last_folder)
                if f.endswith((".pdf", ".docx", ".xlsx"))
            ]
            context.user_data['valid_files_in_folder'] = valid_files_in_folder

            if valid_files_in_folder:
                index_status = self.llm_service.load_and_index_documents(last_folder)
                if index_status != "Documents successfully indexed.":
                    logging.error(f"Error during load_and_index_documents: {index_status}")
                    await update.message.reply_text(
                        "An error occurred while loading and indexing your documents. Please try again later."
                    )
                    return

                context.user_data['vector_store_loaded'] = True

                # Evaluate token count
                token_count = self.llm_service.count_tokens_in_context(last_folder)
                percentage_full = (token_count / MAX_TOKENS_IN_CONTEXT) * 100 if MAX_TOKENS_IN_CONTEXT else 0
                percentage_full = min(percentage_full, 100)

                await update.message.reply_text(
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
            else:
                await update.message.reply_text(
                    f"Welcome back, {user_name}! However, no valid files were found in your last folder: {last_folder}."
                )
        else:
            await update.message.reply_text(
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

    async def projects(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /projects command."""
        projects_list = "\n".join([f"{key}" for key in PROJECT_PATHS])
        await update.message.reply_text(f"Please select a project:\n{projects_list}")
        return WAITING_FOR_PROJECT_SELECTION

    async def handle_project_selection(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle project selection after /projects command."""
        user_choice = update.message.text.strip()

        folder_path = PROJECT_PATHS.get(user_choice)

        if folder_path:
            user_id = update.effective_user.id
            user_name = update.effective_user.full_name

            # Check if the folder path exists
            if not os.path.isdir(folder_path):
                await update.message.reply_text("The selected project's folder path does not exist.")
                return ConversationHandler.END

            # Check for valid files
            valid_files_in_folder = [
                f for f in os.listdir(folder_path)
                if f.endswith((".pdf", ".docx", ".xlsx"))
            ]
            if not valid_files_in_folder:
                await update.message.reply_text(
                    "No valid files found in the selected project's folder."
                )
                return ConversationHandler.END

            # Set user-specific folder path and process the documents
            context.user_data['folder_path'] = folder_path
            context.user_data['valid_files_in_folder'] = valid_files_in_folder
            index_status = self.llm_service.load_and_index_documents(folder_path)
            if index_status != "Documents successfully indexed.":
                logging.error(f"Error during load_and_index_documents: {index_status}")
                await update.message.reply_text(
                    "An error occurred while loading and indexing the project documents. Please try again later."
                )
                return ConversationHandler.END

            context.user_data['vector_store_loaded'] = True

            # Evaluate token count
            token_count = self.llm_service.count_tokens_in_context(folder_path)
            percentage_full = (token_count / MAX_TOKENS_IN_CONTEXT) * 100 if MAX_TOKENS_IN_CONTEXT else 0
            percentage_full = min(percentage_full, 100)

            await update.message.reply_text(
                f"Project folder path set to: {folder_path}\n\nValid files have been indexed.\n\n"
                f"Context storage is {percentage_full:.2f}% full."
            )

            # Save user info in database
            self.db_service.add_user_to_db(user_id=user_id, user_name=user_name, folder=folder_path)
        else:
            await update.message.reply_text(
                "Invalid selection or project is not available. Please select a valid project."
            )
            return ConversationHandler.END

        return ConversationHandler.END

    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /status command."""
        user_name = update.effective_user.full_name
        folder_path = context.user_data.get('folder_path', "")
        valid_files_in_folder = context.user_data.get('valid_files_in_folder', [])

        if not folder_path:
            await update.message.reply_text(
                f"Status Information:\n\n"
                f"Name: {user_name}\n"
                "No folder path has been set yet. Please set it using the /folder command."
            )
        else:
            if valid_files_in_folder:
                file_list = "\n".join(valid_files_in_folder)
                folder_info = (
                    f"The folder path is currently set to: {folder_path}\n\n"
                    f"Valid Files:\n{file_list}"
                )

                # Evaluate token count
                token_count = self.llm_service.count_tokens_in_context(folder_path)
                percentage_full = (token_count / MAX_TOKENS_IN_CONTEXT) * 100 if MAX_TOKENS_IN_CONTEXT else 0
                percentage_full = min(percentage_full, 100)

                await update.message.reply_text(
                    f"Status Information:\n\n"
                    f"Name: {user_name}\n"
                    f"{folder_info}\n\n"
                    f"Context storage is {percentage_full:.2f}% full."
                )
            else:
                await update.message.reply_text(
                    f"Status Information:\n\n"
                    f"Name: {user_name}\n"
                    f"The folder path is currently set to: {folder_path}, but no valid files were found."
                )

    async def folder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /folder command."""
        await update.message.reply_text("Please provide the folder path for your documents:")
        return WAITING_FOR_FOLDER_PATH

    async def set_folder(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Set the folder path after receiving it from the user."""
        folder_path = update.message.text.strip()
        user_id = update.effective_user.id
        user_name = update.effective_user.full_name

        # Check if the folder path exists
        if not os.path.isdir(folder_path):
            await update.message.reply_text("Invalid folder path. Please provide a valid path.")
            return ConversationHandler.END

        # Check for valid files
        valid_files_in_folder = [
            f for f in os.listdir(folder_path)
            if f.endswith((".pdf", ".docx", ".xlsx"))
        ]
        if not valid_files_in_folder:
            await update.message.reply_text(
                "No valid files found in the folder. Please provide a folder containing valid documents."
            )
            return ConversationHandler.END

        # Set user-specific folder path and process the documents
        context.user_data['folder_path'] = folder_path
        context.user_data['valid_files_in_folder'] = valid_files_in_folder
        index_status = self.llm_service.load_and_index_documents(folder_path)
        if index_status != "Documents successfully indexed.":
            logging.error(f"Error during load_and_index_documents: {index_status}")
            await update.message.reply_text(
                "An error occurred while loading and indexing your documents. Please try again later."
            )
            return ConversationHandler.END

        context.user_data['vector_store_loaded'] = True

        # Evaluate token count
        token_count = self.llm_service.count_tokens_in_context(folder_path)
        percentage_full = (token_count / MAX_TOKENS_IN_CONTEXT) * 100 if MAX_TOKENS_IN_CONTEXT else 0
        percentage_full = min(percentage_full, 100)

        await update.message.reply_text(
            f"Folder path successfully set to: {folder_path}\n\nValid files have been indexed.\n\n"
            f"Context storage is {percentage_full:.2f}% full."
        )

        # Save user info in database
        self.db_service.add_user_to_db(user_id=user_id, user_name=user_name, folder=folder_path)

        return ConversationHandler.END

    async def knowledge_base(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /knowledge_base command."""
        folder_path = KNOWLEDGE_BASE_PATH
        user_id = update.effective_user.id
        user_name = update.effective_user.full_name

        # Check if the folder path exists
        if not os.path.isdir(folder_path):
            await update.message.reply_text("The knowledge base folder path does not exist.")
            return

        # Check for valid files
        valid_files_in_folder = [
            f for f in os.listdir(folder_path)
            if f.endswith((".pdf", ".docx", ".xlsx"))
        ]
        if not valid_files_in_folder:
            await update.message.reply_text(
                "No valid files found in the knowledge base folder."
            )
            return

        # Set user-specific folder path and process the documents
        context.user_data['folder_path'] = folder_path
        context.user_data['valid_files_in_folder'] = valid_files_in_folder
        index_status = self.llm_service.load_and_index_documents(folder_path)
        if index_status != "Documents successfully indexed.":
            logging.error(f"Error during load_and_index_documents: {index_status}")
            await update.message.reply_text(
                "An error occurred while loading and indexing the knowledge base documents. Please try again later."
            )
            return

        context.user_data['vector_store_loaded'] = True

        # Evaluate token count
        token_count = self.llm_service.count_tokens_in_context(folder_path)
        percentage_full = (token_count / MAX_TOKENS_IN_CONTEXT) * 100 if MAX_TOKENS_IN_CONTEXT else 0
        percentage_full = min(percentage_full, 100)

        await update.message.reply_text(
            f"Knowledge base folder path set to: {folder_path}\n\nValid files have been indexed.\n\n"
            f"Context storage is {percentage_full:.2f}% full."
        )

        # Save user info in database
        self.db_service.add_user_to_db(user_id=user_id, user_name=user_name, folder=folder_path)

    async def ask(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle the /ask command."""
        if not context.user_data.get('vector_store_loaded', False):
            await update.message.reply_text(
                "Documents are not indexed yet. Use /folder or /knowledge_base first."
            )
            return ConversationHandler.END

        valid_files_in_folder = context.user_data.get('valid_files_in_folder', [])
        if not valid_files_in_folder:
            await update.message.reply_text(
                "No valid documents found in the folder. Please add documents to the folder."
            )
            return ConversationHandler.END

        await update.message.reply_text("Please provide the question you want to ask about the documents:")
        return WAITING_FOR_QUESTION

    async def ask_question(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Process the user's question and provide an answer."""
        user_prompt = update.message.text
        try:
            response, source_files = self.llm_service.retrieve_and_generate(user_prompt)
        except Exception as e:
            logging.error(f"Error during retrieve_and_generate: {e}")
            await update.message.reply_text(
                "An error occurred while processing your question. Please try again later."
            )
            return ConversationHandler.END

        if response == "Invalid folder path.":
            await update.message.reply_text(
                "The vector store is not loaded correctly. Please reset the folder path using /folder or /knowledge_base."
            )
        else:
            if source_files:
                reference_message = "\n".join([f"Document: {file}" for file in source_files])
            else:
                reference_message = "No document references found."

            await update.message.reply_text(f"{response}\n\nReferences:\n{reference_message}")

        return ConversationHandler.END

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle any text message sent by the user."""
        if not context.user_data.get('vector_store_loaded', False):
            await update.message.reply_text(
                "Documents are not indexed yet. Use /folder or /knowledge_base first."
            )
            return

        valid_files_in_folder = context.user_data.get('valid_files_in_folder', [])
        if not valid_files_in_folder:
            await update.message.reply_text(
                "No valid documents found in the folder. Please add documents to the folder."
            )
            return

        user_message = update.message.text

        # Update chat history
        chat_history = context.user_data.get('chat_history', [])
        chat_history.append(("user", user_message))
        if len(chat_history) > 10:  # Keep the last 5 exchanges (user and assistant)
            chat_history = chat_history[-10:]
        context.user_data['chat_history'] = chat_history

        try:
            response, source_files = self.llm_service.retrieve_and_generate(user_message, chat_history=chat_history)
        except Exception as e:
            logging.error(f"Error during retrieve_and_generate: {e}")
            await update.message.reply_text(
                "An error occurred while processing your message. Please try again later."
            )
            return

        # Update chat history with assistant's response
        chat_history.append(("assistant", response))
        if len(chat_history) > 10:
            chat_history = chat_history[-10:]
        context.user_data['chat_history'] = chat_history

        if source_files:
            reference_message = "\n".join([f"Document: {file}" for file in source_files])
        else:
            reference_message = "No document references found."

        await update.message.reply_text(f"{response}\n\nReferences:\n{reference_message}")
