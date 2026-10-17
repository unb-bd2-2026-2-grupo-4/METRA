# Política e Registro de Uso de IA no projeto

O uso de assistentes e agentes de IA nesta disciplina é **esperado, não apenas tolerado**. O princípio norteador é a **transparência e o entendimento real do raciocínio**, conforme estabelecido na [Política de Uso de IA](https://unb-bd2.github.io/PlanoEnsino/uso-de-ia/) oficial de Banco de Dados 2 (FCTE-UnB).

**Duas regras de forma:** Escreva **no momento do uso**, não na véspera da Entrega: registro reconstruído de memória sai impreciso, e imprecisão aqui é o que a política pune. E versione junto com o código: uma entrada por commit relevante é melhor que um resumo mensal.

**Não precisa registrar** autocompletar de editor, correção ortográfica ou tradução. Registre o que produziu artefato ou mudou uma decisão.

> *"Não há penalidade por usar. Há penalidade por não declarar e por não entender."*

---

## Onde é Utilizado e Declarado

- **Arquitetura e Decisões:** Apoio na exploração de tradeoffs técnicos, confronto de alternativas formais (CRUD vs. Insert-Only, 3FN vs. Flat) e levantamento de restrições de infraestrutura para os ADRs.
- **Implementação:** Construção de esquemas SQL versionados, scripts de automação, pipelines de ingestão e testes de integridade referencial.
- **Documentação:** Estruturação de páginas técnicas, diagramas conceituais (Mermaid) e relatórios no MkDocs.

---

## Registro de Entradas

Abaixo constam os registros de todas as atividades:

### 15/09/2026 - Planejamento de Arquitetura, Estruturação da Documentação e Planilha Técnica
- **Ferramenta:** Antigravity (Google DeepMind)
- **Onde:** `AI-USAGE.md`, `README.md`, `docs/diario/` e documentação MkDocs.
- **O que foi pedido:** Guia na seleção da stack técnica adequada para o Novo CAGED, estruturação do repositório.
- **O que foi aproveitado:** A escolha da arquitetura leve baseada em PostgreSQL (OLTP), MinIO/Parquet (Lakehouse), DuckDB/dbt (OLAP) e Metabase (Consumo); as justificativas técnicas e de mitigação de riscos para a planilha; a configuração do site de documentação com MkDocs Material.
- **Como foi verificado:** Confrontação com os requisitos do [Plano de Ensino](https://unb-bd2.github.io/PlanoEnsino/) e regras das Entregas (E1 a E4), checagem das diretrizes de vocabulário do [CONTEXT.md](https://github.com/UnB-BD2/PlanoEnsino/blob/main/CONTEXT.md) e viabilidade de execução reproduzível via Docker em máquina comum.
- **Quem revisou:** Arthur Evangelista

### 16/09/2026 - Camada bronze: carga dos CSVs brutos do Novo CAGED no PostgreSQL
- **Ferramenta:** Claude Code (Anthropic, Claude Opus 5)
- **Onde:** `src/db/`, `src/ingestao/carga_bronze.py`, `docker/ingestao/Dockerfile`, `docker-compose.yml`, `requirements-pipeline.txt`, `.dockerignore`, `.env.example`, `docs/camada-bronze.md`, `docs/diario/semana-04.md`.
- **O que foi pedido:** Atuar como engenheiro de dados para consumir os CSVs de `data/` e montar a camada bronze (dados brutos) seguindo a arquitetura do METRA.
- **O que foi aproveitado:** Perfil dos CSVs feito com DuckDB; schema `bronze` com todas as colunas como `TEXT` e linhagem por arquivo e linha; migração versionada com um executor simples; carga via `COPY` idempotente (SHA-256) e atômica por arquivo; serviços `postgres` e `ingestao-bronze` no Compose; página de documentação com as medições e os achados para a próxima camada.
- **Como foi verificado:** Carga executada em PostgreSQL 16.2 local com os 14.753.112 registros (54 s). Contagens por arquivo e por ano, nulos, zeros à esquerda e CBOs de 5 dígitos conferidos contra o perfil do DuckDB. Reexecução confirmou a idempotência, inclusive com arquivo renomeado. Um arquivo com linha malformada confirmou o rollback sem carga parcial. O caminho via Docker Compose não foi executado na máquina de desenvolvimento, que não tem Docker.
- **Quem revisou:** Lucas Alves

### 27/09/2026 - Camada Bronze Multi-Fontes (IBGE e CBO), Modelo 3FN Insert-Only e Reprodutibilidade E1
- **Ferramenta:** Antigravity (Google DeepMind)
- **Onde:** `src/db/migracoes/0002_camada_bronze_referencias.sql`, `src/db/migracoes/0003_modelo_transacional_oltp.sql`, `src/ingestao/carga_ibge.py`, `src/ingestao/carga_cbo.py`, `src/ingestao/carga_oltp.py`, `src/ingestao/executar_pipeline.py`, `data/caged_centro_oeste_amostra.csv`, `docker-compose.yml`, `docs/adr/0001-modelagem-sistema-origem.md`, `docs/camada-bronze.md`, `docs/arquitetura.md`, `README.md`.
- **O que foi pedido:** Integrar fontes de dados secundárias oficiais (IBGE Localidades, IBGE CNAE 2.0 e CBO 2002) para cumprir o critério de múltiplas fontes na E1, estruturar suas tabelas brutas na camada Bronze com idempotência e linhagem, implementar a normalização completa do modelo relacional transacional em 3FN com padrão estritamente *insert-only* e integridade referencial estrita para o Centro-Oeste (2023-2026), criar amostra representativa versionada de 2,8 MB para garantir reprodutibilidade sem passos manuais por terceiros, e documentar formalmente os três carimbos de tempo e a decisão no ADR 0001.
- **O que foi aproveitado:** Migração de tabelas bronze de referência; enriquecimento das tabelas de domínio do schema `oltp` (`municipio`, `cbo_2002`, `cnae_secao`, `cnae_subclasse`); rotina de transformação e carga idempotente Bronze -> OLTP 3FN com tratamento de outliers e reconciliação de chaves administrativas; unificação do orquestrador de pipeline no contêiner de ingestão; garantia de fallback automático para a amostra representativa de 49 mil linhas se os arquivos pesados de 828 MB não estiverem presentes; revisão ortográfica completa em português culto acentuado.
- **Como foi verificado:** Execução real em contêiner PostgreSQL 16 local no Docker, medição de tempo de carga (IBGE municípios 0,33s, CNAE 0,19s, CBO 0,25s), verificação de integridade referencial com junções SQL relacionais, teste de recuperação de linhagem de movimentações para o arquivo CSV físico de origem, teste de build do portal MkDocs e confirmação de idempotência.
- **Quem revisou:** Arthur Evangelista

### 05/10/2026 - Registro dos Diários de Bordo (Semanas 05 e 06), Feedback da E1 e Ajustes de Arquitetura
- **Ferramenta:** Antigravity (Google DeepMind)
- **Onde:** `docs/diario/semana-05.md`, `docs/diario/semana-06.md`, `mkdocs.yml`, `README.md`, `AI-USAGE.md`, `docs/uso-de-ia.md`.
- **O que foi pedido:** Estruturar e documentar de forma técnica e profissional as atividades das Semanas 05 e 06 nos diários de bordo, registrando os preparativos para a demonstração, o feedback da professora quanto ao excesso de complexidade acidental e sobrecarga de infraestrutura, a entrega e validação positiva da E1, a recomendação do Dagster em substituição ao Airflow, a avaliação de banco de dados vetorial e o aprimoramento do MER com o CAGED como entidade principal centralizando as chaves estrangeiras de IBGE e CBO.
- **O que foi aproveitado:** Redação dos diários de bordo seguindo estritamente as seções canônicas ("O que foi medido e analisado", "O que surpreendeu" e "O que foi decidido") sem inclusão de tabelas ou gráficos conforme instruído; síntese das diretrizes pedagógicas recebidas; atualização do menu de navegação do MkDocs Material e árvore do repositório no README; sincronização dos registros de transparência no uso de IA.
- **Como foi verificado:** Revisão do conteúdo técnico frente às orientações da disciplina e aos apontamentos da professora; verificação de links, coerência cronológica e observância à exigência de não inserção de tabelas ou gráficos nos diários.
- **Quem revisou:** Arthur Evangelista e Yan Matheus

### 05/10/2026 - Correção de código e criação de diagramas Mermaid
- **Ferramenta:** Antigravity (Google DeepMind)
- **Onde:** `docs/relacionamentos.md` e arquivos de código-fonte.
- **O que foi pedido:** Correção de bugs na implementação atual e auxílio na sintaxe para a criação de diagramas Mermaid.
- **O que foi aproveitado:** O código corrigido e a estrutura gerada para a visualização gráfica dos relacionamentos no diagrama.
- **Como foi verificado:** Validação do funcionamento do código corrigido e verificação da renderização do diagrama na documentação.
- **Quem revisou:** Euller Júlio

### 05/10/2026 - Documentação dos relacionamentos entre as bases
- **Ferramenta:** Codex (OpenAI).
- **Onde:** `docs/relacionamentos.md`, `docs/camada-bronze.md`, `docs/dominio.md`, `mkdocs.yml`, `AI-USAGE.md` e `docs/uso-de-ia.md`.
- **O que foi pedido:** Esclarecer no GitHub Pages os pares de tabelas e os códigos que relacionam CAGED, IBGE, CBO e CNAE na branch `fix/git-pages-docs`.
- **O que foi aproveitado:** Página com correspondências entre fontes Bronze, FKs e cardinalidades do OLTP, diagrama Mermaid, regras de padronização implementadas, limitações e exemplo SQL; inclusão na navegação e links nas páginas existentes.
- **Como foi verificado:** Conferência com as migrações 0002 e 0003 e com `src/ingestao/carga_oltp.py`; geração do site com `mkdocs build --strict`. A consulta foi conferida contra o schema, mas não executada em PostgreSQL. A renderização visual do Mermaid no navegador não foi verificada.
- **Quem revisou:** Euller Júlio

### 05/10/2026 - Atualização da documentação da arquitetura da plataforma
- **Ferramenta:** ChatGPT (OpenAI).
- **Onde:** `README.md`
- **O que foi pedido:** Atualizar a documentação para refletir a nova arquitetura pragmática adotada pelo projeto, substituindo a proposta anterior baseada em PostgreSQL + MinIO + CDC + DuckDB + dbt + Metabase + ETL reverso, por uma arquitetura simplificada centrada em PostgreSQL como fonte transacional OLTP e DuckDB como motor analítico principal.
- **O que foi aproveitado:** Revisão do diagrama arquitetural; manutenção do PostgreSQL 16 na E1 como fonte transacional em 3FN; remoção do MinIO como componente obrigatório; simplificação da E2 para extração analítica via DuckDB e/ou Parquet; manutenção do dbt-duckdb e Star Schema na E3; e reformulação da E4 para consumo direto de dados e métricas a partir do DuckDB ou Parquet, sem dependência obrigatória de Metabase ou ETL reverso.
- **Como foi verificado:** A atualização foi comparada com a decisão arquitetural registrada no ADR de simplificação da plataforma, garantindo consistência entre o diagrama, a descrição das entregas e a separação de responsabilidades entre PostgreSQL e DuckDB.
- **Quem revisou:** Davi Camilo

### 10/10/2026 - Implementação mínima da ADR 0002 com DuckDB

- **Ferramenta:** Codex (OpenAI).
- **Onde:** `src/analise.py`, `requirements-pipeline.txt`, `README.md`, `AI-USAGE.md` e `docs/uso-de-ia.md`.
- **O que foi pedido:** Implementar o plano mínimo PostgreSQL → DuckDB local → tabelas no terminal, com um único módulo de código, preservando a E1 e evitando componentes adicionais.
- **O que foi aproveitado:** Carga transacional em modo somente leitura da origem, substituição integral e atômica da tabela DuckDB, indicadores anuais e consolidados de saldo e salário médio nominal de admissão, diferenças capital − interior, denominadores salariais e competências disponíveis; configuração via variáveis libpq e instruções no README.
- **Como foi verificado:** Migrações e cargas Bronze/OLTP da amostra de 49.178 registros em PostgreSQL 16.15 descartável, com cadastros de teste; conciliação de contagens, códigos, tipos e indicadores com SQL PostgreSQL; reexecução sem duplicação; tentativa de escrita na origem recusada; casos controlados de salários nulos/zero, desligamentos, médias por evento, municípios sentinela, grupos ausentes e arredondamento final; rollback em falha SQL e carga vazia; falha de conexão com saída 1, sem apresentação de resultados antigos. Usados DuckDB 1.5.6 e arquivos temporários, sem testes permanentes; documentação validada com `python3 -m mkdocs build --strict`. A ingestão completa das APIs IBGE/CBO e os benchmarks da ADR não foram reproduzidos.
- **Quem revisou:** Tiago Antunes

### 13/10/2026 - Extração para Parquet e tabela Delta (E2, tarefa 2)

- **Ferramenta:** Claude Code (Anthropic, Claude Opus 5.5)
- **Onde:** `src/extracao/exportar_parquet.py`, `src/extracao/materializar_delta.py`, `src/extracao/validar_lake.py`, `requirements-pipeline.txt`, `docs/camada-parquet.md`, `mkdocs.yml`, `README.md`, `AI-USAGE.md` e `docs/uso-de-ia.md`.
- **O que foi pedido:** Analisar como implementar as tarefas 2 e 5 da E2 (Parquet, Delta/Iceberg e compressão) seguindo os padrões do projeto, dividir o trabalho entre dois integrantes e implementar a parte de extração para Parquet e materialização da tabela Delta, deixando a comparação de compressão e o ADR para o outro integrante.
- **O que foi aproveitado:** Extração 1:1 das cinco tabelas do schema `oltp` via DuckDB em modo somente leitura, com `movimentacao` particionada por ano, conciliação de contagens e substituição atômica; materialização da tabela Delta com `deltalake` (delta-rs) lida por `delta_scan`; parâmetro `--compressao` com padrão provisório `snappy`; validação que compara a consulta da pergunta central entre PostgreSQL, Parquet e Delta; a escolha de Delta em vez de Iceberg por dispensar catálogo; página de documentação e instruções no README.
- **Como foi verificado:** Pipeline E1 executado com a amostra de 49.178 registros em PostgreSQL 16 via Docker Compose; extração, materialização e validação executadas com DuckDB 1.5.6 e deltalake 1.6.6 em Python 3.14, com indicadores idênticos nas três fontes e iguais aos de `python3 -m src.analise`; conferência de tipos e de zeros à esquerda nos códigos; reexecução sem acúmulo de registros; senha incorreta com saída 1 e extração anterior preservada; materialização sem Parquet com saída 1; teste direto de que a extensão `delta` do DuckDB 1.5.6 não cria tabelas; documentação validada com `mkdocs build --strict`. Não foi testado com a base completa de 14,7 milhões de registros nem em Python 3.12; nenhuma comparação de compressão foi medida.
- **Quem revisou:** Lucas Alves

### 15/10/2026 - Comparação de compressão Parquet (E2, tarefa 2)

- **Ferramenta:** Codex (OpenAI).
- **Onde:** `src/extracao/comparar_compressao.py`.
- **O que foi pedido:** Implementar somente o benchmark de compressão, ADR 0003, adoção do vencedor, diário e declaração de IA, com commits atômicos.
- **O que foi aproveitado:** Benchmark de uncompressed, Snappy e Zstd, cópia única da fonte, particionamento por ano, aquecimento, sete repetições, varredura de todas as colunas, comparação exata dos dados e relatório JSON. Opção local de CSV tipado para reproduzir com a amostra versionada.
- **Como foi verificado:** Execução com DuckDB 1.5.6 e Python 3.12 sobre as 49.178 linhas da amostra. Os três codecs preservaram schema e multiconjunto de linhas em todas as rodadas. PostgreSQL e Docker indisponíveis neste ambiente: o modo PostgreSQL não foi executado. Os campos de linhagem no modo amostral são reconstruídos e declarados; não se trata de uma exportação do banco populado.
- **Quem revisou:** Euller Júlio.

#### Continuação — ADR e evidências

- **Onde:** `docs/adr/0003-compressao-parquet.md`, relatório JSON em `docs/adr/evidencias/` e navegação em `mkdocs.yml`.
- **O que foi aproveitado:** ADR no template de seis passos, números reais da execução e critério de seleção definido no benchmark. Snappy venceu; a limitação do recorte amostral está explícita.
- **Como foi verificado:** Tabela confrontada com as medianas e tamanhos do JSON; preservação das sete medições por codec e das condições de reprodução.

#### Continuação — padrão de compressão

- **Onde:** `src/extracao/exportar_parquet.py` e `docs/camada-parquet.md`.
- **O que foi aproveitado:** Manutenção de `COMPRESSAO_PADRAO = "snappy"`, vencedor medido, com remoção da indicação de escolha provisória e referência à ADR 0003.
- **Como foi verificado:** O padrão permaneceu Snappy e o benchmark validou seus arquivos. A escrita Delta e o acesso PostgreSQL não foram executados.

#### Continuação — diário e validação final

- **Onde:** `docs/diario/semana-07.md`, `mkdocs.yml` e este registro.
- **O que foi aproveitado:** Registro do que foi medido, do resultado inesperado e da decisão, sem atribuir ao integrante uma revisão ainda não realizada.
- **Como foi verificado:** Benchmark principal completo; casos locais adicionais com valores vazios, salário negativo, códigos com zeros e linhas de entrada repetidas; caminho com apóstrofo; rejeição de origem vazia/ausente, menos de três repetições e zero threads; compilação dos módulos Python, `git diff --check` e geração da documentação com `python -m mkdocs build --strict`. Os testes auxiliares usam dados controlados e não compõem os números da ADR.

### 17/10/2026 - Implementação de CDC por decodificação lógica do WAL (E2, tarefa 1)

- **Ferramenta:** ChatGPT (OpenAI).
- **Onde:** `docker-compose.yml`, `src/cdc/01_preparar.sh`, `src/cdc/02_consumir.sh`, `src/cdc/03_testar.sh`.
- **O que foi pedido:** Analisar como implementar o CDC (Change Data Capture) no PostgreSQL existente, seguindo a arquitetura do projeto e os requisitos da E2. Foram avaliadas alternativas com Debezium e Kafka, optando-se pela decodificação lógica nativa do PostgreSQL utilizando `pg_recvlogical` e o plugin `test_decoding`, sem necessidade de serviços adicionais, considerando o nível de complexidade do projeto. Também foi solicitada a criação de scripts para configurar o CDC, capturar alterações e comprovar a propagação dos eventos para um arquivo.
- **O que foi aproveitado:** Configuração do PostgreSQL 16 com `wal_level=logical`, `max_replication_slots` e `max_wal_senders`; criação do slot lógico `metra_cdc_slot`; utilização do `pg_recvlogical` para consumir alterações do WAL; armazenamento dos eventos em `data/cdc/eventos.log`; criação da tabela auxiliar `oltp.cdc_probe` para testar operações sem modificar os dados reais do Novo CAGED; scripts automatizados para preparação, consumo e teste de `INSERT` e `UPDATE`.
- **Como foi verificado:** Execução dos scripts de CDC no ambiente Docker Compose e conferência do arquivo `data/cdc/eventos.log`. Foi comprovada a captura de um `INSERT` na tabela `oltp.cdc_probe`, registrado na transação 769, e de um `UPDATE` no mesmo registro, registrado na transação 770. Ambos apresentaram os respectivos comandos `BEGIN` e `COMMIT`, demonstrando que as alterações confirmadas no PostgreSQL foram capturadas e propagadas para o arquivo. Verificou-se que a regra `*.log` do `.gitignore` impede o versionamento de novos arquivos de log. Os testes comprovaram a captura e propagação de eventos, mas não validaram o reprocessamento com deduplicação nem a integração com a camada analítica.
- **Quem revisou:** Davi Camilo

#### Continuação — Atualização da documentação no README

- **Onde:** `README.md`.
- **O que foi pedido:** Auxílio na atualização e padronização do README do projeto, incluindo a descrição da implementação de CDC e reprocessamento idempotente da E2.
- **O que foi aproveitado:** Inclusão de instruções para executar os scripts de CDC e replay, com explicações sobre a captura de alterações via `pg_recvlogical`, armazenamento dos eventos e deduplicação com SQLite.
- **Como foi verificado:** Os textos e comandos foram revisados quanto à clareza, coerência técnica e padronização com as demais seções do README.
