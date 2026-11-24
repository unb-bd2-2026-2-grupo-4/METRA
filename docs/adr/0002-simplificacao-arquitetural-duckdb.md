# 0002 - Adotar arquitetura híbrida com PostgreSQL OLTP e DuckDB como motor analítico

- **Status:** Aceito
- **Data:** 05/10/2026
- **Decisores:** Arthur Evangelista, Davi Camilo, Euller Júlio, Lucas Alves, Tiago Antunes e Yan Matheus (Squad G4)

---

## Pergunta de Gestão Central da Plataforma

> **"Qual é a diferença no saldo líquido de empregos gerados e no salário médio de admissão entre as capitais e os municípios do interior da Região Centro-Oeste no período de 2023 a 2026?"**

---

## 1. Contexto

A concepção inicial da plataforma METRA projetou um pipeline corporativo multicamadas para atender às quatro entregas semestrais da disciplina de Banco de Dados 2 (FCTE-UnB):

1. **A prescrição teórica do Plano de Ensino:**
   - O plano de ensino e o roteiro das entregas desenham um ecossistema com múltiplos serviços orquestrados via Docker:
     - **E1:** Banco transacional OLTP de origem (PostgreSQL 16) com schemas segregados (`bronze` e `oltp` em 3FN) e migrações versionadas;
     - **E2:** Captura de Mudanças (CDC) por decodificação lógica de WAL do PostgreSQL associada a ingestão em lote para bucket S3 local (MinIO) armazenando arquivos Apache Parquet;
     - **E3:** Transformações dimensionais em Star Schema com dbt-duckdb;
     - **E4:** Camada dupla de consumo (Metabase) com camada semântica e caminho de ETL Reverso retroalimentando a origem.

2. **O conflito com a realidade operacional e o feedback docente:**
   - Durante a avaliação e apresentação dos artefatos preliminares de arquitetura, a professora da disciplina apontou formalmente que **a arquitetura apresentada continha excesso de complexidade acidental (*overengineering*)**.
   - Para o objetivo real do projeto (ingerir microdados públicos do Novo CAGED de 2023 a 2026 na Região Centro-Oeste e responder às perguntas de gestão), a montagem de um ecossistema com múltiplos containers e fluxos redundantes (como ETL reverso e emulação de S3) impõe uma sobrecarga de infraestrutura desproporcional.
   - A orientação docente recomendou expressamente **simplificar a arquitetura**, sugerindo o uso direto do **DuckDB** como motor analítico colunar para carregar, processar e apresentar as análises com agilidade, sem atrito de servidores em segundo plano.

3. **Restrições de Engenharia e Ambiente:**
   - **Hardware local:** A execução de 4 a 5 containers simultâneos (PostgreSQL, MinIO, Metabase, Ingestão, MkDocs) em computadores pessoais sob Windows/WSL2 consome entre 2,5 GB e 4,0 GB de memória RAM dedicada apenas para sustentação dos daemons em repouso.
   - **Critérios de Aceite da E1:** O checklist oficial de correção da Entrega E1 exige a presença de um banco relacional transacional (OLTP) modelado com chaves, restrições e migrações versionadas a partir do zero. Abandonar por completo o modelo relacional representaria risco direto de desconformidade com a rubrica de avaliação dos monitores.

---

## 2. Alternativas Consideradas

### A. Opção Nula: Manutenção Estrita da Arquitetura Prescrita no Plano de Ensino
- **O que oferece:** Implementação integral de todas as tecnologias citadas no roteiro preliminar (PostgreSQL + MinIO + Debezium/WAL CDC + dbt + DuckDB + Metabase + ETL Reverso), garantindo paridade com pipelines corporativos em nuvem (S3 real, BI com controle de sessão e interface pronta para usuários não técnicos).
- **Por que é inviável neste projeto:** Gera atrito operacional severo para o escopo acadêmico. A equipe despenderia a maior parte da carga horária resolvendo problemas de rede bridge do Docker, orquestração de subida de containers (~2,8 GB de RAM), conexões JDBC do Metabase e replicação assíncrona de WAL, em vez de refinar a qualidade dos dados e responder à pergunta de gestão. Além disso, ignora o direcionamento direto da professora para simplificar o desenho técnico.

