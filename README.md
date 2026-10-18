# METRA (Monitoramento e Engenharia de dados do TRAbalho)

> **Plataforma de Dados do Mercado de Trabalho Formal (Novo CAGED)**  
> **Projeto Integrado: Banco de Dados 2 (FCTE / Universidade de Brasília)**  
> **Oferta:** 2026/2 | **Squad G4**  
> **Documentação completa:** https://unb-bd2-2026-2-grupo-4.github.io/METRA/

---

## Pergunta de Gestão Central (Entrega E1)

> **"Qual é a diferença no saldo líquido de empregos gerados e no salário médio de admissão entre as capitais e os municípios do interior da Região Centro-Oeste no período de 2023 a 2026?"**

---

## Grupo (Squad G4)

<div align="center">
  <table>
    <tr>
      <td align="center"><a href="https://github.com/arthurevg"><img src="https://github.com/arthurevg.png" width="150px" alt=""/><br />Arthur Evangelista</a></td>
      <td align="center"><a href="https://github.com/Davicamilo23"><img src="https://github.com/Davicamilo23.png" width="150px" alt=""/><br />Davi Camilo</a></td>
      <td align="center"><a href="https://github.com/Potatoyz908"><img src="https://github.com/Potatoyz908.png" width="150px" alt=""/><br />Euller Júlio</a></td>
      <td align="center"><a href="https://github.com/LucasAlves71"><img src="https://github.com/LucasAlves71.png" width="150px" alt=""/><br />Lucas Alves</a></td>
      <td align="center"><a href="https://github.com/TiagoBalieiro"><img src="https://github.com/TiagoBalieiro.png" width="150px" alt=""/><br />Tiago Antunes</a></td>
      <td align="center"><a href="https://github.com/Yanmatheus0812"><img src="https://github.com/Yanmatheus0812.png" width="150px" alt=""/><br />Yan Matheus</a></td>
    </tr>
  </table>
</div>

---

## Domínio e Problema

Pessoas que buscam emprego enfrentam grande assimetria de informação: é difícil saber com precisão quando e onde a contratação formal está aquecendo ou esfriando, e faltam evidências públicas consolidadas sobre disparidades salariais e de rotatividade por recorte sociodemográfico (gênero, raça/cor, idade, escolaridade). Decisões críticas como *"é o momento adequado para buscar recolocação ou transição de carreira?"* ou *"onde o poder público deve focar incentivos à geração de emprego?"* ainda são tomadas baseadas em impressões empíricas.

O **METRA** constrói o pipeline completo de dados, do sistema transacional de origem à decisão analítica e operacional, para responder a perguntas de gestão fundamentadas sobre o mercado de trabalho formal brasileiro no Centro-Oeste (DF, GO, MT, MS) entre 2023 e 2026.

---

## Personas

1. **Trabalhador em busca de recolocação:** Busca entender tendências de contratação e demissão por setor econômico, dinâmica salarial e sazonalidade para planejar transições profissionais.
2. **Pesquisador e Gestor Público de Políticas de Emprego:** Necessita de subsídios estatísticos para avaliar dinâmicas regionais (capitais vs. interior), rotatividade setorial (*turnover*) e desigualdades sociodemográficas no emprego formal.

---

## Perguntas de Gestão

O **METRA** foi concebido para responder a cinco perguntas centrais:

1. **Qual é a diferença no saldo líquido de empregos gerados e no salário médio entre as capitais e os municípios do interior?** (Pergunta Central E1)
2. **Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?**
3. **Existe sazonalidade evidente nas contratações e demissões (ex.: pico do comércio no fim de ano)?**
4. **Os setores com maior taxa de rotatividade (*turnover*) praticam salários médios mais baixos?**
5. **Como o perfil sociodemográfico (gênero, raça/cor, idade, escolaridade) impacta o nível salarial e as movimentações de admissão/desligamento?**

---

## Fontes Oficiais de Dados (Multi-Fontes)

O projeto integra três fontes públicas oficiais abertas:

