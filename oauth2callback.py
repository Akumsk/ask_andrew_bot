# oauth2callback.py

from flask import Flask, request, redirect
import threading
from gdrive_service import save_credentials, get_flow
import os

app = Flask(__name__)

@app.route('/oauth2callback')
def oauth2callback():
    code = request.args.get('code')
    state = request.args.get('state')  # Telegram user ID
    if code and state:
        user_id = state
        flow = get_flow(state)
        flow.fetch_token(code=code)
        creds = flow.credentials
        save_credentials(user_id, creds)
        return "Authorization successful! You can go back to the bot and provide the folder ID."
    else:
        return "Authorization failed."

def get_flow():
    """Creates a Flow object for OAuth 2.0 authentication."""
    flow = Flow.from_client_secrets_file(
        'path/to/client_secrets.json',  # Replace with your client secrets JSON file
        scopes=SCOPES,
        redirect_uri='https://yourdomain.com/oauth2callback'  # Replace with your redirect URI
    )
    return flow