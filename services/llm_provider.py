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
#   groq       → ChatOpenAI with Groq's OpenAI-compatible endpoint
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

from config import AI_FAILOVER_PROVIDERS, LLM_MAX_OUTPUT_TOKENS, MOCK_MODE

AI_PROVIDER = os.getenv("AI_PROVIDER", "mock")
AI_API_KEY  = os.getenv("AI_API_KEY",  "")
AI_MODEL    = os.getenv("AI_MODEL",    "gpt-4o")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")


def _env_name(provider: str, suffix: str) -> str:
    aliases = {
        "anthropic": "ANTHROPIC",
        "openai": "OPENAI",
        "azure": "AZURE",
        "gemini": "GEMINI",
        "groq": "GROQ",
    }
    return f"AI_{aliases.get(provider, provider.upper())}_{suffix}"


def provider_configs() -> list[dict]:
    names = [AI_PROVIDER]
    if AI_FAILOVER_PROVIDERS:
        names.extend(p.strip() for p in AI_FAILOVER_PROVIDERS.split(",") if p.strip())
    unique = []
    for name in names:
        name = name.lower()
        if name not in unique and name != "mock":
            unique.append(name)
    configs = []
    for provider in unique:
        key = os.getenv(_env_name(provider, "API_KEY"), AI_API_KEY if provider == AI_PROVIDER else "").strip()
        model = os.getenv(_env_name(provider, "MODEL"), AI_MODEL if provider == AI_PROVIDER else "").strip()
        base_url = os.getenv(_env_name(provider, "BASE_URL"), AI_BASE_URL if provider == AI_PROVIDER else "").strip()
        if key and model:
            configs.append({"provider": provider, "api_key": key, "model": model, "base_url": base_url})
    return configs


def get_llm(temperature: float = 0.1, max_tokens: int = None, config: dict | None = None):
    """
    Returns a LangChain-compatible LLM instance or None in mock mode.
    Install extras as needed:
      pip install langchain-openai        # for openai / azure / groq
      pip install langchain-anthropic     # for anthropic
      pip install langchain-google-genai  # for gemini
    """
    if MOCK_MODE or AI_PROVIDER == "mock":
        return None

    cfg = config or (provider_configs()[0] if provider_configs() else None)
    if not cfg:
        return None

    provider = cfg["provider"]
    api_key = cfg["api_key"]
    model = cfg["model"]
    base_url = cfg.get("base_url", "")
    max_tokens = max_tokens or LLM_MAX_OUTPUT_TOKENS

    if provider in ("openai", "groq"):
        try:
            from langchain_openai import ChatOpenAI
            return ChatOpenAI(
                model       = model,
                api_key     = api_key,
                base_url    = base_url or (
                    "https://api.groq.com/openai/v1"
                    if provider == "groq"
                    else None
                ),
                temperature = temperature,
                max_tokens  = max_tokens,
            )
        except ImportError:
            raise RuntimeError("Install langchain-openai: pip install langchain-openai")

    if provider == "anthropic":
        try:
            from langchain_anthropic import ChatAnthropic
            return ChatAnthropic(
                model       = model,
                api_key     = api_key,
                temperature = temperature,
                max_tokens  = max_tokens,
            )
        except ImportError:
            raise RuntimeError("Install langchain-anthropic: pip install langchain-anthropic")

    if provider == "azure":
        try:
            from langchain_openai import AzureChatOpenAI
            return AzureChatOpenAI(
                azure_endpoint   = base_url,
                api_key          = api_key,
                azure_deployment = model,
                api_version      = "2024-02-01",
                temperature      = temperature,
                max_tokens       = max_tokens,
            )
        except ImportError:
            raise RuntimeError("Install langchain-openai: pip install langchain-openai")

    if provider == "gemini":
        try:
            from langchain_google_genai import ChatGoogleGenerativeAI
            return ChatGoogleGenerativeAI(
                model       = model,
                google_api_key = api_key,
                temperature = temperature,
                max_output_tokens = max_tokens,
            )
        except ImportError:
            raise RuntimeError("Install langchain-google-genai: pip install langchain-google-genai")

    raise ValueError(f"Unknown AI_PROVIDER: {provider}")
