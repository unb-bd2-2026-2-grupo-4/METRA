# Resumo mensal publicado

Este resumo lê o JSON gerado pelo ETL reverso. Ele permite identificar setores e
recortes com contratação, saldo e remuneração para apoiar o acompanhamento do
mercado de trabalho. O dashboard completo e o agente serão integrados por Arthur.

!!! warning "Cobertura dos resultados"
    Grupos com menos de 5 movimentações são omitidos. Medidas salariais com menos
    de 5 salários válidos não são divulgadas. Os totais dos grupos publicados
    podem ser parciais; ausência de grupo não significa zero. Não some coleções
    diferentes nem eixos demográficos entre si. A supressão isolada não comprova
    anonimização.

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

<noscript>Ative o JavaScript para carregar o resumo mensal.</noscript>

Os salários são nominais. As linhas de perfis representam um eixo demográfico por
vez, sem permitir cruzar eixos. A tabela apenas exibe os registros publicados;
não recalcula médias ou respostas P1–P5. O calendário distingue mês sem dados de
zero observado; um mês com dados pode ter todos os seus grupos suprimidos.

O arquivo é publicado após revisão e merge do PR, e não a cada execução local do
Dagster. O procedimento de atualização e o contrato para o dashboard estão em
[Consumo e governança](consumo-e-governanca.md#etl-reverso-json-publico).
