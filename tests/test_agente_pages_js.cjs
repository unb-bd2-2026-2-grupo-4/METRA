const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");

const agente = require("../docs/javascripts/metra-agente.js");

function fixtureDados() {
  return {
    versao_schema: 1,
    recorte: {
      anos: [2023, 2024, 2025, 2026],
      ufs: ["DF", "GO", "MS", "MT"],
      ressalva: "Grupos < 5 omitidos.",
    },
    metricas: {
      admissoes: { label: "Admissões", formato: "inteiro" },
      desligamentos: { label: "Desligamentos", formato: "inteiro" },
      saldo: { label: "Saldo líquido", formato: "inteiro" },
      salario_medio_admissao: { label: "Salário médio", formato: "moeda" },
      qtd_salarios_admissao: { label: "Salários válidos", formato: "inteiro" },
      indice_fluxos_pareados_pct: { label: "Índice de fluxos", formato: "percentual" },
    },
    setores: [
      { competencia: "2023-01-01", sigla_uf: "DF", codigo_secao: "G", admissoes: 10, desligamentos: 5, saldo: 5, salario_medio_admissao: 3000, qtd_salarios_admissao: 10, indice_fluxos_pareados_pct: 66.67 },
      { competencia: "2023-02-01", sigla_uf: "DF", codigo_secao: "G", admissoes: 0, desligamentos: 5, saldo: -5, salario_medio_admissao: null, qtd_salarios_admissao: null, indice_fluxos_pareados_pct: 0 },
      { competencia: "2024-01-01", sigla_uf: "DF", codigo_secao: "G", admissoes: 20, desligamentos: 10, saldo: 10, salario_medio_admissao: 1500, qtd_salarios_admissao: 2, indice_fluxos_pareados_pct: 66.67 },
      { competencia: "2024-01-01", sigla_uf: "DF", codigo_secao: "C", admissoes: 12, desligamentos: 18, saldo: -6, salario_medio_admissao: 2000, qtd_salarios_admissao: 10, indice_fluxos_pareados_pct: 80.0 },
      { competencia: "2024-01-01", sigla_uf: "DF", codigo_secao: "P", admissoes: 8, desligamentos: 4, saldo: 4, salario_medio_admissao: 4000, qtd_salarios_admissao: 8, indice_fluxos_pareados_pct: 66.67 },
      { competencia: "2024-01-01", sigla_uf: "DF", codigo_secao: "Z", admissoes: 99, desligamentos: 1, saldo: 98, salario_medio_admissao: 9000, qtd_salarios_admissao: 99, indice_fluxos_pareados_pct: 2.0 },
      { competencia: "2024-02-01", sigla_uf: "GO", codigo_secao: "C", admissoes: 15, desligamentos: 10, saldo: 5, salario_medio_admissao: 2200, qtd_salarios_admissao: 12, indice_fluxos_pareados_pct: 80.0 },
      { competencia: "2026-01-01", sigla_uf: "DF", codigo_secao: "G", admissoes: 5, desligamentos: 2, saldo: 3, salario_medio_admissao: 2500, qtd_salarios_admissao: 5, indice_fluxos_pareados_pct: 57.14 },
    ],
    geografia: [
      { competencia: "2023-01-01", sigla_uf: "DF", is_capital: true, admissoes: 100, desligamentos: 80, saldo: 20, salario_medio_admissao: 3000, qtd_salarios_admissao: 100, indice_fluxos_pareados_pct: 88.89 },
      { competencia: "2023-01-01", sigla_uf: "GO", is_capital: true, admissoes: 50, desligamentos: 40, saldo: 10, salario_medio_admissao: 2500, qtd_salarios_admissao: 50, indice_fluxos_pareados_pct: 88.89 },
      { competencia: "2023-01-01", sigla_uf: "GO", is_capital: false, admissoes: 80, desligamentos: 60, saldo: 20, salario_medio_admissao: 2000, qtd_salarios_admissao: 80, indice_fluxos_pareados_pct: 85.71 },
    ],
    perfis: [
      { competencia: "2024-01-01", sigla_uf: "DF", is_capital: true, codigo_secao: "G", eixo: "sexo", codigo_categoria: 1, categoria: "Homem", admissoes: 10, desligamentos: 5, saldo: 5, salario_medio_admissao: 3000, qtd_salarios_admissao: 10, indice_fluxos_pareados_pct: 66.67 },
      { competencia: "2024-01-01", sigla_uf: "DF", is_capital: true, codigo_secao: "G", eixo: "sexo", codigo_categoria: 3, categoria: "Mulher", admissoes: 10, desligamentos: 6, saldo: 4, salario_medio_admissao: 2400, qtd_salarios_admissao: 10, indice_fluxos_pareados_pct: 75.0 },
      { competencia: "2024-01-01", sigla_uf: "DF", is_capital: true, codigo_secao: "G", eixo: "raca_cor", codigo_categoria: 1, categoria: "Branca", admissoes: 12, desligamentos: 8, saldo: 4, salario_medio_admissao: 2800, qtd_salarios_admissao: 12, indice_fluxos_pareados_pct: 80.0 },
    ],
    calendario: [
      ...Array.from({ length: 12 }, (_, i) => ({ competencia: `2023-${String(i + 1).padStart(2, "0")}-01`, tem_dados: true })),
      { competencia: "2024-01-01", tem_dados: true },
      { competencia: "2024-02-01", tem_dados: true },
      { competencia: "2024-03-01", tem_dados: false },
      { competencia: "2026-01-01", tem_dados: true },
    ],
  };
}

