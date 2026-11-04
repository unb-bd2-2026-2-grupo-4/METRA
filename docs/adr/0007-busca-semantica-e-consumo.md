# 0007 - Integração de Busca Semântica Vetorial CBO 2002 e Assistente Text-to-SQL Governado pelo Catálogo Gold

- **Status:** Aceito
- **Data:** 03/11/2026
- **Decisores:** Arthur Evangelista e Euller Júlio (com revisão da Squad G4)

---

## 1. Contexto

Na Entrega 4 (E4) do METRA, além do painel gerencial com os indicadores das cinco perguntas de gestão, precisamos atender à recomendação docente (registrada nos diários das Semanas 05 e 06) de incorporar **busca vetorial por similaridade semântica sobre as ocupações da CBO 2002** e um **assistente de consulta em linguagem natural (Text-to-SQL)** integrado à camada analítica `gold` no DuckDB (`data/metra_analitico.duckdb`).

### Caracterização da Carga de Trabalho e Restrições

- **Volume de Dados:**
  - Camada `gold` materializada pelo `dbt-duckdb`: 49.178 movimentações na amostra versionada (`data/caged_centro_oeste_amostra.csv`, SHA-256 `40e7c4e7832d02b1b84b42d094ce5d48be915fa134f21a4435f8aaf472620b88`) e até 14,7 milhões de registros no recorte completo do Centro-Oeste (2023–2026).
  - Dimensão `gold.dim_cbo`: 1.272 códigos ocupacionais distintos na amostra (e mais de 2.600 ocupações formais com +10 mil sinônimos na base oficial da CBO 2002 do MTE).
- **Problema de Vocabulário e Governança de Métricas:**
  - Trabalhadores e gestores pesquisam profissões usando termos coloquiais ou de mercado (*"dev backend"*, *"caminhoneiro"*, *"caixa de supermercado"*, *"bóia-fria"*, *"médico do coração"*), que frequentemente não compartilham palavras exatas com o título burocrático da CBO 2002 (*"Analista de desenvolvimento de sistemas"*, *"Motorista de caminhão"*, *"Operador de caixa"*, *"Trabalhador volante da agricultura"*, *"Médico cardiologista"*).
  - Consultas em linguagem natural sobre os indicadores exigem fidelidade absoluta às regras da camada `gold`: recomposição de médias salariais por `SUM(soma_salarios_admissao) / NULLIF(SUM(qtd_salarios_admissao), 0)`, uso explícito da proxy de equilíbrio de fluxos pareados em P4 (sem inventar taxa de turnover sobre estoque inexistente) e proteção contra exposição de registros individuais (LGPD).
- **Restrições Operacionais (ADR 0002):**
  - Execução 100% reproduzível localmente, sem depender de chaves de API pagas, servidores externos em segundo plano ou GPUs dedicadas, mantendo latência interativa (< 150 ms por consulta).

---

## 2. Alternativas Consideradas

### A. Busca Textual Léxica por Código/Título e Filtros Fixos — Opção Nula

- **O que oferece:** Busca por código exato e interseção de palavras / substring (`ILIKE`) diretamente sobre `titulo_ocupacao` em `gold.dim_cbo`, combinada a seletores fixos no painel.
- **Por que não foi escolhida isoladamente:** Embora previsível para códigos exatos, falha sempre que o usuário emprega sinônimos ou jargões ausentes do título oficial. No conjunto de avaliação de 24 consultas em português sobre o catálogo de 1.272 ocupações (1.220 títulos oficiais da CBO 2002), obteve apenas **33,33% de acerto no Top-1 (`Hit@1`)** e **62,50% no Top-5 (`Hit@5`)**, falhando em buscas como *"dev backend software"*, *"codificador de programas de computador"* e *"bóia-fria colheita lavoura"*.

### B. Índice Vetorial Híbrido Denso (384d L2) + Assistente Text-to-SQL Governado pelo Catálogo Gold (Escolhida)

