# services/ai_service.py
# ─────────────────────────────────────────────────────────
# AI SERVICE — Sprint 2 Final
# Retry + Backoff + Circuit Breaker + Zscaler Detection + Pydantic Validation
# Providers: mock | gemini | anthropic | openai | azure | groq | bedrock
# ─────────────────────────────────────────────────────────

import json
import os
import time
from typing import Generator, List, Optional

import httpx
from dotenv import load_dotenv
from pydantic import BaseModel, validator, ValidationError

load_dotenv()

from config import MOCK_MODE
from services.capa_service import build_mock_capa

_SSL_VERIFY = os.getenv("SSL_VERIFY", "true").lower() == "true"

AI_PROVIDER = os.getenv("AI_PROVIDER", "mock")
AI_API_KEY  = os.getenv("AI_API_KEY",  "")
AI_MODEL    = os.getenv("AI_MODEL",    "llama-3.1-70b-versatile")
AI_BASE_URL = os.getenv("AI_BASE_URL", "")

_MAX_RETRIES = 3
_BACKOFF     = 2
_RETRY_ON    = {429, 500, 502, 503, 504}
_FAIL_FAST   = {400, 401, 403}


# ═════════════════════════════════════════════════════════
# PYDANTIC SCHEMAS — validate AI output before returning
# ═════════════════════════════════════════════════════════

class CAPASchema(BaseModel):
    rootCause:            str
    immediateAction:      str
    correctiveAction:     str
    preventiveAction:     str
    proposedOwner:        str
    effectivenessCheck:   str
    estimatedClosureDays: int
    riskRating:           str
    regulatoryRef:        List[str]

    @validator("rootCause")
    def root_cause_not_vague(cls, v):
        vague = ["human error", "operator error", "lack of training"]
        if any(p in v.lower() for p in vague) and len(v) < 80:
            raise ValueError(
                "Root cause too vague — must cite SOP/equipment/process")
        return v

    @validator("riskRating")
    def valid_risk(cls, v):
        if v not in ("Critical", "High", "Medium", "Low"):
            raise ValueError(f"Invalid riskRating: {v}")
        return v

    @validator("estimatedClosureDays")
    def valid_days(cls, v):
        if not (1 <= v <= 365):
            raise ValueError(f"estimatedClosureDays {v} out of range 1-365")
        return v

    @validator("regulatoryRef")
    def refs_not_empty(cls, v):
        if not v:
            raise ValueError(
                "regulatoryRef must contain at least one reference")
        return v


class RCASchema(BaseModel):
    method:     str
    steps:      Optional[List[dict]] = None
    categories: Optional[dict]       = None
    rootCause:  Optional[str]        = None


# ═════════════════════════════════════════════════════════
# CIRCUIT BREAKER
# ═════════════════════════════════════════════════════════

class _CircuitBreaker:
    def __init__(self, threshold: int = 5, cooldown: int = 10):
        self.failures  = 0
        self.threshold = threshold
        self.cooldown  = cooldown
        self.state     = "CLOSED"
        self.opened_at = None

    def allow(self) -> bool:
        if self.state == "CLOSED":
            return True
        if self.state == "OPEN":
            if time.time() - self.opened_at > self.cooldown:
                self.state = "HALF_OPEN"
                print(f"[ai_service] Circuit HALF_OPEN — testing {AI_PROVIDER} again")
                return True
            return False
        return True

    def record_success(self):
        self.failures = 0
        self.state    = "CLOSED"

    def record_failure(self):
        self.failures += 1
        if self.failures >= self.threshold:
            self.state     = "OPEN"
            self.opened_at = time.time()
            print(f"[ai_service] Circuit OPEN — provider {AI_PROVIDER} appears down. "
                  f"Cooldown: {self.cooldown}s")


_breaker = _CircuitBreaker(threshold=5, cooldown=10)


# ═════════════════════════════════════════════════════════
# PUBLIC FUNCTIONS
# ═════════════════════════════════════════════════════════