test("normalização e matching de palavras inteiras evitam falsos positivos", () => {
  const norm = agente.normalizarTexto("Ação do coração em áreas rurais no DF em 2024");
  assert.equal(agente.contemTermo(norm, ["cor", "rais"]), false);
  assert.equal(agente.contemTermo(norm, ["rurais", "df"]), true);
  assert.deepEqual(agente.extrairFiltros("Setor de educação em Goiânia em 2025"), {
    sigla_uf: "GO",
    ano: 2025,
    codigo_secao: "P",
  });
});

test("média ponderada nunca faz média simples e preserva nulo", () => {
  const agg = agente.agregarRegistros([
    { admissoes: 10, desligamentos: 0, saldo: 10, salario_medio_admissao: 3000, qtd_salarios_admissao: 10 },
    { admissoes: 2, desligamentos: 3, saldo: -1, salario_medio_admissao: 1500, qtd_salarios_admissao: 2 },
    { admissoes: 0, desligamentos: 5, saldo: -5, salario_medio_admissao: null, qtd_salarios_admissao: null },
  ]);
  assert.equal(agg.admissoes, 12);
  assert.equal(agg.qtd_salarios_admissao, 12);
  assert.equal(agg.salario_medio_admissao, (3000 * 10 + 1500 * 2) / 12);
  assert.notEqual(agg.salario_medio_admissao, (3000 + 1500) / 2);

  const semSalario = agente.agregarRegistros([
    { admissoes: 0, desligamentos: 5, saldo: -5, salario_medio_admissao: null, qtd_salarios_admissao: null },
  ]);
  assert.equal(semSalario.salario_medio_admissao, null);
  assert.equal(semSalario.qtd_salarios_admissao, 0);
});

test("P1 exclui seção Z, respeita janela 12 meses e calcula dense_rank independente", () => {
  const p1 = agente.calcularP1(fixtureDados(), { sigla_uf: "DF", ano: 2024 });
  assert.equal(p1.linhas.some((l) => l.codigo_secao === "Z"), false);
  assert.deepEqual(p1.linhas.map((l) => l.codigo_secao), ["G", "C", "P"]);
  assert.equal(p1.linhas[0].ranking_admissoes, 1);
  assert.equal(p1.linhas[1].ranking_desligamentos, 1);
  const resposta = agente.responderPergunta(fixtureDados(), "Que setor mais contratou e demitiu no DF em 2024?");
  assert.match(resposta.resumoExecutivo, /liderança em admissões: G/);
  assert.match(resposta.resumoExecutivo, /liderança em desligamentos: C/i);

  const p1Janela = agente.calcularP1(fixtureDados(), {});
  assert.equal(p1Janela.inicio, "2025-02-01");
  assert.equal(p1Janela.fim, "2026-01-01");
  assert.equal(p1Janela.competenciasDisponiveis, 1);
});

test("P2 distingue meses sem dados, grupos omitidos e zeros observados na média sazonal", () => {
  const p2 = agente.calcularP2(fixtureDados(), { sigla_uf: "DF" });
  const mar24 = p2.serie.find((s) => s.competencia === "2024-03-01");
  assert.equal(mar24.tem_dados, false);
  assert.equal(mar24.admissoes, null);
  const fev24 = p2.serie.find((s) => s.competencia === "2024-02-01");
  assert.equal(fev24.tem_dados, true);
  assert.equal(fev24.admissoes, null);
  assert.deepEqual(p2.anosCompletos, [2023]);
  const jan = p2.resumoMensal.find((m) => m.mes === 1);
  assert.equal(jan.anos_considerados, 1);
  assert.equal(jan.media_admissoes_mes, 10);
  assert.equal(p2.resumoMensal[1].media_admissoes_mes, 0);
  assert.equal(p2.resumoMensal[1].anos_considerados, 1);
  assert.equal(p2.resumoMensal[2].media_admissoes_mes, null);
  assert.equal(p2.resumoMensal[2].anos_considerados, 0);
});

test("P2 sem grupos publicados não anuncia um pico nem preenche a série", () => {
  const dados = fixtureDados();
  const r = agente.responderPergunta(dados, "Existe sazonalidade no DF em 2023 na seção U?");
  assert.match(r.resumoExecutivo, /Nenhum grupo mensal publicado/);
  assert.ok(r.dadosAnalise.serie.every((mes) => mes.tem_dados && mes.admissoes === null));
  assert.ok(r.dadosAnalise.resumoMensal.every((mes) => mes.media_admissoes_mes === null));
  assert.equal(agente.calcularKpisRecorte(dados, { codigo_secao: "U" }).saldo, null);
});

