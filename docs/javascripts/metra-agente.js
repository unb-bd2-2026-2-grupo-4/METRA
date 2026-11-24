/* Agente analítico e calculador sobre o snapshot público `metra.json` (ADR-0008).
 *
 * Porta para JavaScript a lógica de classificação, extração de filtros e guardrails
 * de `src/app/text_to_sql.py` (ADR-0007), executando exclusivamente no navegador
 * sobre as coleções agregadas com supressão (k >= 5) geradas pelo ETL reverso.
 *
 * Regras estritas:
 * - Nunca soma coleções diferentes (`setores`, `geografia`, `perfis`) entre si.
 * - Nunca cruza ou soma eixos demográficos diferentes (`sexo`, `raca_cor`, `escolaridade`, `faixa_etaria`).
 * - Sempre recompõe médias salariais de forma ponderada pela quantidade válida (`qtd_salarios_admissao`).
 * - Nunca converte `null` (suprimido) ou ausência de grupo em `0`, e nunca infere grupos suprimidos.
 */
(function (root, factory) {
  if (typeof module === "object" && module.exports) {
    module.exports = factory();
  } else {
    root.MetraAgente = factory();
  }
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  "use strict";

  const SECOES_CNAE = {
    A: "Agricultura, pecuária, produção florestal, pesca e aquicultura",
    B: "Indústrias extrativas",
    C: "Indústrias de transformação",
    D: "Eletricidade e gás",
    E: "Água, esgoto, atividades de gestão de resíduos e descontaminação",
    F: "Construção",
    G: "Comércio; reparação de veículos automotores e motocicletas",
    H: "Transporte, armazenagem e correio",
    I: "Alojamento e alimentação",
    J: "Informação e comunicação",
    K: "Atividades financeiras, de seguros e serviços relacionados",
    L: "Atividades imobiliárias",
    M: "Atividades profissionais, científicas e técnicas",
    N: "Atividades administrativas e serviços complementares",
    O: "Administração pública, defesa e seguridade social",
    P: "Educação",
    Q: "Saúde humana e serviços sociais",
    R: "Artes, cultura, esporte e recreação",
    S: "Outras atividades de serviços",
    T: "Serviços domésticos",
    U: "Organismos internacionais e outras instituições extraterritoriais",
    Z: "Atividades não identificadas ou não especificadas",
  };

  const NOMES_MESES = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
  };

  const EIXOS_DEMOGRAFICOS = {
    sexo: "Sexo",
    escolaridade: "Escolaridade",
    raca_cor: "Raça/Cor",
    faixa_etaria: "Faixa Etária",
  };

  const UFS_VALIDAS = ["DF", "GO", "MS", "MT"];
  const ANOS_VALIDOS = [2023, 2024, 2025, 2026];

  const TERMOS_SETORIAIS = [
    ["A", ["agro", "agropecuaria", "agricultura", "pecuaria", "florestal", "pesca"]],
    ["B", ["extrativa", "extrativas", "mineracao"]],
    ["C", ["industria", "industrias", "industria de transformacao", "manufatura", "fabrica"]],
    ["D", ["eletricidade", "energia eletrica", "gas"]],
    ["E", ["saneamento", "agua e esgoto", "residuos"]],
    ["F", ["construcao", "construcao civil", "obras"]],
    ["G", ["comercio", "varejo", "atacado", "supermercado", "loja", "lojas"]],
    ["H", ["transporte", "transportes", "logistica", "armazenagem", "correio"]],
    ["I", ["alojamento", "alimentacao", "hotelaria", "restaurante", "restaurantes", "turismo"]],
    ["J", ["tecnologia", "informacao e comunicacao", "ti", "software", "telecomunicacoes"]],
    ["K", ["financeiro", "financeiras", "banco", "bancos", "seguros"]],
    ["L", ["imobiliaria", "imobiliarias", "imoveis"]],
    ["M", ["cientificas", "consultoria", "engenharia", "juridicas", "contabilidade"]],
    ["N", ["servicos complementares", "terceirizacao", "atividades administrativas"]],
    ["O", ["administracao publica", "setor publico", "seguridade social", "governo"]],
    ["P", ["educacao", "ensino", "escolas", "universidades"]],
    ["Q", ["saude", "hospital", "hospitais", "servicos sociais", "clinicas"]],
    ["R", ["artes", "cultura", "esporte", "recreacao"]],
    ["S", ["outras atividades de servicos"]],
    ["T", ["servicos domesticos"]],
  ];

  const GATILHOS_OCUPACAO = [
    "ocupacao", "ocupacoes", "cargo", "cargos", "profissao", "profissoes", "cbo",
    "programador", "desenvolvedor", "engenheiro", "arquiteto", "medico", "medica",
    "enfermeiro", "enfermeira", "tecnico de enfermagem", "dentista", "farmaceutico",
    "psicologo", "nutricionista", "fisioterapeuta", "veterinario", "biomedico",
    "motorista", "caminhoneiro", "carreteiro", "pedreiro", "servente", "carpinteiro",
    "pintor", "vendedor", "vendedora", "balconista", "operador de caixa",
    "caixa de supermercado", "telemarketing", "call center", "professor", "professora",
    "professores", "docente", "advogado", "contador", "administrador", "gerente",
    "diretor", "faxineiro", "auxiliar de limpeza", "vigilante", "porteiro", "cozinheiro",
    "garcom", "trabalhador rural", "trabalhadores rurais", "rurais", "tratorista",
    "boia fria", "agronomo", "eletricista", "mecanico", "soldador", "almoxarife",
    "estoquista", "repositor", "auxiliar administrativo", "assistente administrativo",
    "auxiliar de escritorio", "recepcionista", "secretaria", "acougueiro", "padeiro",
    "motoboy", "cabeleireiro", "cuidador", "jornalista", "designer",
    "cientista de dados", "analista de dados", "analista de sistemas",
  ];

  const SUGESTAO_CNAE_POR_CARGO = [
    [["professor", "professora", "professores", "docente"], "P"],
    [["medico", "medica", "enfermeiro", "enfermeira", "tecnico de enfermagem", "dentista", "farmaceutico", "psicologo", "nutricionista", "fisioterapeuta", "biomedico", "cuidador"], "Q"],
    [["programador", "desenvolvedor", "cientista de dados", "analista de dados", "analista de sistemas", "designer", "jornalista"], "J"],
    [["pedreiro", "servente", "carpinteiro", "pintor", "eletricista", "engenheiro", "arquiteto"], "F"],
    [["vendedor", "vendedora", "balconista", "operador de caixa", "caixa de supermercado", "estoquista", "repositor", "acougueiro"], "G"],
    [["motorista", "caminhoneiro", "carreteiro", "motoboy", "almoxarife"], "H"],
    [["cozinheiro", "garcom", "padeiro"], "I"],
    [["trabalhador rural", "trabalhadores rurais", "rurais", "tratorista", "boia fria", "agronomo", "veterinario"], "A"],
    [["advogado", "contador"], "M"],
    [["telemarketing", "call center", "vigilante", "porteiro", "faxineiro", "auxiliar de limpeza", "auxiliar administrativo", "assistente administrativo", "auxiliar de escritorio", "recepcionista", "secretaria"], "N"],
    [["mecanico", "soldador"], "C"],
  ];

  function normalizarTexto(texto) {
    return String(texto || "")
      .toLowerCase()
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/[^a-z0-9\s]/g, " ")
      .replace(/\s+/g, " ")
      .trim();
  }

  function escaparRegex(texto) {
    return texto.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  }

  function contemTermo(textoNorm, termos) {
    if (!textoNorm) return false;
    const tokens = new Set(textoNorm.split(" "));
    for (const raw of termos) {
      const t = raw.trim();
      if (!t) continue;
      if (!t.includes(" ")) {
        if (tokens.has(t)) return true;
      } else {
        const re = new RegExp(`\\b${escaparRegex(t)}\\b`);
        if (re.test(textoNorm)) return true;
      }
    }
    return false;
  }

  function sugerirCnaeParaCargo(norm) {
    for (const [termos, secao] of SUGESTAO_CNAE_POR_CARGO) {
      if (contemTermo(norm, termos)) {
        return secao;
      }
    }
    return null;
  }

  function parseCompetencia(comp) {
    const [anoStr, mesStr] = String(comp).split("-");
    return { ano: Number(anoStr), mes: Number(mesStr) };
  }

  function subtrairMesesCompetencia(comp, meses) {
    const { ano, mes } = parseCompetencia(comp);
    const total = ano * 12 + (mes - 1) - meses;
    const novoAno = Math.floor(total / 12);
    const novoMes = (total % 12) + 1;
    return `${String(novoAno).padStart(4, "0")}-${String(novoMes).padStart(2, "0")}-01`;
  }

  function extrairFiltros(pergunta) {
    const norm = normalizarTexto(pergunta);
    const filtros = {};

    if (contemTermo(norm, ["distrito federal", "brasilia", "df"])) {
      filtros.sigla_uf = "DF";
    } else if (contemTermo(norm, ["goias", "goiania", "go"])) {
      filtros.sigla_uf = "GO";
    } else if (contemTermo(norm, ["mato grosso do sul", "campo grande", "ms"])) {
      filtros.sigla_uf = "MS";
    } else if (contemTermo(norm, ["mato grosso", "cuiaba", "mt"])) {
      filtros.sigla_uf = "MT";
    }

    const anos = Array.from(norm.matchAll(/\b(202[3-6])\b/g), (m) => Number(m[1]));
    const anosUnicos = Array.from(new Set(anos));
    if (anosUnicos.length === 1) {
      filtros.ano = anosUnicos[0];
    }

    const matchSecao = norm.match(/\b(?:secao|cnae)\s+([a-uz])\b/);
    if (matchSecao && SECOES_CNAE[matchSecao[1].toUpperCase()]) {
      filtros.codigo_secao = matchSecao[1].toUpperCase();
    } else {
      for (const [codigo, termos] of TERMOS_SETORIAIS) {
        if (contemTermo(norm, termos)) {
          filtros.codigo_secao = codigo;
          break;
        }
      }
    }

    if (contemTermo(norm, ["sexo", "genero", "homem", "mulher", "homens", "mulheres", "feminino", "masculino"])) {
      filtros.eixo = "sexo";
    } else if (
      contemTermo(norm, [
        "raca", "racas", "raca cor", "por cor", "cor ou raca",
        "branca", "preta", "parda", "indigena", "amarela", "negros", "negras", "pardos", "pardas",
      ])
    ) {
      filtros.eixo = "raca_cor";
    } else if (
      contemTermo(norm, [
        "escolaridade", "instrucao", "ensino", "superior", "fundamental",
        "ensino medio", "medio completo", "medio incompleto", "pos graduacao",
        "mestrado", "doutorado", "analfabeto", "estudo", "graduacao", "superior completo",
      ])
    ) {
      filtros.eixo = "escolaridade";
    } else if (contemTermo(norm, ["idade", "faixa etaria", "etaria", "jovens", "idosos", "anos de idade"])) {
      filtros.eixo = "faixa_etaria";
    }

    if (contemTermo(norm, ["mensal", "mes a mes"])) {
      filtros.nivel = "mensal";
    } else if (contemTermo(norm, ["anual", "por ano"])) {
      filtros.nivel = "anual";
    } else if (contemTermo(norm, ["total", "consolidado", "acumulado"])) {
      filtros.nivel = "total";
    }

    return filtros;
  }

  function detectarBloqueioOuForaEscopo(pergunta) {
    const bruto = String(pergunta || "").trim();
    const brutoLower = bruto.toLowerCase();
    const norm = normalizarTexto(bruto);

    const padroesAtaque = [
      /\b(drop|delete|insert|update|alter|truncate|attach|copy|pragma|install|load)\b/,
      /\b(read_csv|read_parquet|read_json|delta_scan|postgres_scan|read_text|read_blob)\b/,
      /;\s*(select|drop|delete|insert|update)/,
      /\bselect\s+(?:distinct\s+)?(?:[a-z_][a-z0-9_]*\.)?\*\s+from\b/,
      /\b(?:from|join)\s+'[^']*'/,
    ];
    for (const padrao of padroesAtaque) {
      if (padrao.test(brutoLower)) {
        return {
          intencao: "bloqueada_seguranca",
          titulo: "Bloqueio de Segurança / Governança",
          motivo:
            "Operação bloqueada pelos guardrails de segurança (ADR-0007 / ADR-0008): comandos SQL, " +
            "alteração de esquema, múltiplas instruções, 'SELECT *' ou leitura direta de arquivos não são executados no navegador.",
        };
      }
    }

    if (/^(?:select|with)\b/.test(brutoLower)) {
      return {
        intencao: "bloqueada_seguranca",
        titulo: "Bloqueio de Segurança / Governança",
        motivo:
          "Consultas SQL literais são bloqueadas no canal público estático: formule a pergunta em linguagem natural sobre as métricas publicadas.",
      };
    }

    if (
      contemTermo(norm, [
        "cpf", "rg", "pis", "pasep", "ctps",
        "nome do trabalhador", "dados individuais", "registro individual", "registros individuais",
        "listar trabalhadores", "lista de pessoas", "microdado bruto", "microdados brutos",
        "sem agrupar", "linha por linha", "cada trabalhador",
      ])
    ) {
      return {
        intencao: "bloqueada_seguranca",
        titulo: "Bloqueio de Segurança / Governança (LGPD)",
        motivo:
          "Consulta recusada por governança e privacidade (LGPD): o snapshot público `metra.json` expõe apenas indicadores " +
          "agregados com supressão de pequenos grupos (k >= 5), vedando listagens individuais.",
      };
    }

    if (
      contemTermo(norm, [
        "inferir suprimidos", "ataque por diferenca", "cruzar sexo e raca",
        "combinar raca e idade", "somar colecoes", "cruzar eixos",
      ]) ||
      /\b(homens?|mulheres?)\b.*\b(pard[oa]s?|pret[oa]s?|branc[oa]s?|negr[oa]s?|indigenas?|amarel[oa]s?|escolaridade|doutorado|mestrado|ensino medio)\b/.test(norm) ||
      /\b(pard[oa]s?|pret[oa]s?|branc[oa]s?|negr[oa]s?|indigenas?|amarel[oa]s?)\b.*\b(homens?|mulheres?)\b/.test(norm)
    ) {
      return {
        intencao: "bloqueada_seguranca",
        titulo: "Bloqueio de Governança Estatística",
        motivo:
          "Consulta bloqueada: o contrato público proíbe cruzar dois eixos demográficos ao mesmo tempo, somar coleções " +
          "distintas ou inferir grupos suprimidos (k < 5) por subtração entre totais.",
      };
    }

    if (
      contemTermo(norm, [
        "taxa de desemprego", "pnad", "pnadc",
        "estoque total de empregados", "estoque de vinculos", "estoque total de vinculos",
        "rais", "previsao para 2027", "previsao para 2028", "prever salario",
        "probabilidade de eu ser contratado", "chance individual de recolocacao",
        "efeito causal", "inflacao ipca",
      ])
    ) {
      return {
        intencao: "nao_suportada",
        titulo: "Consulta Fora do Escopo do Catálogo",
        motivo:
          "Pergunta fora do escopo metodológico do METRA: o Novo CAGED registra fluxos mensais (admissões e desligamentos), " +
          "não fornecendo estoque total de vínculos (RAIS), taxa de desemprego (PNAD), previsões futuras ou chance individual de recolocação.",
      };
    }

    const matchCboCodigo = norm.match(/\bcbo\s*(\d{4}\s*\d{2})\b/);
    if (matchCboCodigo || contemTermo(norm, GATILHOS_OCUPACAO)) {
      const secaoSugerida = sugerirCnaeParaCargo(norm);
      const filtrosBase = extrairFiltros(pergunta);
      const complementoUf = filtrosBase.sigla_uf ? ` em ${filtrosBase.sigla_uf}` : "";
      const complementoAno = filtrosBase.ano ? ` em ${filtrosBase.ano}` : "";
      let perguntaSugerida = null;
      if (secaoSugerida) {
        if (filtrosBase.eixo === "sexo") {
          perguntaSugerida = `Qual a diferença salarial entre homens e mulheres na secao ${secaoSugerida}${complementoUf}${complementoAno}?`;
        } else if (filtrosBase.eixo) {
          perguntaSugerida = `Como o perfil (${EIXOS_DEMOGRAFICOS[filtrosBase.eixo]}) impacta os salários na secao ${secaoSugerida}${complementoUf}${complementoAno}?`;
        } else {
          perguntaSugerida = `Qual a rotatividade e o salário médio na secao ${secaoSugerida}${complementoUf}${complementoAno}?`;
        }
      }
      return {
        intencao: "cbo_restrito_lgpd",
        titulo: "Ocupação CBO Oculta no Canal Público (LGPD k >= 5)",
        motivo:
          "Por governança LGPD, a granularidade por ocupação CBO 2002 foi omitida das views públicas e de `metra.json` " +
          "para evitar reidentificação em profissões raras. Para consultar CBO específica, execute o painel interno Streamlit " +
          "(`docker compose --profile painel up`) ou explore abaixo a seção CNAE correspondente.",
        sugestaoCnae: secaoSugerida
          ? {
              codigo_secao: secaoSugerida,
              descricao_secao: SECOES_CNAE[secaoSugerida],
              perguntaSugerida,
            }
          : null,
      };
    }

    return null;
  }

  function classificarIntencao(pergunta) {
    const norm = normalizarTexto(pergunta);
    if (!norm) return "nao_suportada";

    const bloqueio = detectarBloqueioOuForaEscopo(pergunta);
    if (bloqueio) return bloqueio.intencao;

    if (contemTermo(norm, ["capital", "capitais", "interior"])) {
      return "p3_capitais_interior";
    }

    if (
      contemTermo(norm, [
        "sazonalidade", "sazonal", "fim de ano", "meses do ano",
        "variacao mensal", "serie mensal", "ciclo mensal", "quarto trimestre",
      ])
    ) {
      return "p2_sazonalidade";
    }

    if (
      contemTermo(norm, [
        "rotatividade", "turnover", "fluxos pareados", "equilibrio dos fluxos",
        "correlacao", "pearson", "praticam salarios", "salarios mais baixos",
      ])
    ) {
      return "p4_fluxos_salarios";
    }

    if (
      contemTermo(norm, [
        "idade", "sociodemografico", "demografico", "perfil", "genero", "sexo",
        "raca", "racas", "raca cor", "por cor", "cor ou raca",
        "escolaridade", "grau de instrucao", "faixa etaria",
        "mulheres", "homens", "homem", "mulher", "masculino", "feminino",
        "negras", "negros", "pardas", "pardos", "branca", "preta", "indigena", "indigenas",
        "mestrado", "doutorado", "ensino medio", "superior completo",
      ])
    ) {
      return "p5_perfil_remuneracao";
    }

    if (
      contemTermo(norm, [
        "setor", "setores", "cnae", "secao", "ultimos 12 meses",
        "mais contratou", "mais demitiu", "ranking de admissoes",
      ])
    ) {
      return "p1_setores_df";
    }

    const filtros = extrairFiltros(pergunta);
    if (
      filtros.sigla_uf ||
      filtros.ano ||
      filtros.codigo_secao ||
      contemTermo(norm, [
        "salario", "salarios", "saldo", "admissoes", "contratacoes",
        "desligamentos", "demissoes", "empregos", "vagas", "resumo", "indicadores",
      ])
    ) {
      return "resumo_geral";
    }

    return "nao_suportada";
  }

  function agregarRegistros(linhas) {
    let admissoes = 0;
    let desligamentos = 0;
    let saldo = 0;
    let somaSalarios = 0;
    let qtdSalarios = 0;

    for (const r of linhas) {
      if (typeof r.admissoes === "number") admissoes += r.admissoes;
      if (typeof r.desligamentos === "number") desligamentos += r.desligamentos;
      if (typeof r.saldo === "number") saldo += r.saldo;
      if (
        r.salario_medio_admissao !== null &&
        r.salario_medio_admissao !== undefined &&
        typeof r.qtd_salarios_admissao === "number" &&
        r.qtd_salarios_admissao > 0
      ) {
        somaSalarios += r.salario_medio_admissao * r.qtd_salarios_admissao;
        qtdSalarios += r.qtd_salarios_admissao;
      }
    }

    const salarioMedio = qtdSalarios > 0 ? somaSalarios / qtdSalarios : null;
    const totalMov = admissoes + desligamentos;
    const indiceFluxos = totalMov > 0 ? (200.0 * Math.min(admissoes, desligamentos)) / totalMov : null;

    return {
      admissoes,
      desligamentos,
      saldo,
      qtd_salarios_admissao: qtdSalarios,
      salario_medio_admissao: salarioMedio,
      indice_fluxos_pareados_pct: indiceFluxos,
    };
  }

  function filtrarLinhasBase(linhas, filtros) {
    return linhas.filter((r) => {
      if (filtros.sigla_uf && r.sigla_uf !== filtros.sigla_uf) return false;
      if (filtros.ano && parseCompetencia(r.competencia).ano !== Number(filtros.ano)) return false;
      if (filtros.codigo_secao && r.codigo_secao !== filtros.codigo_secao) return false;
      return true;
    });
  }

  function calcularKpisRecorte(dados, filtros = {}) {
    const usaSetores = Boolean(filtros.codigo_secao);
    const colecao = usaSetores ? "setores" : "geografia";
    const linhas = filtrarLinhasBase(dados[colecao] || [], filtros);
    const agg = agregarRegistros(linhas);
    return {
      ...agg,
      colecaoOrigem: colecao,
      registrosPublicados: linhas.length,
    };
  }

  function denseRank(items, chave) {
    const valoresOrdenados = Array.from(new Set(items.map((x) => x[chave]))).sort((a, b) => b - a);
    const mapa = new Map(valoresOrdenados.map((val, idx) => [val, idx + 1]));
    return mapa;
  }

  function calcularP1(dados, filtros = {}) {
    const uf = UFS_VALIDAS.includes(filtros.sigla_uf) ? filtros.sigla_uf : "DF";
    const anoFiltro = filtros.ano ? Number(filtros.ano) : null;
    const secaoFiltro = filtros.codigo_secao || null;

    const calObservado = (dados.calendario || []).filter((c) => {
      if (!c.tem_dados) return false;
      if (anoFiltro && parseCompetencia(c.competencia).ano !== anoFiltro) return false;
      return true;
    });

    if (!calObservado.length) {
      return { uf, ano: anoFiltro, inicio: null, fim: null, competenciasDisponiveis: 0, linhas: [] };
    }

    const compsObs = calObservado.map((c) => c.competencia).sort();
    const fim = compsObs[compsObs.length - 1];
    const inicioJanela = anoFiltro ? compsObs[0] : subtrairMesesCompetencia(fim, 11);
    const inicioEfetivo = inicioJanela < compsObs[0] ? compsObs[0] : inicioJanela;

    const compsNaJanela = compsObs.filter((c) => c >= inicioJanela && c <= fim);
    const setoresFiltrados = (dados.setores || []).filter((r) => {
      if (r.sigla_uf !== uf) return false;
      if (r.codigo_secao === "Z") return false;
      if (secaoFiltro && r.codigo_secao !== secaoFiltro) return false;
      if (anoFiltro && parseCompetencia(r.competencia).ano !== anoFiltro) return false;
      return r.competencia >= inicioJanela && r.competencia <= fim;
    });

    const grupos = new Map();
    for (const r of setoresFiltrados) {
      if (!grupos.has(r.codigo_secao)) grupos.set(r.codigo_secao, []);
      grupos.get(r.codigo_secao).push(r);
    }

    const itens = [];
    for (const [codigo, regs] of grupos.entries()) {
      const agg = agregarRegistros(regs);
      itens.push({
        codigo_secao: codigo,
        descricao_secao: SECOES_CNAE[codigo] || codigo,
        ...agg,
      });
    }

    const rankAdm = denseRank(itens, "admissoes");
    const rankDesl = denseRank(itens, "desligamentos");
    for (const item of itens) {
      item.ranking_admissoes = rankAdm.get(item.admissoes);
      item.ranking_desligamentos = rankDesl.get(item.desligamentos);
    }
    itens.sort((a, b) => a.ranking_admissoes - b.ranking_admissoes || a.codigo_secao.localeCompare(b.codigo_secao));

    return {
      uf,
      ano: anoFiltro,
      codigo_secao: secaoFiltro,
      inicio: anoFiltro ? inicioEfetivo : inicioJanela,
      fim,
      competenciasDisponiveis: compsNaJanela.length,
      linhas: itens,
    };
  }

  function calcularP2(dados, filtros = {}) {
    const anoFiltro = filtros.ano ? Number(filtros.ano) : null;
    const calFiltrado = (dados.calendario || [])
      .filter((c) => !anoFiltro || parseCompetencia(c.competencia).ano === anoFiltro)
      .sort((a, b) => a.competencia.localeCompare(b.competencia));

    const porAnoTemDados = new Map();
    for (const c of calFiltrado) {
      const { ano } = parseCompetencia(c.competencia);
      if (c.tem_dados) {
        porAnoTemDados.set(ano, (porAnoTemDados.get(ano) || 0) + 1);
      }
    }
    const anosCompletos = new Set();
    for (const [ano, qtd] of porAnoTemDados.entries()) {
      if (qtd === 12) anosCompletos.add(ano);
    }

    const setoresFiltrados = filtrarLinhasBase(dados.setores || [], filtros);
    const porCompetencia = new Map();
    for (const r of setoresFiltrados) {
      if (!porCompetencia.has(r.competencia)) porCompetencia.set(r.competencia, []);
      porCompetencia.get(r.competencia).push(r);
    }

    const serie = calFiltrado.map((c) => {
      const { ano, mes } = parseCompetencia(c.competencia);
      const regs = porCompetencia.get(c.competencia) || [];
      if (!c.tem_dados) {
        return {
          competencia: c.competencia,
          ano,
          mes,
          tem_dados: false,
          ano_completo_na_base: false,
          admissoes: null,
          desligamentos: null,
          saldo: null,
        };
      }
      const agg = agregarRegistros(regs);
      return {
        competencia: c.competencia,
        ano,
        mes,
        tem_dados: true,
        ano_completo_na_base: anosCompletos.has(ano),
        admissoes: agg.admissoes,
        desligamentos: agg.desligamentos,
        saldo: agg.saldo,
      };
    });

    const resumoMensal = [];
    for (let mes = 1; mes <= 12; mes++) {
      const doMes = serie.filter((s) => s.mes === mes);
      const completosMes = doMes.filter((s) => s.ano_completo_na_base && s.admissoes !== null);
      const observadosMes = doMes.filter((s) => s.tem_dados && s.admissoes !== null);
      const anosConsid = completosMes.length;
      resumoMensal.push({
        mes,
        nome_mes: `${String(mes).padStart(2, "0")} - ${NOMES_MESES[mes]}`,
        anos_considerados: anosConsid,
        media_admissoes_mes: anosConsid > 0 ? completosMes.reduce((acc, s) => acc + s.admissoes, 0) / anosConsid : null,
        media_desligamentos_mes: anosConsid > 0 ? completosMes.reduce((acc, s) => acc + s.desligamentos, 0) / anosConsid : null,
        media_saldo_mes: anosConsid > 0 ? completosMes.reduce((acc, s) => acc + s.saldo, 0) / anosConsid : null,
        admissoes_obs: observadosMes.length > 0 ? observadosMes.reduce((acc, s) => acc + s.admissoes, 0) : null,
        desligamentos_obs: observadosMes.length > 0 ? observadosMes.reduce((acc, s) => acc + s.desligamentos, 0) : null,
        saldo_obs: observadosMes.length > 0 ? observadosMes.reduce((acc, s) => acc + s.saldo, 0) : null,
      });
    }

    return {
      serie,
      resumoMensal,
      anosCompletos: Array.from(anosCompletos).sort(),
    };
  }

  function compararCapitalInterior(linhasGrupo) {
    const capLinhas = linhasGrupo.filter((r) => r.is_capital === true);
    const intLinhas = linhasGrupo.filter((r) => r.is_capital === false);
    const cap = capLinhas.length ? agregarRegistros(capLinhas) : null;
    const intl = intLinhas.length ? agregarRegistros(intLinhas) : null;

    const salCap = cap ? cap.salario_medio_admissao : null;
    const salInt = intl ? intl.salario_medio_admissao : null;
    const saldoCap = cap ? cap.saldo : null;
    const saldoInt = intl ? intl.saldo : null;
    const difSalario = salCap !== null && salInt !== null ? salCap - salInt : null;
    const difSalarioPct = difSalario !== null && salInt > 0 ? (100.0 * difSalario) / salInt : null;
    const difSaldo = saldoCap !== null && saldoInt !== null ? saldoCap - saldoInt : null;

    return {
      admissoes_capital: cap ? cap.admissoes : null,
      admissoes_interior: intl ? intl.admissoes : null,
      desligamentos_capital: cap ? cap.desligamentos : null,
      desligamentos_interior: intl ? intl.desligamentos : null,
      saldo_capital: saldoCap,
      saldo_interior: saldoInt,
      salario_capital: salCap,
      salario_interior: salInt,
      n_capital: cap ? cap.qtd_salarios_admissao : 0,
      n_interior: intl ? intl.qtd_salarios_admissao : 0,
      diferenca_saldo: difSaldo,
      diferenca_salario: difSalario,
      diferenca_salario_pct: difSalarioPct,
    };
  }

  function calcularP3(dados, filtros = {}) {
    const filtrosGeo = { sigla_uf: filtros.sigla_uf || null, ano: filtros.ano || null };
    const geoFiltrada = filtrarLinhasBase(dados.geografia || [], filtrosGeo);
    const recortePrincipal = filtrosGeo.sigla_uf || "Centro-Oeste";

    const consolidado = {
      recorte: recortePrincipal,
      nivel: "total",
      ano: null,
      ...compararCapitalInterior(geoFiltrada),
    };

    const anosPresentes = Array.from(
      new Set(geoFiltrada.map((r) => parseCompetencia(r.competencia).ano))
    ).sort();
    const serieAnual = anosPresentes.map((ano) => ({
      recorte: recortePrincipal,
      nivel: "anual",
      ano,
      ...compararCapitalInterior(geoFiltrada.filter((r) => parseCompetencia(r.competencia).ano === ano)),
    }));

    const ufsPresentes = Array.from(new Set(geoFiltrada.map((r) => r.sigla_uf))).sort();
    const porUf = [];
    if (!filtrosGeo.sigla_uf) {
      porUf.push(consolidado);
    }
    for (const uf of ufsPresentes) {
      porUf.push({
        recorte: uf,
        nivel: "total",
        ano: null,
        ...compararCapitalInterior(geoFiltrada.filter((r) => r.sigla_uf === uf)),
      });
    }

    return {
      recorte: recortePrincipal,
      consolidado,
      serieAnual,
      porUf,
      avisoSetorIgnorado: Boolean(filtros.codigo_secao),
    };
  }

  function mediana(valores) {
    if (!valores.length) return null;
    const ord = [...valores].sort((a, b) => a - b);
    const meio = Math.floor(ord.length / 2);
    return ord.length % 2 !== 0 ? ord[meio] : (ord[meio - 1] + ord[meio]) / 2;
  }

  function correlacaoPearson(xs, ys) {
    const n = xs.length;
    if (n < 3) return null;
    const mx = xs.reduce((a, b) => a + b, 0) / n;
    const my = ys.reduce((a, b) => a + b, 0) / n;
    let num = 0;
    let dx2 = 0;
    let dy2 = 0;
    for (let i = 0; i < n; i++) {
      const dx = xs[i] - mx;
      const dy = ys[i] - my;
      num += dx * dy;
      dx2 += dx * dx;
      dy2 += dy * dy;
    }
    if (dx2 <= 0 || dy2 <= 0) return null;
    return num / Math.sqrt(dx2 * dy2);
  }

  function calcularP4(dados, filtros = {}) {
    const setoresFiltrados = (dados.setores || []).filter((r) => {
      if (r.codigo_secao === "Z") return false;
      if (filtros.sigla_uf && r.sigla_uf !== filtros.sigla_uf) return false;
      if (filtros.ano && parseCompetencia(r.competencia).ano !== Number(filtros.ano)) return false;
      return true;
    });

    const grupos = new Map();
    for (const r of setoresFiltrados) {
      if (!grupos.has(r.codigo_secao)) grupos.set(r.codigo_secao, []);
      grupos.get(r.codigo_secao).push(r);
    }

    const linhas = [];
    for (const [codigo, regs] of grupos.entries()) {
      const agg = agregarRegistros(regs);
      linhas.push({
        codigo_secao: codigo,
        descricao_secao: SECOES_CNAE[codigo] || codigo,
        ...agg,
        selecionada: filtros.codigo_secao === codigo,
      });
    }
    linhas.sort((a, b) => a.codigo_secao.localeCompare(b.codigo_secao));

    const pares = linhas.filter(
      (s) => s.indice_fluxos_pareados_pct !== null && s.salario_medio_admissao !== null
    );
    const medIndice = mediana(pares.map((s) => s.indice_fluxos_pareados_pct));
    const medSalario = mediana(pares.map((s) => s.salario_medio_admissao));
    const corr = correlacaoPearson(
      pares.map((s) => s.indice_fluxos_pareados_pct),
      pares.map((s) => s.salario_medio_admissao)
    );

    for (const s of linhas) {
      if (s.indice_fluxos_pareados_pct === null || s.salario_medio_admissao === null || medIndice === null || medSalario === null) {
        s.quadrante = "Sem dados";
      } else if (s.indice_fluxos_pareados_pct >= medIndice && s.salario_medio_admissao >= medSalario) {
        s.quadrante = "Índice alto / salário alto";
      } else if (s.indice_fluxos_pareados_pct >= medIndice) {
        s.quadrante = "Índice alto / salário baixo";
      } else if (s.salario_medio_admissao >= medSalario) {
        s.quadrante = "Índice baixo / salário alto";
      } else {
        s.quadrante = "Índice baixo / salário baixo";
      }
    }

    return {
      linhas,
      paresValidos: pares.length,
      correlacaoPearson: corr,
      medianaIndice: medIndice,
      medianaSalario: medSalario,
    };
  }

  function calcularP5(dados, filtros = {}) {
    const eixo = EIXOS_DEMOGRAFICOS[filtros.eixo] ? filtros.eixo : "sexo";
    const baseFiltrada = filtrarLinhasBase(dados.perfis || [], filtros).filter((r) => r.eixo === eixo);

    const grupos = new Map();
    for (const r of baseFiltrada) {
      const chave = `${r.codigo_categoria}::${r.categoria}`;
      if (!grupos.has(chave)) {
        grupos.set(chave, {
          codigo_categoria: r.codigo_categoria,
          categoria: r.categoria,
          regs: [],
        });
      }
      grupos.get(chave).regs.push(r);
    }

    const totalRecorte = agregarRegistros(baseFiltrada);
    const linhas = [];
    for (const g of grupos.values()) {
      const agg = agregarRegistros(g.regs);
      const partPct =
        totalRecorte.admissoes > 0 ? (100.0 * agg.admissoes) / totalRecorte.admissoes : null;
      const difReais =
        agg.salario_medio_admissao !== null && totalRecorte.salario_medio_admissao !== null
          ? agg.salario_medio_admissao - totalRecorte.salario_medio_admissao
          : null;
      const difPct =
        difReais !== null && totalRecorte.salario_medio_admissao > 0
          ? (100.0 * difReais) / totalRecorte.salario_medio_admissao
          : null;

      linhas.push({
        eixo,
        codigo_categoria: g.codigo_categoria,
        categoria: g.categoria,
        ...agg,
        participacao_admissoes_pct: partPct,
        diferenca_salarial: difReais,
        diferenca_salarial_pct: difPct,
      });
    }

    linhas.sort((a, b) => a.codigo_categoria - b.codigo_categoria);

    let resumoSexo = null;
    if (eixo === "sexo") {
      const h = linhas.find((l) => /^hom/i.test(l.categoria) && l.salario_medio_admissao !== null);
      const m = linhas.find((l) => /^mul/i.test(l.categoria) && l.salario_medio_admissao !== null);
      if (h && m) {
        const dif = h.salario_medio_admissao - m.salario_medio_admissao;
        const pct = m.salario_medio_admissao > 0 ? (100.0 * dif) / m.salario_medio_admissao : null;
        resumoSexo = { homem: h, mulher: m, diferenca_reais: dif, variacao_pct: pct };
      }
    }

    return {
      eixo,
      rotuloEixo: EIXOS_DEMOGRAFICOS[eixo],
      mediaRecorte: totalRecorte.salario_medio_admissao,
      admissoesRecorte: totalRecorte.admissoes,
      qtdSalariosRecorte: totalRecorte.qtd_salarios_admissao,
      linhas,
      resumoSexo,
    };
  }

  function moedaSimples(v) {
    if (v === null || v === undefined || !Number.isFinite(v)) return "não divulgado";
    return `R$ ${v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }

  function inteiroSimples(v, sinal = false) {
    if (v === null || v === undefined || !Number.isFinite(v)) return "—";
    const pref = sinal && v > 0 ? "+" : "";
    return `${pref}${Math.round(v).toLocaleString("pt-BR")}`;
  }

  function responderPergunta(dados, pergunta, overrides = {}) {
    const texto = String(pergunta || "").trim();
    if (!texto) {
      return {
        perguntaOriginal: texto,
        suportada: false,
        intencao: "nao_suportada",
        tituloIntencao: "Pergunta vazia",
        motivoRecusa: "Digite uma pergunta sobre emprego, salários, setores, sazonalidade ou perfil demográfico no Centro-Oeste.",
        ressalva: dados.recorte?.ressalva || "",
      };
    }

    const bloqueio = detectarBloqueioOuForaEscopo(texto);
    if (bloqueio) {
      return {
        perguntaOriginal: texto,
        suportada: false,
        intencao: bloqueio.intencao,
        tituloIntencao: bloqueio.titulo,
        motivoRecusa: bloqueio.motivo,
        sugestaoCnae: bloqueio.sugestaoCnae || null,
        ressalva: dados.recorte?.ressalva || "",
      };
    }

    const intencao = classificarIntencao(texto);
    const extraidos = extrairFiltros(texto);
    const filtros = {
      ...extraidos,
      ...(overrides.sigla_uf && !extraidos.sigla_uf ? { sigla_uf: overrides.sigla_uf } : {}),
      ...(overrides.ano && !extraidos.ano ? { ano: Number(overrides.ano) } : {}),
      ...(overrides.codigo_secao && !extraidos.codigo_secao ? { codigo_secao: overrides.codigo_secao } : {}),
      ...(overrides.eixo && !extraidos.eixo ? { eixo: overrides.eixo } : {}),
    };

    const recorteDesc = [
      filtros.sigla_uf || "Centro-Oeste",
      filtros.ano ? `Ano ${filtros.ano}` : "2023–2026",
      filtros.codigo_secao ? `Seção ${filtros.codigo_secao}` : null,
    ].filter(Boolean).join(" · ");

    if (intencao === "p1_setores_df") {
      const r = calcularP1(dados, filtros);
      const topAdm = r.linhas[0];
      const topSaldo = [...r.linhas].sort((a, b) => b.saldo - a.saldo)[0];
      const resumoExecutivo = topAdm
        ? `Em ${r.uf} (${r.ano ? `ano ${r.ano}` : `${r.inicio?.slice(0, 7)} a ${r.fim?.slice(0, 7)}`}), ` +
          `a seção ${topAdm.codigo_secao} (${topAdm.descricao_secao}) lidera as admissões (${inteiroSimples(topAdm.admissoes)}) ` +
          `e a seção ${topSaldo.codigo_secao} teve o maior saldo publicado (${inteiroSimples(topSaldo.saldo, true)}).`
        : "Nenhum grupo de setor publicado neste recorte (grupos < 5 movimentações são omitidos).";

      return {
        perguntaOriginal: texto,
        suportada: true,
        intencao,
        tituloIntencao: `P1 — Setores Econômicos em ${r.uf} (${r.ano ? `Ano ${r.ano}` : "12 meses"})`,
        colecao: "setores",
        filtros,
        dadosAnalise: r,
        resumoExecutivo,
        auditoria: {
          metricas: ["admissoes", "desligamentos", "saldo"],
          consultaDeclarativa: `SELECT codigo_secao, SUM(admissoes), SUM(desligamentos), SUM(saldo) FROM setores WHERE sigla_uf = '${r.uf}' AND codigo_secao <> 'Z' AND competencia BETWEEN '${r.inicio}' AND '${r.fim}' GROUP BY codigo_secao`,
          ressalva: dados.recorte?.ressalva || "",
        },
      };
    }

    if (intencao === "p2_sazonalidade") {
      const r = calcularP2(dados, filtros);
      const validos = r.resumoMensal.filter((m) => m.media_admissoes_mes !== null);
      const pico = [...validos].sort((a, b) => b.media_admissoes_mes - a.media_admissoes_mes)[0];
      const vale = [...validos].sort((a, b) => a.media_saldo_mes - b.media_saldo_mes)[0];
      const resumoExecutivo = pico
        ? `Considerando apenas anos completos (${r.anosCompletos.join(", ")}), o pico médio de admissões ocorreu em ${pico.nome_mes} ` +
          `(${inteiroSimples(pico.media_admissoes_mes)} adm/mês) e o menor saldo médio em ${vale.nome_mes} (${inteiroSimples(vale.media_saldo_mes, true)}).`
        : `O recorte (${recorteDesc}) não possui anos com 12 meses completos na origem; exibindo apenas a série mensal observada.`;

      return {
        perguntaOriginal: texto,
        suportada: true,
        intencao,
        tituloIntencao: `P2 — Sazonalidade Mensal (${recorteDesc})`,
        colecao: "setores + calendario",
        filtros,
        dadosAnalise: r,
        resumoExecutivo,
        auditoria: {
          metricas: ["admissoes", "desligamentos", "saldo"],
          consultaDeclarativa: `SELECT mes, AVG(admissoes), AVG(desligamentos), AVG(saldo) FROM serie WHERE ano_completo_na_base GROUP BY mes`,
          ressalva: `Meses sem dados permanecem nulos; anos parciais não entram na média sazonal. ${dados.recorte?.ressalva || ""}`,
        },
      };
    }

    if (intencao === "p3_capitais_interior") {
      const r = calcularP3(dados, filtros);
      const c = r.consolidado;
      let resumoExecutivo;
      if (r.recorte === "DF") {
        resumoExecutivo =
          `No DF (${filtros.ano || "2023–2026"}), não há municípios de interior. As movimentações publicadas somam saldo de ` +
          `${inteiroSimples(c.saldo_capital, true)} e salário médio de admissão de ${moedaSimples(c.salario_capital)} (n = ${inteiroSimples(c.n_capital)}).`;
      } else {
        const maisSaldo = (c.saldo_capital ?? -Infinity) >= (c.saldo_interior ?? -Infinity) ? "capitais" : "municípios do interior";
        const difTexto = c.diferenca_salario !== null
          ? `diferença salarial Capital − Interior de ${moedaSimples(c.diferenca_salario)} (${c.diferenca_salario_pct >= 0 ? "+" : ""}${c.diferenca_salario_pct.toFixed(1)}%)`
          : "comparação salarial indisponível por supressão";
        resumoExecutivo =
          `Em ${r.recorte} (${filtros.ano || "2023–2026"}), os(as) ${maisSaldo} concentraram o maior saldo publicado ` +
          `(${inteiroSimples(c.saldo_capital, true)} nas capitais vs. ${inteiroSimples(c.saldo_interior, true)} no interior), com ${difTexto}.`;
      }

      return {
        perguntaOriginal: texto,
        suportada: true,
        intencao,
        tituloIntencao: `P3 — Capitais vs. Interior (${r.recorte})`,
        colecao: "geografia",
        filtros,
        dadosAnalise: r,
        resumoExecutivo,
        auditoria: {
          metricas: ["saldo", "salario_medio_admissao", "qtd_salarios_admissao"],
          consultaDeclarativa: `SELECT is_capital, SUM(saldo), SUM(salario_medio_admissao * qtd_salarios_admissao) / SUM(qtd_salarios_admissao) FROM geografia GROUP BY is_capital`,
          ressalva: `O DF não possui municípios de interior. ${dados.recorte?.ressalva || ""}`,
        },
      };
    }

    if (intencao === "p4_fluxos_salarios") {
      const r = calcularP4(dados, filtros);
      const corrTexto = r.correlacaoPearson !== null
        ? `Correlação de Pearson r = ${r.correlacaoPearson.toFixed(3)} entre índice de fluxos pareados e salário médio em ${r.paresValidos} seções válidas.`
        : "Menos de 3 pares válidos com variação positiva neste recorte para estimar correlação de Pearson.";
      return {
        perguntaOriginal: texto,
        suportada: true,
        intencao,
        tituloIntencao: `P4 — Equilíbrio de Fluxos Pareados e Salário (${recorteDesc})`,
        colecao: "setores",
        filtros,
        dadosAnalise: r,
        resumoExecutivo: `${corrTexto} O índice é uma proxy de equilíbrio entre entradas e saídas (0–100%), não taxa sobre estoque de vínculos.`,
        auditoria: {
          metricas: ["admissoes", "desligamentos", "saldo", "salario_medio_admissao", "indice_fluxos_pareados_pct"],
          consultaDeclarativa: `SELECT codigo_secao, indice_fluxos_pareados_pct, salario_medio_admissao FROM setores WHERE codigo_secao <> 'Z' GROUP BY codigo_secao`,
          ressalva: dados.recorte?.ressalva || "",
        },
      };
    }

    if (intencao === "p5_perfil_remuneracao") {
      const r = calcularP5(dados, filtros);
      let resumoExecutivo;
      if (r.resumoSexo) {
        const s = r.resumoSexo;
        resumoExecutivo =
          `No recorte ${recorteDesc} (${r.rotuloEixo}), homens tiveram salário médio publicado de ${moedaSimples(s.homem.salario_medio_admissao)} ` +
          `e mulheres de ${moedaSimples(s.mulher.salario_medio_admissao)} (diferença Homem − Mulher: ${moedaSimples(s.diferenca_reais)}, ` +
          `${s.variacao_pct >= 0 ? "+" : ""}${s.variacao_pct.toFixed(1)}%).`;
      } else {
        const ord = [...r.linhas].filter((l) => l.salario_medio_admissao !== null).sort((a, b) => b.salario_medio_admissao - a.salario_medio_admissao);
        resumoExecutivo = ord.length
          ? `No eixo ${r.rotuloEixo} (${recorteDesc}), o maior salário médio publicado foi em "${ord[0].categoria}" (${moedaSimples(ord[0].salario_medio_admissao)}) e o menor em "${ord[ord.length - 1].categoria}" (${moedaSimples(ord[ord.length - 1].salario_medio_admissao)}).`
          : `Nenhuma categoria salarial publicada para ${r.rotuloEixo} em ${recorteDesc} (grupos ou salários < 5 omitidos).`;
      }
      return {
        perguntaOriginal: texto,
        suportada: true,
        intencao,
        tituloIntencao: `P5 — Perfil Sociodemográfico: ${r.rotuloEixo} (${recorteDesc})`,
        colecao: "perfis",
        filtros: { ...filtros, eixo: r.eixo },
        dadosAnalise: r,
        resumoExecutivo,
        auditoria: {
          metricas: ["admissoes", "desligamentos", "saldo", "salario_medio_admissao", "qtd_salarios_admissao"],
          consultaDeclarativa: `SELECT codigo_categoria, categoria, SUM(admissoes), SUM(saldo), salario_medio_ponderado FROM perfis WHERE eixo = '${r.eixo}' GROUP BY codigo_categoria, categoria`,
          ressalva: `Cada consulta usa exatamente um eixo demográfico, sem cruzar atributos. ${dados.recorte?.ressalva || ""}`,
        },
      };
    }

    if (intencao === "resumo_geral") {
      const k = calcularKpisRecorte(dados, filtros);
      return {
        perguntaOriginal: texto,
        suportada: true,
        intencao,
        tituloIntencao: `Resumo de Indicadores (${recorteDesc})`,
        colecao: k.colecaoOrigem,
        filtros,
        dadosAnalise: k,
        resumoExecutivo:
          `Nos registros publicados de ${recorteDesc} (coleção ${k.colecaoOrigem}), foram apuradas ${inteiroSimples(k.admissoes)} admissões, ` +
          `${inteiroSimples(k.desligamentos)} desligamentos, saldo de ${inteiroSimples(k.saldo, true)} e salário médio de ${moedaSimples(k.salario_medio_admissao)}.`,
        auditoria: {
          metricas: ["admissoes", "desligamentos", "saldo", "salario_medio_admissao", "qtd_salarios_admissao", "indice_fluxos_pareados_pct"],
          consultaDeclarativa: `SELECT SUM(admissoes), SUM(desligamentos), SUM(saldo), salario_medio_ponderado FROM ${k.colecaoOrigem}`,
          ressalva: dados.recorte?.ressalva || "",
        },
      };
    }

    return {
      perguntaOriginal: texto,
      suportada: false,
      intencao: "nao_suportada",
      tituloIntencao: "Pergunta Não Mapeada no Catálogo Público",
      motivoRecusa:
        "A pergunta não corresponde a nenhum dos cinco recortes homologados (P1 setores, P2 sazonalidade, " +
        "P3 capitais vs. interior, P4 rotatividade e salários, P5 perfil demográfico) nem a um filtro de UF/ano/seção.",
      ressalva: dados.recorte?.ressalva || "",
    };
  }

  return {
    SECOES_CNAE,
    NOMES_MESES,
    EIXOS_DEMOGRAFICOS,
    UFS_VALIDAS,
    ANOS_VALIDOS,
    normalizarTexto,
    contemTermo,
    extrairFiltros,
    detectarBloqueioOuForaEscopo,
    classificarIntencao,
    agregarRegistros,
    calcularKpisRecorte,
    calcularP1,
    calcularP2,
    calcularP3,
    calcularP4,
    calcularP5,
    responderPergunta,
  };
});
