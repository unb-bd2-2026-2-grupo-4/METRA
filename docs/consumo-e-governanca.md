# Consumo e governança

**Documento inicial de integração, em 29/10/2026.** O repositório contém ingestão, OLTP, exportação Parquet/Delta, Silver e testes. Gold, dashboard, índice vetorial, controle de acesso e ETL reverso ainda dependem das entregas da equipe. As políticas abaixo estão propostas para revisão; esta página não declara esses mecanismos implementados.

## Catálogo preliminar de métricas

As definições partem de `silver.stg_movimentacao`. Os nomes físicos e a implementação centralizada na Gold serão alinhados com Tiago. O painel e o assistente devem consumir essa implementação única, sem duplicar fórmulas em Python.

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
| Turnover setorial | **Pendente:** escolher fórmula e obter estoque compatível de vínculos | Não calculável como taxa de estoque apenas com admissões/desligamentos e saldo |

Agregados devem guardar soma salarial e quantidade válida para recompor médias. Não calcular média simples de médias municipais. Categorias não informadas permanecem identificadas; não atribuir valores demográficos ausentes. Os rótulos dos códigos precisam ser validados com o dicionário CAGED adotado.

### Correspondência com as perguntas publicadas

| Pergunta | Recorte necessário | Pendência para consumo |
|---|---|---|
| P1: setores no DF nos últimos 12 meses | UF DF, seção CNAE e janela de 12 competências | Definir âncora na última competência disponível e informar isso no painel |
| P2: sazonalidade | Série mensal por ano | Distinguir padrões de calendário de meses parciais/ausentes |
| P3: capitais versus interior | Município identificado, flag de capital e competência | Agregação mensal complementa a comparação geográfica |
| P4: turnover e salário | Setor, competência, salário válido e estoque | Fonte, denominador e fórmula de turnover ainda não definidos |
| P5: perfil e remuneração | Sexo, raça/cor, idade e escolaridade | Não confundir movimentos observados com chance de recolocação |

## Linhagem da fonte ao consumo

| Informação | Origem → persistência → Silver | Destino previsto |
|---|---|---|
| Competência e saldo | CAGED → `bronze.caged_movimentacao` → `oltp.movimentacao` → Parquet `movimentacao` → `stg_movimentacao` | Fato e agregados Gold → painel/assistente |
| Município/UF | IBGE → `bronze.ibge_municipio` → `oltp.municipio` → Parquet `municipio` → `stg_municipio` | Dimensão geográfica |
| Ocupação | CBO → `bronze.cbo_ocupacao` → `oltp.cbo_2002` → Parquet `cbo_2002` → `stg_cbo` | Dimensão versionada e índice de busca |
| Atividade econômica | IBGE CNAE → `bronze.ibge_cnae_subclasse` → `oltp.cnae_subclasse`/`cnae_secao` → respectivos Parquets → `stg_cnae` | Dimensão econômica |
| Perfil e salário | Campos do CAGED → movimentação Bronze/OLTP/Parquet → `stg_movimentacao` | Perfil, fato e métricas agregadas |

`id_ingestao` e `numero_linha` permitem voltar à origem da movimentação; `manifest.json` descreve as dependências dbt e `run_results.json` registra o resultado da execução. A vinculação desses artefatos ao lote e ao grafo Dagster é a próxima etapa de Davi. O replay CDC SQLite existente não está automaticamente conectado à Silver; não representar essa integração como pronta.

## Privacidade e acesso: análise inicial

O modelo atual não contém CPF ou nome do trabalhador, mas combina município, competência, CBO, idade, sexo, raça/cor e salário. Combinações raras podem permitir identificação indireta; ausência de identificador direto não comprova anonimização. Raça/cor, quando vinculada a pessoa identificada ou identificável, requer atenção como informação sensível. Essas distinções constam do [art. 5º da LGPD](https://www2.camara.leg.br/legin/fed/lei/2018/lei-13709-14-agosto-2018-787077-normaatualizada-pl.html).

| Item | Situação ou proposta | Ação ainda necessária |
|---|---|---|
| Finalidade | Análise acadêmica agregada do mercado formal | Registrar responsável institucional e escopo aprovado |
| Base legal | **Pendente de validação institucional** | Documentar a hipótese aplicável; não presumir que dado público ou trabalho acadêmico resolve todo enquadramento |
| Minimização | Painel proposto só com métricas agregadas; sem linhagem individual nas telas públicas | Criar relações de consumo com colunas permitidas e testá-las |
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

- Publicar Gold, dicionário e métricas com nomes definitivos e testes de reconciliação.
- Integrar Streamlit, busca CBO e consulta em linguagem natural conforme [ADR-0007](adr/0007-busca-semantica-e-consumo.md), depois de medir e revisar a proposta.
- Demonstrar SCD, freshness, retry/backfill e atualização de consumo somente após validação.
- Validar base legal, retenção, pequenos grupos e controle de acesso; guardar evidências reais.
- Implementar e demonstrar o caminho de ETL reverso com seu consumidor.
- Atualizar diários e registro de IA conforme as atividades ocorrerem; não antecipar evidências de execução futura.
