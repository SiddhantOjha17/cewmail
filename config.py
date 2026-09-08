"""Loads settings from .env (explicit path, so it works regardless of cwd -- important under nssm)."""

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).parent
load_dotenv(BASE_DIR / ".env")

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.6-flash")

OPENAI_API_KEY = os.environ.get("OPENAI_API_KEY", "")
OPENAI_MODEL = os.environ.get("OPENAI_MODEL", "gpt-4o-mini")

GMAIL_ADDRESS = os.environ.get("GMAIL_ADDRESS", "")
GMAIL_APP_PASSWORD = os.environ.get("GMAIL_APP_PASSWORD", "")

FLASK_PORT = int(os.environ.get("FLASK_PORT", "5000"))

EMAIL_TEMPLATES_DIR = BASE_DIR / "email_templates"

# Gmail's real cap is 25MB including base64 overhead (~37% larger than raw bytes).
MAX_ATTACHMENT_BYTES = 18 * 1024 * 1024
