# settings.py

import os
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

MODEL_NAME = "gpt-4o"
"""
gpt-4o
gpt-4o-mini
"""

MAX_TOKENS_IN_CONTEXT = 128000

PROJECT_PATHS = {
    "Lima": r"G:\Shared drives\ARC.HITENSE\ARC.LIM lima Residence\ARC.LIM.D Docs\ARC.LIM.D Tracked documents",
    "Origins": r"G:\Shared drives\ARC.HITENSE\ARC.ORI Origins\ARC.ORI.D Docs\Tracked documents",
    # Add more projects as needed
}

KNOWLEDGE_BASE_PATH = (
    r"G:\Shared drives\NUANU ARCHITECTS\LIB Library\LIB Standards and Regulations"
)

CHAT_HISTORY_LEVEL=5