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
│       ├── deploy-docs.yml # Pipeline de deploy automatizado no GitHub Pages
│       └── testes-integracao.yml # Fluxo do zero e suíte de testes no Docker
├── .gitignore              # Regras de exclusão para dados pesados (permite a amostra de 2.8 MB)
├── AI-USAGE.md             # Ponteiro para o registro de uso de IA em docs/uso-de-ia.md (conforme política)
├── README.md               # Visão geral do METRA, domínio, setup e governança
├── docker-compose.yml      # Manifesto que sobe todos os serviços locais da plataforma (E1 a E4)
├── mkdocs.yml              # Configuração do portal de documentação (Material for MkDocs)
├── requirements-docs.txt   # Dependências Python para execução local do MkDocs
├── requirements-pipeline.txt # Dependências Python da ingestão, das migrações, da extração e do dbt
├── .env.example            # Variáveis de ambiente do PostgreSQL (opcional)
├── docker/                 # Arquivos de configuração e Dockerfiles dos serviços
│   ├── ingestao/Dockerfile # Imagem da tarefa de ingestão e carga do pipeline E1
│   ├── dagster/Dockerfile  # Imagem do webserver e do daemon do Dagster
│   └── painel/Dockerfile   # Imagem do painel Streamlit (somente leitura do banco analítico)
├── scripts/
│   └── metra-do-zero.sh    # Fluxo completo do zero: volumes limpos -> Bronze ... Gold -> painel
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
│   ├── acesso/
│   │   ├── base_consumo.py       # Base de consumo isolada (só views consumo.*) e conexão do consumidor
│   │   └── demonstrar_acesso.py  # Acessos permitidos e negados ao detalhe, por perfil
│   ├── qualidade/
│   │   └── verificar_fluxo.py    # Concilia contagem e saldo de Bronze, OLTP, Parquet, Delta, Silver e Gold
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
├── dbt_metra/              # Projeto dbt-duckdb da camada analítica (E3)
│   ├── dbt_project.yml     # Camadas: staging -> schema silver; marts -> schema gold
│   ├── profiles.yml        # Alvo DuckDB local (data/metra_analitico.duckdb), sem credenciais
│   ├── macros/             # generate_schema_name e metrica(): SQL das métricas compilado da camada semântica
│   └── models/
│       ├── staging/        # Silver: fontes Parquet e modelos stg_movimentacao, stg_municipio, stg_cbo, stg_cnae
│       ├── marts/          # Gold: dimensões e fatos do Star Schema
│       ├── consumo/        # Views agregadas públicas, com supressão de grupos com menos de 5
│       └── semantic/       # Camada semântica: metricas.yml (definição única das métricas) e time spine
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
    │   ├── 0004-cdc-decodificacao-logica.md          # Estratégia de CDC com pg_recvlogical
    │   ├── 0005-modelagem-analitica-dbt.md           # Grão de movimentação, Star Schema e qualidade dbt
    │   ├── 0006-orquestracao-com-dagster.md          # Orquestração integrada com Dagster e dagster-dbt
    │   └── 0007-busca-semantica-e-consumo.md         # Busca vetorial CBO 2002 e Text-to-SQL governado
    └── diario/             # Diários de bordo semanais da Squad G4
        ├── semana-01.md    # Formação da Squad e alinhamento dos critérios de avaliação
        ├── semana-02.md    # Escolha do domínio, personas e as 5 perguntas de gestão
        ├── semana-03.md    # Engenharia de Dados aplicada ao projeto e mapeamento de riscos
        ├── semana-04.md    # Perfil dos dados brutos e carga da camada bronze no PostgreSQL
        ├── semana-05.md    # Arquitetura do METRA, complexidade acidental e feedback docente
        ├── semana-06.md    # Validação da E1, Dagster, banco vetorial e refinamento do MER
        ├── semana-07.md    # Apresentação da E1, simplificação com DuckDB e ADR 0002
        ├── semana-08.md    # Extração Parquet, tabela Delta Lake e benchmark de compressão (ADR 0003)
        ├── semana-09.md    # CDC por decodificação lógica, replay idempotente e ADR 0004
        ├── semana-10.md    # Camadas Silver e Gold no dbt, Star Schema, Dagster (ADRs 0005 e 0006)
        └── semana-11.md    # Busca vetorial CBO, Text-to-SQL (ADR 0007), SCD2, EXPLAIN e fechamento da E3