def generate_capa(record: dict) -> dict:
    if MOCK_MODE or AI_PROVIDER == "mock" or not AI_API_KEY:
        time.sleep(0.5)
        return build_mock_capa(record)
    return _live_generate(_build_capa_prompt(record))


def stream_capa(record: dict) -> Generator[str, None, None]:
    if MOCK_MODE or AI_PROVIDER == "mock" or not AI_API_KEY:
        yield from _mock_stream(record)
    else:
        yield from _live_stream(_build_capa_prompt(record))


def generate_rca(record: dict, method: str) -> dict:
    from services.rca_service import build_five_why, build_fishbone
    if MOCK_MODE or AI_PROVIDER == "mock" or not AI_API_KEY:
        time.sleep(0.4)
        return build_five_why(record) if method == "5why" else build_fishbone(record)
    try:
        result = _live_generate(_build_rca_prompt(record, method))
        if result.get("_fallback") or "rootCause" in result:
            return build_five_why(record) if method == "5why" else build_fishbone(record)
        return result
    except Exception:
        return build_five_why(record) if method == "5why" else build_fishbone(record)


# ═════════════════════════════════════════════════════════
# LIVE GENERATION WITH RETRY + CIRCUIT BREAKER
# ═════════════════════════════════════════════════════════

def _live_generate(prompt: str) -> dict:
    print(f"[ai_service] Calling {AI_PROVIDER} | "
          f"URL: {AI_BASE_URL or 'default'} | "
          f"Model: {AI_MODEL} | "
          f"Key: {AI_API_KEY[:8]}...")

    if AI_PROVIDER == "bedrock":
        return _bedrock_generate(prompt)

    if not _breaker.allow():
        print("[ai_service] Circuit OPEN — returning mock fallback")
        result = build_mock_capa({})
        result["_fallback"] = True
        result["_error"]    = "Circuit breaker open — AI provider unavailable"
        return result

    last_error = None

    for attempt in range(_MAX_RETRIES):
        try:
            headers, payload, url = _build_request(prompt, stream=False)
            resp = httpx.post(url, headers=headers, json=payload,
                              timeout=60.0, verify=_SSL_VERIFY)

            if resp.status_code in _FAIL_FAST:
                _breaker.record_failure()
                if "zscaler" in resp.text.lower() or \
                   "<!doctype" in resp.text.lower():
                    print("[ai_service] ZSCALER BLOCK — returning mock fallback")
                    result = build_mock_capa({})
                    result["_fallback"] = True
                    result["_error"]    = "Blocked by corporate proxy (Zscaler)"
                    return result
                raise RuntimeError(
                    f"AI API fatal {resp.status_code}: {resp.text[:300]}")

            if resp.status_code in _RETRY_ON:
                wait = _BACKOFF ** (attempt + 1)
                retry_after = resp.headers.get("Retry-After")
                if retry_after:
                    wait = int(retry_after)
                last_error = f"HTTP {resp.status_code}"
                print(f"[ai_service] Attempt {attempt+1}/{_MAX_RETRIES} "
                      f"failed ({last_error}) — retrying in {wait}s")
                time.sleep(wait)
                continue

            resp.raise_for_status()
            text   = _extract_text(resp.json())
            text   = text.replace("```json", "").replace("```", "").strip()
            result = json.loads(text)

            # ── Pydantic validation ───────────────────────
            if "rootCause" in result:
                try:
                    CAPASchema(**result)
                    print("[ai_service] Pydantic schema validation passed")
                except ValidationError as ve:
                    warnings = [e["msg"] for e in ve.errors()]
                    print(f"[ai_service] Schema warnings: {warnings}")
                    result["_validation_warnings"] = warnings

            _breaker.record_success()
            print(f"[ai_service] Success — {AI_PROVIDER}/{AI_MODEL} "
                  f"(attempt {attempt+1})")
            return result

        except httpx.TimeoutException:
            last_error = "Timeout"
            wait = _BACKOFF ** (attempt + 1)
            print(f"[ai_service] Attempt {attempt+1}/{_MAX_RETRIES} "
                  f"timed out — retrying in {wait}s")
            time.sleep(wait)

        except json.JSONDecodeError as e:
            _breaker.record_failure()
            raise RuntimeError(f"AI returned invalid JSON: {e}") from e

        except RuntimeError:
            raise

        except Exception as e:
            last_error = str(e)
            error_type = type(e).__name__
            _breaker.record_failure()
            wait = _BACKOFF ** (attempt + 1)
            if "WinError 10054" in str(e):
                print(f"[ai_service] Attempt {attempt+1}/{_MAX_RETRIES} — "
                      f"CONNECTION RESET: Zscaler/firewall dropped the connection.")
            elif "CERTIFICATE_VERIFY_FAILED" in str(e):
                print(f"[ai_service] Attempt {attempt+1}/{_MAX_RETRIES} — "
                      f"SSL BLOCKED.")
            elif "401" in str(e) or "Unauthorized" in str(e):
                print(f"[ai_service] Attempt {attempt+1}/{_MAX_RETRIES} — "
                      f"AUTH FAILED: API key wrong or expired.")
            elif "ConnectError" in error_type or "ConnectionError" in error_type:
                print(f"[ai_service] Attempt {attempt+1}/{_MAX_RETRIES} — "
                      f"CANNOT CONNECT: DNS or network unreachable.")
            else:
                print(f"[ai_service] Attempt {attempt+1}/{_MAX_RETRIES} — "
                      f"{error_type}: {e}")
            time.sleep(wait)

    _breaker.record_failure()
    print(f"[ai_service] All {_MAX_RETRIES} retries failed "
          f"({last_error}) — returning mock fallback")
    result = build_mock_capa({})
    result["_fallback"] = True
    result["_error"]    = last_error or "All retries exhausted"
    return result


