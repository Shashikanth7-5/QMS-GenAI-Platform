# services/llm_provider.py
# ─────────────────────────────────────────────────────────────
# LLM Provider Factory — Sprint 2
# Returns a configured LLM object for use in LangChain chains.
# Switch provider by changing AI_PROVIDER in .env — no code changes.
#
# Supported:
#   mock       → returns None  (chains fall back to mock responses)
#   openai     → ChatOpenAI
#   anthropic  → ChatAnthropic
#   azure      → AzureChatOpenAI
#   gemini     → ChatGoogleGenerativeAI
#
# Usage in chains:
#   from services.llm_provider import get_llm
#   llm = get_llm()
#   if llm is None:
#       return mock_response()
#   chain = prompt | llm | parser
#   result = chain.invoke({"record": record})
# ─────────────────────────────────────────────────────────────

import os

AI_PROVIDER = os.getenv("AI_PROVIDER", "mock")
AI_API_KEY  = os.getenv("AI_API_KEY",  "")
AI_MODEL    = os.getenv("AI_MODEL",    "gpt-4o")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")


def get_llm(temperature: float = 0.1, max_tokens: int = 1500):
    """
    Returns a LangChain-compatible LLM instance or None in mock mode.
    Install extras as needed:
      pip install langchain-openai        # for openai / azure
      pip install langchain-anthropic     # for anthropic
      pip install langchain-google-genai  # for gemini
    """
    if AI_PROVIDER == "mock" or not AI_API_KEY:
        return None

    if AI_PROVIDER == "openai":
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model       = AI_MODEL,
                api_key     = AI_API_KEY,
                temperature = temperature,
                max_tokens  = max_tokens,
            )
        except ImportError:
            raise RuntimeError("Install langchain-openai: pip install langchain-openai")

    if AI_PROVIDER == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model       = AI_MODEL,
                api_key     = AI_API_KEY,
                temperature = temperature,
                max_tokens  = max_tokens,
            )
        except ImportError:
            raise RuntimeError("Install langchain-anthropic: pip install langchain-anthropic")

    if AI_PROVIDER == "azure":
        try:
            from langchain_openai import AzureChatOpenAI
            return AzureChatOpenAI(
                azure_endpoint   = AI_BASE_URL,
                api_key          = AI_API_KEY,
                azure_deployment = AI_MODEL,
                api_version      = "2024-02-01",
                temperature      = temperature,
                max_tokens       = max_tokens,
            )
        except ImportError:
            raise RuntimeError("Install langchain-openai: pip install langchain-openai")

    if AI_PROVIDER == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model       = AI_MODEL,
                google_api_key = AI_API_KEY,
                temperature = temperature,
                max_output_tokens = max_tokens,
            )
        except ImportError:
            raise RuntimeError("Install langchain-google-genai: pip install langchain-google-genai")

    raise ValueError(f"Unknown AI_PROVIDER: {AI_PROVIDER}")