```

---

## Como Subir o METRA (Execução 100% Reprodutível)

### Pré-requisitos

- [Git](https://git-scm.com/)
- [Docker Engine](https://docs.docker.com/engine/) e [Docker Compose](https://docs.docker.com/compose/)

### Fluxo completo em um comando

Na raiz do clone, um único comando executa o METRA do zero (Bronze → OLTP → Parquet/Delta → dbt Silver/Gold → painel):

```bash
sh scripts/metra-do-zero.sh
```

O script pede confirmação, apaga os volumes do PostgreSQL e do Dagster e os artefatos gerados em `data/` (lake e `metra_analitico.duckdb`) e executa o job `pipeline_metra`. Em seguida, `src.qualidade.verificar_fluxo` confere que as seis camadas têm a mesma quantidade de movimentações e o mesmo saldo e que as tabelas Gold do painel têm dados. O painel só sobe se tudo passar. A amostra versionada e os CSVs completos não são apagados. Com as imagens já construídas, o fluxo sobre a amostra leva menos de um minuto; a primeira execução também constrói as imagens. Para pular a confirmação, como na CI, use `--sim`.

Sem apagar os volumes, o mesmo fluxo roda com `docker compose --profile completo up --build -d painel-completo`.

### Testes automatizados e integração contínua

Depois do fluxo completo, execute todos os testes na imagem Python 3.12 do Dagster, a partir da raiz:

```bash
docker compose --profile dagster run --build --rm \
  -v "$PWD":/repo -w /repo dagster-webserver \
  python -m unittest discover -s tests -v
```

Esse ambiente instala `requirements-pipeline.txt` e fornece as variáveis de conexão com o PostgreSQL do Compose. Evita depender do Python 3.14 local, que não instala `dagster-dbt`. A suíte foi validada com **72 testes passando**, incluindo os 12 de integração com a Gold real. Para executar somente esses 12, acrescente `-p 'test_gold_integracao.py'` ao comando `unittest discover`.

[`tests/test_gold_integracao.py`](tests/test_gold_integracao.py) abre `data/metra_analitico.duckdb` somente para leitura, respeitando `METRA_DUCKDB`. Sem o arquivo, a classe é pulada; com ele presente, banco inválido, tabelas ausentes ou falha de conexão ao Postgres são erros. O OLTP precisa corresponder à carga que gerou a Gold. Na execução fora do Docker, configure `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` e `PGPASSWORD`; sem `PGHOST`, o psycopg procura um socket local.

O workflow [Fluxo completo e testes](.github/workflows/testes-integracao.yml) roda em pushes, pull requests e manualmente pelo GitHub Actions. Em um runner limpo, usa a amostra versionada, executa `sh scripts/metra-do-zero.sh --sim`, exige que o DuckDB tenha sido criado e roda a suíte completa no Dagster. Se houver falha, imprime o estado e os logs dos serviços; ao terminar, remove serviços e volumes (a validação local executou a suíte sobre os bancos existentes, sem apagar os dados locais).

### Passos de Execução

Os passos abaixo executam as mesmas etapas uma a uma.

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

# 5. Gerar o lake Parquet/Delta e as camadas Silver e Gold pelo job do Dagster
#    (--build reconstrói a imagem quando o código do pipeline mudou)
docker compose --profile dagster run --build --rm dagster-webserver \
  dagster job execute -m dagster_metra.definitions -j pipeline_metra

# 6. Subir o painel Streamlit sobre a Gold gerada
docker compose --profile painel up --build -d painel
```

