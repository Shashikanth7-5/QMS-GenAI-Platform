# Alembic migrations

Everything in `models.py` is the source of truth. To evolve the schema:

```bash
# Generate a new migration from model diffs
alembic revision --autogenerate -m "add fooBar to CAPARecord"

# Apply pending migrations to the current DATABASE_URL
alembic upgrade head

# Roll back one revision (dev only)
alembic downgrade -1
```

In production the entrypoint runs `alembic upgrade head` before Gunicorn
starts (see `Dockerfile`), so every deploy applies pending migrations
atomically. Do not use `_apply_lightweight_migrations` in production; it
is SQLite-only and reserved for local dev.
