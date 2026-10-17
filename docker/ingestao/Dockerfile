FROM python:3.12-slim

WORKDIR /app

COPY requirements-pipeline.txt .
RUN pip install --no-cache-dir -r requirements-pipeline.txt

COPY src/ src/

# Garante o schema (migrações idempotentes), carrega as fontes Bronze e popula o OLTP (3FN).
CMD ["python", "-m", "src.ingestao.executar_pipeline"]
