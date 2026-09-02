# Agentic Orchestration Branch

This branch keeps the existing production CAPA/RCA behavior intact while adding
the first skeleton for a LangGraph and MCP-ready orchestration layer.

## Current Shape

- `services.ai_service` keeps live LLM calls behind provider failover.
- `services.llm_provider` exposes LangChain chat models for OpenAI, Groq,
  Anthropic, Azure OpenAI, and Gemini.
- `services.agents.langgraph_workflow` can wrap the existing intake,
  eligibility, RCA, and CAPA agents in a LangGraph state machine.
- `services.mcp_registry` loads optional MCP server declarations from
  `MCP_SERVER_CONFIG` without opening network connections at startup.

## Enablement

Set `LANGGRAPH_WORKFLOW_ENABLED=true` to route agent CAPA/RCA orchestration
through `services.agents.langgraph_workflow.run_capa_workflow`. If LangGraph is
unavailable, the module falls back to the current `CapaAgentOrchestrator`.

Example MCP configuration:

```json
[
  {
    "name": "salesforce-qms",
    "transport": "http",
    "endpoint": "https://example-mcp-server.internal/mcp",
    "authEnv": "SALESFORCE_MCP_TOKEN",
    "scopes": ["quality-records", "capa-sync"]
  }
]
```

The registry is intentionally passive for now. The next implementation step is
to bind approved MCP tools into graph nodes for Salesforce lookup, attachment
retrieval, and approved CAPA sync.
