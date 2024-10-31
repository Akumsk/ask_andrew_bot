# auth.py

from db_service import DatabaseService

class AuthService:
    def __init__(self):
        self.db_service = DatabaseService()

    def check_user_access(self, user_id):
        return self.db_service.check_user_access(user_id)

    def save_user_info(self, user_id, user_name, language_code):
        self.db_service.save_user_info(user_id, user_name, language_code)

    def update_last_active(self, user_id):
        self.db_service.update_last_active(user_id)

    def grant_access(self, user_id):
        self.db_service.grant_access(user_id)

    def close(self):
        self.db_service.close()