def _bedrock_generate(prompt: str) -> dict:
    try:
        import boto3
        import json as _json
        region = os.getenv("AWS_REGION", "us-east-1")
        client = boto3.client("bedrock-runtime", region_name=region)
        body   = _json.dumps({
            "anthropic_version": "bedrock-2023-05-31",
            "max_tokens":        2000,
            "messages": [{"role": "user", "content": prompt}],
        })
        response      = client.invoke_model(
            modelId=AI_MODEL, body=body,
            contentType="application/json", accept="application/json",
        )
        response_body = _json.loads(response["body"].read())
        text          = response_body["content"][0]["text"]
        text          = text.replace("```json", "").replace("```", "").strip()
        result        = _json.loads(text)
        print(f"[ai_service] Bedrock success — {AI_MODEL}")
        return result
    except ImportError:
        print("[ai_service] boto3 not installed — run: pip install boto3")
        result = build_mock_capa({})
        result["_fallback"] = True
        result["_error"]    = "boto3 not installed"
        return result
    except Exception as e:
        print(f"[ai_service] Bedrock error: {e}")
        result = build_mock_capa({})
        result["_fallback"] = True
        result["_error"]    = str(e)
        return result


def _live_stream(prompt: str) -> Generator[str, None, None]:
    if not _breaker.allow():
        print("[ai_service] Circuit OPEN — streaming mock fallback")
        yield from _mock_stream({})
        return

    for attempt in range(_MAX_RETRIES):
        try:
            headers, payload, url = _build_request(prompt, stream=True)
            buffer = ""

            with httpx.Client(timeout=120.0, verify=_SSL_VERIFY) as client:
                with client.stream("POST", url,
                                   headers=headers, json=payload) as resp:

                    if resp.status_code in _FAIL_FAST:
                        _breaker.record_failure()
                        yield f"data: {json.dumps({'error': f'API auth error {resp.status_code}'})}\n\n"
                        yield "data: [DONE]\n\n"
                        return

                    if resp.status_code in _RETRY_ON:
                        wait = _BACKOFF ** (attempt + 1)
                        print(f"[ai_service] Stream attempt {attempt+1} "
                              f"failed (HTTP {resp.status_code}) — retrying in {wait}s")
                        time.sleep(wait)
                        break

                    current_event = None
                    for line in resp.iter_lines():
                        if line.startswith("event: "):
                            current_event = line[7:].strip()
                            if current_event in ("message_stop", "error"):
                                _breaker.record_success()
                                yield "data: [DONE]\n\n"
                                return
                            continue
                        if not line.startswith("data: "):
                            continue
                        raw = line[6:].strip()
                        if raw == "[DONE]":
                            _breaker.record_success()
                            yield "data: [DONE]\n\n"
                            return
                        if not raw:
                            continue
                        try:
                            event_data = json.loads(raw)
                            delta = ""
                            if current_event == "content_block_delta":
                                delta = (event_data.get("delta", {})
                                         .get("text", ""))
                            else:
                                delta = _extract_delta(event_data)
                            if delta:
                                buffer += delta
                                yield (f"data: {json.dumps({'delta': delta, 'buffer': buffer})}"
                                       f"\n\n")
                        except (json.JSONDecodeError, KeyError):
                            pass

            _breaker.record_success()
            yield "data: [DONE]\n\n"
            return

        except httpx.TimeoutException:
            wait = _BACKOFF ** (attempt + 1)
            print(f"[ai_service] Stream timeout attempt {attempt+1} "
                  f"— retrying in {wait}s")
            time.sleep(wait)

        except Exception as e:
            _breaker.record_failure()
            print(f"[ai_service] Stream error: {e}")
            yield f"data: {json.dumps({'error': str(e)})}\n\n"
            yield "data: [DONE]\n\n"
            return

    print("[ai_service] Stream retries exhausted — falling back to mock")
    yield from _mock_stream({})


