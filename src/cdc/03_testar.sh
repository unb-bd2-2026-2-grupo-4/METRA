#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
# Inserir e atualizar uma linha OLTP isolada, sempre em transações COMMIT.
# Gerar um identificador exclusivo baseado no timestamp do servidor.
SUFFIX="$(date +%s)-$$"
docker compose exec -T postgres psql -v ON_ERROR_STOP=1 -U "${POSTGRES_USER:-metra}" -d "${POSTGRES_DB:-metra}" -v tag="metra-${SUFFIX}" <<'SQL'
INSERT INTO oltp.cdc_probe(descricao) VALUES (:'tag') RETURNING id, descricao;
UPDATE oltp.cdc_probe SET descricao = descricao || '-atualizado', atualizado_em = now()
 WHERE descricao = :'tag' RETURNING id, descricao;
SQL
echo 'Confirme no outro terminal as linhas "table oltp.cdc_probe: INSERT" e "UPDATE".'
echo 'Também podem ser inspecionadas em data/cdc/eventos.log.'
