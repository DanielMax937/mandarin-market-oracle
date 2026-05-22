FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ORACLE_ENV=production \
    ORACLE_EXECUTION_MODE=research \
    ORACLE_PROVENANCE_NETWORK=arc-testnet \
    ORACLE_ALLOW_REAL_ORDERS=false

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY oracle ./oracle
COPY data ./data
COPY web ./web
COPY README.md .

EXPOSE 8000

CMD ["uvicorn", "oracle.api:app", "--host", "0.0.0.0", "--port", "8000"]
