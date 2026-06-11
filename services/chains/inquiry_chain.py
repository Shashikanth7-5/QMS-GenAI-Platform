# services/chains/inquiry_chain.py
from __future__ import annotations
from typing import Dict, List


_SYSTEM = """You are a QMS AI assistant grounded on a specific quality record.
Answer questions based ONLY on the record context provided.
Be concise, professional, and cite specific fields when relevant.
If information is not in the record, say so clearly.

RECORD CONTEXT:
{context}"""


def _build_context(record: Dict) -> str:
    return (
        f"ID: {record.get('id','—')} | Type: {record.get('type','—').upper()} | "
        f"Sector: {record.get('sector','—')} | Priority: {record.get('priority','—')} | "
        f"Status: {record.get('status','—')}\n"
        f"Title: {record.get('title','—')}\n"
        f"Description: {record.get('description','—')}\n"
        f"Site: {record.get('site','—')} | Owner: {record.get('owner','—')}\n"
        f"Detected: {record.get('detectedDate','—')} | "
        f"Batch/Lot: {record.get('batchLot','—')}\n"
        f"Regulatory: {', '.join(record.get('regulatoryRef',[]))}"
    )


def run_inquiry_chain(record: Dict, question: str, history: List[Dict]) -> str:
    try:
        from services.llm_provider import get_llm
        from langchain_core.prompts import ChatPromptTemplate

        llm = get_llm(temperature=0.2, max_tokens=600)
        if llm is None:
            return _try_direct_then_mock(record, question, history)

        context  = _build_context(record)
        messages = [("system", _SYSTEM.format(context=context))]
        for h in history[-8:]:
            if h.get("role") == "user":
                messages.append(("human", h["content"]))
            elif h.get("role") == "assistant":
                messages.append(("ai", h["content"]))
        messages.append(("human", question))

        prompt = ChatPromptTemplate.from_messages(messages)
        chain  = prompt | llm
        result = chain.invoke({})
        return result.content if hasattr(result, "content") else str(result)

    except ImportError:
        return _try_direct_then_mock(record, question, history)
    except Exception as e:
        print(f"[inquiry_chain] Chain failed: {e}")
        return _try_direct_then_mock(record, question, history)


def _try_direct_then_mock(record: Dict, question: str,
                           history: List[Dict]) -> str:
    """Try live API first, fall back to smart mock if blocked."""
    import os
    provider = os.getenv("AI_PROVIDER", "mock")
    api_key  = os.getenv("AI_API_KEY", "")

    if not api_key or provider == "mock":
        return _smart_mock(record, question)

    try:
        import httpx
        model    = os.getenv("AI_MODEL", "llama-3.1-70b-versatile")
        base_url = os.getenv("AI_BASE_URL", "")
        system   = _SYSTEM.format(context=_build_context(record))
        messages = [h for h in history[-8:]
                    if h.get("role") in ("user", "assistant")]
        messages.append({"role": "user", "content": question})

        if provider == "anthropic":
            resp = httpx.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": model, "max_tokens": 600,
                    "system": system, "messages": messages,
                },
                timeout=30, verify=False,
            )
            if resp.status_code == 200:
                return resp.json()["content"][0]["text"]
            return _smart_mock(record, question)

        elif provider in ("openai", "azure", "groq"):
            base = base_url or "https://api.openai.com/v1"
            resp = httpx.post(
                f"{base}/chat/completions",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system}
                    ] + messages,
                },
                timeout=30, verify=False,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            return _smart_mock(record, question)

    except Exception as e:
        print(f"[inquiry_chain] Direct call failed: {e}")

    return _smart_mock(record, question)


def _smart_mock(record: Dict, question: str) -> str:
    """
    Intelligent rule-based answers from record fields.
    No API needed — works offline and through any proxy.
    """
    q   = question.lower()
    rid = record.get("id", "—")
    t   = record.get("type", "—").upper()
    sec = record.get("sector", "—")
    pri = record.get("priority", "—")
    sts = record.get("status", "—")
    ttl = record.get("title", "—")
    dsc = record.get("description", "No description available.")
    ste = record.get("site", "—")
    own = record.get("owner", "Unassigned")
    det = record.get("detectedDate", "—")
    bat = record.get("batchLot", "N/A")
    reg = record.get("regulatoryRef", [])

    # Priority / urgency questions
    if any(w in q for w in ["priority", "urgent", "severity", "critical"]):
        return (f"**{rid}** has a priority of **{pri}**. "
                + ("This is a critical issue requiring immediate attention and escalation."
                   if pri == "Critical" else
                   "This requires prompt action within standard SLA timelines."
                   if pri == "High" else
                   "This should be addressed in the normal quality workflow."))

    # Owner / responsibility questions
    if any(w in q for w in ["owner", "responsible", "who", "assigned", "accountability"]):
        return (f"Record **{rid}** is assigned to **{own}** at **{ste}**. "
                f"They are responsible for investigation and CAPA implementation.")

    # Status questions
    if any(w in q for w in ["status", "stage", "progress", "where"]):
        return (f"Current status of **{rid}**: **{sts}**. "
                + ("A CAPA draft has been generated and is under QA review."
                   if sts == "Under Review" else
                   "This record is eligible for CAPA generation."
                   if sts == "Draft Generated" else
                   f"The record is in the **{sts}** stage of the quality workflow."))

    # Batch / lot questions
    if any(w in q for w in ["batch", "lot", "product", "material"]):
        pf = record.get("productFamily", "—")
        return (f"**Batch/Lot:** {bat}\n"
                f"**Product Family:** {pf}\n"
                f"**Site:** {ste}")

    # Regulatory questions
    if any(w in q for w in ["regulat", "compliance", "standard", "cfr", "iso", "requirement"]):
        if reg:
            refs = "\n".join(f"• {r}" for r in reg)
            return f"**Applicable regulations for {rid}:**\n{refs}"
        return (f"No specific regulatory references have been added to record **{rid}**. "
                f"For a {t} in {sec}, typical references include "
                f"21 CFR Part 820 and ISO 13485:2016.")

    # Immediate action questions
    if any(w in q for w in ["immediate", "action", "contain", "fix", "resolve", "remedy"]):
        return (f"For **{rid}** ({pri} priority {t}):\n"
                f"1. Quarantine affected materials/products immediately\n"
                f"2. Notify {own} and QA management\n"
                f"3. Initiate investigation per applicable SOP\n"
                f"4. Document all containment actions in the quality system\n"
                f"5. Generate CAPA using the CAPA Creation module")

    # Summarise questions
    if any(w in q for w in ["summar", "overview", "describe", "tell me", "explain", "about"]):
        reg_str = ", ".join(reg) if reg else "None specified"
        return (f"**Quality Record Summary — {rid}**\n\n"
                f"**Type:** {t} | **Sector:** {sec} | **Priority:** {pri}\n"
                f"**Status:** {sts} | **Site:** {ste}\n"
                f"**Detected:** {det} | **Owner:** {own}\n\n"
                f"**Issue:** {ttl}\n\n"
                f"**Description:** {dsc}\n\n"
                f"**Regulatory References:** {reg_str}")

    # Date / timing questions
    if any(w in q for w in ["when", "date", "detected", "found", "reported", "time"]):
        return (f"Record **{rid}** was detected on **{det}**. "
                f"Current age: {record.get('age', 0)} days since detection.")

    # Default — full summary
    return (f"**{rid}** is a {pri.lower()}-priority {t} from the "
            f"{sec} sector, detected at {ste} on {det}.\n\n"
            f"**{ttl}**\n\n{dsc}\n\n"
            f"Owner: {own} | Status: {sts}")