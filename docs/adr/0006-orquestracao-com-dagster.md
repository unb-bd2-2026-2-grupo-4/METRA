# 0006 - Adotar o Dagster para o pipeline

- **Status:** Aceito
- **Data:** 05/11/2026
- **Decisores:** Davi Camilo

---

## 1. Contexto

O METRA precisa coordenar a atualização da origem PostgreSQL, a extração para o lake Parquet e a transformação dbt-duckdb das camadas Silver e Gold. Antes desta decisão, os scripts `src/ingestao/executar_pipeline.py` e `src/extracao/exportar_parquet.py` podiam ser executados diretamente, mas a dependência entre as etapas e a visão operacional do pipeline ficavam fora de uma interface única.

A E3 também exige que a linhagem seja verificável. O grafo deve mostrar a sequência `executar_pipeline` → `exportar_parquet` → sources `lake/*` → modelos Silver → modelos Gold. Os arquivos Parquet são produzidos pela extração, por isso, os cinco sources declarados no dbt não são materializações independentes, mas precisam aparecer como assets virtuais no grafo.

O desenho deve permanecer compatível com a simplificação arquitetural da [ADR 0002](0002-simplificacao-arquitetural-duckdb.md), usar o Python e o dbt já adotados e funcionar tanto localmente quanto nos serviços Docker do projeto.

---

## 2. Alternativas consideradas

### A. Manter apenas scripts e comandos independentes — opção nula

É a opção de menor complexidade imediata e preserva os scripts já existentes. Porém, a ordem de execução depende do operador, não há uma representação operacional única das dependências e a linhagem entre a extração, os sources Parquet e os modelos dbt não aparece em uma UI de assets. Pode continuar sendo usada para depuração e execução manual, mas não atende integralmente à necessidade da E3.

### B. Usar Airflow

O Airflow oferece agendamento, execução e monitoramento maduros. Em contrapartida, acrescenta infraestrutura e conceitos de DAG, operadores e serviços de suporte que são desproporcionais ao ambiente local baseado em PostgreSQL, Parquet e DuckDB. Também não representa naturalmente os modelos dbt como ativos de dados sem uma camada adicional de integração.

### C. Usar Dagster integrado ao dbt — proposta escolhida

O Dagster permite declarar `executar_pipeline` e `exportar_parquet` como assets Python, carregar os assets do dbt a partir do manifesto e visualizar dependências em um grafo de assets. A integração `dagster-dbt` mantém Silver e Gold no projeto dbt, enquanto specs virtuais representam os cinco sources Parquet sem fingir que a UI materializa esses arquivos novamente.

---

## 3. Medição e Prototipação

A validação foi feita sobre o código e o manifesto presentes no repositório, com `dagster==1.13.28`, `dagster-dbt==0.29.28`, `dbt-core==1.12.6` e `dbt-duckdb==1.11.1`. A implementação foi feita em `dagster_metra/assets.py` e `dagster_metra/definitions.py`.

Foram verificadas as seguintes propriedades:

| Verificação | Resultado esperado |
|---|---|
| Carregamento das definições | `Definitions.validate_loadable` sem erro |
| Dependência de ingestão e extração | `executar_pipeline` precede `exportar_parquet` |
| Sources do lake | Cinco sources Parquet virtuais dependem de `exportar_parquet` |
| Transformação analítica | O manifesto dbt expõe Silver e Gold no mesmo grafo |
| Ambiente containerizado | `docker compose config --quiet` válido; webserver e daemon compartilham `DAGSTER_HOME` |
| Evidência visual | Grafo revisado na UI e preservado em [grafo_linhagem.svg](../assets/grafo_linhagem.svg) |

Reprodução da validação principal na raiz do repositório:

```bash
dagster definitions validate -w workspace.yaml
docker compose config --quiet
git diff --check
```

Essas verificações validam a estrutura das definições e da configuração, porém não constituem benchmark de latência nem comprovam, sozinhas, a execução de uma carga completa de produção.

---

## 4. Decisão

**Adotar Dagster como orquestrador do pipeline, integrado ao dbt por `dagster-dbt`, mantendo os scripts existentes como implementação das etapas e expondo a linhagem completa como um grafo de assets.**

O pipeline passa a ter dois assets Python materializáveis, cinco sources Parquet virtuais e os assets Silver/Gold derivados do manifesto dbt. `exportar_parquet` depende explicitamente de `executar_pipeline`, cada source `lake/*` depende de `exportar_parquet`, e o dbt conserva as dependências entre sources, Silver e Gold.

---

## 5. Consequências e Tradeoffs

### O que se ganha

- Ordem de execução declarada e visível na interface do Dagster.
- Linhagem ponta a ponta entre PostgreSQL, Parquet, Silver e Gold.
- Reutilização dos scripts de ingestão e extração, sem duplicar a lógica de negócio.
- Integração entre o manifesto dbt e a materialização via `dbt build`.
- Execução local com `dagster dev` e execução containerizada com webserver e daemon.

### O que se perde ou se compromete

- O manifesto dbt precisa estar disponível para o carregamento das definições; em desenvolvimento ele é preparado quando necessário e na imagem Docker é criado durante o build.
- Os sources `lake/*` são virtuais: aparecem na linhagem, mas não são escritos pelo Dagster.
- O Dagster não torna automaticamente a publicação do DuckDB atômica; falhas de `dbt build`, concorrência de escrita e promoção do resultado continuam exigindo política operacional.
- A interface e o daemon acrescentam dependências e consumo de recursos em relação à execução direta dos scripts.

### O que restringe o sistema futuro

Os nomes dos assets e as chaves de origem passam a ser contratos da observabilidade do pipeline. Alterações nos nomes dos sources, nos caminhos Parquet ou no manifesto dbt exigem revisar as specs virtuais, a documentação e a evidência do grafo. A escolha de Dagster continua substituível, desde que as dependências, os contratos de qualidade e a linhagem sejam preservados.

---

## 6. Gatilho de Revisão

Revisar esta ADR se a carga completa não puder ser executada dentro da janela operacional definida pela Squad, se o daemon não conseguir processar materializações disparadas pela UI, se a geração do manifesto deixar de ser reprodutível ou se a linhagem exibida deixar de representar a sequência real de dados. Também revisar antes de adicionar múltiplos consumidores, ambientes distribuídos ou requisitos de SLA que justifiquem uma plataforma de orquestração diferente.
