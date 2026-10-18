# 0003 - Manter Snappy na extração Parquet após comparação de compressão

- **Status:** Aceito para o recorte amostral; revisão com a carga completa prevista abaixo
- **Data:** 15/10/2026
- **Responsável pela tarefa:** Euller Júlio 

---

## 1. Contexto

A E2 extrai `oltp.movimentacao` para Parquet particionado por `ano`. O código usava Snappy provisoriamente. Precisamos escolher com evidência entre espaço ocupado, tempo de escrita em lote e leitura analítica, mantendo o formato aberto e os tipos da origem. Esta ADR trata somente de compressão; complementa, mas não substitui, a decisão sobre mecanismo de ingestão exigida pela [E2](https://unb-bd2.github.io/PlanoEnsino/projeto/e2/).

A amostra versionada contém 49.178 movimentações do Centro-Oeste: 14.834 em 2023, 16.160 em 2024, 16.735 em 2025 e 1.449 em 2026. Não representa todo o volume de produção. Não foi estabelecido SLA pelo grupo; a tolerância de desempenho abaixo é um critério operacional deste experimento, sujeito a revisão.

---

## 2. Alternativas consideradas

### A. Snappy

Manter o padrão existente, com compressão e descompressão rápidas. Não exige dependências novas nem mudança no leitor. Foi escolhido pelo critério medido abaixo.

### B. Zstd

Busca maior redução de armazenamento, podendo consumir mais processamento. É suportado pelo mesmo escritor e leitor. Gerou o menor arquivo, mas excedeu a tolerância de tempo neste experimento.

### C. Uncompressed — opção nula

Dispensa codec de compressão, mas mantém a codificação colunar do Parquet. É a referência de tamanho e de custo sem compressão; não equivale a CSV bruto. Foi descartado por ocupar mais espaço sem vantagem suficiente de tempo.

---

## 3. Medição e Prototipação

**Fonte e limites:** `data/caged_centro_oeste_amostra.csv`, SHA-256 `507f52f8599a91e6750f56f89dcad9a8674a3a02c6e1f180d39da3e0dc63066c`. Não havia PostgreSQL nem Docker disponíveis no ambiente de execução. O modo `--amostra` aplica os tipos e tratamentos de `src/ingestao/carga_oltp.py`, preserva códigos textuais e reconstrói os campos técnicos: IDs sequenciais, `id_ingestao=1`, número da linha e timestamp constante declarado no script. Não valida as FKs dos cadastros, não mede extração PostgreSQL e não é um dump do OLTP real. A distribuição da linhagem poderá afetar a compressão na base completa.

**Ambiente:** Python 3.12.14, DuckDB 1.5.6, Linux 6.18.44 x86_64/glibc 2.39, uma thread DuckDB, ambiente compartilhado de execução do Codex. Recursos físicos e carga concorrente do host não são controlados; os tempos são indicativos deste ambiente.

**Método:** fonte materializada uma vez antes do cronômetro; um aquecimento descartado por codec e sete rodadas válidas, com ordem rotativa. Todos usam as mesmas 17 colunas, quatro partições por ano e demais opções padrão do mesmo DuckDB. O tempo de escrita mede `COPY` até seu retorno (sem `fsync` explícito). A leitura calcula contagem e soma de hashes de **todas as colunas**, obrigando a varredura dos dados; `count(*)` isolado poderia usar somente metadados. O cache do sistema operacional não é limpo: não é leitura de disco frio nem a consulta completa capital/interior. A igualdade exata dos multiconjuntos (`EXCEPT ALL` nos dois sentidos) e do schema é verificada fora dos tempos em todas as rodadas.

**Critério definido no script:** escolher o menor tamanho entre codecs cuja soma das medianas de escrita e leitura seja no máximo 1,25 vez a soma de Snappy. A tolerância de 25% evita trocar espaço por uma regressão maior no ciclo de lote + leitura. Medianas de sete rodadas:

| Codec | Tamanho (bytes) | Escrita (ms) | Leitura (ms) | Soma (ms) |
|---|---:|---:|---:|---:|
| Uncompressed | 1.685.300 | 55,715 | 20,742 | 76,457 |
| Snappy | 960.593 | 56,731 | 18,913 | 75,644 |
| Zstd | 556.147 | 82,367 | 35,132 | 117,499 |

Os [resultados brutos](evidencias/0003-compressao-parquet.json) incluem cada rodada, versões, schema, hash da fonte e partições. Tamanhos são a soma dos quatro arquivos Parquet de uma rodada, sem metadados JSON ou arquivos de outras rodadas.

Reprodução, na raiz do projeto:

```bash
python3 -m pip install -r requirements-pipeline.txt
python3 -m src.extracao.comparar_compressao \
  --amostra data/caged_centro_oeste_amostra.csv --repeticoes 7 --threads 1
```

O comando imprime o diretório exclusivo em `data/lake/benchmarks/compressao-*/`, contendo os três conjuntos de arquivos e `resultados.json`. Cada execução cria outro diretório e não altera `data/lake/parquet` ou Delta. Esses artefatos locais podem ocupar espaço e devem ser removidos pelo operador depois da análise.

Para reavaliar com o OLTP populado e as variáveis `PG*` configuradas conforme o README:

```bash
python3 -m src.extracao.comparar_compressao --repeticoes 7 --threads 1
```

Esse segundo modo anexa PostgreSQL em `READ_ONLY` e copia `movimentacao` em uma transação; não foi executado neste ambiente. Origens vazias são rejeitadas.

---

## 4. Decisão

**Manter Snappy como `COMPRESSAO_PADRAO`, agora fundamentado no recorte medido.** Reduz o tamanho em 43,0% frente a uncompressed. Zstd economiza mais 42,1% frente a Snappy, mas sua soma de tempos é 55,3% maior: 117,499 ms contra o limite de 94,554 ms. Snappy é o menor arquivo entre os candidatos que atendem à tolerância.

---

## 5. Consequências e Tradeoffs

### O que se ganha

- Compressão com custo compatível com o critério do experimento, sem dependência nova.
- Procedimento reproduzível para reavaliar a escolha e evidências versionadas.
- Conservação de tipos, linhas e particionamento, verificada para todos os codecs.

### O que se perde ou se compromete

- Aceitamos 404.446 bytes a mais que Zstd neste recorte.
- A amostra, o cache aquecido e o ambiente compartilhado limitam a generalização; não há evidência de desempenho na carga completa nem garantia de significância estatística.
- A medição não inclui rede, extração da origem, joins, filtros analíticos ou escrita Delta. `materializar_delta.py` importa o mesmo padrão, mas seu escritor não foi comparado neste benchmark.

### O que se torna irreversível ou restringe o sistema futuro

- A escolha é reversível com `--compressao` e reexportação. Os arquivos existentes mantêm o codec com que foram gravados; mudar o padrão não os converte automaticamente.

---

## 6. Gatilho de Revisão

Reexecutar com o OLTP completo antes de extrapolar a decisão para produção; também reavaliar quando houver troca de versão do DuckDB, hardware, particionamento, schema ou padrão de consulta. Substituir Snappy se um codec ocupar menos bytes e cumprir a tolerância de 25% no novo recorte. Se o objetivo passar a privilegiar armazenamento, redefinir explicitamente essa tolerância antes de medir. O escritor Delta requer avaliação própria caso passe a ser o principal consumidor de espaço.
