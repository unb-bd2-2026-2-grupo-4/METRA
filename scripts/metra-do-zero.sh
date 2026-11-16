#!/usr/bin/env sh
# Executa o METRA do zero: Bronze -> OLTP -> Parquet/Delta -> dbt Silver/Gold -> painel.
#
# Apaga os volumes do PostgreSQL e do Dagster e os artefatos gerados em data/
# (lake e metra_analitico.duckdb). A amostra versionada e os CSVs completos ficam.
#
# Uso, na raiz do repositório:
#     sh scripts/metra-do-zero.sh         # pede confirmação
#     sh scripts/metra-do-zero.sh --sim   # sem confirmação (CI)
set -eu

cd "$(dirname "$0")/.."

if [ "${1:-}" != "--sim" ]; then
    printf 'Isto apaga os volumes do PostgreSQL e do Dagster e os artefatos gerados em data/. Continuar? [s/N] '
    read -r resposta
    case "$resposta" in
        s | S) ;;
        *) echo "Nada foi alterado."; exit 1 ;;
    esac
fi

echo "==> Derrubando os serviços e apagando os volumes"
docker compose --profile completo --profile dagster --profile painel --profile ingestao \
    down --volumes --remove-orphans

echo "==> Apagando o lake e o banco analítico gerados"
# Dentro do contêiner, para remover também arquivos criados pelo Docker como root.
docker compose --profile completo run --rm --no-deps --build pipeline \
    sh -c 'rm -rf /app/data/lake /app/data/metra_analitico.duckdb /app/data/metra_analitico.duckdb.wal'

echo "==> Executando o fluxo completo e subindo o painel"
if ! docker compose --profile completo up --build --wait painel-completo; then
    echo "O fluxo falhou. Últimas linhas do pipeline:" >&2
    docker compose --profile completo logs --no-log-prefix --tail 40 pipeline >&2
    exit 1
fi

docker compose --profile completo logs --no-log-prefix pipeline | grep -A 7 '^Bronze'
echo "Painel no ar: http://localhost:${PAINEL_PORT:-8501}"
