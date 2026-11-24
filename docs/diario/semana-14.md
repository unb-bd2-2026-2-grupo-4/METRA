# Diário de Bordo - Semana 14

- **Data:** Semana 14 (Semestre 2026/2)
- **Autor(es):** Squad G4 (Arthur Evangelista, Davi Camilo, Euller Júlio, Lucas Alves, Tiago Antunes e Yan Matheus)

---

## O que foi medido e analisado

- **Controle de acesso e consumo agregado:** Criação das views `consumo.setor_mensal`, `geografia_mensal`, `perfil_mensal` e `calendario`, além de uma base DuckDB isolada e demonstração de acessos permitidos e negados. O contrato omite grupos com menos de cinco movimentações e oculta medidas salariais com menos de cinco salários válidos.
- **ETL reverso e publicação:** Implementação do asset `exportar_json_consumo`, com validação das views, exportação idempotente, substituição atômica, SHA-256 e retry no Dagster. O snapshot versionado contém 1.681 registros setoriais, 259 geográficos, 11.326 de perfil e 37 competências no calendário.
- **LGPD, catálogo e linhagem:** Auditoria dos quase-identificadores e dos riscos de inferência por diferença, com demonstração de descarte em ambiente isolado. O catálogo dbt passou a documentar as views e as exposições dos consumidores, com publicação no GitHub Pages.
- **Painel público, agente e ADR 0008:** Publicação das cinco perguntas e de um agente em JavaScript sobre o JSON agregado. O benchmark da ADR 0008 registrou mediana de 64,838 ms para leitura do JSON e consultas P1–P5 em V8, além de paridade da P3 entre os caminhos avaliados.
- **Freshness e SLA:** Documentação da meta proposta de publicação validada em até 24 horas após a extração do mesmo lote. O intervalo entre a integração do snapshot à `main` e o commit de deploy foi de 18h 32min 57s. O prazo completo do lote permanece indeterminado até associar o evento de extração ao snapshot publicado.

## O que surpreendeu

- **Risco residual de inferência:** A auditoria registrou partições em que valores omitidos podem ser inferidos por diferença entre recortes. Os resultados ressaltaram a necessidade de avaliar os totais e dimensões publicados em conjunto.
- **Ausência de grupos na P2:** Na revisão do painel, meses sem grupos publicados para determinado filtro apareciam como zero. A correção passou a mantê-los sem valor e fora da média sazonal, preservando os zeros observados.
- **Views vazias em amostras pequenas:** Uma view de consumo pode ficar vazia quando todos os grupos são suprimidos. Os contratos foram ajustados para aceitar esse resultado.

## O que foi decidido

- **Disponibilizar consumo agregado:** Publicar as views protegidas em uma base isolada e gerar o JSON para o painel e o agente no Pages. O acesso ao detalhe permanece no ambiente interno.
- **Documentar limites e evidências de governança:** Registrar retenção, descarte demonstrado e risco residual de inferência em [Consumo e governança](../consumo-e-governanca.md).
- **Adotar JSON com camada semântica e Pages:** Formalizar a escolha e seus critérios de revisão na [ADR 0008](../adr/0008-disponibilizacao-camada-semantica-e-json-pages.md). Acompanhar o prazo de publicação por `run_id` e hash conforme [Freshness e SLA](../freshness-sla.md).
