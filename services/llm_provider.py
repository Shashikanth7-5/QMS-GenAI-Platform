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
AI_MODEL    = os.getenv("AI_MODEL",    "openai/gpt-oss-120b")
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


def _env_value(provider: str, suffix: str, default: str = "") -> str:
    sdk_aliases = {
        "anthropic": "ANTHROPIC",
        "openai": "OPENAI",
        "azure": "AZURE_OPENAI",
        "gemini": "GEMINI",
        "groq": "GROQ",
    }
    names = [_env_name(provider, suffix)]
    alias = sdk_aliases.get(provider)
    if alias:
        names.append(f"{alias}_{suffix}")
    if provider == "gemini" and suffix == "API_KEY":
        names.append("GOOGLE_API_KEY")
    for name in names:
        value = os.getenv(name, "").strip()
        if value:
            return value
    return default.strip()


def _default_model(provider: str) -> str:
    return {
        "anthropic": "claude-3-5-sonnet-latest",
        "openai": "gpt-4o-mini",
        "azure": "",
        "gemini": "gemini-1.5-flash",
        "groq": "openai/gpt-oss-120b",
    }.get(provider, "")


def _normalize_model(provider: str, model: str) -> str:
    replacements = {
        "groq": {
            "llama-3.1-70b-versatile": "openai/gpt-oss-120b",
            "llama-3.1-70b-specdec": "openai/gpt-oss-120b",
            "llama-3.3-70b-versatile": "openai/gpt-oss-120b",
            "llama3-70b-8192": "openai/gpt-oss-120b",
            "llama3-8b-8192": "openai/gpt-oss-20b",
        },
    }
    return replacements.get(provider, {}).get((model or "").strip(), model)


def provider_configs() -> list[dict]:
    primary = os.getenv("AI_PROVIDER", AI_PROVIDER).strip().lower()
    generic_key = os.getenv("AI_API_KEY", AI_API_KEY)
    generic_model = os.getenv("AI_MODEL", AI_MODEL)
    generic_base_url = os.getenv("AI_BASE_URL", AI_BASE_URL)
    failover = os.getenv("AI_FAILOVER_PROVIDERS", AI_FAILOVER_PROVIDERS)
    names = [primary]
    if failover:
        names.extend(p.strip() for p in failover.split(",") if p.strip())
    unique = []
    for name in names:
        name = name.lower()
        if name not in unique and name != "mock":
            unique.append(name)
    configs = []
    for provider in unique:
        key = _env_value(provider, "API_KEY", generic_key if provider == primary else "")
        model = _env_value(provider, "MODEL", generic_model if provider == primary else _default_model(provider))
        base_url = _env_value(provider, "BASE_URL", generic_base_url if provider == primary else "")
        model = _normalize_model(provider, model)
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
