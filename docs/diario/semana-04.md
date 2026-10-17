# Diário de Bordo - Semana 04

- **Data:** Semana 4 (Semestre 2026/2)
- **Autor(es):** Lucas Alves (com apoio de IA, registrado no `uso-de-ia.md`)

---

## O que foi medido e analisado

- **Perfil dos CSVs brutos** exportados do BigQuery, medido com DuckDB antes de qualquer carga:
  - 2 arquivos, 828 MB e **14.753.112 registros**: 9.298.118 de 2023-01 a 2024-12 e 5.454.994 de 2025-01 a 2026-01.
  - Por UF: GO 5,80 M · MT 3,88 M · DF 2,63 M · MS 2,44 M. Os dois arquivos não têm nenhum mês em comum.
  - Nulos reais em `salario_mensal` (1.862), `horas_contratuais` (851), `idade` (132) e `id_municipio` (13).
- **Carga da camada bronze** no PostgreSQL 16.2, feita localmente num MacBook Apple Silicon com 16 GB de RAM:
  - Carga completa em **54 s**, entre 258 e 286 mil linhas/s.
  - Uma segunda execução, sem nada novo a carregar, termina em **0,5 s**.
  - Ocupação no banco: **1,98 GB** (1,54 GB de dados e 444 MB do índice da chave primária), cerca de 2,4 vezes o tamanho dos CSVs.
  - As contagens por arquivo e por ano, os nulos e os códigos com zero à esquerda no banco batem 1:1 com o perfil do DuckDB.

## O que surpreendeu

- **O recorte termina em janeiro de 2026**, não em fevereiro como registrado na Semana 03.
- **O export do BigQuery apagou zeros à esquerda:** 352 códigos `cbo_2002` vieram com 5 dígitos (ex.: `10105`). Já a `cnae_2_subclasse` manteve os zeros em 1.671.793 linhas, o que teria sido destruído se as colunas fossem tipadas como número.
- **606.842 linhas são exatamente iguais a outras** e não são erro: como o CAGED não identifica o trabalhador, duas admissões de mesmo perfil no mesmo mês ficam idênticas.
- **Salários absurdos:** 251.598 registros abaixo de R$ 100, divididos quase igualmente entre admissões e desligamentos, e um máximo de R$ 1.000.000.000.000.
- **O export tem só 15 colunas** e não parece trazer a indicação de movimentação fora do prazo ou excluída, que é necessária para o saldo oficial.

## O que foi decidido

- **A bronze fica no PostgreSQL 16, no schema `bronze`**, como primeira camada persistida da arquitetura. O modelo 3FN da E1 será derivado dela por SQL.
- **Todas as colunas de negócio são `TEXT`**, sem limpeza nem conversão. Todo tratamento fica para a camada seguinte.
- **Linhagem por arquivo e linha:** a tabela `bronze.ingestao_arquivo` registra cada carga, e cada registro guarda `id_ingestao` e `numero_linha`.
- **Carga idempotente e atômica:** cada arquivo é identificado pelo SHA-256 do conteúdo e carregado com `COPY` numa única transação.
- **Migrações SQL versionadas** em `src/db/migracoes/`, registradas em `public.schema_migracoes`.
- **Novos serviços no `docker-compose.yml`:** `postgres` e `ingestao-bronze`. Detalhes em [Camada Bronze](../camada-bronze.md).

### Pendências para a Squad

- Reexportar fevereiro de 2026 ou corrigir o recorte documentado.
- Conferir na query do BigQuery se as movimentações fora do prazo e excluídas foram incluídas.
- Validar a carga via Docker Compose, que ainda não foi executada nesse caminho.
- Definir as regras de tratamento da camada seguinte: CBO com 5 dígitos, salários atípicos e códigos "não identificado".
