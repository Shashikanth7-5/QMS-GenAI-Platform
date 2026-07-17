# Sprint 3 Week 4 Deployment

## Local Container Run

```powershell
docker compose up --build
```

The web app runs at `http://localhost:5000`.

## Services

- `web`: Flask app served by Gunicorn.
- `worker`: Celery worker for async CAPA batch jobs.
- `redis`: Celery broker/result backend.
- `qms_data`: Docker volume for SQLite data and ChromaDB persistence.

## Environment

Set these in `.env` or the deployment platform:

```text
SECRET_KEY=change-me
MOCK_MODE=true
AI_PROVIDER=mock
AI_API_KEY=
AI_MODEL=mock-mode
AI_BASE_URL=
CELERY_BROKER_URL=redis://redis:6379/0
DATABASE_URL=sqlite:////app/data/qms_data.db
```

## CI

GitHub Actions runs `python -m pytest -q` on every push and pull request.
