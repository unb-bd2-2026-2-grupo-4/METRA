# Diário de Bordo - Semana 08

- **Data:** Semana 8 (Semestre 2026/2)
- **Autor(es):** Euller Júlio e Lucas Alves (com apoio da Squad G4, registrado no `uso-de-ia.md`)

---

## O que foi medido e analisado

- **Extração em lote OLTP para Parquet e materialização Delta Lake:** Execução e medição da exportação 1:1 das cinco tabelas do schema `oltp` para arquivos Apache Parquet (`src/extracao/exportar_parquet.py`) com particionamento de `movimentacao` por `ano`, seguida da materialização da tabela Delta Lake via `delta-rs` (`src/extracao/materializar_delta.py`) e validação cruzada nas três fontes (`src/extracao/validar_lake.py`).
- **Comparação empírica de codecs de compressão Parquet:** Avaliação de `uncompressed`, `snappy` e `zstd` sobre as 49.178 movimentações da amostra versionada, tipadas conforme o modelo OLTP e particionadas por ano (`src/extracao/comparar_compressao.py`).
- **Protocolo experimental de benchmark:** Execução com um aquecimento descartado e sete rodadas válidas por codec, em ordem rotativa, com uma thread e sobre a mesma cópia da fonte, medindo tamanho em bytes, tempo de escrita e tempo de leitura de todas as 17 colunas.
- **Resultados medidos (medianas de 7 rodadas):** `uncompressed` ocupou 1.685.300 bytes (55,715 ms de escrita e 20,742 ms de leitura, soma de 76,457 ms); `snappy` ocupou 960.593 bytes (56,731 ms de escrita e 18,913 ms de leitura, soma de 75,644 ms); `zstd` ocupou 556.147 bytes (82,367 ms de escrita e 35,132 ms de leitura, soma de 117,499 ms). Todas as rodadas foram preservadas em `docs/adr/evidencias/0003-compressao-parquet.json`.

## O que surpreendeu

- **Tradeoff entre taxa de compressão e tempo no Zstd:** Embora o Zstd tenha reduzido o espaço em mais 42,1% frente ao Snappy, seu custo combinado de escrita e leitura foi 55,3% maior nesta execução, ultrapassando o limite operacional de 25% definido no experimento.
- **Comportamento de metadados no Parquet e escrita Delta no DuckDB:** Uma consulta `count(*)` isolada em Parquet é respondida pelo rodapé de metadados sem ler os blocos de dados, exigindo o uso de `sum(hash(COLUMNS(*)))` no benchmark para forçar a descompressão real. Além disso, verificou-se que a extensão `delta` do DuckDB 1.5.6 realiza leitura (`delta_scan`), mas ainda não suporta criação direta de tabelas, motivando a escrita via biblioteca `deltalake` (`delta-rs`).

## O que foi decidido

- **Adoção de Delta Lake via `delta-rs` para a camada aberta da E2:** Escolha do formato Delta Lake em vez de Apache Iceberg por dispensar servidor de catálogo externo e JVM, mantendo total aderência à simplificação do ADR 0002.
- **Formalização do ADR 0003 mantendo Snappy como padrão:** Manutenção de `COMPRESSAO_PADRAO = "snappy"` fundamentada pelo critério objetivo do experimento (menor tamanho cujo tempo combinado de escrita e leitura não exceda Snappy em mais de 25%), com gatilho de revisão previsto para a carga completa de 14,7 milhões de registros.
- **Garantia de roteamento por tempo do evento e conciliação tripla:** Particionamento estrito pela competência do evento (`ano`) para absorver dados atrasados na janela histórica correta, com validação automatizada garantindo resultados idênticos entre PostgreSQL, Parquet e Delta Lake.
