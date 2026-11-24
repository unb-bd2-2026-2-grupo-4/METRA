# 0005 - Preservar o grão de movimentação na Gold e validar as camadas com dbt

- **Status:** Aceito
- **Data:** 29/10/2026 (atualização de escopo em 03/11/2026; revisão E4 em 23/11/2026)
- **Decisores:** Euller Júlio (revisão E4: Arthur Evangelista)

---

## 1. Contexto

A Silver já transforma cinco conjuntos Parquet em quatro tabelas DuckDB. A E3 exige modelagem dimensional, grão explícito, dimensão de variação lenta e testes de esquema, volume, unicidade, integridade e distribuição. As cinco perguntas incluem recortes geográficos, temporais, setoriais e demográficos; uma agregação precoce pode eliminar os recortes necessários à P5.

A amostra versionada tem 49.178 movimentações; o volume completo documentado pelo projeto é de `14.753.112` registros (inicialmente não executado no experimento de granularidade da amostra e posteriormente medido em `src/qualidade/comparar_explain.py`, Seção 7). A proposta usa ambiente local, sem novo servidor de banco. A Gold de Tiago iniciou na base deste PR com cinco dimensões, uma fato detalhada e três fatos mensais, estendida depois pelo histórico SCD2 (`dim_cbo_historico`) e pelas views `consumo.*` (E4). Esta ADR documenta a escolha do grão e os testes acrescentados por Euller.

---

## 2. Alternativas consideradas

### A. Manter consultas sobre Parquet/Silver com scripts SQL — opção nula

É viável para poucas consultas e não exige dimensões. Entretanto, repetir joins e fórmulas em cada consumidor aumenta a possibilidade de divergência. Um cron poderia executar os scripts, mas os contratos de qualidade e dependências ainda precisariam ser implementados. Não houve benchmark comparativo de cron versus dbt.

### B. Usar apenas uma tabela agregada por competência, município e subclasse CNAE

Reduz linhas e espaço; pode conservar saldo, admissões, desligamentos e médias se guardar soma salarial e quantidade válida. Elimina ocupação, perfil, idade e linhagem individual. Não atende aos recortes de P5 nem à busca de indicadores por CBO sem outra estrutura.

### C. Fato por movimentação, dimensões e agregados derivados no dbt — proposta

Preserva os recortes e a rastreabilidade. A estrela implementada contém competência, município, CBO, CNAE e perfil; os agregados mensais são derivados para consumo. Exige joins e mais armazenamento. A evolução para SCD exigirá gerenciamento de chaves por versão. Reutiliza o projeto dbt já presente, com testes declarados junto aos modelos.

---

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

---

## 4. Decisão

**Manter o grão de uma movimentação por linha, dimensões compartilhadas e agregados de consumo derivados, usando dbt para transformação e validação.** Esse desenho corresponde à Gold materializada na base, complementada pelo histórico observado da CBO por SCD Tipo 2 (`snapshots/snp_cbo.yml` e `gold.dim_cbo_historico`, implementado na sequência da E3 — ver Seção 7).

---

## 5. Consequências e Tradeoffs

### O que se ganha

- Conservação dos recortes das cinco perguntas e da linhagem até arquivo/linha.
- Contratos versionados e verificações de perda/duplicação/distribuição antes do consumo.
- Uma origem para métricas compartilhadas entre painel e futura interface em linguagem natural.

### O que se perde ou se compromete

- Mais linhas e joins do que uma tabela mensal (custo medido posteriormente na base completa em `0005-explain-completo.json` e superado pelos 3 agregados mensais).
- SCD exige snapshots persistentes, tratamento de intervalos e associação estável de cada fato à versão do cadastro (`referencia_cadastro_em` segue como evolução pendente em reconstruções completas).
- `dbt build` não publica todo o banco atomicamente; o Dagster precisa impedir consumo de uma execução incompleta.
- Limites de variação mensal são avisos operacionais, sujeitos a calibração com os dados reais.

### O que restringe o sistema futuro

As chaves e métricas virarão contratos do painel. A CBO atual não oferece vigência histórica: os intervalos documentam observação, não validade retroativa. Trocar o grão ou reconstruir versões SCD exige preservar as associações e revalidar os 4 marts, `metricas.yml`, as 4 views `consumo.*` e mais de 210 testes dbt (custo estimado de ~3 a 4 dias de engenharia para migrar tudo para um modelo alternativo). A seleção de ferramentas continua reversível; os dados permanecem em formatos locais abertos.

---

## 6. Gatilho de Revisão

Revisar antes de aceitar a ADR se a Gold não puder responder aos recortes de P5, se o ensaio de mudança de título CBO perder histórico, se houver duplicação após joins ou se o SLA proposto de publicação em 24 horas após extração validada não for atendido. Repetir o benchmark com a carga completa, dimensões reais e consultas do painel antes de afirmar desempenho. A definição de turnover depende de uma fonte de estoque de empregos; não substituir esse denominador pelo saldo.

---

## 7. Revisão E4 (23/11/2026)

Todas as pendências registradas originalmente em 29/10–03/11 foram implementadas no fechamento da E3 e consolidadas na E4:

1. **SCD Tipo 2 implementado e testado:** `dbt_metra/snapshots/snp_cbo.yml` materializa `gold.dim_cbo_historico` com intervalos `[observado_desde, observado_ate)`, validado por `dbt_metra/tests/assert_cbo_uma_versao_vigente.sql` e `tests/test_scd_cbo.py`. Permanece apenas a limitação documentada de a fato usar `dim_cbo` vigente em reconstruções completas (`referencia_cadastro_em` não vinculada retroativamente).
2. **Carga completa medida (`EXPLAIN ANALYZE`):** O benchmark `src/qualidade/comparar_explain.py` sobre as `14.753.112` movimentações reais confirmou ganho de **`≈ 40×`** na consulta P1: `33,27 ms` (`fct_movimentacao`, 918.397 linhas após filtros) contra `0,84 ms` (`fct_setor_mensal`, 251 linhas), preservado em [0005-explain-completo.json](evidencias/0005-explain-completo.json).
3. **Evolução na E4:** A Gold passou a ser governada pela camada semântica única (`dbt_metra/models/semantic/metricas.yml`), exposta com supressão $k \ge 5$ nas views `consumo.*` e auditada por 12 testes sobre a Gold real em `tests/test_gold_integracao.py`. Os gatilhos de revisão de P5, SCD2 e duplicação foram superados com sucesso.
