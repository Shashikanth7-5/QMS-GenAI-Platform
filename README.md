# QMS GenAI Platform — TrackWise® Digital

AI-powered Quality Management System for Life Sciences compliance.
Built with Python · Flask · SQLAlchemy · Anthropic Claude · SSE Streaming

![Python](https://img.shields.io/badge/Python-3.11-blue)
![Flask](https://img.shields.io/badge/Flask-3.x-green)
![SQLAlchemy](https://img.shields.io/badge/SQLAlchemy-PostgreSQL-orange)

## Features

- **AI CAPA Generation** — 8-field structured regulatory output with root cause, corrective/preventive actions, regulatory references
- **RCA Analysis** — 5-Why chain + Fishbone with quality scoring (specificity, actionability, completeness)
- **Decision Tree** — 6-gate compliance engine classifies quality events → CAPA or deviation
- **RAG Document Extraction** — PDF, Excel, Word, CSV, images → AI extracts structured quality fields
- **Global Search** — Full-text search across 1000+ records with relevance scoring
- **Audit Trail** — Every action logged with user, timestamp, and change detail
- **Chat** — "Ask About This Record" answers questions from record fields
- **Role-Based Access** — 6 roles: QA Admin, Manager, Analyst, Reviewer, Auditor, Developer

## Tech Stack

Python · Flask · SQLAlchemy · SQLite/PostgreSQL · httpx · Anthropic Claude · OpenAI · Azure OpenAI · SSE Streaming · pdfplumber · python-docx

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

Open `http://localhost:5000` — login with `admin/admin`

## AI Configuration (.env)
AI_PROVIDER=openai           # openai | anthropic | azure | bedrock
AI_BASE_URL=https://api.groq.com/openai/v1
AI_API_KEY=xxxxxxxxxxxxxxxxxxxxx

AI_MODEL=llama-3.1-70b-versatile
MOCK_MODE=false

Supports Groq (free), Anthropic Claude, OpenAI, Azure OpenAI, and Amazon Bedrock — switch provider with one `.env` change.

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

Provider-agnostic AI service layer — `services/ai_service.py` handles retry, exponential backoff, circuit breaker, and Zscaler detection. Switch LLM providers with one `.env` change.