1. **Novo CAGED (Ministério do Trabalho e Emprego):** [Microdados de Movimentação](https://basedosdados.org/dataset/562b56a3-0b01-4735-a049-eeac5681f056?raw_data_source=59844eec-a948-4ef4-adf0-1db8228fc8e9) contendo as declarações mensais obrigatórias de admissões e desligamentos formais (+14,7 milhões de linhas para o Centro-Oeste, 2023-2026, com amostra representativa versionada de 49 mil linhas para reprodutibilidade).
2. **IBGE (Instituto Brasileiro de Geografia e Estatística):**
   - **Localidades:** API REST oficial (`/api/v1/localidades/municipios`) fornecendo todos os 5.571 municípios brasileiros com microrregião, mesorregião, UF e região.
   - **CNAE 2.0 Subclasses:** API REST oficial (`/api/v2/cnae/subclasses`) com 1.332 subclasses econômicas e seções correspondentes.
3. **CBO 2002 (Ministério do Trabalho e Emprego):** Classificação Brasileira de Ocupações oficial com mais de 10 mil cargos formais e sinônimos ocupacionais.

---

## Arquitetura e Roteiro de Entregas

O **METRA** é construído incrementalmente ao longo das quatro Entregas da disciplina, operando integralmente em contêineres Docker locais via `docker-compose.yml`:

```text
[Fontes Oficiais: Novo CAGED (MTE) / IBGE / CBO]
                         |
                         v
              (Carga Reprodutível e Versionada)
              +---------------------------+
E1            |       PostgreSQL 16       |
              | Fonte Transacional OLTP   |
              | Modelo 3FN + PKs/FKs      |
              +-------------+-------------+
                            |
                            v
                 (Extração Analítica)
              +---------------------------+
E2            |          DuckDB           |
              | Leitura do PostgreSQL     |
              | e/ou arquivos Parquet     |
              +-------------+-------------+
                            |
                            v
              (Transformações Analíticas)
              +---------------------------+
E3            |    DuckDB + dbt-duckdb    |
              |      Star Schema          |
              | Testes de Qualidade       |
              +-------------+-------------+
                            |
                            v
                    (Consumo)
              +---------------------------+
E4            | Análises e Visualizações  |
              | sobre DuckDB / Parquet    |
              | + Camada de Métricas      |
              +---------------------------+
```

- **E1 (Semana 7):** Fonte transacional implementada em **PostgreSQL 16**, com modelo OLTP normalizado em **3FN**, integridade referencial por PKs/FKs, migrações versionadas e carga reprodutível dos dados oficiais utilizados pelo projeto.

- **E2 (Semana 10):** Extração dos dados da fonte transacional para processamento analítico pelo **DuckDB**, que pode consultar diretamente o PostgreSQL ou consumir arquivos colunares **Parquet** gerados em lote, eliminando a necessidade de uma camada intermediária baseada em MinIO.

- **E3 (Semana 13):** Construção da camada analítica em **DuckDB**, utilizando **dbt-duckdb** para transformar os dados em modelo dimensional **Star Schema**, aplicar testes automatizados de qualidade e manter as transformações reproduzíveis e versionadas.

- **E4 (Semana 16):** Camada de consumo baseada diretamente nos dados analíticos disponibilizados pelo **DuckDB** ou pelos arquivos Parquet gerados por ele, permitindo consultas, métricas, análises e visualizações. Ferramentas externas de visualização podem ser integradas quando necessário, sem constituírem dependência obrigatória da arquitetura.

---

## Estrutura do Repositório

```text
.
├── .github/
│   └── workflows/
│       └── deploy-docs.yml # Pipeline de deploy automatizado no GitHub Pages
├── .gitignore              # Regras de exclusão para dados pesados (permite a amostra de 2.8 MB)
├── AI-USAGE.md             # Registro contemporâneo de uso de assistentes de IA (conforme política)
├── README.md               # Visão geral do METRA, domínio, setup e governança
├── docker-compose.yml      # Manifesto que sobe todos os serviços locais da plataforma (E1 a E4)
├── mkdocs.yml              # Configuração do portal de documentação (Material for MkDocs)
├── requirements-docs.txt   # Dependências Python para execução local do MkDocs
├── requirements-pipeline.txt # Dependências Python da ingestão, das migrações e da extração
├── .env.example            # Variáveis de ambiente do PostgreSQL (opcional)
├── docker/                 # Arquivos de configuração e Dockerfiles dos serviços
│   └── ingestao/Dockerfile # Imagem da tarefa de ingestão e carga do pipeline E1
├── src/                    # Scripts de ingestão, pipeline e transformações
│   ├── analise.py          # Carga PostgreSQL -> DuckDB e indicadores no terminal
│   ├── cdc/
│   │   ├── 01_preparar.sh        # Configura tabela de teste oltp.cdc_probe e slot lógico
│   │   ├── 02_consumir.sh        # Captura eventos do WAL via pg_recvlogical
│   │   ├── 03_testar.sh          # Gera INSERT e UPDATE confirmados na origem
│   │   └── 04_reprocessar.py     # Consumidor idempotente com deduplicação em SQLite
│   ├── extracao/
│   │   ├── comparar_compressao.py # Benchmark reproduzível de codecs Parquet (ADR 0003)
│   │   ├── exportar_parquet.py   # Extração PostgreSQL (oltp) -> Parquet, com compressão configurável
│   │   ├── materializar_delta.py # Materialização Parquet -> tabela Delta de movimentações
│   │   └── validar_lake.py       # Confere a pergunta central em PostgreSQL, Parquet e Delta
│   ├── db/
│   │   ├── migrar.py       # Aplica migrações pendentes (registradas em public.schema_migracoes)
│   │   └── migracoes/      # Migrações SQL versionadas
│   │       ├── 0001_camada_bronze.sql             # Schema bronze inicial e microdados CAGED
│   │       ├── 0002_camada_bronze_referencias.sql # Tabelas bronze para IBGE e CBO
│   │       └── 0003_modelo_transacional_oltp.sql  # Schema OLTP normalizado em 3FN
│   └── ingestao/
│       ├── carga_bronze.py      # Carga dos CSVs do CAGED no schema bronze (com fallback automático)
│       ├── carga_ibge.py        # Ingestão das APIs do IBGE (municípios e CNAE) no bronze
│       ├── carga_cbo.py         # Ingestão da base CBO 2002 no bronze
│       ├── carga_oltp.py        # Promoção e normalização Bronze -> OLTP 3FN
│       └── executar_pipeline.py # Orquestrador sequencial de ponta a ponta
├── tests/
│   └── test_cdc_replay.py  # Testes unitários de replay idempotente, transações incompletas e dados atrasados
├── data/                   # Diretório de dados (inclui amostra versionada de 2.8 MB)
│   └── caged_centro_oeste_amostra.csv # Amostra representativa reproduzível (49.178 linhas)
└── docs/
    ├── index.md            # Página inicial do site de documentação
    ├── dominio.md          # Detalhamento do domínio, personas e 5 perguntas de gestão
    ├── arquitetura.md      # Visão técnica das camadas e Entregas (E1 a E4)
    ├── camada-bronze.md    # Regras, modelo multi-fontes e validações da camada bronze
    ├── relacionamentos.md  # Chaves e cardinalidades entre CAGED, IBGE, CBO e CNAE
    ├── cdc.md              # Captura de mudanças via WAL lógico e reprocessamento idempotente
    ├── camada-parquet.md   # Extração para Parquet, tabela Delta e como consultá-las
    ├── uso-de-ia.md        # Política de transparência de IA
    ├── stylesheets/
    │   └── extra.css       # Estilização customizada com texto justificado
    ├── adr/                # Registros de Decisões de Arquitetura (Método de Decisão em 6 passos)
    │   ├── template.md     # Template oficial Nygard padronizado para os ADRs
    │   ├── 0001-modelagem-sistema-origem.md          # Decisão 3FN Insert-Only e multi-fontes
    │   ├── 0002-simplificacao-arquitetural-duckdb.md # Simplificação com DuckDB
    │   ├── 0003-compressao-parquet.md                # Benchmark e escolha de compressão Snappy
    │   └── 0004-cdc-decodificacao-logica.md          # Estratégia de CDC com pg_recvlogical
    └── diario/             # Diários de bordo semanais da Squad G4
        ├── semana-01.md    # Formação da Squad e alinhamento dos critérios de avaliação
        ├── semana-02.md    # Escolha do domínio, personas e as 5 perguntas de gestão
        ├── semana-03.md    # Engenharia de Dados aplicada ao projeto e mapeamento de riscos
        ├── semana-04.md    # Perfil dos dados brutos e carga da camada bronze no PostgreSQL
        ├── semana-05.md    # Arquitetura do METRA, complexidade acidental e feedback docente
        ├── semana-06.md    # Validação da E1, Dagster, banco vetorial e refinamento do MER
        ├── semana-07.md    # Apresentação da E1, simplificação com DuckDB e ADR 0002
        ├── semana-08.md    # Extração Parquet, tabela Delta Lake e benchmark de compressão (ADR 0003)
        └── semana-09.md    # CDC por decodificação lógica, replay idempotente e ADR 0004
```

---

## Como Subir o METRA (Execução 100% Reprodutível)

### Pré-requisitos

- [Git](https://git-scm.com/)
- [Docker Engine](https://docs.docker.com/engine/) e [Docker Compose](https://docs.docker.com/compose/)

### Passos de Execução

```bash
# 1. Clonar o repositório
git clone https://github.com/unb-bd2-2026-2-grupo-4/METRA.git
cd METRA

# 2. Subir a documentação localmente (opcional)
docker compose up -d docs

# 3. Subir o PostgreSQL 16
docker compose up -d postgres

# 4. Executar o pipeline E1 completo (migrações, bronze multi-fontes e modelo OLTP 3FN)
#    Se os CSVs pesados estiverem em data/, carrega os 14,7 milhões de registros.
#    Em uma máquina limpa de terceiro, utiliza automaticamente a amostra de 49 mil linhas versionada.
docker compose run --rm ingestao-bronze
```

Acesse o portal de documentação em: [http://localhost:8000](http://localhost:8000).

### Análise local com DuckDB

Após concluir a E1, execute a análise com Python 3.12 local, sem cargas concorrentes:

```bash
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements-pipeline.txt

# Ajuste conforme as credenciais e a porta do PostgreSQL local.
export PGHOST=localhost PGPORT=5432 PGDATABASE=metra PGUSER=metra
read -r -s -p 'Senha do PostgreSQL: ' PGPASSWORD
export PGPASSWORD
python3 -m src.analise
```

As variáveis `PG*` são as mesmas utilizadas pela ingestão Python. O módulo não carrega `.env` automaticamente; as variáveis `POSTGRES_*` do Compose devem ser traduzidas para os valores `PG*` correspondentes. A primeira execução precisa de internet para baixar a extensão `postgres` do DuckDB.

O comando lê PostgreSQL em modo somente leitura e substitui, em uma transação, a tabela analítica de `data/metra.duckdb`. Reexecuções não acumulam registros. Uma falha interrompe a análise com erro e preserva a tabela anterior; o arquivo gerado não é versionado.

As tabelas no terminal comparam capitais e interior por ano e para o período consolidado de 2023-2026. Consideram municípios identificados de DF, GO, MT e MS, usando `is_capital` da origem. O saldo é a soma de `saldo_movimentacao`; a definição operacional de admissão é `saldo_movimentacao = 1`. A média salarial nominal considera apenas salários positivos dessas admissões, excluindo nulos e zeros, inclusive valores ausentes ou negativos convertidos em zero pela E1. A média é calculada sobre eventos, e as diferenças são **capital - interior**, arredondadas somente na apresentação. As quantidades de salários considerados e as competências disponíveis acompanham os resultados; grupos ausentes ou sem salários elegíveis produzem valores nulos.

### Captura de Mudanças (CDC) e Reprocessamento Idempotente (E2)

Com o PostgreSQL em execução e o schema `oltp` criado, execute na raiz do projeto:

```bash
bash src/cdc/01_preparar.sh       # Cria a tabela de teste e o slot de replicação lógica
bash src/cdc/02_consumir.sh       # Captura alterações do WAL e grava em data/cdc/eventos.log
```

Em outro terminal, execute o teste de captura e o reprocessamento:

```bash
bash src/cdc/03_testar.sh         # Executa INSERT e UPDATE para validar a captura
python3 src/cdc/04_reprocessar.py # Processa os eventos com deduplicação
python3 src/cdc/04_reprocessar.py # Reexecuta e comprova que não há duplicação no destino
```

O CDC utiliza a **decodificação lógica do WAL do PostgreSQL**, por meio do `pg_recvlogical` e do plugin `test_decoding`, sem depender de Kafka ou Debezium. As alterações confirmadas no banco são capturadas e registradas em `data/cdc/eventos.log`. O teste utiliza a tabela auxiliar `oltp.cdc_probe`, preservando os dados reais do Novo CAGED.

O reprocessamento é realizado por um consumidor Python que identifica cada evento por um hash SHA-256 e utiliza uma chave primária no SQLite (`data/cdc/replay.sqlite3`) para impedir inserções duplicadas. Assim, **executar novamente o consumidor não duplica os eventos já processados no destino**, embora o arquivo de log bruto possa conter eventos repetidos. A solução demonstra idempotência no consumidor, tratamento de transações incompletas e incorporação de dados atrasados em janelas reprocessadas, sem afirmar *exactly-once* de ponta a ponta.

Os arquivos gerados em `data/cdc/` não são versionados. Detalhes em [`docs/cdc.md`](./docs/cdc.md).

### Extração para Parquet e Tabela Delta (E2)

No mesmo ambiente Python, com as variáveis `PG*` exportadas:

```bash
python3 -m src.extracao.exportar_parquet    # PostgreSQL (oltp) -> data/lake/parquet/
python3 -m src.extracao.materializar_delta  # Parquet -> data/lake/delta/movimentacao/
python3 -m src.extracao.validar_lake        # compara PostgreSQL, Parquet e Delta
```

A extração copia as cinco tabelas do schema `oltp` em modo somente leitura, particiona `movimentacao` por `ano` (roteando pelo tempo do evento para absorver dados atrasados na competência correta) e concilia a contagem de linhas com a origem. A tabela Delta é gravada com `deltalake` (delta-rs) e lida pelo DuckDB com `delta_scan`. Reexecuções substituem os arquivos sem acumular registros, e nada em `data/lake/` é versionado. A primeira execução precisa de internet para baixar as extensões `postgres` e `delta` do DuckDB.

Os dois primeiros comandos aceitam `--compressao` (`snappy`, `zstd` ou `uncompressed`); o padrão `snappy` foi validado por benchmark reproduzível conforme documentado no [`ADR 0003`](./docs/adr/0003-compressao-parquet.md). Detalhes em [`docs/camada-parquet.md`](./docs/camada-parquet.md).

---

## Governança, Transparência e Evolução do Projeto

- **ADRs:** Todas as decisões arquiteturais seguem o **Método de Decisão em 6 passos** e ficam versionadas em [`docs/adr/`](./docs/adr/).
- **Uso de IA:** Este repositório cumpre integralmente a [Política de Uso de IA](https://unb-bd2.github.io/PlanoEnsino/uso-de-ia/) da disciplina. Todas as contribuições de assistentes são documentadas de forma contemporânea no arquivo [`docs/uso-de-ia.md`](./docs/uso-de-ia.md).
- **Diário de Bordo:** O acompanhamento contínuo de aprendizados, medições e surpresas da Squad é registrado semanalmente em [`docs/diario/`](./docs/diario/).
