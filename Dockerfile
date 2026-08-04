FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PORT=5000

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN python -m pip install --upgrade pip \
    && python -m pip install -r requirements.txt

COPY . .

EXPOSE 5000

# alembic upgrade migrates the schema; then gunicorn boots the app.
CMD ["sh", "-c", "alembic upgrade head && exec gunicorn --bind 0.0.0.0:5000 --workers 2 --threads 4 --timeout 120 --access-logfile - --error-logfile - app:app"]
