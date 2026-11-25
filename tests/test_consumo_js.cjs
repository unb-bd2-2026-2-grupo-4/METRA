// DOM mínimo: testa o consumidor sem navegador, backend ou dependências novas.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const script = fs.readFileSync(path.join(__dirname, "../docs/javascripts/consumo.js"), "utf8");

class Elemento {
  constructor() {
    this.children = [];
    this.value = "";
    this.textContent = "";
    this.disabled = true;
    this.hidden = true;
    this.events = {};
  }
  append(child) { this.children.push(child); }
  replaceChildren(...children) { this.children = children; }
  add(option) { this.append(option); }
  addEventListener(name, callback) { this.events[name] = callback; }
}

function fixture() {
  const linha = { competencia: "2025-01-01", sigla_uf: "GO", codigo_secao: "A",
    admissoes: 5, salario_medio_admissao: null, indice_fluxos_pareados_pct: 80 };
  return {
    versao_schema: 2,
    recorte: { ufs: ["DF", "GO"], ressalva: "Totais parciais." },
    metricas: {
      admissoes: { label: "Admissões", formato: "inteiro" },
      salario_medio_admissao: { label: "Salário médio", formato: "moeda" },
      indice_fluxos_pareados_pct: { label: "Índice", formato: "percentual" },
    },
    setores: [linha, { ...linha, sigla_uf: "DF", salario_medio_admissao: 2000 }],
    geografia: [],
    // Perfis anuais (v2): sem competência; a competência escolhida seleciona o ano.
    perfis: [{ ...linha, competencia: undefined, ano: 2025, is_capital: true, eixo: "sexo", codigo_categoria: 1,
      categoria: "<img src=x onerror=alert(1)>" }],
    calendario: [{ competencia: "2025-01-01", tem_dados: true },
      { competencia: "2025-02-01", tem_dados: false }],
  };
}

async function carregar(dados = fixture(), httpOk = true) {
  const ids = ["json", "status", "colecao", "uf", "competencia", "tabela", "cobertura"];
  const elementos = Object.fromEntries(ids.map((id) => [`consumo-${id}`, new Elemento()]));
  elementos["consumo-json"].dataset = { fonte: "../assets/dados/metra.json" };
  elementos["consumo-colecao"].value = "setores";
  const head = new Elemento();
  const body = new Elemento();
  elementos["consumo-tabela"].querySelector = (nome) => nome === "thead" ? head : body;
  let url;
  await vm.runInNewContext(script, {
    document: {
      baseURI: "https://exemplo.github.io/ProjetoIntegrado/consumo-json/",
      getElementById: (id) => elementos[id],
      createElement: () => new Elemento(),
      createDocumentFragment: () => new Elemento(),
    },
    Option: class extends Elemento { constructor(texto, valor) { super(); this.textContent = texto; this.value = valor; } },
    Intl, URL, console: { error() {} },
    fetch: async (destino) => { url = destino.href; return { ok: httpOk, status: 404, json: async () => dados }; },
  });
  const linhas = () => body.children[0]?.children.map((tr) => tr.children.map((td) => td.textContent)) || [];
  const selecionar = (id, valor) => {
    elementos[`consumo-${id}`].value = valor;
    elementos[`consumo-${id}`].events.change();
  };
  return { elementos, url, linhas, selecionar };
}

test("URL respeita subdiretório; nulo não vira zero e índice mantém escala", async () => {
  const pagina = await carregar();
  assert.equal(pagina.url, "https://exemplo.github.io/ProjetoIntegrado/assets/dados/metra.json");
  assert.equal(pagina.linhas().length, 2);
  assert.ok(pagina.linhas()[0].includes("não divulgado"));
  assert.ok(pagina.linhas()[0].includes("80%"));
  assert.match(pagina.linhas()[1].find((v) => String(v).includes("R$")), /2\.000,00/);
  assert.match(pagina.elementos["consumo-cobertura"].textContent, /Totais parciais/);
});

test("filtros distinguem grupo não publicado de mês sem dados", async () => {
  const pagina = await carregar();
  pagina.selecionar("uf", "GO");
  assert.equal(pagina.linhas().length, 1);
  pagina.selecionar("colecao", "geografia");
  assert.match(pagina.elementos["consumo-status"].textContent, /ausência não significa zero/);
  pagina.selecionar("competencia", "2025-02-01");
  assert.match(pagina.elementos["consumo-status"].textContent, /sem dados na origem/);
  assert.equal(pagina.elementos["consumo-tabela"].hidden, true);
});

test("calendário ignora UF e rótulos demográficos permanecem texto", async () => {
  const pagina = await carregar();
  pagina.selecionar("colecao", "calendario");
  assert.equal(pagina.elementos["consumo-uf"].disabled, true);
  assert.equal(pagina.linhas()[0][1], "Sim");
  pagina.selecionar("colecao", "perfis");
  assert.equal(pagina.elementos["consumo-uf"].disabled, false);
  assert.ok(pagina.linhas()[0].includes("<img src=x onerror=alert(1)>"));
});

test("arquivo ausente ou contrato incompatível mantém controles desabilitados", async () => {
  for (const [dados, ok] of [[fixture(), false], [{ ...fixture(), versao_schema: 1 }, true]]) {
    const pagina = await carregar(dados, ok);
    assert.match(pagina.elementos["consumo-status"].textContent, /indisponível/);
    assert.equal(pagina.elementos["consumo-colecao"].disabled, true);
    assert.equal(pagina.elementos["consumo-tabela"].hidden, true);
  }
});
