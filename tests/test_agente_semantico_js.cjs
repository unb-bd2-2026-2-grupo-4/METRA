// Consulta semântica do agente do Pages: métrica + operação + dimensão + filtros.
// O vocabulário vem do metra.json publicado (camada semântica); os dados são controlados.
// Executar na raiz: node --test tests/test_agente_semantico_js.cjs
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const agente = require("../docs/javascripts/metra-agente.js");

const publicado = JSON.parse(fs.readFileSync(path.join(__dirname, "../docs/assets/dados/metra.json"), "utf8"));

function linha(competencia, sigla_uf, extra, admissoes, desligamentos, salario, qtd) {
  return {
    competencia, sigla_uf, ...extra, admissoes, desligamentos, saldo: admissoes - desligamentos,
    salario_medio_admissao: salario, qtd_salarios_admissao: qtd,
    indice_fluxos_pareados_pct: (200 * Math.min(admissoes, desligamentos)) / (admissoes + desligamentos),
  };
}

function dados() {
  return {
    versao_schema: 1,
    recorte: publicado.recorte,
    metricas: publicado.metricas,
    dimensoes: publicado.dimensoes,
    setores: [
      linha("2024-01-01", "DF", { codigo_secao: "G" }, 20, 10, 2000, 20),
      linha("2024-02-01", "DF", { codigo_secao: "G" }, 15, 25, 3000, 10),
      linha("2024-01-01", "DF", { codigo_secao: "P" }, 8, 4, 6000, 8),
      linha("2024-01-01", "GO", { codigo_secao: "C" }, 30, 12, 2500, 30),
      // Seção não identificada: maior volume e salário, mas fora dos rankings por seção.
      linha("2024-01-01", "GO", { codigo_secao: "Z" }, 90, 1, 9000, 90),
      // Salário suprimido: entra nas contagens, não na média.
      linha("2025-01-01", "MT", { codigo_secao: "F" }, 6, 2, null, null),
    ],
    geografia: [
      linha("2024-01-01", "DF", { is_capital: true }, 28, 14, 2667, 28),
      linha("2024-02-01", "DF", { is_capital: true }, 15, 25, 3000, 10),
      linha("2024-01-01", "GO", { is_capital: true }, 60, 6, 6000, 60),
      linha("2024-01-01", "GO", { is_capital: false }, 60, 7, 4000, 60),
      linha("2025-01-01", "MT", { is_capital: false }, 6, 2, null, null),
    ],
    perfis: [],
    calendario: [
      { competencia: "2024-01-01", tem_dados: true },
      { competencia: "2024-02-01", tem_dados: true },
      { competencia: "2025-01-01", tem_dados: true },
    ],
  };
}

function responder(pergunta, base = dados()) {
  const r = agente.responderPergunta(base, pergunta);
  assert.equal(JSON.stringify(r).includes("NaN"), false, pergunta);
  return r;
}

test("'qual o maior salário?' responde a maior média por seção e explica o máximo individual", () => {
  const r = responder("qual o maior salário?");
  assert.equal(r.intencao, "consulta_semantica");
  // P: 6000 (n=8); G: (2000*20 + 3000*10) / 30 = 2333,33; C: 2500. Z fica fora; F não tem salário.
  assert.deepEqual(r.dadosAnalise.linhas.map((l) => l.chave), ["P", "C", "G"]);
  assert.equal(Math.round(r.dadosAnalise.linhas[2].salario_medio_admissao * 100), 233333);
  assert.match(r.resumoExecutivo, /^Maior salário médio de admissão por seção CNAE/);
  assert.match(r.resumoExecutivo, /P — Educação, com R\$ 6\.000,00 \(n = 8 salários\)/);
  assert.match(r.resumoExecutivo, /salário individual máximo ou mínimo não é publicado/);
});

test("'menor salário' inverte a ordem; sinônimos como 'paga' e 'piores' identificam a mesma métrica", () => {
  assert.equal(responder("qual o menor salário?").dadosAnalise.linhas[0].chave, "G");
  assert.equal(responder("qual setor tem os piores salários?").dadosAnalise.linhas[0].chave, "G");
  assert.equal(responder("qual setor paga mais?").dadosAnalise.linhas[0].chave, "P");
});

test("top N, filtros de UF e ano e dimensão citada na pergunta", () => {
  const top = responder("quais os 2 setores que mais contrataram no DF?");
  assert.equal(top.intencao, "consulta_semantica");
  assert.deepEqual(top.filtros, { sigla_uf: "DF" });
  assert.deepEqual(top.dadosAnalise.linhas.map((l) => [l.chave, l.admissoes]), [["G", 35], ["P", 8]]);
  assert.match(top.resumoExecutivo, /^Mais admissões por seção CNAE no recorte DF/);

  // Por UF, a coleção usada é a geografia: GO = 6 + 7 desligamentos.
  const uf = responder("qual UF mais demitiu em 2024?");
  assert.equal(uf.colecao, "geografia");
  assert.deepEqual(uf.dadosAnalise.linhas.map((l) => [l.chave, l.desligamentos]), [["DF", 39], ["GO", 13]]);

  // 2024-01: DF 14 + GO 6 + 7 = 27; 2024-02: 25; 2025-01: 2.
  const mes = responder("qual mês teve mais demissões?");
  assert.deepEqual(mes.dadosAnalise.linhas.map((l) => [l.rotulo, l.desligamentos]), [["2024-01", 27], ["2024-02", 25], ["2025-01", 2]]);
});

