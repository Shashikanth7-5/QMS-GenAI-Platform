# Production Deployment Checklist

This project is cloud-ready when the web, worker, beat scheduler, database,
Redis broker, SMTP, and upload storage are all configured.

## Required Processes

- `web`: Flask/Gunicorn application
- `worker`: Celery worker for async/background jobs
- `beat`: Celery Beat scheduler for autonomous agent scans every 20 minutes

`Procfile` commands:

```text
web: gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${WEB_CONCURRENCY:-2} --threads ${WEB_THREADS:-4} --timeout ${WEB_TIMEOUT:-120} app:app
worker: celery -A services.celery_app:celery_app worker --loglevel=${CELERY_LOG_LEVEL:-INFO}
beat: celery -A services.celery_app:celery_app beat --loglevel=${CELERY_LOG_LEVEL:-INFO}
```

Docker Compose includes all three processes plus PostgreSQL and Redis:

```powershell
docker compose up --build
```

## Required Environment Variables

```text
FLASK_ENV=production
SECRET_KEY=<64+ random chars>
API_V1_KEY=<strong integration API key>
QMS_DATA_DIR=/var/data
DATABASE_URL=sqlite:////var/data/qms_data.db
CHROMA_PERSIST_DIR=/var/data/chroma_db
CELERY_BROKER_URL=redis://<host>:6379/0
RATE_LIMIT_STORAGE_URI=redis://<host>:6379/1
UPLOAD_STORAGE_BACKEND=local
UPLOAD_STORAGE_DIR=/var/data/uploads
SMTP_HOST=<smtp host>
SMTP_PORT=587
SMTP_FROM=qms-workflow@yourcompany.com
SMTP_USERNAME=<smtp user>
SMTP_PASSWORD=<smtp password>
SMTP_STARTTLS=true
AGENT_ALERT_EMAIL=qms-admins@yourcompany.com
SEED_BUILTIN_USERS=false
MOCK_MODE=false
AI_PROVIDER=<mock|openai|anthropic|azure|gemini|groq|bedrock>
AI_API_KEY=<provider key>
AI_MODEL=<model name>
```

## Autonomous Agents

Celery Beat runs:

```text
qms.agent_supervisor_run
```

Default schedule:

```text
AGENT_SUPERVISOR_INTERVAL_SECONDS=1200
AGENT_SUPERVISOR_LIMIT=50
AGENT_SUPERVISOR_ALLOW_WEEKEND=false
```

The supervisor:

- scans eligible records
- skips weekends by default
- invokes intake, decision, RCA scoring, and CAPA draft agents
- saves qualifying CAPA drafts for human review
- retries failures
- parks repeated failures in dead-letter queue
- sends alert email when SMTP is configured

Admin UI:

```text
/admin/agents
```

## Upload Storage

For the SQLite/Chroma pilot, all runtime state must live on one mounted persistent volume:

```text
QMS_DATA_DIR=/var/data
DATABASE_URL=sqlite:////var/data/qms_data.db
CHROMA_PERSIST_DIR=/var/data/chroma_db
UPLOAD_STORAGE_BACKEND=local
UPLOAD_STORAGE_DIR=/var/data/uploads
```

For Render, attach a persistent disk at `/var/data`. Data outside that path is ephemeral.
For higher-volume multi-instance production, move from SQLite to managed Postgres and object storage.

## Health / Readiness

```text
/healthz
/readyz
```

`/readyz` reports:

- database connectivity
- Celery broker configured/eager status
- SMTP configured/reachable
- upload storage writable
- CSRF/rate limiter hardening package availability

## Production Fail-Fast

In production, the app refuses to start if these hardening dependencies are
missing:

- `flask-wtf`
- `flask-limiter`

Install dependencies cleanly:

```powershell
python -m pip install -r requirements.txt
```

## External Integration

Main endpoint for TrackWise/Salesforce/Java QMS:

```text
POST /api/v1/integrations/quality-event/capa
```

See `INTEGRATION_READY.md` for payload and response contract.
