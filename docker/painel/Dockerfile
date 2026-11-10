FROM python:3.12-slim

WORKDIR /app

COPY requirements-pipeline.txt .
RUN pip install --no-cache-dir -r requirements-pipeline.txt

COPY src/ src/

ENV PYTHONPATH=/app
# Banco analítico gerado pelo dbt/Dagster; o painel apenas lê este arquivo.
ENV METRA_DUCKDB=/app/data/metra_analitico.duckdb

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=30s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=4)"

CMD ["streamlit", "run", "src/app/dashboard.py", \
     "--server.address=0.0.0.0", "--server.port=8501", \
     "--server.headless=true", "--browser.gatherUsageStats=false"]
