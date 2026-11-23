# Consumo e governança

**Documento de integração atualizado em 22/11/2026.** O repositório já contém ingestão, OLTP, exportação Parquet/Delta, camadas Silver e Gold com 176 testes dbt de qualidade, SCD tipo 2 da CBO (`gold.dim_cbo_historico`), orquestração Dagster (com retry, schedule e backfill) e a integração da Busca Semântica CBO + Assistente Text-to-SQL Governado no painel Streamlit (`src/app/dashboard.py`), validada na [ADR-0007](adr/0007-busca-semantica-e-consumo.md), e a camada semântica única de métricas (`dbt_metra/models/semantic/metricas.yml`), consumida por dbt, painel e assistente. O controle de acesso por views de consumo agregadas e base de consumo isolada está implementado e demonstrado; LGPD institucional e ETL reverso seguem em consolidação para o fechamento da E4.

## Camada semântica: catálogo único de métricas

Cada métrica tem **uma única definição versionada**, em [`dbt_metra/models/semantic/metricas.yml`](https://github.com/unb-bd2-2026-2-grupo-4/METRA/blob/main/dbt_metra/models/semantic/metricas.yml), no formato de `semantic_models` e `metrics` do dbt. O dbt valida esse arquivo a cada `parse`/`build`, e ele aparece no `manifest.json` e no `dbt docs`. Todos os pontos de consumo compilam o SQL da métrica a partir dele, sem fórmula própria:

| Consumidor | Como lê a definição |
|---|---|
| Marts da Gold (`fct_setor_mensal`, `fct_geografia_mensal`, `fct_perfil_mensal`) e análises `p1`–`p5` | Macro dbt `metrica(nome, origem)` (`dbt_metra/macros/metricas.sql`), que lê o grafo do dbt |
| Painel Streamlit, busca CBO e assistente Text-to-SQL | `src.metricas.camada_semantica.expressao()` / `montar_consulta()` |
| Exportação JSON e ETL reverso (E4) | `src.metricas.camada_semantica.consultar()` |

Medidas aditivas, com o mesmo nome das colunas dos marts, sobre `gold.fct_movimentacao` (uma linha por movimentação, recorte `is_identificado and is_centro_oeste and ano between 2023 and 2026`):

| Medida | Agregação sobre os eventos |
|---|---|
| `admissoes` | `count` de `saldo_movimentacao = 1` |
| `desligamentos` | `count` de `saldo_movimentacao = -1` |
| `saldo` | `sum(saldo_movimentacao)` |
| `soma_salarios_admissao` | `sum` do salário das admissões com `salario_valido` |
| `qtd_salarios_admissao` | `count` das admissões com `salario_valido` |

Métricas publicadas:

| Métrica | Tipo | Definição | Unidade e ressalva |
|---|---|---|---|
| Admissões | simples | medida `admissoes` | Movimentações, não pessoas distintas |
| Desligamentos | simples | medida `desligamentos` | Movimentações |
| Saldo líquido | simples | medida `saldo` (admissões − desligamentos) | Fluxo líquido; não é estoque de vínculos |
| Admissões com salário válido | simples | medida `qtd_salarios_admissao` | Denominador da média; deve acompanhar o valor exibido |
| Salário médio de admissão | razão | `soma_salarios_admissao` / `qtd_salarios_admissao` | R$ nominais; nulo quando não há admissão com salário válido |
| Índice de fluxos pareados (turnover proxy) | derivada | `200 × least(admissoes, desligamentos) / (admissoes + desligamentos)` ([ADR-0007](adr/0007-busca-semantica-e-consumo.md)) | 0 a 100%; não é taxa sobre estoque de vínculos (indisponível no CAGED) |

A métrica tem duas origens. Sobre **eventos** (`gold.fct_movimentacao`), cada medida aplica sua agregação. Sobre **agregados** (marts ou CTEs que já trazem as medidas), a recomposição é sempre `sum(<medida>)`. Por isso o salário médio é sempre a razão das somas, e nunca a média simples de médias. Com `janela=`, a mesma métrica é recomposta sobre uma janela nomeada; a P5 usa isso para a média do recorte.

Recortes analíticos (série mensal, capital/interior, disparidade por sexo, raça/cor, escolaridade e faixa etária) são as mesmas métricas agrupadas por dimensão. Categorias não informadas permanecem identificadas; não se atribuem valores demográficos ausentes. A disparidade é uma associação descritiva, sem inferir causalidade nem probabilidade individual de recolocação.

**Garantias testadas:**

- `tests/test_camada_semantica.py` confere a definição, o SQL compilado e os valores calculados à mão. Também **falha se algum consumidor voltar a escrever uma fórmula de métrica à mão**.
- `tests/test_dbt_quality.py` confere que o macro dbt e o compilador Python geram **SQL idêntico** nos marts e nas cinco análises.
- `tests/test_gold_integracao.py` confere na Gold real que a mesma métrica dá o mesmo valor a partir dos eventos e de cada mart, e que os KPIs do painel batem com a camada semântica.

Ficam de fora da regra, de propósito, os gabaritos independentes: os scripts de medição em `src/qualidade/`, o avaliador da ADR-0007 e as referências dos testes de conciliação. Eles recalculam os números por conta própria justamente para conferir a camada semântica.

### Correspondência com as perguntas publicadas

| Pergunta | Recorte necessário | Tratamento implementado no consumo |
|---|---|---|
| P1: setores no DF nos últimos 12 meses | UF DF, seção CNAE e janela de 12 competências | Âncora na última competência disponível (ou no ano filtrado), exibindo o intervalo e o número de competências no painel |
| P2: sazonalidade | Série mensal por ano | Distingue meses sem dados (`NULL`) de zero observado (`0`) e calcula médias sazonais apenas sobre anos completos (12 meses) |
| P3: capitais versus interior | Município identificado, flag de capital, ano (2023–2026) e competência | Série anual (2023–2026), consolidado (`Total`) e recorte por UF conciliados com `python3 -m src.analise` |
| P4: turnover e salário | Setor, competência, salário válido e fluxos mensais | Usa o índice de fluxos pareados (`indice_fluxos_pareados_pct`) e a correlação de Pearson com `salario_medio_admissao` como aproximação explícita ([ADR-0007](adr/0007-busca-semantica-e-consumo.md)) |
| P5: perfil e remuneração | Sexo, raça/cor, idade e escolaridade | Associação descritiva com nota metodológica explícita de que fluxos observados não estimam chance individual de recolocação |

## Linhagem da fonte ao consumo

| Informação | Origem → persistência → Silver | Destino na Gold e no consumo |
|---|---|---|
| Competência e saldo | CAGED → `bronze.caged_movimentacao` → `oltp.movimentacao` → Parquet `movimentacao` → `stg_movimentacao` | Fato e agregados Gold → painel/assistente |
| Município/UF | IBGE → `bronze.ibge_municipio` → `oltp.municipio` → Parquet `municipio` → `stg_municipio` | Dimensão geográfica (`gold.dim_municipio`) |
| Ocupação | CBO → `bronze.cbo_ocupacao` → `oltp.cbo_2002` → Parquet `cbo_2002` → `stg_cbo` | Dimensão vigente (`gold.dim_cbo`), histórico SCD2 (`gold.dim_cbo_historico`) e índice de busca |
| Atividade econômica | IBGE CNAE → `bronze.ibge_cnae_subclasse` → `oltp.cnae_subclasse`/`cnae_secao` → respectivos Parquets → `stg_cnae` | Dimensão econômica (`gold.dim_cnae`) |
| Perfil e salário | Campos do CAGED → movimentação Bronze/OLTP/Parquet → `stg_movimentacao` | Dimensão demográfica (`gold.dim_perfil_demografico`), fato e métricas agregadas |

`id_ingestao` e `numero_linha` permitem voltar à origem da movimentação; `manifest.json` descreve as dependências dbt e `run_results.json` registra o resultado da execução. Esses artefatos estão integrados ao grafo de linhagem do Dagster em `dagster_metra/definitions.py` (ver [Orquestração com Dagster](orquestracao.md)). O replay CDC SQLite existente não está automaticamente conectado à Silver; não representar essa integração como pronta.

## Privacidade e acesso: análise inicial

O modelo atual não contém CPF ou nome do trabalhador, mas combina município, competência, CBO, idade, sexo, raça/cor e salário. Combinações raras podem permitir identificação indireta; ausência de identificador direto não comprova anonimização. Raça/cor, quando vinculada a pessoa identificada ou identificável, requer atenção como informação sensível. Essas distinções constam do [art. 5º da LGPD](https://www2.camara.leg.br/legin/fed/lei/2018/lei-13709-14-agosto-2018-787077-normaatualizada-pl.html).

| Item | Situação ou proposta | Ação ainda necessária |
|---|---|---|
| Finalidade | Análise acadêmica agregada do mercado formal | Registrar responsável institucional e escopo aprovado |
| Base legal | **Pendente de validação institucional** | Documentar a hipótese aplicável; não presumir que dado público ou trabalho acadêmico resolve todo enquadramento |
| Minimização | Painel implementado (`src/app/dashboard.py`) expõe apenas métricas agregadas da Gold; sem linhagem individual nas telas públicas e com bloqueio de linhas individuais no validador Text-to-SQL | Criar visões/relações dedicadas caso outros processos de consumo acessem o banco sem passar pelo validador da aplicação |
| Pequenos grupos | Implementado nas views `consumo.*`: grupos com menos de 5 movimentações são omitidos e medidas salariais com menos de 5 salários válidos ficam nulas (ver [Controle de acesso](#controle-de-acesso)) | Validar o limiar e os ataques por diferença entre recortes; o limiar isolado não prova anonimização |
| Retenção | Proposta: manter artefatos locais até 30 dias após encerramento da avaliação e recursos, sujeito à política institucional | Aprovar prazo, inventariar cópias e automatizar descarte; nenhum descarte executado nesta tarefa |
| Descarte | Remover cópias locais, índices, backups e logs conforme política aprovada | Documentar execução e verificar ausência de cópias não autorizadas |
| Repositório público | Já contém amostra de microdados | Revisar risco e finalidade da publicação; ignorar arquivos novos não remove histórico Git existente |
| Modelo externo | Nenhum provedor escolhido nesta proposta | Definir dados permitidos, custos e retenção antes de enviar perguntas ou contexto |

## Controle de acesso

Uma conexão DuckDB `read_only` impede escrita, mas não recorta linhas nem colunas: quem abre `data/metra_analitico.duckdb` lê `gold.fct_movimentacao`, com uma linha por movimentação. O DuckDB também não tem usuários nem `GRANT`. Por isso, o acesso é separado em duas camadas.

**1. Views de consumo agregadas** (`dbt_metra/models/consumo/`, schema `consumo`): as únicas relações publicadas para consumidores externos.

| View | Grão |
|---|---|
| `consumo.setor_mensal` | competência × UF × seção CNAE (P1, P2 e P4) |
| `consumo.geografia_mensal` | competência × UF × capital/interior (P3) |
| `consumo.perfil_mensal` | competência × UF × capital/interior × seção × categoria de um eixo demográfico por vez (P5) |
| `consumo.calendario` | competência, com `tem_dados` |

A macro `publicar_grupos` (`dbt_metra/macros/consumo.sql`) recompõe as medidas pela camada semântica e aplica a supressão com o limite da variável `metra_limite_publicacao` (5):

- grupos com `admissoes + desligamentos < 5` são omitidos;
- com menos de 5 salários válidos (inclusive zero), `soma_salarios_admissao` e `qtd_salarios_admissao` ficam nulas juntas, e os fluxos permanecem;
- os eixos demográficos não se cruzam: cruzar sexo, raça/cor, escolaridade e idade criaria grupos menores.

As views expõem só dimensões agregadas e medidas aditivas: nenhum identificador de movimentação, município ou CBO. Os testes em `_consumo__models.yml` fixam as colunas e os tipos de cada view, conferem o limite e a supressão salarial, e um teste singular confere que setores e geografia publicam exatamente os grupos liberados da Gold, com os mesmos fluxos. Sem a supressão na macro, três testes falham.

**2. Base de consumo isolada** (`src/acesso/base_consumo.py`): o asset `base_consumo` do Dagster copia as quatro views para `data/metra_consumo.duckdb` a cada execução do `pipeline_metra`, com troca atômica. O consumidor externo abre só esse arquivo, por `conectar_consumidor()`: somente leitura, com `enable_external_access = false` e `lock_configuration = true`. O detalhe não está no arquivo, e a configuração travada impede alcançá-lo por `ATTACH`, `read_parquet` ou `COPY`.

| Perfil | Abre | Pode | Não pode |
|---|---|---|---|
| Consumidor externo (JSON público, Pages, agente) | `data/metra_consumo.duckdb` | ler `consumo.*` | ler a Gold, anexar o banco analítico, ler o lake, exportar arquivos, alterar a configuração ou escrever |
| Analista interno (painel Streamlit, dbt, Dagster) | `data/metra_analitico.duckdb` em `read_only` | ler Silver, Gold e consumo | escrever (só o pipeline escreve) |

O painel Streamlit continua sendo uma ferramenta interna: lê a Gold detalhada e protege o detalhe com o validador do Text-to-SQL, não com esta base.

### Demonstração

`python -m src.acesso.demonstrar_acesso` executa cada tentativa e falha se algum resultado divergir do esperado. Ela roda ao fim do serviço `pipeline` do perfil `completo`, então o fluxo do zero (`sh scripts/metra-do-zero.sh`) também falha se um acesso negado passar. Saída sobre a amostra:

```text
[    ok    ] consumidor agregado por setor         PERMITIDO (1681,)
[    ok    ] consumidor perfis um eixo por vez     PERMITIDO (11326,)
[    ok    ] consumidor detalhe da Gold            NEGADO    CatalogException: Catalog Error: Table with name "gold.fct_movimentacao" does not exist ...
[    ok    ] consumidor anexar o banco analítico   NEGADO    PermissionException: Permission Error: Cannot access file ".../metra_analitico.duckdb" ...
[    ok    ] consumidor ler o lake Parquet         NEGADO    PermissionException: Permission Error: Cannot access file ".../lake/parquet/movimentacao/**/*.parquet" ...
[    ok    ] consumidor religar o acesso externo   NEGADO    InvalidInputException: Invalid Input Error: Cannot change configuration option "enable_external_access" ...
[    ok    ] consumidor exportar para arquivo      NEGADO    PermissionException: Permission Error: Cannot access file "consumo.csv" ...
[    ok    ] analista   detalhe da Gold            PERMITIDO (49178,)
[    ok    ] analista   alterar a Gold             NEGADO    InvalidInputException: Invalid Input Error: Cannot execute statement of type "DELETE" ...

Controle de acesso conforme o esperado.
```

A leitura do detalhe é uma contagem, para que nem a demonstração imprima registros individuais.

### Limites

- **Proteção por arquivo, não por usuário.** O controle vale para quem recebe só a base de consumo. Quem tem acesso ao sistema de arquivos com `data/metra_analitico.duckdb`, ao lake ou ao PostgreSQL continua lendo o detalhe; a separação desses ambientes é operacional.
- **Ataques por diferença.** A supressão é aplicada em cada view, isoladamente. Um grupo omitido pode ser estimado subtraindo, do total de um recorte publicado, os grupos publicados de outro (por exemplo, a geografia de uma UF menos os setores publicados dessa UF). A análise desse risco e do limiar fica com a frente de LGPD.
- **Amostra do repositório.** `data/caged_centro_oeste_amostra.csv` continua público no repositório; o controle de acesso não muda isso.

## Operação e freshness

O destino configurável deve ser compartilhado por dbt, Dagster e consumidores; hoje o padrão dbt é `data/metra_analitico.duckdb`. O consumo só deve apontar para uma execução validada. SLA inicialmente proposto: até 24 horas entre conclusão da extração e publicação validada do mesmo lote. Ver [camada analítica](camada-analitica-dbt.md#freshness-e-proximos-criterios-de-aceite) para separar atraso de processamento de cobertura temporal da fonte.

## ETL reverso: proposta a definir com a equipe

Um caminho possível é exportar um resumo mensal validado de saldo e remuneração por setor/UF para um arquivo que um processo de acompanhamento do gestor consuma. Ainda faltam consumidor real, ação tomada, formato, chave idempotente, frequência e tratamento de falhas. Apenas gravar mais uma tabela ou CSV sem consumo não conclui ETL reverso. A escolha e a demonstração são necessárias na [E4](https://unb-bd2.github.io/PlanoEnsino/projeto/e4/).

## Checklist para fechar com a equipe

- [x] Publicar Gold, dicionário e métricas com nomes definitivos e testes de reconciliação (176 testes dbt).
- [x] Centralizar a definição de cada métrica na camada semântica (`metricas.yml`), com marts, análises, painel, busca CBO e assistente compilando dela e teste que impede fórmula duplicada (E4).
- [x] Integrar painel Streamlit (`src/app/dashboard.py`), busca semântica CBO e consulta em linguagem natural conforme [ADR-0007](adr/0007-busca-semantica-e-consumo.md).
- [x] Demonstrar SCD tipo 2 (`snp_cbo` / `gold.dim_cbo_historico`), retry, schedule mensal e backfill no Dagster, com consumo em modo somente leitura após materialização da Gold.
- [x] Controle de acesso além de `read_only`: views `consumo.*` com supressão de grupos com menos de 5 movimentações, base de consumo isolada e demonstração de acesso permitido e negado ao detalhe (E4).
- [ ] Validar base legal da LGPD, retenção, o limiar de pequenos grupos e os ataques por diferença; guardar evidências reais (E4).
- [ ] Implementar e demonstrar o caminho de ETL reverso com seu consumidor (E4).
- [ ] Atualizar diários e registro de IA conforme as atividades da E4 ocorrerem; não antecipar evidências de execução futura.
