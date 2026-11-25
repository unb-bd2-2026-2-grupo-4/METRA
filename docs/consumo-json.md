---
hide:
  - toc
---

# Painel Público e Agente Analítico (GitHub Pages)

Esta página consome diretamente o snapshot JSON público gerado pelo **ETL reverso**
(`docs/assets/dados/metra.json`) a partir das views agregadas `consumo.*` e da
camada semântica única (`metricas.yml`). Todo o processamento e as respostas do
agente ocorrem localmente no seu navegador, sem necessidade de backend ou chave de API.

!!! warning "Cobertura e regras de governança LGPD"
    Grupos com menos de 5 movimentações são omitidos. Medidas salariais com menos
    de 5 salários válidos não são divulgadas (`não divulgado`). Os totais dos
    grupos publicados podem ser parciais; ausência de grupo não significa zero.
    Não some coleções diferentes nem eixos demográficos entre si. A supressão
    isolada não comprova anonimização (ver [Consumo e governança](consumo-e-governanca.md)
    e [ADR-0008](adr/0008-disponibilizacao-camada-semantica-e-json-pages.md)).

<div id="metra-painel-app" class="metra-app" data-fonte="../assets/dados/metra.json">
  <p>Carregando painel público e agente analítico…</p>
</div>

<noscript>Ative o JavaScript para carregar o painel público, o agente e o resumo mensal.</noscript>

<details class="metra-raw-details">
  <summary>Explorar tabela bruta publicada (contrato JSON v1)</summary>

  <div id="consumo-json" data-fonte="../assets/dados/metra.json">
    <p id="consumo-status" role="status" aria-live="polite">Carregando dados publicados…</p>
    <p>
      <label for="consumo-colecao">Recorte</label>
      <select id="consumo-colecao" disabled>
        <option value="setores">Setores — P1, P2 e P4</option>
        <option value="geografia">Capital e interior — P3</option>
        <option value="perfis">Perfis demográficos — P5</option>
        <option value="calendario">Calendário e disponibilidade</option>
      </select>
      <label for="consumo-uf">UF</label>
      <select id="consumo-uf" disabled><option value="">Todas</option></select>
      <label for="consumo-competencia">Competência</label>
      <select id="consumo-competencia" disabled></select>
    </p>
    <p id="consumo-cobertura"></p>
    <div style="overflow-x: auto">
      <table id="consumo-tabela" hidden>
        <caption>Indicadores dos grupos publicados no recorte selecionado</caption>
        <thead></thead>
        <tbody></tbody>
      </table>
    </div>
  </div>
</details>

Os salários são nominais. As linhas de perfis representam um eixo demográfico por
vez, sem permitir cruzar eixos. O calendário distingue mês sem dados de zero
observado. Em P2, competências sem grupos publicados ficam sem valor na série
e fora do cálculo da média sazonal. A média usa apenas meses publicados em anos
com 12 competências observadas na origem, com contagem de anos por mês.
A comparação entre capitais e interior (P3) aceita UF e ano no agente.

Além de P1–P5, o agente responde perguntas livres de ranking, total e evolução,
como "Qual o maior salário?", "Quais os 3 setores que mais contrataram em GO?",
"Qual mês teve mais demissões em 2024?" ou "Evolução do saldo no DF". Ele
identifica a métrica e a dimensão pelo vocabulário da camada semântica, publicado
no próprio JSON ([como funciona](consumo-e-governanca.md#vocabulario-como-uma-pergunta-livre-chega-a-metrica)).
O salário individual não é publicado: rankings de salário usam a média de grupos
com pelo menos 5 salários válidos.

O arquivo é atualizado após revisão e merge do PR na `main` (detalhes em
[Consumo e governança](consumo-e-governanca.md#etl-reverso-json-publico)).
