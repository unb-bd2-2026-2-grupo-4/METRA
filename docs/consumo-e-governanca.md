# Consumo e governança

**Documento de integração atualizado em 10/11/2026.** O repositório já contém ingestão, OLTP, exportação Parquet/Delta, camadas Silver e Gold com 176 testes dbt de qualidade, SCD tipo 2 da CBO (`gold.dim_cbo_historico`), orquestração Dagster (com retry, schedule e backfill) e a integração da Busca Semântica CBO + Assistente Text-to-SQL Governado no painel Streamlit (`src/app/dashboard.py`), validada na [ADR-0007](adr/0007-busca-semantica-e-consumo.md). Os pontos de controle de acesso formal, LGPD institucional e ETL reverso seguem em consolidação para o fechamento da E4.

## Catálogo de métricas da camada Gold

As definições partem de `silver.stg_movimentacao` e estão materializadas de forma centralizada no schema `gold` (`gold.fct_movimentacao`, `gold.fct_setor_mensal`, `gold.fct_geografia_mensal`, `gold.fct_perfil_mensal` e dimensões `gold.dim_*`). O painel Streamlit e o assistente Text-to-SQL consomem diretamente essa implementação única, sem duplicar fórmulas em Python.

| Métrica | Definição no conjunto filtrado | Unidade e ressalva |
|---|---|---|
| Admissões | `count(*) filter (where saldo_movimentacao = 1)` | Movimentações, não pessoas distintas |
| Desligamentos | `count(*) filter (where saldo_movimentacao = -1)` | Movimentações |
| Saldo líquido | `sum(saldo_movimentacao)` = admissões − desligamentos | Movimentações líquidas; não é estoque de vínculos |
| Salário médio de admissão | `avg(salario_mensal) filter (where saldo_movimentacao = 1 and salario_valido)` | R$ nominais; nulo quando não há observação elegível |
| Quantidade salarial válida | `count(*) filter (where saldo_movimentacao = 1 and salario_valido)` | Denominador da média; deve acompanhar o valor exibido |
| Série mensal | Mesmas métricas agrupadas por `competencia` | Mês da movimentação; distinguir mês ausente de zero observado |
| Capital/interior | Métricas por `is_capital`, somente municípios identificados do recorte | Sentinela não deve ser classificada como interior |
| Disparidade salarial | Comparar salário médio e quantidade válida por sexo, raça/cor, escolaridade e faixa etária | Associação descritiva, sem inferir causalidade ou probabilidade individual de recolocação |
| Turnover setorial (proxy de fluxos) | `200.0 * least(admissoes, desligamentos) / nullif(admissoes + desligamentos, 0)` ([ADR-0007](adr/0007-busca-semantica-e-consumo.md)) | Índice de equilíbrio de fluxos pareados (0 a 100%) usado como aproximação; não é taxa sobre estoque de vínculos (indisponível no CAGED) |

Agregados guardam soma salarial (`soma_salarios_admissao`) e quantidade válida (`qtd_salarios_admissao`) para recompor médias ponderadas exatas. Não calcular média simples de médias municipais. Categorias não informadas permanecem identificadas; não atribuir valores demográficos ausentes.

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

## ETL reverso: proposta a definir com a equipe

Um caminho possível é exportar um resumo mensal validado de saldo e remuneração por setor/UF para um arquivo que um processo de acompanhamento do gestor consuma. Ainda faltam consumidor real, ação tomada, formato, chave idempotente, frequência e tratamento de falhas. Apenas gravar mais uma tabela ou CSV sem consumo não conclui ETL reverso. A escolha e a demonstração são necessárias na [E4](https://unb-bd2.github.io/PlanoEnsino/projeto/e4/).

## Checklist para fechar com a equipe

- [x] Publicar Gold, dicionário e métricas com nomes definitivos e testes de reconciliação (176 testes dbt).
- [x] Integrar painel Streamlit (`src/app/dashboard.py`), busca semântica CBO e consulta em linguagem natural conforme [ADR-0007](adr/0007-busca-semantica-e-consumo.md).
- [x] Demonstrar SCD tipo 2 (`snp_cbo` / `gold.dim_cbo_historico`), retry, schedule mensal e backfill no Dagster, com consumo em modo somente leitura após materialização da Gold.
- [ ] Validar base legal da LGPD, retenção, pequenos grupos e controle de acesso (além de `read_only`); guardar evidências reais (E4).
- [ ] Implementar e demonstrar o caminho de ETL reverso com seu consumidor (E4).
- [ ] Atualizar diários e registro de IA conforme as atividades da E4 ocorrerem; não antecipar evidências de execução futura.