- **O que oferece:**
  1. **Embeddings Semânticos Determinísticos (`metra-cbo-hybrid-384d-v1`):** Vetores densos de **384 dimensões** (`FLOAT32` normalizados em norma $L_2$), combinando **64 dimensões de projeção em conceitos ocupacionais do mercado de trabalho brasileiro (thesaurus de sinônimos CBO/MTE)** e **320 dimensões de *signed feature hashing*** sobre unigramas, radicais morfológicos do português, bigramas e n-gramas de caracteres (`char_wb` de 3 a 5 caracteres). Os vetores ocupam menos de **2 MB em RAM** para todo o catálogo e são consultáveis tanto via produto interno $L_2$ em NumPy quanto via `array_cosine_similarity(vetor::FLOAT[384], ?::FLOAT[384])` diretamente no DuckDB.
  2. **Assistente Text-to-SQL Governado pelo Catálogo (`src/app/text_to_sql.py`):** Identifica a intenção analítica dentre os contratos homologados (`p1_setores_df` a `p5_perfil_remuneracao` e `cbo_ocupacao`), extrai parâmetros de filtro (UF, ano, nível temporal, eixo demográfico e códigos CBO resolvidos pelo índice vetorial), gera o SQL auditável correspondente e valida a instrução com guardrails sintáticos (`validar_sql_seguro`) antes de executar em conexão `read_only=True`.

### C. Embeddings Externos via API + SQL Livre Gerado por LLM Irrestrito

- **O que oferece:** Flexibilidade para perguntas abertas arbitrárias via chamada a modelos remotos.
- **Por que foi descartada como caminho primário:** Exige chave de API externa (impedindo a reprodução imediata por terceiros em ambiente isolado), eleva a latência para centenas de milissegundos e introduz risco de violação metodológica (ex.: gerar `AVG(salario_medio_admissao)` sem ponderar pelo denominador `qtd_salarios_admissao`, calcular turnover incorreto sobre o saldo ou executar `SELECT * FROM gold.fct_movimentacao` expondo combinações individuais raras).

---

## 3. Medição e Prototipação

O benchmark reproduzível implementado em `src/app/avaliar_busca_e_text2sql.py` executou os cinco experimentos do protocolo sobre a camada `gold` construída a partir da amostra versionada (`49.178` movimentações e `1.272` ocupações em `gold.dim_cbo`, versão do índice `metra-cbo-hybrid-384d-v1:e210f18dd120`, matriz vetorial de `1.953.792 bytes`).

**Ambiente:** Python 3.11.16, DuckDB 1.5.6, NumPy 2.4.6, Windows 11 (10.0.26200), 1 aquecimento descartado e 7 repetições válidas. Os resultados completos estão versionados em [`docs/adr/evidencias/0007-busca-semantica-e-text2sql.json`](evidencias/0007-busca-semantica-e-text2sql.json).

### 3.1. Qualidade da Busca de Ocupações (24 Consultas por Sinônimo e 8 Códigos Exatos)

| Alternativa Avaliada | Hit@1 (Sinônimos) | Hit@5 (Sinônimos) | MRR (Sinônimos) | Hit@1 (Código 6 Dígitos c/ Zero Inicial) | Códigos Inexistentes Retornados |
|---|---:|---:|---:|---:|---:|
| **A. Busca Léxica (Opção Nula)** | 33,33% (8/24) | 62,50% (15/24) | 0,4514 | 100,00% (8/8) | 0 |
| **B. Busca Semântica Vetorial (384d L2)** | **87,50% (21/24)** | **100,00% (24/24)** | **0,9271** | **100,00% (8/8)** | **0** |

### 3.2. Fidelidade Text-to-SQL, Latência e Guardrails de Segurança (7 Repetições)

| Operação / Experimento Medido | Mediana (ms) | p95 (ms) | Resultado de Conformidade e Segurança |
|---|---:|---:|---|
| **Indexação Vetorial do Catálogo (`gold.dim_cbo`)** | 434,147 | 1.071,223 | 1.272 ocupações vetorizadas em 384d (`1,95 MB` em memória) |
| **Busca Léxica por Consulta (Alternativa A)** | 16,276 | 37,266 | Varredura textual de tokens sobre o catálogo |
| **Busca Vetorial 384d (NumPy L2) por Consulta** | **1,212** | **2,401** | Produto interno vetorizado em `FLOAT32` |
| **Busca Vetorial 384d (`DuckDB array_cosine_similarity`)** | **6,518** | **10,279** | Consulta SQL sobre relação Arrow registrada em conexão `READ_ONLY` |
| **Assistente Text-to-SQL (Ponta a Ponta por Pergunta)** | **30,133** | **139,107** | **100% de igualdade exata (6/6)** com os SQLs compilados de referência (P1–P5 e CBO) |
| **Guardrails de Segurança e Recusas Metodológicas** | < 0,100 | < 0,200 | **10/10 ataques SQL bloqueados** (`DROP`, `INSERT`, `read_parquet`, `;`, `silver.*`, linhas individuais) e **5/5 recusas corretas** |

