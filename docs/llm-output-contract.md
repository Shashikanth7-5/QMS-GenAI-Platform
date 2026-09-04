# LLM Output Contract

This app is designed by Shashi for QMS CAPA intelligence workflows. In production testing, set `MOCK_MODE=false` and configure at least one live provider key.

## How to confirm live LLM usage

- Header badge: should show `Live LLM: <provider> / <model>`.
- Health endpoint: `/api/health` returns `llm.liveReady=true` and configured providers.
- RCA/CAPA payloads: successful live generations include `_provider`, `_model`, and `_latency_ms`.
- Database audit: `LLMCallLog` rows capture provider, model, task, token counts, latency, and estimated cost.

If the header says `Mock Mode`, the app is not configured for live LLM calls in that environment.

## Expected RCA response

RCA analysis must return grounded JSON with record-specific details:

- `method`, `record_id`, `problem_statement`, and `root_cause`.
- For 5-Why: a `chain` array with five levels where the final item is the root cause.
- For Fishbone: `categories` covering Man, Machine, Method, Material, Measurement, and Environment.
- RCA model proposals return three options using different sampling settings: Basic, Standard, Enhanced.

## Expected CAPA response

CAPA generation must return valid JSON with enough field detail for QA review:

- `rootCause`: specific process, SOP, equipment, batch, or evidence-based cause.
- `immediateAction`: containment action already taken or required immediately.
- `correctiveAction`: action addressing the verified root cause.
- `preventiveAction`: systemic action to prevent recurrence.
- `proposedOwner`: role/title, not a personal name.
- `effectivenessCheck`: measurable criterion and timeframe.
- `estimatedClosureDays`, `riskRating`, and `regulatoryRef`.

All prompt inputs pass through guardrails that redact patent identifiers, secrets, tokens, emails, phone numbers, SSNs, and payment-card-like values before calling an LLM.
