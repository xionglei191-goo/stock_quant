FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml README.md ./
COPY app ./app
COPY config ./config
COPY docs ./docs
COPY scripts ./scripts
COPY tasks ./tasks

ENV PYTHONUNBUFFERED=1
ENV AI_QUANT_DB=/data/state.db
ENV AI_QUANT_OBJECT_STORE=/data/objects
ENV AI_QUANT_HOST=0.0.0.0

RUN sed -i 's|http://deb.debian.org|https://deb.debian.org|g' /etc/apt/sources.list.d/debian.sources \
    && apt-get update \
    && apt-get install -y --no-install-recommends poppler-utils \
    && rm -rf /var/lib/apt/lists/*

RUN python -m pip install --no-cache-dir --retries 10 --timeout 120 ".[postgres,market-data,dynamic-allocation-dashboard]"

EXPOSE 8000 8501

CMD ["python", "-m", "app.server"]
