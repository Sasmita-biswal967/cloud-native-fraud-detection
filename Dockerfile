# ---- base: same Python + dependencies as production ----
FROM python:3.14-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /srv
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app

# ---- test: only built when you run `docker build --target test .` (CI does this) ----
FROM base AS test
RUN pip install --no-cache-dir pytest httpx
COPY tests ./tests
RUN python -m pytest -q tests

# ---- runtime: the image that is deployed (no tests, no model baked in) ----
FROM base AS runtime
RUN useradd -r -u 10001 appuser && chown -R appuser /srv
USER 10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
