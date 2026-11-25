/* Consumidor mínimo do contrato v2 (perfis anuais); o dashboard completo usa o mesmo JSON. */
(async () => {
  const raiz = document.getElementById("consumo-json");
  if (!raiz) return;
  const status = document.getElementById("consumo-status");
  const colecao = document.getElementById("consumo-colecao");
  const uf = document.getElementById("consumo-uf");
  const competencia = document.getElementById("consumo-competencia");
  const tabela = document.getElementById("consumo-tabela");
  const dimensoes = {
    setores: ["competencia", "sigla_uf", "codigo_secao"],
    geografia: ["competencia", "sigla_uf", "is_capital"],
    perfis: ["ano", "sigla_uf", "is_capital", "codigo_secao", "eixo", "codigo_categoria", "categoria"],
    calendario: ["competencia", "tem_dados"],
  };
  const rotulos = {
    competencia: "Competência", ano: "Ano", sigla_uf: "UF", codigo_secao: "Seção CNAE",
    is_capital: "Capital", eixo: "Eixo", codigo_categoria: "Código",
    categoria: "Categoria", tem_dados: "Há dados na origem",
  };
  const numero = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
  const moeda = new Intl.NumberFormat("pt-BR", { style: "currency", currency: "BRL" });
  try {
    const resposta = await fetch(new URL(raiz.dataset.fonte, document.baseURI));
    if (!resposta.ok) throw new Error(`HTTP ${resposta.status}`);
    const dados = await resposta.json();
    if (dados.versao_schema !== 2 || !dados.metricas ||
        !Object.keys(dimensoes).every((nome) => Array.isArray(dados[nome])) ||
        !dados.calendario.length) {
      throw new Error("Contrato JSON incompatível");
    }
    for (const sigla of dados.recorte.ufs) uf.add(new Option(sigla, sigla));
    for (const mes of dados.calendario) {
      competencia.add(new Option(mes.competencia.slice(0, 7), mes.competencia));
    }
    const observadas = dados.calendario.filter((mes) => mes.tem_dados);
    if (!observadas.length) throw new Error("Calendário sem dados");
    competencia.value = observadas.at(-1).competencia;
    document.getElementById("consumo-cobertura").textContent =
      `Competências com dados: ${observadas[0].competencia.slice(0, 7)} a ` +
      `${observadas.at(-1).competencia.slice(0, 7)}. ${dados.recorte.ressalva}`;

    function renderizar() {
      uf.disabled = colecao.value === "calendario";
      const metricas = colecao.value === "calendario" ? [] : Object.keys(dados.metricas);
      const colunas = [...dimensoes[colecao.value], ...metricas];
      // Perfis são anuais: a competência escolhida seleciona o ano dela.
      const linhas = dados[colecao.value].filter((linha) =>
        ("ano" in linha ? linha.ano === Number(competencia.value.slice(0, 4)) : linha.competencia === competencia.value) &&
        (uf.disabled || !uf.value || linha.sigla_uf === uf.value));
      const cabecalho = document.createElement("tr");
      for (const coluna of colunas) {
        const celula = document.createElement("th");
        celula.scope = "col";
        celula.textContent = rotulos[coluna] || dados.metricas[coluna].label;
        cabecalho.append(celula);
      }
      tabela.querySelector("thead").replaceChildren(cabecalho);
      const corpo = document.createDocumentFragment();
      for (const linha of linhas) {
        const tr = document.createElement("tr");
        for (const coluna of colunas) {
          const td = document.createElement("td");
          const valor = linha[coluna];
          const formato = dados.metricas[coluna]?.formato;
          if (valor === null) td.textContent = "não divulgado";
          else if (typeof valor === "boolean") td.textContent = valor ? "Sim" : "Não";
          else if (formato === "moeda") td.textContent = moeda.format(valor);
          else if (formato === "percentual") td.textContent = `${numero.format(valor)}%`;
          else td.textContent = typeof valor === "number" ? numero.format(valor) : valor;
          tr.append(td);
        }
        corpo.append(tr);
      }
      tabela.querySelector("tbody").replaceChildren(corpo);
      tabela.hidden = !linhas.length;
      const mes = dados.calendario.find((item) => item.competencia === competencia.value);
      status.textContent = linhas.length ? `${linhas.length} registro(s) publicado(s).` :
        (mes?.tem_dados ? "Nenhum grupo publicado neste recorte; ausência não significa zero." :
          "Competência sem dados na origem; não representa zero movimentações.");
    }
    colecao.disabled = uf.disabled = competencia.disabled = false;
    for (const seletor of [colecao, uf, competencia]) seletor.addEventListener("change", renderizar);
    renderizar();
  } catch (erro) {
    tabela.hidden = true;
    colecao.disabled = uf.disabled = competencia.disabled = true;
    status.textContent = "Resumo indisponível. Aguarde a geração e revisão do JSON público ou tente novamente mais tarde.";
    console.error("Falha ao carregar o resumo METRA:", erro);
  }
})();
