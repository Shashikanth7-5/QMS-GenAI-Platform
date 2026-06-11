# services/chains/capa_chain.py
# ─────────────────────────────────────────────────────────────
# LangChain CAPA Generation Chain — Sprint 2
# Falls back to mock when no LLM is configured.
#
# To activate: set AI_PROVIDER + AI_API_KEY in .env
# ─────────────────────────────────────────────────────────────

from __future__ import annotations
import json
from typing import Dict


_CAPA_PROMPT_TEMPLATE = """You are a pharmaceutical / medical device quality expert.
Generate a CAPA for the quality record below.

Record ID:   {id}
Type:        {type}
Sector:      {sector}
Priority:    {priority}
Title:       {title}
Description: {description}
Site:        {site}
Regulations: {regulations}

Respond ONLY with valid JSON — no markdown, no preamble.
Required keys: rootCause, immediateAction, correctiveAction,
preventiveAction, proposedOwner, effectivenessCheck,
estimatedClosureDays (int), riskRating, regulatoryRef (array)"""


def run_capa_chain(record: Dict) -> Dict:
    """
    Generates CAPA using LangChain LCEL chain if LLM is configured,
    otherwise falls back to mock.
    """
    try:
        from services.llm_provider import get_llm
        from langchain_core.prompts import PromptTemplate
        from langchain_core.output_parsers import JsonOutputParser

        llm = get_llm(temperature=0.1, max_tokens=1200)
        if llm is None:
            return _mock_fallback(record)

        prompt = PromptTemplate.from_template(_CAPA_PROMPT_TEMPLATE)
        parser = JsonOutputParser()
        chain  = prompt | llm | parser

        return chain.invoke({
            "id":          record.get("id",""),
            "type":        record.get("type","").upper(),
            "sector":      record.get("sector",""),
            "priority":    record.get("priority",""),
            "title":       record.get("title",""),
            "description": record.get("description",""),
            "site":        record.get("site",""),
            "regulations": ", ".join(record.get("regulatoryRef",[])),
        })

    except ImportError:
        # LangChain not installed yet — use direct httpx path
        return _mock_fallback(record)
    except Exception as e:
        print(f"[capa_chain] Chain failed: {e} — using mock")
        return _mock_fallback(record)


def _mock_fallback(record: Dict) -> Dict:
    try:
        from services.capa_service import build_mock_capa
    except ImportError:
        from capa_service import build_mock_capa
    return build_mock_capa(record)
