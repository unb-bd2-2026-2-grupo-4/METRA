#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# Executar após configurar wal_level=logical e recriar o container postgres.
docker compose up -d postgres
WAL=$(docker compose exec -T postgres psql -U "${POSTGRES_USER:-metra}" -d "${POSTGRES_DB:-metra}" -Atc 'SHOW wal_level;')
if [ "$WAL" != logical ]; then
  echo "ERRO: wal_level=$WAL. Configure wal_level=logical no docker-compose.yml e recrie o container." >&2
  exit 1
fi
# Tabela de teste isolada dentro do esquema OLTP, sem alterar movimentações oficiais.
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-metra}" -d "${POSTGRES_DB:-metra}" -c '
CREATE SCHEMA IF NOT EXISTS oltp;
CREATE TABLE IF NOT EXISTS oltp.cdc_probe (
  id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  descricao TEXT NOT NULL,
  atualizado_em TIMESTAMPTZ NOT NULL DEFAULT now()
);'
# Criar slot uma única vez, preservando a posição entre execuções.
EXISTE=$(docker compose exec -T postgres psql -U "${POSTGRES_USER:-metra}" -d "${POSTGRES_DB:-metra}" -Atc "SELECT count(*) FROM pg_replication_slots WHERE slot_name='metra_cdc_slot';")
if [ "$EXISTE" = "0" ]; then
  docker compose exec -T postgres pg_recvlogical -U "${POSTGRES_USER:-metra}" -d "${POSTGRES_DB:-metra}" --slot=metra_cdc_slot --plugin=test_decoding --create-slot
fi
docker compose exec -T postgres psql -U "${POSTGRES_USER:-metra}" -d "${POSTGRES_DB:-metra}" -c "SELECT slot_name, plugin, slot_type, active FROM pg_replication_slots WHERE slot_name='metra_cdc_slot';"
echo 'Preparação concluída.'
