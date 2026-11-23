# Consumo e governança

**Documento de integração atualizado em 22/11/2026.** O repositório já contém ingestão, OLTP, exportação Parquet/Delta, camadas Silver e Gold com 176 testes dbt de qualidade, SCD tipo 2 da CBO (`gold.dim_cbo_historico`), orquestração Dagster (com retry, schedule e backfill) e a integração da Busca Semântica CBO + Assistente Text-to-SQL Governado no painel Streamlit (`src/app/dashboard.py`), validada na [ADR-0007](adr/0007-busca-semantica-e-consumo.md), e a camada semântica única de métricas (`dbt_metra/models/semantic/metricas.yml`), consumida por dbt, painel e assistente. Os pontos de controle de acesso formal, LGPD institucional e ETL reverso seguem em consolidação para o fechamento da E4.

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
| Pequenos grupos | Proposta de suprimir resultados com menos de 5 observações salariais válidas | Validar limiar e ataques por diferença entre filtros; limiar isolado não prova anonimização |
| Retenção | Proposta: manter artefatos locais até 30 dias após encerramento da avaliação e recursos, sujeito à política institucional | Aprovar prazo, inventariar cópias e automatizar descarte; nenhum descarte executado nesta tarefa |
| Descarte | Remover cópias locais, índices, backups e logs conforme política aprovada | Documentar execução e verificar ausência de cópias não autorizadas |
| Repositório público | Já contém amostra de microdados | Revisar risco e finalidade da publicação; ignorar arquivos novos não remove histórico Git existente |
| Modelo externo | Nenhum provedor escolhido nesta proposta | Definir dados permitidos, custos e retenção antes de enviar perguntas ou contexto |

**Controle de acesso proposto:** separar execução do pipeline e processo de consumo; publicar apenas relações/arquivos agregados aprovados e dar ao processo do painel acesso somente a esse artefato. Uma conexão DuckDB `read_only` impede escrita no banco, mas não implementa por si só recorte de linha/coluna. Demonstrar um acesso permitido e uma tentativa negada ao detalhe antes de considerar atendido o checklist da E4.

## Operação e freshness