test("total e evolução no tempo", () => {
  const total = responder("quantas admissões houve em GO?");
  assert.equal(total.dadosAnalise.operacao.tipo, "total");
  assert.equal(total.dadosAnalise.linhas[0].admissoes, 120);
  assert.match(total.resumoExecutivo, /Admissões no recorte GO · 2023–2026: 120\./);

  const serie = responder("evolução do saldo no DF");
  assert.equal(serie.dadosAnalise.operacao.tipo, "serie");
  assert.deepEqual(serie.dadosAnalise.linhas.map((l) => [l.rotulo, l.saldo]), [["2024-01", 14], ["2024-02", -10]]);
  assert.equal(responder("saldo por mês no DF").dadosAnalise.operacao.tipo, "serie");
});

test("rotatividade com superlativo é ranking; a relação com salário continua na P4", () => {
  const ranking = responder("qual setor tem a maior rotatividade?");
  assert.equal(ranking.intencao, "consulta_semantica");
  assert.equal(ranking.dadosAnalise.metrica, "indice_fluxos_pareados_pct");
  assert.equal(responder("Os setores com maior rotatividade praticam salários médios mais baixos?").intencao, "p4_fluxos_salarios");
});

test("as perguntas oficiais P1–P5 e os bloqueios mantêm suas rotas", () => {
  const rotas = {
    "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?": "p1_setores_df",
    "Que setor mais contratou e demitiu no DF em 2024?": "p1_setores_df",
    "Existe sazonalidade evidente nas contratações e demissões?": "p2_sazonalidade",
    "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?": "p3_capitais_interior",
    "Qual a diferença salarial entre homens e mulheres?": "p5_perfil_remuneracao",
    "Listar CPF e salário de cada trabalhador": "bloqueada_seguranca",
    "qual o maior salário de cada trabalhador linha por linha?": "bloqueada_seguranca",
  };
  for (const [pergunta, intencao] of Object.entries(rotas)) {
    assert.equal(agente.classificarIntencao(pergunta, dados()), intencao, pergunta);
  }
});

test("o vocabulário vem da camada semântica: sem o sinônimo, a pergunta não é entendida", () => {
  assert.equal(responder("qual a maior remuneração?").intencao, "consulta_semantica");
  const semRemuneracao = dados();
  semRemuneracao.metricas = JSON.parse(JSON.stringify(publicado.metricas));
  const salario = semRemuneracao.metricas.salario_medio_admissao;
  salario.sinonimos = salario.sinonimos.filter((s) => !s.startsWith("remunera"));
  assert.notEqual(responder("qual a maior remuneração?", semRemuneracao).intencao, "consulta_semantica");

  // Snapshot antigo, sem vocabulário: o agente volta ao comportamento anterior, sem erro.
  const antigo = dados();
  delete antigo.dimensoes;
  assert.equal(responder("qual o maior salário?", antigo).intencao, "resumo_geral");
});

test("banco de perguntas sobre o snapshot publicado: todas respondidas, sem NaN", () => {
  const livres = [
    "qual o maior salário?", "qual o menor salário?", "qual setor paga o maior salário?",
    "qual setor paga mais em Goiás?", "qual o menor salário médio por UF?", "qual estado tem o maior salário médio?",
    "quais os 3 setores que mais contrataram em GO?", "top 5 setores com mais demissões em 2024",
    "qual mês teve mais demissões?", "qual ano teve o maior saldo?", "qual setor gerou mais empregos no DF?",
    "qual setor tem a maior rotatividade?", "quantas admissões houve em GO em 2025?",
    "qual o total de desligamentos no MT?", "evolução do saldo em MS", "saldo por mês no DF em 2024",
    "ranking de salários por setor", "onde se paga mais?", "qual UF mais demitiu em 2023?",
    "qual setor tem os piores salários?", "qual a maior remuneração no setor de saúde?",
  ];
  for (const pergunta of livres) {
    const r = responder(pergunta, publicado);
    assert.equal(r.intencao, "consulta_semantica", pergunta);
    assert.ok(r.dadosAnalise.linhas.length > 0, pergunta);
    assert.ok(r.resumoExecutivo.length > 30, pergunta);
  }
  const top3 = responder("quais os 3 setores que mais contrataram em GO?", publicado);
  assert.equal(top3.dadosAnalise.linhas.length, 3);
});
