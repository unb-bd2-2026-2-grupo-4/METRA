# 0005 - Preservar o grão de movimentação na Gold e validar as camadas com dbt

- **Status:** implementado
- **Data:** 29/10/2026
- **Responsável pela proposta:** Euller Júlio;

## 1. Contexto

A Silver de Lucas já transforma cinco conjuntos Parquet em quatro tabelas DuckDB. A E3 exige modelagem dimensional, grão explícito, dimensão de variação lenta e testes de esquema, volume, unicidade, integridade e distribuição. As cinco perguntas incluem recortes geográficos, temporais, setoriais e demográficos; uma agregação precoce pode eliminar os recortes necessários à P5.

A amostra versionada tem 49.178 movimentações; o volume completo documentado pelo projeto é de aproximadamente 14,7 milhões e não foi executado neste experimento. A proposta usa ambiente local, sem novo servidor de banco. A modelagem Gold é tarefa de Tiago; esta ADR antecipa o contrato a revisar com ele.

## 2. Alternativas consideradas

### A. Manter consultas sobre Parquet/Silver com scripts SQL — opção nula

É viável para poucas consultas e não exige dimensões. Entretanto, repetir joins e fórmulas em cada consumidor aumenta a possibilidade de divergência. Um cron poderia executar os scripts, mas os contratos de qualidade e dependências ainda precisariam ser implementados. Não houve benchmark comparativo de cron versus dbt.

### B. Usar apenas uma tabela agregada por competência, município e subclasse CNAE

Reduz linhas e espaço; pode conservar saldo, admissões, desligamentos e médias se guardar soma salarial e quantidade válida. Elimina ocupação, perfil, idade e linhagem individual. Não atende aos recortes de P5 nem à busca de indicadores por CBO sem outra estrutura.

### C. Fato por movimentação, dimensões e agregados derivados no dbt — proposta

Preserva os recortes e a rastreabilidade. A proposta de estrela contém competência, município, CBO versionada, CNAE e perfil; os agregados mensais são derivados para consumo. Exige joins, gerenciamento de chaves SCD e mais armazenamento. Reutiliza o projeto dbt já presente, com testes declarados junto aos modelos.

## 3. Medição e Prototipação

O script `src/qualidade/avaliar_granularidade.py` usa a amostra CSV normalizada pela mesma expressão do experimento da ADR-0003. IDs e timestamps de linhagem são sintéticos. Não lê cadastros oficiais, não simula a estrela final e não executa PostgreSQL. O ensaio compara dois grãos, não duas implementações completas de ferramentas.

Uma thread DuckDB, cinco repetições após aquecimento, tabelas em memória, mesma consulta de saldo e componentes salariais por competência/subclasse. Cache e carga do host não são controlados; as alternativas são executadas em ordem fixa. Cada candidato é exportado para um único Parquet Snappy. Os resultados não são comparáveis diretamente aos arquivos particionados da ADR-0003.

| Candidato medido | Linhas | Parquet (bytes) | Mediana da consulta (ms) | Limite funcional |
|---|---:|---:|---:|---|
| Detalhe por movimentação | 49.178 | 934.225 | 21,512 | Preserva atributos necessários à futura estrela |
| Mensal por município/subclasse | 36.869 | 309.897 | 26,001 | Perde CBO, perfil e linhagem individual |

A agregação reduz espaço, mas não foi mais rápida nesta execução. A escolha do detalhe é funcional, não uma alegação de superioridade de desempenho. As métricas aditivas reconciliaram por comparação de multiconjuntos nos dois sentidos. Evidências, versões, hash da amostra, tempos e planos DuckDB: [0005-granularidade.json](evidencias/0005-granularidade.json).

Reprodução na raiz, com `requirements-pipeline.txt` instalado:

```bash
python -m src.qualidade.avaliar_granularidade --saida /tmp/metra-granularidade.json
python -m unittest discover -s tests -p 'test_dbt_quality.py' -v
```

A suíte de qualidade usa Parquet sintético independente: valida o dbt real, os casos aceitos e a detecção de falhas. Não é evidência de qualidade da carga completa. O catálogo dos testes e comandos da carga real está na [página da camada analítica](../camada-analitica-dbt.md).

## 4. Decisão

**Propor fato com uma linha por movimentação, dimensões compartilhadas e agregados de consumo derivados, mantendo dbt como transformação e validação.** Preservar o histórico observado da CBO por SCD2. Esta proposta depende da revisão dos nomes, chaves e estratégia de SCD com Tiago; não declara a Gold implementada ou aceita pela Squad.

## 5. Consequências e Tradeoffs

### O que se ganha

- Conservação dos recortes das cinco perguntas e da linhagem até arquivo/linha.
- Contratos versionados e verificações de perda/duplicação/distribuição antes do consumo.
- Uma origem para métricas compartilhadas entre painel e futura interface em linguagem natural.

### O que se perde ou se compromete

- Mais linhas e joins do que uma tabela mensal; a carga completa ainda precisa ser medida.
- SCD exige snapshots persistentes, tratamento de intervalos e associação estável de cada fato à versão do cadastro.
- `dbt build` não publica todo o banco atomicamente; o Dagster precisa impedir consumo de uma execução incompleta.
- Limites de variação mensal são avisos operacionais, sujeitos a calibração com os dados reais.

### O que restringe o sistema futuro

As chaves e métricas virarão contratos do painel. A CBO atual não oferece vigência histórica: os intervalos documentam observação, não validade retroativa. Trocar o grão ou reconstruir versões SCD exige preservar as associações e revalidar agregados e consumidores. A seleção de ferramentas continua reversível; os dados permanecem em formatos locais abertos.

## 6. Gatilho de Revisão

Revisar antes de aceitar a ADR se a Gold não puder responder aos recortes de P5, se o ensaio de mudança de título CBO perder histórico, se houver duplicação após joins ou se o SLA proposto de publicação em 24 horas após extração validada não for atendido. Repetir o benchmark com a carga completa, dimensões reais e consultas do painel antes de afirmar desempenho. A definição de turnover depende de uma fonte de estoque de empregos; não substituir esse denominador pelo saldo.