### Comandos para Reprodução

```bash
python -m src.app.avaliar_busca_e_text2sql --saida docs/adr/evidencias/0007-busca-semantica-e-text2sql.json
python -m unittest discover -s tests -p "test_busca_e_text2sql.py" -v
streamlit run src/app/dashboard.py
```

---

## 4. Decisão

**Adotamos a Alternativa B: integração da Busca Semântica Vetorial Híbrida de 384 dimensões (`src/app/busca_cbo.py`) e do Assistente Text-to-SQL Governado pelo Catálogo Gold (`src/app/text_to_sql.py`) na aba interativa do painel (`src/app/dashboard.py`).**

### Contrato Implementado

1. **Busca Semântica (`IndiceVetorialCBO`):** recebe consulta textual e `top_k`; prioriza código exato de 6 dígitos (inclusive iniciados por zero, como `010105`) na 1ª posição (`score = 1.0`) e ranqueia ocupações por similaridade de cosseno em 384 dimensões, retornando `codigo_cbo`, `titulo_ocupacao`, `codigo_grande_grupo`, `score`, `is_cadastro_oficial` e `versao_indice` (`metra-cbo-hybrid-384d-v1:<sha256>`). Pontuação de similaridade não representa probabilidade de emprego.
2. **Catálogo Único de Métricas:** tanto o painel quanto o assistente Text-to-SQL consultam exclusivamente as tabelas homologadas do schema `gold` (`fct_setor_mensal`, `fct_geografia_mensal`, `fct_perfil_mensal`, `fct_movimentacao` agregada e dimensões), preservando a recomposição de médias salariais e denominadores (`qtd_salarios_admissao`).
3. **Execução Segura e Guardrails (`validar_sql_seguro`):** o banco analítico é aberto exclusivamente com `read_only=True`; qualquer tentativa de escrita (`INSERT`, `UPDATE`, `DELETE`, `DROP`, `ATTACH`), múltiplas instruções (`;`), leitura de arquivos externos (`read_csv`, `read_parquet`), acesso a schemas internos (`silver`, `bronze`, `oltp`) ou listagem desagregada de linhas individuais de `gold.fct_movimentacao` é bloqueada deterministicamente.
4. **Transparência no Painel:** a interface exibe a intenção identificada, os filtros aplicados, as ocupações CBO resolvidas, a fórmula oficial da métrica, a ressalva metodológica e o SQL gerado.
5. **Histórico CBO:** a busca opera sobre uma representação única por `codigo_cbo` da versão vigente do catálogo (`gold.dim_cbo`) e agrega os indicadores sem duplicar movimentações.

---

## 5. Consequências e Tradeoffs

### O que se ganha
- Elevação do acerto em consultas por sinônimos sobre as 1.272 ocupações de **33,33% para 87,50% no Top-1** e de **62,50% para 100,00% no Top-5** (`MRR = 0,9271`), com latência mediana de **1,21 ms** (NumPy) a **6,52 ms** (DuckDB SQL).
- Garantia matemática de que respostas em linguagem natural jamais divergem das consultas oficiais das 5 perguntas de gestão.
- Execução 100% local, gratuita e determinística em qualquer máquina, sem dependência de chaves de API externas.

### O que se perde ou se compromete
- O assistente responde estritamente ao escopo de intenções e dimensões homologadas no catálogo Gold, recusando perguntas abertas fora desse domínio.
- A inclusão de novas famílias de jargões regionais ou mudança da tabela oficial da CBO 2002 requer atualização do índice e reexecução da suíte de avaliação.

### O que restringe o sistema futuro
- Qualquer evolução para geração assistida por LLM externo deverá atuar apenas como classificador/extrator de parâmetros sobre este mesmo catálogo e passar obrigatoriamente pelo validador `validar_sql_seguro`, mantendo o bloqueio a consultas individuais desagregadas.

---

## 6. Gatilho de Revisão

Esta decisão será revista se:
1. O `Hit@5` sobre o conjunto de avaliação de sinônimos cair abaixo de **90%** após atualização do catálogo CBO;
2. Qualquer resposta do assistente Text-to-SQL divergir dos resultados das consultas compiladas em `dbt_metra/analyses/`; ou
3. A latência p95 das consultas no painel ultrapassar **500 ms** sobre a carga completa de 14,7 milhões de registros.
