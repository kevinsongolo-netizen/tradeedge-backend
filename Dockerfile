FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

RUN mkdir -p /app/data/exports /app/data/models

# Audit finding: the container ran as root with no USER directive —
# fine for local dev, a real hardening gap for any shared/production
# host. Runs as an unprivileged user from here on; /app/data (SQLite
# file, ML exports, joblib model artifacts) is the only path the app
# writes to, so it's the only one that needs to be owned by it.
RUN useradd --no-create-home --uid 1000 tradeedge \
    && chown -R tradeedge:tradeedge /app/data
USER tradeedge

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s \
    CMD python -c "import os,urllib.request; urllib.request.urlopen('http://localhost:' + os.environ.get('PORT','8000') + '/healthz')" || exit 1

# Sprint 9 — hosting platforms like Render assign a dynamic port via
# the $PORT environment variable rather than always using 8000; the
# app must bind to whatever $PORT actually is, falling back to 8000 for
# plain `docker run` / local use where $PORT isn't set. This has to be
# shell form (not the JSON-array exec form) so $PORT actually expands —
# exec-form CMD does not invoke a shell and would pass the literal
# string "$PORT" to uvicorn.
# Sprint 14 -- run any pending Alembic migrations before the app starts.
# alembic upgrade head is safe to run every boot: it's a no-op once the
# database is already current, so this doesn't need Render's paid Shell
# or a separate one-off job -- it just happens automatically on deploy.
CMD alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}