Acesse o portal de documentação em: [http://localhost:8000](http://localhost:8000) e o painel em: [http://localhost:8501](http://localhost:8501).

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
### Camada Silver com dbt-duckdb (E3)

Depois da extração para Parquet, no mesmo ambiente Python:

```bash
cd dbt_metra
dbt build   # Parquet -> schemas silver e gold de data/metra_analitico.duckdb
```

Os modelos `stg_movimentacao`, `stg_municipio`, `stg_cbo` e `stg_cnae` leem o Parquet de `data/lake/parquet/<tabela>/` e são materializados como tabelas no schema `silver`. Mantêm uma linha por registro da origem, padronizam nomes e acrescentam colunas derivadas (`competencia`, `tipo_evento`, `salario_valido` e marcações de registros sentinela ou não oficiais), sem agregar nem decodificar os códigos do CAGED. O alvo é um arquivo próprio, separado de `data/metra.duckdb`, porque o DuckDB aceita um único processo escrevendo por vez; o arquivo não é versionado.

O `profiles.yml` versionado em `dbt_metra/` dispensa configuração em `~/.dbt/`. As variáveis `METRA_LAKE_PARQUET` (diretório do Parquet, relativo a `dbt_metra/`) e `METRA_DUCKDB` (arquivo de destino) permitem apontar para outros caminhos, como em contêineres ou no orquestrador.

### Qualidade das fontes, da Silver e da Gold

O projeto dbt tem 176 testes. Os 122 das fontes e da Silver estão em `dbt_metra/models/staging/schema.yml` e `_lake__sources.yml` e verificam schema, chaves, referências, domínios, volume, distribuição e linhagem. Os 54 da Gold estão em `dbt_metra/models/marts/_gold__models.yml` e em `dbt_metra/tests/`: chaves únicas e não nulas das dimensões, integridade referencial da fato, grão dos agregados, contagem da fato igual à Silver e os contratos do SCD tipo 2 da CBO. Execute `dbt test --profiles-dir .` dentro de `dbt_metra/`, depois de materializar os modelos, ou `dbt build --profiles-dir .` para construir e validar.

Para validar a detecção de falhas com Parquet sintético isolado, na raiz:

```bash
python -m unittest discover -s tests -p 'test_dbt_quality.py' -v
```

Veja a [camada analítica e o Star Schema](docs/camada-analitica-dbt.md) e a [ADR-0005](docs/adr/0005-modelagem-analitica-dbt.md). Os testes de negócio Gold abaixo e os testes de integração sobre a carga real complementam os contratos dbt e o histórico SCD.

### Camada Gold e perguntas de gestão (E3)

O mesmo `dbt build` também reconstrói o schema `gold`, usando `ref()` sobre a Silver:

- Dimensões `dim_competencia`, `dim_municipio`, `dim_cnae`, `dim_cbo` e `dim_perfil_demografico`.
- Histórico da CBO como dimensão de variação lenta (SCD tipo 2): o snapshot `snp_cbo` preserva cada versão observada e `dim_cbo_historico` a expõe com `observado_desde`, `observado_ate` e `is_versao_vigente`; `dim_cbo` segue com a versão vigente.
- `fct_movimentacao`: uma linha por evento da Silver, com chaves dimensionais e linhagem.
- `fct_setor_mensal`: competência × UF × seção CNAE (P1, P2 e P4).
- `fct_geografia_mensal`: competência × UF × capital/interior (P3).
- `fct_perfil_mensal`: competência × UF × capital/interior × seção CNAE × perfil (P5).

Os agregados usam municípios identificados do Centro-Oeste entre 2023 e 2026. Preservam somas e denominadores salariais para recalcular médias em qualquer agrupamento. As tabelas são reconstruídas integralmente, incluindo competências antigas que recebam dados atrasados.

#### ETL reverso e resumo público (E4)

O asset `exportar_json_consumo`, incluído no job `pipeline_metra` e no seu schedule
mensal, exporta as views públicas `consumo.*` para `docs/assets/dados/metra.json`.
O JSON fornece séries mensais de setor, geografia, perfis e calendário para P1–P5.
As fórmulas vêm da camada semântica; a publicação é atômica e idempotente, com o
retry compartilhado do Dagster. Uma página mínima no MkDocs lê o arquivo por
JavaScript. O merge do PR com o JSON revisado aciona o deploy existente do Pages.

**Dependência de integração:** as views públicas são entregues pela frente de
controle de acesso. Sem elas, o exportador e o pipeline completo falham, mantendo
o JSON anterior. Não há fallback para a Gold nem JSON fictício de produção.

Para regenerar somente a publicação, depois de materializar as views:

```bash
docker compose --profile dagster run --build --rm dagster-webserver \
  dagster job execute -m dagster_metra.definitions -j exportar_json_consumo_job
```

Contrato, supressão, comandos e procedimento de publicação em
[Consumo e governança](docs/consumo-e-governanca.md#etl-reverso-json-publico).
O [resumo mensal](docs/consumo-json.md) exibe apenas os grupos publicados; seus
totais podem ser parciais por causa das supressões.

#### Camada semântica única de métricas (E4)

Cada métrica (admissões, desligamentos, saldo, salário médio de admissão e índice de fluxos pareados) é definida **uma única vez** em [`dbt_metra/models/semantic/metricas.yml`](dbt_metra/models/semantic/metricas.yml), no formato de `semantic_models`/`metrics` do dbt, que o próprio dbt valida. Os marts e as análises compilam o SQL pelo macro `metrica()`. O painel, a busca CBO e o assistente Text-to-SQL compilam pelo módulo [`src/metricas/camada_semantica.py`](src/metricas/camada_semantica.py). Os dois caminhos geram SQL idêntico, e um teste falha se alguém reescrever uma fórmula à mão. Detalhes em [Consumo e governança](docs/consumo-e-governanca.md#camada-semantica-catalogo-unico-de-metricas).

```bash
python -m unittest tests.test_camada_semantica -v   # definição, SQL compilado e guarda anti-duplicação
```

As cinco consultas de referência estão em [`dbt_metra/analyses/`](./dbt_metra/analyses/README.md). P2 trata sazonalidade; P3 compara capitais e interior. P4 usa explicitamente a proxy `200 × min(admissões, desligamentos) / (admissões + desligamentos)`, que mede equilíbrio dos fluxos e não a taxa convencional de turnover sobre estoque. P5 descreve salários e movimentações, sem estimar chances individuais de recolocação. Os resultados se referem aos dados carregados, não a totais populacionais ou ao saldo oficial ajustado do CAGED.

Para compilar e consultar P3, no ambiente de `requirements-pipeline.txt`, depois da extração:

```bash
cd dbt_metra
dbt build
dbt compile
python - <<'PY'
from pathlib import Path
import os
import duckdb

sql = Path('target/compiled/metra/analyses/p3_capitais_interior.sql').read_text()
with duckdb.connect(os.environ.get('METRA_DUCKDB', '../data/metra_analitico.duckdb'), read_only=True) as conn:
    conn.sql(sql).show()
PY
```

Não execute o SQL Jinja original diretamente no DuckDB; use a consulta compilada. Compilar não executa nem publica as análises como tabelas. Dashboard e consultas devem abrir o banco após o término da escrita pelo dbt.

Para validar as regras de negócio com Parquet e DuckDB temporários, a partir da raiz:

```bash
python -m unittest discover -s tests -p 'test_gold.py' -v
```

Essa verificação executa os modelos reais com fixtures e com a amostra versionada (referências sintéticas), incluindo reexecução e evento atrasado. Os contratos descritivos da Gold estão em `models/marts/_gold__models.yml`, complementando os 122 testes genéricos de qualidade das fontes e da Silver em `models/staging/schema.yml`.

### Orquestração com Dagster (E3)

O ambiente de orquestração usa `dagster`, `dagster-dbt` e `dagster-webserver`. A definição em `dagster_metra/definitions.py` expõe o pipeline de ingestão e extração como os assets `executar_pipeline` e `exportar_parquet`, conecta os cinco sources Parquet do dbt à extração e carrega os modelos Silver e Gold a partir do manifesto dbt. Assim, a linhagem completa aparece como `executar_pipeline` → `exportar_parquet` → `lake/*` → Silver → Gold (o asset `exportar_parquet` depende de `executar_pipeline`, fazendo com que a origem PostgreSQL seja atualizada antes da geração do lake Parquet).

Em container, o `target/manifest.json` é gerado durante o build da imagem. No desenvolvimento com `dagster dev`, `prepare_if_dev()` continua atualizando-o quando necessário.

Para abrir a interface localmente:

```bash
dagster dev -w workspace.yaml
```

Acesse [http://localhost:3000](http://localhost:3000). Alternativamente, execute a interface em container:

```bash
docker compose --profile dagster up --build -d postgres dagster-webserver dagster-daemon
```

O comando sobe o `dagster-webserver` e o `dagster-daemon` com o mesmo `DAGSTER_HOME`, portanto os jobs enviados pela UI são executados pelo daemon.

Na interface, materialize `executar_pipeline` para executar as migrações e cargas E1, e em seguida, materialize `exportar_parquet` para gerar os arquivos Parquet. Depois, os assets dbt podem então ser materializados para executar `dbt build` sobre o lake. Os sources `lake/*` são virtuais: representam os Parquets produzidos pela extração e aparecem como parte da linhagem, sem uma materialização adicional. O arquivo DuckDB e os Parquets são montados a partir de `data/`.

Todos os assets têm política de retry (até 3 novas tentativas, com espera exponencial). O job `pipeline_metra` tem o schedule mensal `pipeline_metra_mensal`, e o asset `conciliacao_mensal`, particionado por competência, confere o OLTP contra a fato Gold e permite backfill de um intervalo de meses em uma execução:

```bash
dagster job execute -m dagster_metra.definitions -j pipeline_metra
dagster asset materialize -m dagster_metra.definitions --select conciliacao_mensal --partition-range "2023-01-01...2026-10-01"
```

O procedimento operacional detalhado está em [`docs/orquestracao.md`](./docs/orquestracao.md), enquanto a decisão arquitetural foi registrada na [ADR 0006](./docs/adr/0006-orquestracao-com-dagster.md).

### Busca Semântica CBO, Assistente Text-to-SQL e Painel Streamlit (E4)

A camada de consumo interativa (`src/app/dashboard.py`) integra duas abas conectadas em modo somente leitura (`read_only=True`) ao banco analítico `data/metra_analitico.duckdb` (construindo-o automaticamente a partir da amostra versionada quando ausente):

1. **Busca Semântica CBO 2002 & Assistente Text-to-SQL (`ADR 0007`):**
   - **Busca Semântica de Ocupações (`src/app/busca_cbo.py`):** índice vetorial híbrido de 384 dimensões normalizado em norma $L_2$ (`metra-cbo-hybrid-384d-v1`) sobre `gold.dim_cbo`, suportando busca por código exato de 6 dígitos (inclusive com zero inicial) e por sinônimos ou termos coloquiais (ex.: *"dev backend"*, *"caminhoneiro"*, *"bóia-fria"*), tanto via produto interno em NumPy quanto via `array_cosine_similarity(vetor::FLOAT[384], ?::FLOAT[384])` diretamente no DuckDB, cruzando os códigos com os indicadores agregados de `gold.fct_movimentacao`.
   - **Assistente Text-to-SQL Governado pelo Catálogo (`src/app/text_to_sql.py`):** traduz perguntas em linguagem natural para consultas SQL auditáveis sobre os contratos da camada `gold` (P1–P5 e ocupações CBO), exibindo a fórmula oficial, ressalvas metodológicas e bloqueando deterministicamente comandos DDL/DML, leituras externas, acessos fora do schema `gold` ou consultas desagregadas de registros individuais (LGPD).
2. **Painel das 5 Perguntas de Gestão (Contratos Gold):** visualização tabular e gráfica das cinco perguntas estratégicas do projeto sobre as tabelas agregadas da camada `gold`.

No Docker, o serviço `painel` (perfil `painel`) serve o app em `http://localhost:8501` (porta configurável por `PAINEL_PORT`). Ele monta `data/` como somente leitura e só abre o banco durante cada consulta, então o dbt e o Dagster continuam escrevendo na Gold com o painel no ar; depois de uma nova materialização, basta recarregar a página. Sem a Gold gerada, o painel mostra o comando a executar.

```bash
docker compose --profile painel up --build -d painel
```

Para executar o painel localmente, os testes e o benchmark reproduzível da [`ADR 0007`](./docs/adr/0007-busca-semantica-e-consumo.md):

```bash
streamlit run src/app/dashboard.py
python -m unittest discover -s tests -p 'test_busca_e_text2sql.py' -v
python -m src.app.avaliar_busca_e_text2sql --saida docs/adr/evidencias/0007-busca-semantica-e-text2sql.json
```

### Controle de acesso (E4)

Consumidores externos não abrem o banco analítico. O dbt publica as views agregadas `consumo.setor_mensal`, `consumo.geografia_mensal`, `consumo.perfil_mensal` e `consumo.calendario`, que omitem grupos com menos de 5 movimentações e anulam o salário com menos de 5 salários válidos. O asset `base_consumo` copia essas views para `data/metra_consumo.duckdb`, a única base que o consumidor abre: somente leitura, sem acesso externo e com a configuração travada, sem caminho até a Gold detalhada.

```bash
python -m src.acesso.base_consumo        # publica a base de consumo (o pipeline_metra já faz isso)
python -m src.acesso.demonstrar_acesso   # acessos permitidos e negados, por perfil
python -m unittest discover -s tests -p 'test_controle_acesso.py' -v
```

A demonstração também roda ao fim do fluxo completo. Perfis, saída esperada e limites estão em [Consumo e governança](docs/consumo-e-governanca.md#controle-de-acesso).

### Governança LGPD, Retenção e Script de Descarte (E4)

O módulo [`src/lgpd/descarte.py`](src/lgpd/descarte.py) formaliza o inventário dos dados tratados (quase-identificadores em nível de movimentação individual nos termos do art. 5º, I da LGPD e `raca_cor` como dado pessoal sensível nos termos do art. 5º, II), a base legal para pesquisa acadêmica sobre microdados públicos oficiais do MTE (**art. 7º, IV e § 3º** e **art. 11, II, alínea "c"** da Lei nº 13.709/2018) e o prazo de retenção (**até 30 dias corridos** após o encerramento oficial do semestre letivo 2026/2 e prazo recursal da disciplina na FCTE/UnB, data-limite `31/12/2026`). Também audita o risco de reidentificação na Gold, mede a exposição a ataques por diferença nas views `consumo.*` e executa o descarte verificável dos artefatos locais com microdados individuais (`metra_analitico.duckdb`, `metra.duckdb`, `data/lake/parquet/`, `data/lake/delta/` e `data/cdc/`), preservando apenas os agregados anonimizados ($k \ge 5$).

```bash
python -m src.lgpd.descarte --simular
python -m src.lgpd.descarte --demonstrar-descarte --saida docs/adr/evidencias/0008-lgpd-descarte.json
python -m unittest discover -s tests -p 'test_lgpd_descarte.py' -v
```

Enquadramento completo, tabela de retenção e evidências em [Consumo e governança](docs/consumo-e-governanca.md#privacidade-e-governanca-lgpd-dados-tratados-base-legal-retencao-e-descarte) e [`docs/adr/evidencias/0008-lgpd-descarte.json`](docs/adr/evidencias/0008-lgpd-descarte.json).

### Catálogo de Dados (`dbt docs` no GitHub Pages) e Linhagem Ponta a Ponta (E4)

O dicionário de dados completo dos modelos (`silver`, `gold`, `snapshots` e `consumo`), das 5 fontes Parquet, das 7 métricas da camada semântica e dos 4 consumidores finais (`exposures`: Painel Streamlit, Busca Vetorial CBO / Text-to-SQL, Base de Consumo Isolada e ETL Reverso JSON Público) é compilado em um portal estático (`dbt docs generate --static`) por [`src/catalogo/gerar_dbt_docs.py`](src/catalogo/gerar_dbt_docs.py) e publicado automaticamente no GitHub Pages em `assets/dbt-docs/index.html` pelo workflow [`.github/workflows/deploy-docs.yml`](.github/workflows/deploy-docs.yml), acompanhado do manifesto versionado [`docs/assets/dbt-docs/linhagem.json`](docs/assets/dbt-docs/linhagem.json).

```bash
python -m src.catalogo.gerar_dbt_docs
python -m unittest discover -s tests -p 'test_catalogo_linhagem.py' -v
```

Grafo completo e matriz de linhagem da fonte até o painel e o ETL reverso em [Consumo e governança](docs/consumo-e-governanca.md#catalogo-de-dados-dbt-docs-no-pages-e-linhagem-da-fonte-ao-painel-e-ao-etl-reverso).

---

## Governança, Transparência e Evolução do Projeto

- **ADRs:** Todas as decisões arquiteturais seguem o **Método de Decisão em 6 passos** e ficam versionadas em [`docs/adr/`](./docs/adr/).
- **Uso de IA:** Este repositório cumpre integralmente a [Política de Uso de IA](https://unb-bd2.github.io/PlanoEnsino/uso-de-ia/) da disciplina. Todas as contribuições de assistentes são documentadas de forma contemporânea no arquivo [`docs/uso-de-ia.md`](./docs/uso-de-ia.md).
- **Diário de Bordo:** O acompanhamento contínuo de aprendizados, medições e surpresas da Squad é registrado semanalmente em [`docs/diario/`](./docs/diario/).
