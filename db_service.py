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
        self.conn = self.connect()
        self.conn.autocommit = True

    def connect(self):
        return psycopg2.connect(
            dbname=self.dbname,
            user=self.user,
            password=self.password,
            host=self.host,
            port=self.port,
        )

    def save_folder(self, user_id, user_name, folder):
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
            print("Contex Folder Data SAVED!!!")

        except Exception as e:
            print(f"Error saving folder data: {e}")
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

    def save_event_log(self, user_id, event_type, user_message, system_response, conversation_id, timestamp=None):
        try:
            connection = self.connect()
            cursor = connection.cursor()
            if timestamp is None:
                timestamp = datetime.now()
            query = """
                INSERT INTO event_log (user_id, event_type, user_message, system_response, conversation_id)
                VALUES (%s, %s, %s, %s, %s)
            """
            cursor.execute(
                query,
                (user_id, event_type, user_message, system_response, conversation_id),
            )
            connection.commit()
            print("Event log saved successfully.")
        except Exception as e:
            print(f"Error saving event log: {e}")
            connection.rollback()
        finally:
            cursor.close()
            connection.close()

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

    def get_chat_history(self, dialog_numbers, user_id):
        connection = None
        cursor = None
        try:
            connection = self.connect()
            cursor = connection.cursor()

            # Step 1: Get the last 'dialog_numbers' conversation_ids for the user
            query_conversation_ids = """
                SELECT conversation_id, MAX(date + timestamp) as last_datetime
                FROM messages
                WHERE user_id = %s AND sender_type = 'user'
                GROUP BY conversation_id
                ORDER BY last_datetime DESC
                LIMIT %s
            """

            cursor.execute(query_conversation_ids, (user_id, dialog_numbers))
            conversation_data = cursor.fetchall()
            conversation_ids = [str(row[0]) for row in conversation_data]

            if not conversation_ids:
                return []

            # Step 2: Fetch messages for these conversation_ids, ordered by datetime
            query_messages = """
                SELECT conversation_id, sender_type, message_text, date + timestamp as datetime
                FROM messages
                WHERE conversation_id = ANY(%s::uuid[])
                ORDER BY conversation_id, datetime ASC
            """
            cursor.execute(query_messages, (conversation_ids,))
            messages = cursor.fetchall()

            conversations = defaultdict(list)
            for conversation_id, sender_type, message_text, datetime in messages:
                conversations[str(conversation_id)].append((sender_type, message_text))

            # Step 3: Construct the chat history
            chat_history = []
            # Maintain the order of conversation_ids as per their datetime descending
            for conversation_id in conversation_ids:
                conversation = conversations.get(conversation_id, [])
                for sender_type, message_text in conversation:
                    if sender_type == "user":
                        chat_history.append(f"HumanMessage: {message_text}")
                    elif sender_type == "bot":
                        chat_history.append(f"AIMessage: {message_text}")

            return chat_history

        except Exception as e:
            # Handle exceptions
            print(f"An error occurred: {e}")
            return []
        finally:
            if cursor:
                cursor.close()
            if connection:
                connection.close()

    def check_user_access(self, user_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "SELECT access FROM users WHERE user_id = %s AND is_active = True",
                (user_id,)
            )
            result = cursor.fetchone()
            if result:
                return result[0]  # True or False
            else:
                return False
        except Exception as e:
            print(f"Error checking user access: {e}")
            return False
        finally:
            cursor.close()

    def save_user_info(self, user_id, user_name, language_code):
        now = datetime.utcnow()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                """
                INSERT INTO users (user_id, user_name, language_code, date_joined, last_active, is_active, access, role)
                VALUES (%s, %s, %s, %s, %s, True, False, 'user')
                ON CONFLICT (user_id) DO UPDATE
                SET user_name = EXCLUDED.user_name,
                    language_code = EXCLUDED.language_code,
                    last_active = EXCLUDED.last_active
                """,
                (user_id, user_name, language_code, now, now)
            )
            print("User info saved/updated successfully.")
        except Exception as e:
            print(f"Error saving user info: {e}")
            self.conn.rollback()
        finally:
            cursor.close()

    def update_last_active(self, user_id):
        now = datetime.utcnow()
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE users SET last_active = %s WHERE user_id = %s",
                (now, user_id)
            )
            print("User last_active updated.")
        except Exception as e:
            print(f"Error updating last_active: {e}")
            self.conn.rollback()
        finally:
            cursor.close()

    def grant_access(self, user_id):
        try:
            cursor = self.conn.cursor()
            cursor.execute(
                "UPDATE users SET access = True WHERE user_id = %s",
                (user_id,)
            )
            print(f"Access granted to user {user_id}.")
        except Exception as e:
            print(f"Error granting access: {e}")
            self.conn.rollback()
        finally:
            cursor.close()

    def close(self):
        self.conn.close()

