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
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/healthz')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
