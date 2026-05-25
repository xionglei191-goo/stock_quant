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

RUN python -m pip install --no-cache-dir --retries 10 --timeout 120 "psycopg[binary]==3.3.4"
RUN python -m pip install --no-cache-dir --retries 10 --timeout 120 --prefer-binary \
    "numpy==2.4.6" "python-dateutil==2.9.0.post0" "six==1.17.0" "pandas==3.0.3"
RUN python -m pip install --no-cache-dir --retries 10 --timeout 120 --no-deps "baostock==0.9.1"

EXPOSE 8000

CMD ["python", "-m", "app.server"]
