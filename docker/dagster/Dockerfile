FROM python:3.12-slim

WORKDIR /app

COPY requirements-pipeline.txt .
RUN pip install --no-cache-dir -r requirements-pipeline.txt

COPY dagster_metra/ dagster_metra/
COPY src/ src/
COPY dbt_metra/ dbt_metra/
COPY workspace.yaml .

RUN dbt parse \
    --project-dir /app/dbt_metra \
    --profiles-dir /app/dbt_metra \
    --no-partial-parse

ENV PYTHONPATH=/app
ENV METRA_LAKE_PARQUET=/app/data/lake/parquet
ENV METRA_DUCKDB=/app/data/metra_analitico.duckdb
ENV DAGSTER_HOME=/opt/dagster/dagster_home

RUN mkdir -p "$DAGSTER_HOME"

EXPOSE 3000

CMD ["dagster-webserver", "-h", "0.0.0.0", "-p", "3000", "-w", "workspace.yaml"]
