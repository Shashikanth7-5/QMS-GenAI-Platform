# services/celery_app.py
# ─────────────────────────────────────────────────────────
# CELERY APP — Sprint 3 Week 3 (async batch processing)
# Local dev: eager mode (tasks run inline) — no Redis needed.
# Production: set CELERY_BROKER_URL to a real Redis and run a worker.
# ─────────────────────────────────────────────────────────

import os
from celery import Celery
from celery.schedules import schedule

# In production, set CELERY_BROKER_URL=redis://<host>:6379/0 in .env
_BROKER = os.getenv("CELERY_BROKER_URL", "").strip()
_SUPERVISOR_INTERVAL = int(os.getenv("AGENT_SUPERVISOR_INTERVAL_SECONDS", "1200"))

celery_app = Celery("qms")

if _BROKER:
    # Real Redis broker (deployment) — tasks run on a separate worker
    celery_app.conf.update(
        broker_url=_BROKER,
        result_backend=_BROKER,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
        task_track_started=True,
        timezone=os.getenv("CELERY_TIMEZONE", "Asia/Kolkata"),
        beat_schedule={
            "qms-agent-supervisor-every-20-minutes": {
                "task": "qms.agent_supervisor_run",
                "schedule": schedule(run_every=_SUPERVISOR_INTERVAL),
            },
        },
    )
    EAGER = False
else:
    # Local dev / no Redis: run tasks inline, synchronously.
    # Same task code — only execution mode differs.
    celery_app.conf.update(
        task_always_eager=True,
        task_eager_propagates=True,
        task_serializer="json",
        result_serializer="json",
        accept_content=["json"],
    )
    EAGER = True

# Ensure task modules are registered when the app is imported
celery_app.autodiscover_tasks(["services"])
