FROM python:3.12-slim AS base

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Training image: same libraries as the backend plus PyTorch. Used by `docker compose run --rm ml-train`.
FROM base AS ml
COPY requirements-ml.txt .
RUN pip install --no-cache-dir -r requirements-ml.txt

FROM base AS runtime
COPY app ./app

RUN useradd --create-home --uid 10001 amhews && mkdir -p /data/visual && chown amhews:amhews /data/visual
USER amhews

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
