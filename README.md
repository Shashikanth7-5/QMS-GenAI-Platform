# AI Quality Management System - CAPA Generator

AI-powered Quality Management System for Life Sciences compliance.
Built with Python Â· Flask Â· SQLAlchemy Â· Anthropic Claude Â· SSE Streaming

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Flask](https://img.shields.io/badge/Flask-3.x-green)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-PostgreSQL-orange)

## Features

- **AI CAPA Generation** â€” 8-field structured regulatory output with root cause, corrective/preventive actions, regulatory references
- **RCA Analysis** â€” 5-Why chain + Fishbone with quality scoring (specificity, actionability, completeness)
- **CAPA Trigger Rules** â€” gate-based compliance engine classifies quality events for CAPA eligibility
- **Document Extraction** â€” PDF, Excel, Word, CSV, and images can prefill structured quality record fields from the Draft CAPA page
- **Global Search** â€” Full-text search across 1000+ records with relevance scoring
- **Audit Trail** â€” Every action logged with user, timestamp, and change detail
- **Chat** â€” "Ask About This Record" answers questions from record fields
- **Role-Based Access** â€” 3 roles: admin, quality analyst, user

## Tech Stack

Python Â· Flask Â· SQLAlchemy Â· SQLite/PostgreSQL Â· httpx Â· Anthropic Claude Â· OpenAI Â· Azure OpenAI Â· SSE Streaming Â· pdfplumber Â· python-docx

## Setup

```bash
git clone https://github.com/Shashikanth755/QMS-GenAI-Platform
cd QMS-GenAI-Platform
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
cp _env .env        # edit with your API key
python app.py
```

Open `http://localhost:5000` â€” login with `admin/admin`

## AI Configuration (.env)
AI_PROVIDER=openai           # openai | anthropic | azure | bedrock
AI_BASE_URL=https://api.groq.com/openai/v1
AI_API_KEY=xxxxxxxxxxxxxxxxxxxxx

AI_MODEL=llama-3.1-70b-versatile
MOCK_MODE=false

Supports Groq (free), Anthropic Claude, OpenAI, Azure OpenAI, and Amazon Bedrock â€” switch provider with one `.env` change.

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/records` | All quality records |
| POST | `/api/capa/generate` | Generate CAPA (AI or mock) |
| POST | `/api/rca/fishbone` | Fishbone RCA analysis |
| POST | `/api/rca/five-why` | 5-Why chain analysis |
| POST | `/api/records/inquire` | Chat about a record |
| GET | `/api/metrics` | Dashboard KPIs |

## Architecture

Provider-agnostic AI service layer â€” `services/ai_service.py` handles retry, exponential backoff, circuit breaker, and Zscaler detection. Switch LLM providers with one `.env` change.

## Integration Direction

The product UI is branded as **AI Quality Management System**, but the architecture must remain compatible with TrackWise Digital, Salesforce-based quality workflows, Java services, and other enterprise systems. External integration should be added through stable APIs, plugin-style adapters, or event/webhook layers so the core CAPA workflow can run independently while exchanging records, status updates, audit events, and approvals with customer systems.

Current integration principles:

- Keep CAPA, RCA, trigger, audit, and agent operations available through REST APIs.
- Preserve source-system IDs and external references on records and CAPA drafts.
- Avoid hard-coding TrackWise/Salesforce terms into the core UI or business logic.
- Add future TrackWise, Salesforce, Java, or multi-language integration as adapters around the core workflow.