### B. Migração Radical para DuckDB Exclusivo (Eliminação Total do PostgreSQL)
- **O que oferece:** Uso único e exclusivo do DuckDB em memória ou arquivo local (`.duckdb`), consultando arquivos CSV/Parquet diretamente sem qualquer container Docker ativo.
- **Por que foi rejeitada para a E1:** Embora elimine todo o overhead de infraestrutura e responda à sugestão da professora com máxima simplicidade, o DuckDB é um SGBD analítico (OLAP), e não um banco de dados transacional de linha (OLTP). A ementa da Entrega E1 exige uma fonte transacional modelada em 3FN com chaves estrangeiras rígidas, integridade referencial estrita e simulação do sistema gerador das contratações. Além disso, a ausência de um log de transações transacional inviabilizaria a simulação de CDC da Entrega E2.

### C. Arquitetura Pragmática Híbrida: PostgreSQL como Origem OLTP Estrita + DuckDB como Motor Analítico Direto (Escolhida)
- **O que oferece:**
  1. **Aderência Estrita aos Requisitos da E1:** Mantém-se o PostgreSQL 16 estritamente para o papel formal de **Fonte Transacional OLTP**, com esquema relacional normalizado em 3FN (`oltp.movimentacao`, `oltp.municipio`, `oltp.cbo_2002`, `oltp.cnae_subclasse`), migrações versionadas e carga reprodutível a partir de amostra auditada (atendendo com 100% de conformidade à rubrica do [Plano de Ensino](https://unb-bd2.github.io/PlanoEnsino/projeto/e1/)).
  2. **Simplificação Radical do Pipeline Analítico:** Elimina-se a sobrecarga de ferramentas auxiliares pesadas (MinIO local, dependência mandatória de Metabase e complexidade de ETL Reverso).
  3. **DuckDB como Motor Analítico e Apresentação:** O DuckDB assume o papel de motor primário de consulta, análise e visualização. Ele conecta-se diretamente à fonte transacional via extensão nativa ou lê arquivos colunares Parquet gerados em lote, entregando agregações instantâneas vetorizadas sem consumir memória em repouso.

---

## 3. Medição e Prototipação

Para fundamentar empiricamente a decisão, foram executados testes comparativos na mesma máquina de desenvolvimento (Windows 11, Intel Core i7, 16 GB RAM), comparando o perfil de consumo e desempenho das abordagens sobre o recorte de movimentações do Centro-Oeste:

| Critério de Medição | Stack Prescrita Completa (Opção A) | DuckDB Puro em Arquivo (Opção B) | Arquitetura Híbrida Pragmática (Opção C) |
| :--- | :--- | :--- | :--- |
| **Memória RAM em Repouso** | ~2.800 MB (4 containers ativos) | **0 MB** (biblioteca in-process) | **~180 MB** (apenas container PostgreSQL 16) |
| **Tempo de Inicialização** | 25 a 45 segundos (subida de containers) | **0,01 segundo** (`import duckdb`) | **4 a 6 segundos** (apenas PostgreSQL) |
| **Tempo de Consulta Agregada (50k linhas)** | 48 ms (Postgres com Seq Scan) | **1,6 ms** (vetorizado colunar) | **1,8 ms** (DuckDB consultando dados locais) |
| **Conformidade com a Rubrica da E1** | Plena, porém com excesso de componentes | Nula (DuckDB não é fonte transacional OLTP) | **Plena e pontual (atende 100% dos itens da E1)** |
| **Complexidade de Manutenção** | Extrema (múltiplas portas e configs) | Mínima | **Baixa (fluxo direto e reprodutível)** |

### Comandos de Reprodução do Teste:
```bash
# Execução da carga transacional padrão (E1)
python -m src.ingestao.executar_pipeline

# Execução da análise instantânea via DuckDB (em memória/vetorizado)
python -c "import duckdb; print(duckdb.query(\"SELECT * FROM 'data/caged_centro_oeste_amostra.csv' LIMIT 5\").df())"
```

---

## 4. Decisão

**Adotamos a Alternativa C (Arquitetura Pragmática Híbrida): preservamos o PostgreSQL 16 para o papel exclusivo de Fonte Transacional OLTP da Entrega E1 e adotamos o DuckDB como motor analítico vetorizado central para simplificar a extração, o processamento e a apresentação dos dados nas etapas subsequentes.**

Esta decisão concilia de forma harmoniosa o que está formalmente estipulado no Plano de Ensino com a recomendação pedagógica de simplificação feita pela professora, eliminando complexidades operacionais que não agregam valor à resposta da pergunta de gestão.

---

## 5. Consequências e Tradeoffs

### O que se ganha
- **Alinhamento duplo:** Atendimento integral aos critérios objetivos de avaliação da E1 (esquema OLTP normalizado, integridade referencial com chaves e migrações executáveis a partir do zero) e atendimento simultâneo ao feedback da professora de simplificar a arquitetura.
- **Eficiência de recursos:** Redução de mais de 90% no consumo contínuo de memória RAM e eliminação da necessidade de orquestrar containers complexos para armazenamento em nuvem simulada.
- **Velocidade de resposta:** As consultas que respondem à pergunta de gestão (saldo líquido por município e salário médio por setor) rodam em frações de segundo através da execução colunar do DuckDB.
- **Portabilidade:** Terceiros conseguem rodar e auditar toda a plataforma em qualquer máquina sem requisitos de hardware corporativo.

### O que se perde ou se compromete
- Abre-se mão de explorar recursos empresariais avançados previstos inicialmente (como emulação de buckets S3 com MinIO e orquestração de ETL Reverso complexo para a origem).
- A separação de papéis exige clareza didática na documentação para explicar que o PostgreSQL atua como gerador transacional e o DuckDB atua como motor analítico consumidor.

### O que se torna irreversível ou restringe o sistema futuro
- O DuckDB é consagrado como o motor analítico oficial do projeto para as entregas E2, E3 e E4. Qualquer futura interface de visualização ou camada de IA consumirá os dados prioritariamente a partir do DuckDB ou de arquivos colunares Parquet por ele gerados.
- Migrar o motor analítico de volta para um cluster distribuído ou retornar ao Metabase + MinIO exigiria ~3 a 5 dias de engenharia para adaptar o dialeto SQL do `dbt_metra/`, reconfigurar conexões do painel/consumo e provisionar infraestrutura adicional.

---

## 6. Gatilho de Revisão

Esta decisão será formalmente revista se:
1. O volume de dados analíticos ativos no projeto superar **100 milhões de registros**, exigindo um cluster analítico distribuído (como Trino ou ClickHouse); ou
2. A banca avaliadora da disciplina exigir de forma mandatória e documentada a presença de um servidor de S3 local (MinIO) ativo no manifesto do Docker Compose como pré-requisito eliminatório para a Entrega E2.

---

## 7. Revisão E4 (23/11/2026)

Conciliação com o ciclo final da E4: nenhum dos dois gatilhos disparou (`14,75 milhões` < 100 milhões; MinIO não foi exigido). MinIO e Metabase permaneceram descartados, mas o **ETL reverso** previsto na E4 foi implementado sem servidores extras via exportação idempotente de `docs/assets/dados/metra.json` para o painel e agente estáticos no GitHub Pages, conforme formalizado na [ADR-0008](0008-disponibilizacao-camada-semantica-e-json-pages.md).
