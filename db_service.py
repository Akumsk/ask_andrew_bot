# db_service.py
import os
import psycopg2
from datetime import datetime
from dotenv import load_dotenv

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
            port = self.port
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

    def log_exception(self, exception_id, exception_type, exception_message, stack_trace, occurred_at, user_id,
                      data_context, resolved, resolved_at=None, resolver_notes=None):
        try:
            connection = self.connect()
            cursor = connection.cursor()
            query = """
                INSERT INTO exceptions (exception_id, exception_type, exception_message, stack_trace, occurred_at, user_id, data_context, resolved, resolved_at, resolver_notes)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """
            cursor.execute(query, (
            exception_id, exception_type, exception_message, stack_trace, occurred_at, user_id, data_context, resolved,
            resolved_at, resolver_notes))
            connection.commit()
            cursor.close()
            connection.close()
        except Exception as e:
            print(f"Failed to log exception: {e}")
