# db_service.py
import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv
from collections import defaultdict


load_dotenv()
db_password = os.getenv("DB_PASSWORD")
db_host = os.getenv("DB_HOST")
db_user = os.getenv("DB_USER")
db_name = os.getenv("DB_NAME")
db_port = os.getenv("DB_PORT")


class DatabaseService:
    def __init__(self):
        self.dbname = db_name
        self.user = db_user
        self.password = db_password
        self.host = db_host
        self.port = db_port

    def connect(self):
        return psycopg2.connect(
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
        )

    def add_user_to_db(self, user_id, user_name, folder):
        try:
            connection = self.connect()
            cursor = connection.cursor()
            query = """
                INSERT INTO folders (user_id, user_name, folder, date_time)
                VALUES (%s, %s, %s, %s)
            """
            date_time = (
                datetime.now().date().strftime("%Y-%m-%d")
                + ", "
                + datetime.now().time().strftime("%H:%M:%S")
            )
            cursor.execute(query, (user_id, user_name, folder, date_time))

            connection.commit()
            print("User Data SAVED!!!")

        except Exception as e:
            print(f"Error saving user data: {e}")
            connection.rollback()

    def get_last_folder(self, user_id):
        folder = None
        try:
            connection = self.connect()
            cursor = connection.cursor()
            query = """
                SELECT folder FROM folders
                WHERE user_id = %s
                ORDER BY date_time DESC
                LIMIT 1
            """
            cursor.execute(query, (user_id,))
            result = cursor.fetchone()
            if result:
                folder = result[0]

        except Exception as e:
            print(f"An error occurred while fetching folder: {e}")

        return folder

    def log_exception(
        self,
        exception_id,
        exception_type,
        exception_message,
        stack_trace,
        occurred_at,
        user_id,
        data_context,
        resolved,
        resolved_at=None,
        resolver_notes=None,
    ):
        try:
            connection = self.connect()
            cursor = connection.cursor()
            query = """
                INSERT INTO exceptions (exception_id, exception_type, exception_message, stack_trace, occurred_at, user_id, data_context, resolved, resolved_at, resolver_notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(
                query,
                (
                    exception_id,
                    exception_type,
                    exception_message,
                    stack_trace,
                    occurred_at,
                    user_id,
                    data_context,
                    resolved,
                    resolved_at,
                    resolver_notes,
                ),
            )
            connection.commit()
            cursor.close()
            connection.close()
        except Exception as e:
            print(f"Failed to log exception: {e}")

    def save_message(self, conversation_id, sender_type, user_id, message_text):
        try:
            connection = self.connect()
            cursor = connection.cursor()
            query = """
                INSERT INTO messages (conversation_id, sender_type, user_id, message_text)
                VALUES (%s, %s, %s, %s)
            """
            cursor.execute(query, (conversation_id, sender_type, user_id, message_text))
            connection.commit()
            print("Message saved successfully")

        except Exception as e:
            print(f"Error saving message: {e}")
            connection.rollback()
        finally:
            cursor.close()
            connection.close()

    def chat_history_from_db(self, dialog_numbers, user_id):
        connection = None
        cursor = None
        try:
            connection = self.connect()
            cursor = connection.cursor()

            # Step 1: Get the last 'dialog_numbers' conversation_ids for the user
            query_conversation_ids = """
                SELECT conversation_id, MAX(timestamp) as last_timestamp
                FROM messages
                WHERE user_id = %s AND sender_type = 'user'
                GROUP BY conversation_id
                ORDER BY last_timestamp DESC
                LIMIT %s
            """

            cursor.execute(query_conversation_ids, (user_id, dialog_numbers))
            conversation_data = cursor.fetchall()
            conversation_ids = [
                str(row[0]) for row in conversation_data
            ]

            if not conversation_ids:
                return []

            # Step 2: Prepare the list of conversation_ids as a string for SQL
            conversation_ids_str = "{" + ",".join(conversation_ids) + "}"

            query_messages = """
                SELECT conversation_id, sender_type, message_text, timestamp
                FROM messages
                WHERE conversation_id = ANY(%s::uuid[])
                ORDER BY conversation_id, timestamp ASC
            """
            cursor.execute(query_messages, (conversation_ids_str,))
            messages = cursor.fetchall()

            conversations = defaultdict(list)
            for conversation_id, sender_type, message_text, timestamp in messages:
                conversations[str(conversation_id)].append((sender_type, message_text))

            # Step 4: Construct the chat history
            chat_history = []
            # Maintain the order of conversation_ids as per their timestamp descending
            for conversation_id in conversation_ids:
                conversation = conversations.get(conversation_id, [])
                for sender_type, message_text in conversation:
                    if sender_type == "user":
                        chat_history.append(f"HumanMessage: {message_text}")
                    elif sender_type == "bot":
                        chat_history.append(f"AIMessage: {message_text}")

            return chat_history

        except Exception as e:
            print(f"Error fetching chat history: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()


# # Instantiate the DatabaseService class
# db_service = DatabaseService()
#
# test_chat_history = db_service.chat_history_from_db(user_id=244732168, dialog_numbers=2)
# print(test_chat_history)