test("P3 mantém interior do DF nulo e compara GO capital vs interior", () => {
  const p3Df = agente.calcularP3(fixtureDados(), { sigla_uf: "DF" });
  assert.equal(p3Df.consolidado.salario_interior, null);
  assert.equal(p3Df.consolidado.n_interior, 0);
  assert.equal(p3Df.consolidado.diferenca_saldo, null);

  const p3Go = agente.calcularP3(fixtureDados(), { sigla_uf: "GO" });
  assert.equal(p3Go.consolidado.saldo_capital, 10);
  assert.equal(p3Go.consolidado.saldo_interior, 20);
  assert.equal(p3Go.consolidado.diferenca_salario, 500);
});

test("o agente recusa seção em P3 e nomes ou siglas fora da cobertura", () => {
  const dados = fixtureDados();
  const perguntaP3 = "Qual o saldo em capitais e no interior?";
  for (const r of [
    agente.responderPergunta(dados, "Qual o saldo em capitais e no interior na seção P?"),
    agente.responderPergunta(dados, perguntaP3, { codigo_secao: "P" }),
  ]) {
    assert.equal(r.suportada, false);
    assert.match(r.motivoRecusa, /não tem seção CNAE/);
    assert.equal(r.dadosAnalise, undefined);
  }
  for (const local of ["São Paulo", "SP", "sp", "Pará", "Recife"]) {
    const r = agente.responderPergunta(dados, `Qual o saldo em ${local} em 2025?`);
    assert.equal(r.suportada, false, local);
    assert.match(r.tituloIntencao, /geográfico/i);
  }
  for (const pergunta of ["Qual o saldo para Goiás?", "Qual o saldo em Mato Grosso do Sul?", "Qual a sazonalidade no Natal?"]) {
    assert.equal(agente.responderPergunta(dados, pergunta).suportada, true, pergunta);
  }
});

test("P4 e P5 calculam correlação, quadrantes, eixo único e diferença Homem - Mulher", () => {
  const p4 = agente.calcularP4(fixtureDados(), {});
  assert.equal(p4.paresValidos, 3);
  assert.ok(typeof p4.correlacaoPearson === "number");

  const p5 = agente.calcularP5(fixtureDados(), { eixo: "sexo" });
  assert.equal(p5.linhas.length, 2);
  assert.equal(p5.resumoSexo.diferenca_reais, 600);
});

test("guardrails bloqueiam SQL injection, LGPD, ataque por diferença, fora de escopo e CBO", () => {
  const d = fixtureDados();
  for (const q of [
    "DROP TABLE gold.fct_movimentacao;",
    "SELECT * FROM gold.fct_movimentacao",
    "SELECT count(*) FROM read_parquet('a.parquet')",
    "Listar CPF e salário de cada trabalhador",
    "Cruzar sexo e raca para inferir suprimidos",
  ]) {
    const r = agente.responderPergunta(d, q);
    assert.equal(r.suportada, false, q);
    assert.equal(r.intencao, "bloqueada_seguranca", q);
  }

  for (const q of ["Qual a taxa de desemprego (PNAD)?", "Qual o estoque de vínculos na RAIS?", "Previsão para 2027"]) {
    const r = agente.responderPergunta(d, q);
    assert.equal(r.suportada, false, q);
    assert.equal(r.intencao, "nao_suportada", q);
  }

  const rProf = agente.responderPergunta(d, "Qual a diferença salarial entre homens e mulheres para professor no DF?");
  assert.equal(rProf.suportada, false);
  assert.equal(rProf.intencao, "cbo_restrito_lgpd");
  assert.equal(rProf.sugestaoCnae.codigo_secao, "P");
  assert.ok(rProf.sugestaoCnae.perguntaSugerida.includes("secao P"));
});

test("snapshot real docs/assets/dados/metra.json responde P1-P5 sem NaN e concilia KPIs", () => {
  const caminho = path.join(__dirname, "../docs/assets/dados/metra.json");
  const dados = JSON.parse(fs.readFileSync(caminho, "utf8"));
  const kpis = agente.calcularKpisRecorte(dados, {});
  assert.equal(kpis.admissoes, 25325);
  assert.equal(kpis.saldo, 1472);

  const perguntas = [
    "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?",
    "Existe sazonalidade evidente nas contratações e demissões?",
    "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?",
    "Os setores com maior rotatividade praticam salários médios mais baixos?",
    "Como a escolaridade impacta o salário médio de admissão?",
  ];
  for (const pergunta of perguntas) {
    const resp = agente.responderPergunta(dados, pergunta);
    assert.equal(resp.suportada, true, pergunta);
    assert.ok(resp.resumoExecutivo.length > 20, pergunta);
    assert.equal(JSON.stringify(resp).includes("NaN"), false, pergunta);
  }
});