# ═════════════════════════════════════════════════════════
# PROMPT BUILDERS
# ═════════════════════════════════════════════════════════

def _build_capa_prompt(record: dict) -> str:
    reg_refs = ', '.join(record.get('regulatoryRef', [])) or \
               "21 CFR Part 820, ISO 13485"
    return (
        "You are a senior QA expert for pharmaceutical and medical device compliance.\n"
        "Generate a thorough, regulatory-grade CAPA for the quality record below.\n"
        "Root cause must be SPECIFIC — name the exact process gap, SOP number, "
        "or equipment ID. Never say just 'human error'.\n"
        "Regulatory references must cite the exact clause "
        "(e.g. 21 CFR 820.100(a)).\n\n"
        f"Record ID:   {record.get('id')}\n"
        f"Type:        {record.get('type', '').upper()}\n"
        f"Sector:      {record.get('sector')}\n"
        f"Priority:    {record.get('priority')}\n"
        f"Title:       {record.get('title')}\n"
        f"Description: {record.get('description')}\n"
        f"Site:        {record.get('site')}\n"
        f"Regulations: {reg_refs}\n\n"
        "Respond ONLY with valid JSON — no markdown, no preamble.\n"
        "Required keys:\n"
        "  rootCause (string — specific, cites process/SOP/equipment),\n"
        "  immediateAction (string),\n"
        "  correctiveAction (string),\n"
        "  preventiveAction (string),\n"
        "  proposedOwner (string — job title, not a name),\n"
        "  effectivenessCheck (string — measurable criterion),\n"
        "  estimatedClosureDays (integer),\n"
        "  riskRating (Critical | High | Medium | Low),\n"
        "  regulatoryRef (array of strings — specific clauses)"
    )


