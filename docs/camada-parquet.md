# Extração para Parquet e Tabela Delta

A extração em lote é o primeiro passo da Entrega E2: os dados da fonte transacional (PostgreSQL 16, schema `oltp`) são copiados para arquivos colunares **Apache Parquet**, e as movimentações são materializadas em uma tabela **Delta Lake**. A partir daqui, o **DuckDB** consulta os arquivos diretamente, sem depender do PostgreSQL em execução, conforme o [ADR 0002](adr/0002-simplificacao-arquitetural-duckdb.md).

A extração é 1:1: nenhuma tabela é filtrada, unida ou remodelada. A modelagem dimensional (Star Schema) fica para as transformações dbt-duckdb da E3.

---

## O que é Gerado?

Tudo é gravado em `data/lake/`, que não é versionado (o `.gitignore` exclui `data/*` e `*.parquet`).

| Origem (`oltp`) | Destino | Formato | Particionamento |
|---|---|---|---|
| `municipio` | `data/lake/parquet/municipio/municipio.parquet` | Parquet | Não |
| `cnae_secao` | `data/lake/parquet/cnae_secao/cnae_secao.parquet` | Parquet | Não |
| `cnae_subclasse` | `data/lake/parquet/cnae_subclasse/cnae_subclasse.parquet` | Parquet | Não |
| `cbo_2002` | `data/lake/parquet/cbo_2002/cbo_2002.parquet` | Parquet | Não |
| `movimentacao` | `data/lake/parquet/movimentacao/ano=AAAA/` | Parquet | Por `ano` |
| `movimentacao` | `data/lake/delta/movimentacao/` | Delta Lake | Por `ano` |

Com a amostra versionada, a extração produz 49.178 movimentações, 5.572 municípios, 22 seções e 1.333 subclasses da CNAE e 3.203 ocupações da CBO.

---

## Regras da Extração

| Regra | Como é garantida |
|---|---|
| **Origem somente leitura** | O DuckDB anexa o PostgreSQL com `READ_ONLY`; nenhum comando de escrita chega à origem. |
| **Leitura única** | Todas as tabelas e contagens são lidas dentro de uma única transação do DuckDB. |
| **Conciliação** | A contagem de linhas de cada Parquet é comparada com a da tabela de origem; qualquer diferença interrompe a extração. |
| **Atomicidade** | A extração é gravada em `data/lake/parquet.tmp/` e só substitui a anterior depois de conciliada. Uma falha preserva a extração anterior. |
| **Idempotência** | Reexecutar substitui os arquivos; não acumula registros. |
| **Tipos preservados** | Códigos (`id_municipio`, `cbo_2002`, `cnae_2_subclasse`) permanecem texto, mantendo zeros à esquerda; salários e horas permanecem `DECIMAL`. |

---

## Por que Delta e não Iceberg?

A tarefa pede pelo menos uma tabela Delta **ou** Iceberg. A Squad materializa em **Delta Lake**, gravada com a biblioteca `deltalake` (delta-rs):

- **Sem serviço adicional:** uma tabela Delta é um diretório com arquivos Parquet e um log de transações (`_delta_log/`). O Iceberg exige um catálogo para localizar os metadados, o que reintroduziria o tipo de componente removido pelo ADR 0002.
- **Sem JVM:** o delta-rs é uma biblioteca Python com núcleo em Rust; não há Spark envolvido.
- **Leitura nativa no DuckDB:** a função `delta_scan` da extensão `delta` lê a tabela, mantendo o DuckDB como motor analítico único.

A escrita usa o `deltalake` porque a extensão `delta` do DuckDB 1.5.6 lê tabelas Delta, mas não cria tabelas (o `CREATE TABLE AS` em um catálogo Delta falha com `Not implemented`).

Cada execução sobrescreve o conteúdo e registra novas versões no log. Os arquivos de dados de versões anteriores são removidos (`vacuum`) para não acumular espaço em disco; o histórico das operações permanece em `_delta_log/`.

---

## Como Executar

Com o PostgreSQL populado pela E1 e o ambiente Python do README ativo (variáveis `PG*` exportadas):

```bash
# 1. PostgreSQL (oltp) -> Parquet
python3 -m src.extracao.exportar_parquet

# 2. Parquet -> tabela Delta de movimentações
python3 -m src.extracao.materializar_delta

# 3. Confere que Parquet e Delta respondem à pergunta central como a origem
python3 -m src.extracao.validar_lake
```

A primeira execução precisa de internet para o DuckDB baixar as extensões `postgres` e `delta`.

---

## Como Consultar

Os arquivos são consultáveis por qualquer sessão DuckDB, sem carga prévia:

```sql
-- Parquet particionado
SELECT ano, count(*) AS movimentacoes, sum(saldo_movimentacao) AS saldo
FROM read_parquet('data/lake/parquet/movimentacao/**/*.parquet')
GROUP BY ano
ORDER BY ano;

-- Tabela Delta unida ao cadastro de municípios
SELECT municipio.is_capital, sum(m.saldo_movimentacao) AS saldo
FROM delta_scan('data/lake/delta/movimentacao') AS m
JOIN read_parquet('data/lake/parquet/municipio/municipio.parquet') AS municipio
  USING (id_municipio)
WHERE municipio.sigla_uf IN ('DF', 'GO', 'MT', 'MS')
GROUP BY municipio.is_capital;
```

O módulo `src.extracao.validar_lake` executa a consulta de indicadores de `src/analise.py` (saldo de empregos e salário médio de admissão, capitais × interior) sobre três fontes, PostgreSQL, Parquet e Delta, e falha se os resultados não forem idênticos.

---

## Compressão

Os dois módulos aceitam `--compressao` com `snappy`, `zstd` ou `uncompressed`:

```bash
python3 -m src.extracao.exportar_parquet --compressao zstd
python3 -m src.extracao.materializar_delta --compressao zstd
```

O padrão é `snappy`, mantido após a comparação registrada no [ADR 0003](adr/0003-compressao-parquet.md). Na amostra de 49.178 movimentações, ocupou 960.593 bytes, com medianas de 56,731 ms de escrita e 18,913 ms de leitura. Zstd ocupou menos espaço, mas excedeu a tolerância definida de 25% no custo combinado de escrita e leitura. A leitura medida varre todas as colunas; não equivale à consulta com joins da pergunta central.

Para reproduzir a comparação sem PostgreSQL:

```bash
python3 -m src.extracao.comparar_compressao --amostra data/caged_centro_oeste_amostra.csv
```

Para comparar a tabela OLTP populada, execute sem `--amostra`, com as variáveis `PG*` configuradas. O relatório JSON e os arquivos de cada rodada ficam em um diretório exclusivo de `data/lake/benchmarks/`. O benchmark não altera a extração existente.

A decisão foi medida com CSV tipado e campos técnicos reconstruídos, em ambiente compartilhado com cache aquecido; precisa ser reavaliada na carga completa. O padrão compartilhado também é usado por `materializar_delta.py`, mas os tempos do escritor Delta não foram medidos.
