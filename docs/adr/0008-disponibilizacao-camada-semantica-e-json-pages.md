# 0008 - Disponibilizar métricas pela camada semântica dbt e snapshot JSON estático no GitHub Pages

- **Status:** Aceito
- **Data:** 23/11/2026
- **Decisores:** Arthur Evangelista, com revisão da Squad G4

---

## 1. Contexto

Na Entrega 4 (E4), o METRA precisa unificar o cálculo das sete métricas do catálogo em uma fonte única, publicar um caminho de ETL reverso para acompanhamento externo e disponibilizar os indicadores para gestores e trabalhadores sem servidor pago na nuvem.

### Caracterização da Carga e Restrições

- **Volume:** A origem cobre `49.178` movimentações na amostra versionada (`14.753.112` na base completa, 37 competências entre `2023-01` e `2026-01`). Após agregação e supressão de pequenos grupos ($k \ge 5$) nas quatro views `consumo.*`, o universo publicado soma **`13.303` registros**: `1.681` em `setor_mensal`, `259` em `geografia_mensal`, `11.326` em `perfil_mensal` e `37` em `calendario`.
- **Padrão de acesso e latência:** Carga em lote mensal (dia 5, acompanhando o Novo CAGED via Dagster); leituras exclusivamente agregadas sobre as 7 métricas declaradas em `dbt_metra/models/semantic/metricas.yml`, com resposta interativa tolerada abaixo de `500 ms` no navegador.
- **Restrições não funcionais:** Custo zero de hospedagem (uso de GitHub Pages já existente via `deploy-docs.yml`), nenhuma chave de API externa (ADR-0007), separação entre ambiente interno (`gold.fct_movimentacao`) e canal público (`consumo.*` / `metra.json`) conforme LGPD arts. 7º IV e 11 II "c".

---

## 2. Alternativas Consideradas

### A. Entrega em CSV agendado (Opção Nula)

Exportar as quatro relações `consumo.*` como arquivos CSV mensais gerados pelo Dagster para download direto no repositório ou consumo em planilhas/scripts.

- **Por que é viável e forte:** Menor custo de escrita (`998 KB` brutos, `39,0 ms` de exportação), formato universal para analistas em Excel, LibreOffice ou Python, e mínima manutenção de código.
- **Por que foi descartada como canal principal:** CSV puro não transporta os metadados do catálogo semântico (`label`, descrição, formato e ressalvas de supressão) no mesmo contrato, exige que usuários de gestão baixem e cruzem quatro arquivos manualmente e não entrega painel visual nem agente em linguagem natural no GitHub Pages.

### B. Camada semântica única + ETL reverso JSON no GitHub Pages + Painel/Agente JS (Escolhida)

Centralizar as métricas em `dbt_metra/models/semantic/metricas.yml` (`src/metricas/camada_semantica.py`), exportar via asset `exportar_json_consumo` o snapshot idempotente `docs/assets/dados/metra.json` (`versao_schema: 1`) e servi-lo no GitHub Pages com painel interativo e agente JavaScript local no navegador (`docs/javascripts/metra-agente.js` e `metra-painel.js`), mantendo o Streamlit para uso interno sobre a Gold.

- **O que oferece:** Custo R$ 0 de servidor, zero backend, envio compactado em ~`242 KB` gzip-6, metadados semânticos embarcados no JSON e mesma lógica de guardrails e médias ponderadas no navegador e no painel interno.

### C. Servidor BI tradicional (Metabase sobre DuckDB)

Subir container Metabase conectado ao `data/metra_consumo.duckdb` para exploração visual e agendamento de entregas.

- **Por que foi descartada:** Conforme restringido pela [ADR-0002](0002-simplificacao-arquitetural-duckdb.md), o Metabase exige JVM e banco próprio de metadados (~1 a 2 GB de RAM em repouso), não inclui driver oficial embutido para DuckDB (depende de driver comunitário externo) e exigiria servidor público pago ou túnel aberto para terceiros acessarem fora da máquina local.

---

## 3. Medição e Prototipação

O script reproduzível `src/consumo/avaliar_disponibilizacao.py` leu o snapshot real versionado (`docs/assets/dados/metra.json`, SHA-256 `e890cf810a48077667228e1e91f79c553c838958da942a6b54c8887f6079e45e`), populou as quatro relações `consumo.*` em DuckDB temporário (1 thread) e executou 1 aquecimento descartado mais 7 repetições válidas. A alternativa C mediu as consultas SQL equivalentes (P1 e P3) direto no DuckDB, registrando os requisitos operacionais do Metabase sem fabricar tempos de servidor JVM ausente.