O destino configurável deve ser compartilhado por dbt, Dagster e consumidores; hoje o padrão dbt é `data/metra_analitico.duckdb`. O consumo só deve apontar para uma execução validada. SLA inicialmente proposto: até 24 horas entre conclusão da extração e publicação validada do mesmo lote. Ver [camada analítica](camada-analitica-dbt.md#freshness-e-proximos-criterios-de-aceite) para separar atraso de processamento de cobertura temporal da fonte.

## ETL reverso: JSON público

O asset `exportar_json_consumo` publica um snapshot do histórico disponível para
o [resumo mensal](consumo-json.md). Esse consumidor permite inspecionar contratação,
saldo e remuneração por recorte e apoiar a escolha de setores para acompanhamento.
O dashboard e o agente de Arthur poderão usar o mesmo contrato. A página mínima
exibe registros; não implementa o agente nem recalcula as respostas P1–P5.

**Estado:** exportador, asset e consumidor implementados. A publicação de dados
reais depende das views de acesso de Lucas, da revisão com Yan e de um PR com o
JSON gerado. Não apresentar a demonstração de produção como concluída antes disso.

### Contrato de entrada com a frente de acesso

Os nomes abaixo são o contrato proposto para integração com Lucas, ainda sujeito à
validação pela equipe. As views devem ser modelos dbt no schema `consumo`, com
os mesmos nomes usados no grafo Dagster. O exportador não cria essas views e não
consulta tabelas da Gold. Views ausentes ou incompatíveis fazem a execução falhar.

| View | Chave única / dimensões |
|---|---|
| `consumo.setor_mensal` | `competencia`, `sigla_uf`, `codigo_secao` |
| `consumo.geografia_mensal` | `competencia`, `sigla_uf`, `is_capital` |
| `consumo.perfil_mensal` | `competencia`, `sigla_uf`, `is_capital`, `codigo_secao`, `eixo`, `codigo_categoria` |
| `consumo.calendario` | `competencia` |

Tipos: `competencia` é `DATE`, primeiro dia do mês, entre 2023 e 2026;
`sigla_uf` é DF/GO/MT/MS; `codigo_secao` é A–U ou Z; `is_capital` é `BOOLEAN`.
Na view de perfis, `eixo` é `sexo`, `raca_cor`, `escolaridade` ou `faixa_etaria`,
`codigo_categoria` é inteiro e `categoria` é seu rótulo textual não nulo. Os eixos
seguem a P5 e não representam filtros demográficos combinados.

As três views de indicadores fornecem `admissoes`, `desligamentos`, `saldo`,
`soma_salarios_admissao` (decimal) e `qtd_salarios_admissao`. Essas medidas têm os
nomes da camada semântica e devem ser produzidas pelas suas macros. Cada grupo
ocorre uma vez; códigos não informados permanecem categorias explícitas.

Na origem, omitir grupos com `admissoes + desligamentos < 5`. Para menos de cinco
salários válidos, incluindo zero, tornar **ambas** as medidas salariais nulas,
mantendo os fluxos. O exportador verifica esse contrato e recusa grupos inseguros;
não executa uma segunda política de supressão e não usa a Gold como alternativa.
O índice de fluxos é calculado pela camada semântica, não pela regra de supressão.

O calendário fornece `competencia` e `tem_dados` booleano, sem lacunas entre seus
meses inicial e final e com pelo menos um mês observado. `tem_dados` indica dados
na origem, independentemente da supressão. Meses sem dados permanecem no calendário;
não inventar linhas de indicadores com zero para preencher ausências.

### Contrato JSON v1 com o consumidor

Destino versionado: `docs/assets/dados/metra.json`. O objeto contém:

- `versao_schema`: inteiro `1`;
- `recorte`: anos, UFs e ressalva sobre cobertura e supressão;
- `metricas`: metadados do catálogo semântico, indexados pelo nome da métrica;
- `setores`, `geografia`, `perfis`: listas de registros, com as dimensões da tabela
  acima; perfis incluem também `categoria`;
- `calendario`: lista de objetos com `competencia` e `tem_dados`.

Cada registro de indicadores expõe somente `admissoes`, `desligamentos`, `saldo`,
`qtd_salarios_admissao`, `salario_medio_admissao` e `indice_fluxos_pareados_pct`, além
das dimensões. Datas são strings `YYYY-MM-DD`; contagens são inteiros; médias e
índices são números, ou `null` para o salário suprimido. O índice já está na escala
0–100. Não publicar o numerador salarial, identificadores individuais ou outros
campos, mesmo que existam na view. Não converter `null` ou ausência de grupo em zero.

Os cálculos usam `colunas_select()` da camada semântica, sobre as medidas da view.
O JSON mantém a precisão numérica do resultado; arredondamento visual é tarefa do
consumidor. As coleções cobrem os recortes de P1–P5 no universo publicado. Supressões
podem tornar os totais parciais e as comparações diferentes das análises internas.
Não somar diferentes coleções ou eixos. Não inferir valores suprimidos por diferença.

### Execução, idempotência e falhas

O job `pipeline_metra` inclui o exportador, com dependências nas quatro views de
consumo. O schedule existente roda no dia 5, às 6h em `America/Sao_Paulo`; o daemon
precisa estar ativo e o schedule habilitado. Para executar só a exportação:

```bash
docker compose --profile dagster run --build --rm dagster-webserver \
  dagster job execute -m dagster_metra.definitions -j exportar_json_consumo_job
```

Alternativa local, no ambiente Python do pipeline:

```bash
python -m src.consumo.exportar_json
python -m src.consumo.exportar_json --banco /caminho/analitico.duckdb --destino /tmp/metra.json
```

O banco respeita `METRA_DUCKDB` (relativo a `dbt_metra/`); o destino respeita
`METRA_JSON_DESTINO` (relativo ao diretório de execução, quando não absoluto).
No Compose o destino é `/app/publicacao/metra.json`, montado no diretório versionado.
O banco é aberto somente para leitura, numa transação, com acesso externo desabilitado.
Essa restrição do exportador não substitui o controle de acesso da frente de Lucas.

A chave idempotente é a combinação das dimensões de cada coleção. Toda execução
reconstrói o histórico completo e substitui o snapshot, incorporando correções de
meses antigos sem duplicar linhas. Mesmo conteúdo gera bytes e SHA-256 iguais;
o horário da execução fica só nos metadados do Dagster, junto com contagens,
competências, destino e tamanho. O horário não representa a data de atualização
da fonte nem o instante da publicação no Pages.

Um lock serializa exportações ao mesmo destino. A escrita usa temporário no mesmo
diretório e substituição atômica após validação, preservando a versão anterior em
caso de falha. O Dagster reutiliza a política de três retries com espera inicial de
10 segundos, backoff exponencial e jitter. Erros não são engolidos; esgotadas as
tentativas, o run falha e precisa ser inspecionado. A execução direta pela CLI não
faz retry por conta própria. Banco ocupado também segue o retry do asset.

### Revisão e publicação

1. Integrar as views do Lucas, validar o acesso e revisar a publicação com Yan.
2. Materializar as views e executar o exportador. Conferir materialização e hash.
3. Revisar o JSON gerado e incluí-lo no PR, com evidência da conciliação e do consumo.
4. Exigir a CI verde. O fluxo de integração exige o JSON produzido pelo pipeline.
5. Após revisão e merge na `main`, o workflow `deploy-docs.yml` publica pelo MkDocs.
6. Abrir o resumo no Pages e conferir os filtros e a cobertura publicada.

Não há commit, push ou credencial GitHub dentro do asset. O schedule atualiza o
arquivo local; a publicação pública só muda após o PR. O SLA proposto de 24 horas
até publicação depende também dessa etapa manual. O repositório preserva versões
anteriores; remover o JSON atual não elimina dados do histórico Git.

Verificar localmente com:

```bash
python -m unittest discover -s tests -p 'test_exportar_json.py' -v
python -m unittest discover -s tests -p 'test_orquestracao.py' -v
node --test tests/test_consumo_js.cjs
mkdocs build --strict
```

As fixtures das views existem apenas nos testes. Nunca usar o JSON sintético como
artefato público real. O consumidor mostra indisponibilidade enquanto a primeira
publicação revisada não existir.

## Checklist para fechar com a equipe

- [x] Publicar Gold, dicionário e métricas com nomes definitivos e testes de reconciliação (176 testes dbt).
- [x] Centralizar a definição de cada métrica na camada semântica (`metricas.yml`), com marts, análises, painel, busca CBO e assistente compilando dela e teste que impede fórmula duplicada (E4).
- [x] Integrar painel Streamlit (`src/app/dashboard.py`), busca semântica CBO e consulta em linguagem natural conforme [ADR-0007](adr/0007-busca-semantica-e-consumo.md).
- [x] Demonstrar SCD tipo 2 (`snp_cbo` / `gold.dim_cbo_historico`), retry, schedule mensal e backfill no Dagster, com consumo em modo somente leitura após materialização da Gold.
- [ ] Validar base legal da LGPD, retenção, pequenos grupos e controle de acesso (além de `read_only`); guardar evidências reais (E4).
- [ ] Implementar e demonstrar o caminho de ETL reverso com seu consumidor (E4).
- [ ] Atualizar diários e registro de IA conforme as atividades da E4 ocorrerem; não antecipar evidências de execução futura.
