#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
mkdir -p data/cdc
# Mantém a conexão e transmite a saída para arquivo local.
echo 'Consumindo alterações lógicas. Em outro terminal, rode src/cdc/03_testar.sh (Ctrl+C para sair).'
docker compose exec -T postgres pg_recvlogical \
  -U "${POSTGRES_USER:-metra}" \
  -d "${POSTGRES_DB:-metra}" \
  --slot=metra_cdc_slot --start -f - \
  | tee -a data/cdc/eventos.log
