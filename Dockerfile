FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY docs ./docs
COPY scripts ./scripts
COPY tasks ./tasks

ENV PYTHONUNBUFFERED=1
ENV AI_QUANT_DB=/data/state.db
ENV AI_QUANT_OBJECT_STORE=/data/objects
ENV AI_QUANT_HOST=0.0.0.0

RUN python -m pip install --no-cache-dir "psycopg[binary]==3.3.4"

EXPOSE 8000

CMD ["python", "-m", "app.server"]
