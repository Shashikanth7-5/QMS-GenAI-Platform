# config.py
# All environment variables loaded once here.
# Every other file imports from here — never from os.getenv directly.
# Like application.properties in Spring Boot.

import os
from dotenv import load_dotenv

load_dotenv()   # reads .env file

# ── Flask ─────────────────────────────────────────────────
SECRET_KEY = os.getenv("SECRET_KEY", "qms-genai-dev-key")
PORT       = int(os.getenv("PORT", "5000"))

# ── Mock mode ─────────────────────────────────────────────
# True  → uses template-based mock responses (no API key needed)
# False → calls the real AI provider set below
MOCK_MODE  = os.getenv("MOCK_MODE", "true").lower() == "true"

# ── AI Provider config ────────────────────────────────────
# Change these in .env to switch AI provider — no code changes needed.
# Supported: mock | openai | anthropic | azure | gemini
AI_PROVIDER = os.getenv("AI_PROVIDER", "mock")
AI_API_KEY  = os.getenv("AI_API_KEY",  "")
AI_MODEL    = os.getenv("AI_MODEL",    "mock-mode")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")   # needed for Azure OpenAI