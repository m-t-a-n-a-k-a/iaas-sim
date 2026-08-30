FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml README.md ./
COPY src ./src

RUN uv venv .venv && . .venv/bin/activate && uv pip install --system .[dev]

EXPOSE 8000

CMD ["bash", "-lc", ". .venv/bin/activate && uvicorn iaas_sim.bootstrap.main:app --host 0.0.0.0 --port 8000"]