def _build_rca_prompt(record: dict, method: str) -> str:
    method_label = "5-Why chain" if method == "5why" \
                   else "Fishbone (Ishikawa) diagram"
    return (
        f"You are a senior QA expert. Perform a {method_label} "
        f"root cause analysis.\n"
        f"Each cause must be specific — cite SOP numbers, equipment IDs, "
        f"or process steps.\n\n"
        f"Record: {record.get('id')} | {record.get('type', '').upper()}\n"
        f"Title: {record.get('title')}\n"
        f"Description: {record.get('description')}\n"
        f"Priority: {record.get('priority')}\n\n"
        "Respond ONLY with valid JSON — no markdown, no explanation."
    )


# ═════════════════════════════════════════════════════════
# REQUEST BUILDER
# ═════════════════════════════════════════════════════════

def _build_request(prompt: str, stream: bool = False):
    if AI_PROVIDER == "anthropic":
        url     = "https://api.anthropic.com/v1/messages"
        headers = {
            "x-api-key":         AI_API_KEY,
            "anthropic-version": "2023-06-01",
            "content-type":      "application/json",
        }
        payload = {
            "model":      AI_MODEL,
            "max_tokens": 2000,
            "stream":     stream,
            "messages":   [{"role": "user", "content": prompt}],
        }

    elif AI_PROVIDER in ("openai", "groq"):
        url     = AI_BASE_URL or "https://api.openai.com/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {AI_API_KEY}",
            "Content-Type":  "application/json",
        }
        payload = {
            "model":    AI_MODEL,
            "stream":   stream,
            "messages": [{"role": "user", "content": prompt}],
        }

    elif AI_PROVIDER == "azure":
        url     = AI_BASE_URL
        headers = {
            "api-key":      AI_API_KEY,
            "Content-Type": "application/json",
        }
        payload = {
            "messages": [{"role": "user", "content": prompt}],
            "stream":   stream,
        }

    elif AI_PROVIDER == "gemini":
        if stream:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models"
                f"/{AI_MODEL}:streamGenerateContent"
                f"?key={AI_API_KEY}&alt=sse"
            )
        else:
            url = (
                f"https://generativelanguage.googleapis.com/v1beta/models"
                f"/{AI_MODEL}:generateContent?key={AI_API_KEY}"
            )
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {
                "temperature":     0.2,
                "maxOutputTokens": 2000,
            },
        }

    elif AI_PROVIDER == "bedrock":
        raise ValueError(
            "Bedrock uses boto3 — handled in _bedrock_generate()")

    else:
        raise ValueError(
            f"Unknown AI_PROVIDER: '{AI_PROVIDER}'. "
            f"Use: mock | gemini | anthropic | openai | azure | groq | bedrock"
        )

    return headers, payload, url


# ═════════════════════════════════════════════════════════
# RESPONSE PARSERS
# ═════════════════════════════════════════════════════════

def _extract_text(response: dict) -> str:
    if "content" in response:
        return response["content"][0]["text"]
    if "choices" in response:
        return response["choices"][0]["message"]["content"]
    if "candidates" in response:
        try:
            return response["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            if response.get("promptFeedback"):
                raise RuntimeError(
                    f"Gemini blocked prompt: {response['promptFeedback']}")
            raise ValueError(f"Unexpected Gemini response: {response}")
    raise ValueError(
        f"Unrecognised API response shape: {list(response.keys())}")


def _extract_delta(event: dict) -> str:
    if "choices" in event:
        return event["choices"][0].get("delta", {}).get("content", "")
    if "delta" in event:
        return event["delta"].get("text", "")
    if "candidates" in event:
        try:
            return event["candidates"][0]["content"]["parts"][0]["text"]
        except (KeyError, IndexError):
            return ""
    return ""


# ═════════════════════════════════════════════════════════
# MOCK STREAM
# ═════════════════════════════════════════════════════════

def _mock_stream(record: dict) -> Generator[str, None, None]:
    capa   = build_mock_capa(record)
    text   = json.dumps(capa, indent=2)
    buffer = ""
    for ch in text:
        buffer += ch
        yield f"data: {json.dumps({'delta': ch, 'buffer': buffer})}\n\n"
        if ch == "\n":
            time.sleep(0.006)
    yield "data: [DONE]\n\n"