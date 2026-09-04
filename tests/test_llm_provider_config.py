import json


class FakeResponse:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text or json.dumps(self._payload)
        self.headers = {}

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")


def _reset_llm_env(monkeypatch):
    names = [
        "AI_PROVIDER", "AI_API_KEY", "AI_MODEL", "AI_BASE_URL",
        "AI_FAILOVER_PROVIDERS", "AI_GROQ_API_KEY", "GROQ_API_KEY",
        "AI_GROQ_MODEL", "AI_ANTHROPIC_API_KEY", "ANTHROPIC_API_KEY",
        "AI_ANTHROPIC_MODEL", "AI_OPENAI_API_KEY", "OPENAI_API_KEY",
        "AI_GEMINI_API_KEY", "GEMINI_API_KEY", "GOOGLE_API_KEY",
    ]
    for name in names:
        monkeypatch.delenv(name, raising=False)


def test_llm_status_reports_live_groq_with_native_key_alias(monkeypatch):
    from services import ai_service

    _reset_llm_env(monkeypatch)
    monkeypatch.setenv("MOCK_MODE", "false")
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("AI_GROQ_MODEL", "llama-3.1-70b-versatile")

    status = ai_service.llm_status()

    assert status["liveReady"] is True
    assert status["primaryProvider"] == "groq"
    assert status["configuredProviders"][0]["provider"] == "groq"
    assert status["configuredProviders"][0]["model"] == "openai/gpt-oss-120b"
    assert status["configuredProviders"][0]["hasKey"] is True


def test_live_generate_skips_bad_primary_and_uses_groq_failover(monkeypatch):
    from services import ai_service

    _reset_llm_env(monkeypatch)
    monkeypatch.setenv("AI_PROVIDER", "anthropic")
    monkeypatch.setenv("AI_MODEL", "claude-3-5-sonnet-latest")
    monkeypatch.setenv("AI_API_KEY", "bad-anthropic-key")
    monkeypatch.setenv("AI_FAILOVER_PROVIDERS", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("AI_GROQ_MODEL", "llama-3.1-70b-versatile")
    monkeypatch.setattr(ai_service._breaker, "state", "CLOSED")
    monkeypatch.setattr(ai_service._breaker, "failures", 0)

    calls = []

    def fake_post(url, headers, json, timeout, verify):
        calls.append(url)
        if "anthropic.com" in url:
            return FakeResponse(
                401,
                {"type": "error"},
                '{"type":"error","error":{"type":"authentication_error","message":"invalid x-api-key"}}',
            )
        return FakeResponse(
            200,
            {
                "choices": [{
                    "message": {
                        "content": json_module.dumps({
                            "rootCause": "SOP-QA-001 complaint intake verification missed required device history review.",
                            "immediateAction": "Quarantine impacted units and notify QA.",
                            "correctiveAction": "Revise intake checklist and retrain QA reviewers.",
                            "preventiveAction": "Add weekly audit of complaint intake completeness.",
                            "proposedOwner": "Quality Manager",
                            "effectivenessCheck": "Zero missing intake reviews across 30 days.",
                            "estimatedClosureDays": 30,
                            "riskRating": "High",
                            "regulatoryRef": ["21 CFR 820.100(a)"],
                        })
                    }
                }],
                "usage": {"prompt_tokens": 10, "completion_tokens": 20},
            },
        )

    import json as json_module

    monkeypatch.setattr(ai_service.httpx, "post", fake_post)

    result = ai_service._live_generate("return capa json")

    assert result["_provider"] == "groq"
    assert any("anthropic.com" in url for url in calls)
    assert any("api.groq.com" in url for url in calls)
