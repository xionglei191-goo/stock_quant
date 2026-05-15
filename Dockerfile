FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY docs ./docs
COPY tasks ./tasks

ENV PYTHONUNBUFFERED=1
ENV AI_QUANT_DB=/data/state.db
ENV AI_QUANT_OBJECT_STORE=/data/objects

EXPOSE 8000

CMD ["python", "-m", "app.server"]