**Ambiente:** Python `3.11.16`, DuckDB `1.5.6`, `Node.js v22.12.0` (V8), `Windows-10-10.0.26200-SP0`. Evidências completas em [0008-disponibilizacao.json](evidencias/0008-disponibilizacao.json).

| Alternativa medida | Tamanho bruto (bytes) | Transferência gzip-6 (bytes) | Mediana escrita (ms) | Mediana leitura / consulta (ms) | p95 leitura (ms) | Infra pública extra |
|---|---:|---:|---:|---:|---:|---|
| **A. CSV agendado (4 arquivos)** | 997.716 | 194.363 | 39,000 | 7,106 *(Python CSV + P1/P3)* | 10,010 | Nenhuma |
| **B. JSON v1 + Agente JS (Pages)** | 5.194.966 *(3.743.226 compacto)* | 242.292 *(220.875 compacto)* | 303,143 | 64,838 *(V8 `JSON.parse` + P1–P5)* | 72,116 | Nenhuma (GitHub Pages) |
| **C. SQL DuckDB (referência BI/Metabase)** | — *(arquivo `.duckdb`)* | — | — | 4,110 *(SQL P1 + P3)* | 5,563 | JVM + banco Metabase + hospedagem |

A resposta consolidada da pergunta central (P3 sobre o snapshot publicado) atingiu **paridade exata** entre CSV, JS e DuckDB (`paridade_p3_identica = true`): saldo `+528` e salário médio `R$ 2.268,97` (`n = 10.514`) nas capitais vs. saldo `+944` e salário médio `R$ 2.138,23` (`n = 14.491`) no interior.

Reprodução na raiz do repositório:

```bash
python -m src.consumo.avaliar_disponibilizacao --saida docs/adr/evidencias/0008-disponibilizacao.json
node --test tests/test_consumo_js.cjs tests/test_agente_pages_js.cjs
```

---

## 4. Decisão

**Adotamos a Alternativa B: centralizar as definições na camada semântica dbt (`metricas.yml` + `src/metricas/camada_semantica.py`), publicar via ETL reverso (`exportar_json_consumo`) o snapshot `docs/assets/dados/metra.json` e servir o painel público com agente JavaScript no GitHub Pages, mantendo o Streamlit como interface interna sobre a Gold.**

---

## 5. Consequências e Tradeoffs

### O que ganhamos

- Definição matemática e metadados únicos em `metricas.yml` consumidos por dbt, Streamlit, Text-to-SQL, ETL reverso e GitHub Pages.
- Canal público acessível por navegador sem backend, container Docker ou chave de API, respondendo P1–P5 em `~65 ms` após transferência de `~242 KB` gzip-6.
- Isolamento físico completo dos microdados individuais (`gold.fct_movimentacao` e CBOs não chegam ao navegador nem ao JSON público).

### O que perdemos

- Cada snapshot JSON versionado com `indent=2` adiciona `5.194.966` bytes em LF (~`5,19 MB`; `5.386.426` bytes em CRLF) ao repositório Git a cada ciclo mensal publicado.
- A atualização visível no GitHub Pages depende de revisão e merge de PR (o schedule do Dagster atualiza apenas o arquivo local), somando etapa manual ao SLA de 24 horas.
- O painel e agente públicos não suportam filtro por ocupação CBO ou município individual (suprimidos por $k \ge 5$) e operam sobre totais recompostos parciais quando células menores que 5 são omitidas.
- Passamos a manter duas implementações de interface (Streamlit em Python e SVG/DOM em JavaScript), embora o contrato semântico e os testes de paridade evitem divergência numérica.

### O que se torna irreversível

- Remover snapshots futuros do working tree exige `git rm`, mas expurgar snapshots já commitados do histórico do Git exige reescrever commits (`git filter-repo`). Migrar o canal público do Pages estático para uma API ou instância Metabase consumiria cerca de 2 a 3 dias de engenharia (provisionamento de servidor/container, autenticação e substituição dos scripts em `docs/javascripts/`).

---

## 6. Gatilho de Revisão

Reavaliar esta arquitetura e migrar para API paginada/backend analítico ou formato binário fragmentado se qualquer um destes limiares for ultrapassado:

1. O snapshot `docs/assets/dados/metra.json` ultrapassar **`15 MB` brutos** (ou **`1,5 MB` em gzip-6**), seja por ampliação para todo o Brasil ou inclusão de novos recortes;
2. A soma de carregamento e primeira consulta (`p95`) no navegador exceder **`1.000 ms`** em conexão residencial padrão; ou
3. O consumidor operacional exigir atualização intradiária (`SLA < 1 hora` sem etapa manual de PR) ou autenticação individual por perfil de usuário externo.
