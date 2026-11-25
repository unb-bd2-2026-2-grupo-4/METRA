/* Interface pública do painel executivo e agente analítico no GitHub Pages (ADR-0008).
 * Consome exclusivamente `docs/assets/dados/metra.json` via `window.MetraAgente`.
 */
(() => {
  "use strict";

  const COR_ACENTO = "#0f766e";
  const COR_SECUNDARIA = "#64748b";
  const COR_ALERTA = "#b45309";
  const SVG_NS = "http://www.w3.org/2000/svg";

  const EXEMPLOS_PERGUNTAS = [
    ["P1 · Setores no DF", "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?"],
    ["P2 · Sazonalidade", "Existe sazonalidade evidente nas contratações e demissões?"],
    ["P3 · Capitais vs. Interior", "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?"],
    ["P4 · Rotatividade e Salário", "Os setores com maior rotatividade praticam salários médios mais baixos?"],
    ["P5 · Diferença por sexo", "Qual a diferença salarial entre homens e mulheres?"],
    ["Consulta livre · Ranking", "Qual setor paga o maior salário em Goiás?"],
    ["Bloqueio LGPD", "Listar CPF e salário de cada trabalhador"],
  ];

  const PERGUNTAS_GESTAO = {
    p1: {
      rotulo: "Pergunta de gestão P1",
      enunciado: "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?",
      nota: "Sem ano filtrado, usa uma janela de 12 meses até a competência mais recente da base. O DF é a UF padrão.",
    },
    p2: {
      rotulo: "Pergunta de gestão P2",
      enunciado: "Existe sazonalidade evidente nas contratações e demissões?",
      nota: "A média sazonal usa meses com grupos publicados em anos com 12 competências observadas na base.",
    },
    p3: {
      rotulo: "Pergunta de gestão P3",
      enunciado: "Qual é a disparidade no saldo de empregos formais e no salário médio entre as capitais e os municípios do interior?",
      nota: "Pergunta central da E1 — diferença calculada como Capital − Interior; no DF não há municípios do interior.",
    },
    p4: {
      rotulo: "Pergunta de gestão P4",
      enunciado: "Setores econômicos com maior taxa de rotatividade praticam salários médios menores?",
      nota: "Usa o índice de fluxos pareados como aproximação de rotatividade (ADR-0007) e correlação de Pearson por seção CNAE.",
    },
    p5: {
      rotulo: "Pergunta de gestão P5",
      enunciado: "Como o perfil sociodemográfico (sexo, raça/cor, idade e escolaridade) impacta o nível salarial e o saldo de empregos?",
      nota: "Leitura descritiva de fluxos e salários por um eixo demográfico por vez; não estima probabilidade individual de recolocação.",
    },
  };

  function criarCabecalhoPergunta(id) {
    const info = PERGUNTAS_GESTAO[id];
    if (!info) return null;
    return el("div", { className: "metra-question-banner" },
      el("div", { className: "metra-question-code", textContent: info.rotulo }),
      el("p", { className: "metra-question-text", textContent: info.enunciado }),
      el("p", { className: "metra-question-note", textContent: info.nota })
    );
  }

  const fmtMoeda = (v) =>
    v === null || v === undefined || !Number.isFinite(v)
      ? "não divulgado"
      : v.toLocaleString("pt-BR", { style: "currency", currency: "BRL" });

  const fmtMoedaCurta = (v) =>
    v === null || v === undefined || !Number.isFinite(v)
      ? "—"
      : `R$ ${Math.round(v).toLocaleString("pt-BR")}`;

  const fmtInt = (v, comSinal = false) => {
    if (v === null || v === undefined || !Number.isFinite(v)) return "—";
    const n = Math.round(v);
    const sinal = comSinal && n > 0 ? "+" : "";
    return `${sinal}${n.toLocaleString("pt-BR")}`;
  };

  const fmtPct = (v, comSinal = false) => {
    if (v === null || v === undefined || !Number.isFinite(v)) return "—";
    const sinal = comSinal && v > 0 ? "+" : "";
    return `${sinal}${v.toLocaleString("pt-BR", { minimumFractionDigits: 1, maximumFractionDigits: 1 })}%`;
  };

  const fmtMedia = (v) => v === null ? "—" : v.toLocaleString("pt-BR", { maximumFractionDigits: 2 });

  function el(tag, props = {}, ...filhos) {
    const node = document.createElement(tag);
    for (const [k, val] of Object.entries(props)) {
      if (val === undefined || val === null) continue;
      if (k === "className") node.className = val;
      else if (k === "textContent") node.textContent = val;
      else if (k.startsWith("on") && typeof val === "function") node.addEventListener(k.slice(2).toLowerCase(), val);
      else node.setAttribute(k, String(val));
    }
    for (const f of filhos) {
      if (f !== null && f !== undefined && f !== false) node.append(f);
    }
    return node;
  }

  function svgEl(tag, attrs = {}, ...filhos) {
    const node = document.createElementNS(SVG_NS, tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (v !== undefined && v !== null) node.setAttribute(k, String(v));
    }
    for (const f of filhos) {
      if (f !== null && f !== undefined && f !== false) node.append(f);
    }
    return node;
  }

  function criarKpi(rotulo, valor, meta) {
    return el("div", { className: "metra-kpi" },
      el("div", { className: "metra-kpi-label", textContent: rotulo }),
      el("div", { className: "metra-kpi-val", textContent: valor }),
      meta ? el("div", { className: "metra-kpi-meta", textContent: meta }) : null
    );
  }

  function criarTabela(colunas, linhas) {
    const thead = el("thead", {}, el("tr", {},
      ...colunas.map((c) => el("th", { className: c.num ? "num" : "", scope: "col", textContent: c.label }))
    ));
    const tbody = el("tbody", {},
      ...linhas.map((linha) => el("tr", {},
        ...colunas.map((c) => el("td", {
          className: c.num ? "num" : "",
          textContent: c.fmt ? c.fmt(linha[c.key], linha) : (linha[c.key] ?? "—"),
        }))
      ))
    );
    return el("div", { className: "metra-table-wrap" }, el("table", { className: "metra-table" }, thead, tbody));
  }

  function criarLegenda(itens) {
    return el("div", { className: "metra-legend" },
      ...itens.map(([cor, texto]) =>
        el("span", { className: "metra-legend-item" },
          el("span", { className: "metra-swatch", style: `background:${cor}` }),
          texto
        )
      )
    );
  }

  function graficoBarrasAgrupadasSvg(categorias, serieA, serieB, formatarValor, permiteNegativo = false) {
    const w = 520;
    const h = 230;
    const padL = 62;
    const padR = 16;
    const padT = 18;
    const padB = 34;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;

    const todos = [...serieA, ...serieB].filter((v) => v !== null && Number.isFinite(v));
    if (!todos.length) return el("p", { className: "metra-source-note", textContent: "Sem valores publicados neste recorte." });

    let minV = permiteNegativo ? Math.min(0, ...todos) : 0;
    let maxV = Math.max(0, ...todos);
    if (minV === maxV) maxV = minV + 1;
    const yParaPx = (v) => padT + ((maxV - v) / (maxV - minV)) * plotH;
    const yZero = yParaPx(0);

    const svg = svgEl("svg", { viewBox: `0 0 ${w} ${h}`, className: "metra-svg", role: "img" });
    for (let i = 0; i <= 4; i++) {
      const val = minV + ((maxV - minV) * i) / 4;
      const y = yParaPx(val);
      svg.append(
        svgEl("line", { x1: padL, x2: w - padR, y1: y, y2: y, stroke: "rgba(148,163,184,0.22)", "stroke-width": 1 }),
        svgEl("text", { x: padL - 6, y: y + 3, "text-anchor": "end", "font-size": 10, fill: COR_SECUNDARIA }, formatarValor(val))
      );
    }
    svg.append(svgEl("line", { x1: padL, x2: w - padR, y1: yZero, y2: yZero, stroke: "rgba(148,163,184,0.55)", "stroke-width": 1 }));

    const step = plotW / Math.max(1, categorias.length);
    const barW = Math.min(24, Math.max(8, step * 0.3));
    categorias.forEach((cat, idx) => {
      const cx = padL + step * (idx + 0.5);
      [[serieA[idx], COR_ACENTO, -barW - 2, "Capitais"], [serieB[idx], COR_SECUNDARIA, 2, "Interior"]].forEach(([v, cor, dx, nome]) => {
        if (v === null || !Number.isFinite(v)) return;
        const yV = yParaPx(v);
        const top = Math.min(yV, yZero);
        const altura = Math.max(2, Math.abs(yZero - yV));
        svg.append(
          svgEl("rect", { x: cx + dx, y: top, width: barW, height: altura, rx: 2, fill: cor },
            svgEl("title", {}, `${cat} · ${nome}: ${formatarValor(v)}`)
          )
        );
      });
      svg.append(svgEl("text", { x: cx, y: h - 10, "text-anchor": "middle", "font-size": 11, fill: "currentColor" }, cat));
    });
    return svg;
  }

  function graficoBarrasHorizontaisSvg(itens, campoValor, campoRotulo, formatar, campoSub = null) {
    const filtrados = itens.filter((i) => i[campoValor] !== null && Number.isFinite(i[campoValor]));
    if (!filtrados.length) return el("p", { className: "metra-source-note", textContent: "Sem valores publicados neste recorte." });

    const rowH = 30;
    const padL = 175;
    const padR = 88;
    const padT = 8;
    const padB = 10;
    const w = 540;
    const h = padT + padB + filtrados.length * rowH;
    const plotW = w - padL - padR;

    const valoresSub = campoSub
      ? filtrados.map((i) => i[campoSub]).filter((x) => x !== null && Number.isFinite(x))
      : [];
    const minV = Math.min(0, ...filtrados.map((i) => i[campoValor]), ...valoresSub);
    const maxV = Math.max(0, ...filtrados.map((i) => i[campoValor]), ...valoresSub);
    const temNegativos = minV < 0;
    const range = maxV - minV || 1;
    const xParaPx = (v) => padL + ((v - minV) / range) * plotW;
    const xZero = xParaPx(0);

    const svg = svgEl("svg", { viewBox: `0 0 ${w} ${h}`, className: "metra-svg", role: "img" });
    if (temNegativos) {
      svg.append(svgEl("line", { x1: xZero, x2: xZero, y1: padT, y2: h - padB, stroke: "rgba(148,163,184,0.5)", "stroke-width": 1 }));
    }

    filtrados.forEach((item, idx) => {
      const y = padT + idx * rowH;
      const v = item[campoValor];
      const rotulo = String(item[campoRotulo] || "");
      const curto = rotulo.length > 26 ? `${rotulo.slice(0, 24)}…` : rotulo;
      svg.append(svgEl("text", { x: padL - 8, y: y + 18, "text-anchor": "end", "font-size": 10.5, fill: "currentColor" }, curto));

      const xV = xParaPx(v);
      const xBar = Math.min(xZero, xV);
      const wBar = Math.max(2, Math.abs(xV - xZero));
      const cor = v < 0 ? COR_ALERTA : COR_ACENTO;
      svg.append(
        svgEl("rect", { x: xBar, y: y + 7, width: wBar, height: 14, rx: 2, fill: cor },
          svgEl("title", {}, `${rotulo}: ${formatar(v)}`)
        )
      );

      if (campoSub && item[campoSub] !== null && Number.isFinite(item[campoSub])) {
        const xSub = xParaPx(item[campoSub]);
        svg.append(
          svgEl("rect", { x: padL, y: y + 22, width: Math.max(2, xSub - padL), height: 4, rx: 1, fill: COR_SECUNDARIA },
            svgEl("title", {}, `${rotulo} (Desligamentos): ${formatar(item[campoSub])}`)
          )
        );
      }

      const xTxt = temNegativos ? w - padR + 6 : xBar + wBar + 6;
      svg.append(svgEl("text", { x: xTxt, y: y + 18, "text-anchor": "start", "font-size": 10, fill: "currentColor" }, formatar(v)));
    });

    return svg;
  }

  function graficoLinhasSerieSvg(pontos, chaveA, chaveB, rotuloEixoX) {
    const validos = pontos.filter((p) => p[chaveA] !== null || p[chaveB] !== null);
    if (!validos.length) return el("p", { className: "metra-source-note", textContent: "Sem dados observados neste recorte." });

    const w = 540;
    const h = 230;
    const padL = 56;
    const padR = 16;
    const padT = 16;
    const padB = 34;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;

    const vals = pontos.flatMap((p) => [p[chaveA], p[chaveB]]).filter((v) => v !== null && Number.isFinite(v));
    const minV = Math.min(0, ...vals);
    const maxV = Math.max(1, ...vals);
    const xParaPx = (i) => padL + (pontos.length > 1 ? (i / (pontos.length - 1)) * plotW : plotW / 2);
    const yParaPx = (v) => padT + ((maxV - v) / (maxV - minV || 1)) * plotH;

    const svg = svgEl("svg", { viewBox: `0 0 ${w} ${h}`, className: "metra-svg", role: "img" });
    for (let i = 0; i <= 4; i++) {
      const val = minV + ((maxV - minV) * i) / 4;
      const y = yParaPx(val);
      svg.append(
        svgEl("line", { x1: padL, x2: w - padR, y1: y, y2: y, stroke: "rgba(148,163,184,0.22)", "stroke-width": 1 }),
        svgEl("text", { x: padL - 6, y: y + 3, "text-anchor": "end", "font-size": 10, fill: COR_SECUNDARIA }, fmtInt(val))
      );
    }

    function construirSegmentos(chave) {
      const paths = [];
      let atual = [];
      pontos.forEach((p, idx) => {
        const v = p[chave];
        if (v === null || !Number.isFinite(v)) {
          if (atual.length) { paths.push(atual); atual = []; }
        } else {
          atual.push([xParaPx(idx), yParaPx(v), p]);
        }
      });
      if (atual.length) paths.push(atual);
      return paths;
    }

    [[chaveA, COR_ACENTO, "Admissões"], [chaveB, COR_SECUNDARIA, "Desligamentos"]].forEach(([chave, cor, label]) => {
      for (const seg of construirSegmentos(chave)) {
        if (seg.length > 1) {
          const d = seg.map(([x, y], i) => `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`).join(" ");
          svg.append(svgEl("path", { d, fill: "none", stroke: cor, "stroke-width": 2 }));
        }
        for (const [x, y, p] of seg) {
          svg.append(svgEl("circle", { cx: x, cy: y, r: 2.6, fill: cor },
            svgEl("title", {}, `${rotuloEixoX(p)} · ${label}: ${fmtInt(p[chave])}`)
          ));
        }
      }
    });

    const passoTick = Math.max(1, Math.ceil(pontos.length / 6));
    pontos.forEach((p, idx) => {
      if (idx % passoTick === 0 || idx === pontos.length - 1) {
        svg.append(svgEl("text", { x: xParaPx(idx), y: h - 10, "text-anchor": "middle", "font-size": 9.5, fill: COR_SECUNDARIA }, rotuloEixoX(p)));
      }
    });
    return svg;
  }

  function graficoDispersaoP4Svg(linhas, medX, medY) {
    const pontos = linhas.filter((s) => s.indice_fluxos_pareados_pct !== null && s.salario_medio_admissao !== null);
    if (!pontos.length) return el("p", { className: "metra-source-note", textContent: "Sem pares suficientes para dispersão." });

    const w = 540;
    const h = 280;
    const padL = 62;
    const padR = 24;
    const padT = 18;
    const padB = 36;
    const plotW = w - padL - padR;
    const plotH = h - padT - padB;

    const xs = pontos.map((p) => p.indice_fluxos_pareados_pct);
    const ys = pontos.map((p) => p.salario_medio_admissao);
    const minX = Math.max(0, Math.floor(Math.min(...xs) - 5));
    const maxX = Math.min(100, Math.ceil(Math.max(...xs) + 5));
    const minY = Math.max(0, Math.floor(Math.min(...ys) * 0.9));
    const maxY = Math.ceil(Math.max(...ys) * 1.08);
    const xParaPx = (x) => padL + ((x - minX) / (maxX - minX || 1)) * plotW;
    const yParaPx = (y) => padT + ((maxY - y) / (maxY - minY || 1)) * plotH;

    const svg = svgEl("svg", { viewBox: `0 0 ${w} ${h}`, className: "metra-svg", role: "img" });
    for (let i = 0; i <= 4; i++) {
      const yVal = minY + ((maxY - minY) * i) / 4;
      const y = yParaPx(yVal);
      svg.append(
        svgEl("line", { x1: padL, x2: w - padR, y1: y, y2: y, stroke: "rgba(148,163,184,0.22)", "stroke-width": 1 }),
        svgEl("text", { x: padL - 6, y: y + 3, "text-anchor": "end", "font-size": 10, fill: COR_SECUNDARIA }, fmtMoedaCurta(yVal))
      );
    }

    if (medX !== null && medY !== null) {
      const mx = xParaPx(medX);
      const my = yParaPx(medY);
      svg.append(
        svgEl("line", { x1: mx, x2: mx, y1: padT, y2: h - padB, stroke: COR_SECUNDARIA, "stroke-dasharray": "4,3", "stroke-width": 1 }),
        svgEl("line", { x1: padL, x2: w - padR, y1: my, y2: my, stroke: COR_SECUNDARIA, "stroke-dasharray": "4,3", "stroke-width": 1 })
      );
    }

    pontos.forEach((p) => {
      const cx = xParaPx(p.indice_fluxos_pareados_pct);
      const cy = yParaPx(p.salario_medio_admissao);
      const cor = p.selecionada ? COR_ALERTA : COR_ACENTO;
      const r = p.selecionada ? 6.5 : 4.8;
      svg.append(
        svgEl("circle", { cx, cy, r, fill: cor, "fill-opacity": p.selecionada ? 1 : 0.82 },
          svgEl("title", {}, `${p.codigo_secao} - ${p.descricao_secao}\nÍndice: ${fmtPct(p.indice_fluxos_pareados_pct)}\nSalário: ${fmtMoeda(p.salario_medio_admissao)}`)
        ),
        svgEl("text", { x: cx + 6, y: cy + 3, "font-size": 9.5, "font-weight": p.selecionada ? 700 : 500, fill: "currentColor" }, p.codigo_secao)
      );
    });

    svg.append(svgEl("text", { x: padL + plotW / 2, y: h - 8, "text-anchor": "middle", "font-size": 10.5, fill: COR_SECUNDARIA }, "Índice de fluxos pareados (%) — mediana tracejada"));
    return svg;
  }

  function renderConteudoP3(p3) {
    const frag = document.createDocumentFragment();
    frag.append(criarCabecalhoPergunta("p3"));
    if (p3.avisoSetorIgnorado) {
      frag.append(el("div", {
        className: "metra-callout metra-callout-warn",
        textContent: "A coleção pública `geografia` não estratifica por seção CNAE; a comparação Capital × Interior abaixo considera todas as seções publicadas da UF/ano selecionados.",
      }));
    }
    const ref = p3.consolidado;
    frag.append(el("div", { className: "metra-kpi-grid-3" },
      criarKpi("Salário médio (Capitais)", fmtMoeda(ref.salario_capital), `Saldo: ${fmtInt(ref.saldo_capital, true)} · n = ${fmtInt(ref.n_capital)}`),
      criarKpi("Salário médio (Interior)", fmtMoeda(ref.salario_interior), `Saldo: ${fmtInt(ref.saldo_interior, true)} · n = ${fmtInt(ref.n_interior)}`),
      criarKpi("Diferença (Capital − Interior)", fmtMoeda(ref.diferenca_salario), `Dif. saldo: ${fmtInt(ref.diferenca_saldo, true)}`)
    ));

    if (p3.serieAnual.length > 1) {
      const anos = p3.serieAnual.map((r) => String(r.ano));
      frag.append(el("div", { className: "metra-two-col" },
        el("div", { className: "metra-card" },
          el("h4", { className: "metra-card-title", textContent: "Salário médio de admissão por ano (R$)" }),
          criarLegenda([[COR_ACENTO, "Capitais"], [COR_SECUNDARIA, "Interior"]]),
          graficoBarrasAgrupadasSvg(anos, p3.serieAnual.map((r) => r.salario_capital), p3.serieAnual.map((r) => r.salario_interior), fmtMoedaCurta)
        ),
        el("div", { className: "metra-card" },
          el("h4", { className: "metra-card-title", textContent: "Saldo líquido publicado por ano (vínculos)" }),
          criarLegenda([[COR_ACENTO, "Capitais"], [COR_SECUNDARIA, "Interior"]]),
          graficoBarrasAgrupadasSvg(anos, p3.serieAnual.map((r) => r.saldo_capital), p3.serieAnual.map((r) => r.saldo_interior), (v) => fmtInt(v, true), true)
        )
      ));
    }

    const linhasSerie = [...p3.serieAnual.map((r) => ({ ...r, periodo: String(r.ano) })), { ...ref, periodo: "Total publicado" }];
    frag.append(el("h4", { className: "metra-card-title", textContent: `Série anual e consolidado (${p3.recorte})` }));
    frag.append(criarTabela([
      { key: "periodo", label: "Período" },
      { key: "saldo_capital", label: "Saldo Cap.", num: true, fmt: (v) => fmtInt(v, true) },
      { key: "saldo_interior", label: "Saldo Int.", num: true, fmt: (v) => fmtInt(v, true) },
      { key: "diferenca_saldo", label: "Dif. Saldo", num: true, fmt: (v) => fmtInt(v, true) },
      { key: "salario_capital", label: "Salário Cap.", num: true, fmt: fmtMoeda },
      { key: "salario_interior", label: "Salário Int.", num: true, fmt: fmtMoeda },
      { key: "diferenca_salario", label: "Dif. Salário", num: true, fmt: fmtMoeda },
    ], linhasSerie));

    frag.append(el("h4", { className: "metra-card-title", textContent: "Resumo por Unidade da Federação" }));
    frag.append(criarTabela([
      { key: "recorte", label: "Recorte" },
      { key: "saldo_capital", label: "Saldo Cap.", num: true, fmt: (v) => fmtInt(v, true) },
      { key: "saldo_interior", label: "Saldo Int.", num: true, fmt: (v) => fmtInt(v, true) },
      { key: "salario_capital", label: "Salário Cap.", num: true, fmt: fmtMoeda },
      { key: "salario_interior", label: "Salário Int.", num: true, fmt: fmtMoeda },
      { key: "diferenca_salario", label: "Dif. Salário", num: true, fmt: fmtMoeda },
      { key: "n_capital", label: "n Cap.", num: true, fmt: (v) => fmtInt(v) },
      { key: "n_interior", label: "n Int.", num: true, fmt: (v) => fmtInt(v) },
    ], p3.porUf));

    return frag;
  }

  function renderConteudoP1(p1) {
    const frag = document.createDocumentFragment();
    frag.append(criarCabecalhoPergunta("p1"));
    if (!p1.linhas.length) {
      frag.append(el("div", { className: "metra-callout metra-callout-warn", textContent: "Nenhum setor publicado neste recorte (grupos < 5 movimentações são omitidos)." }));
      return frag;
    }
    const topAdm = p1.linhas[0];
    const topDesl = p1.linhas.find((linha) => linha.ranking_desligamentos === 1);
    frag.append(el("div", { className: "metra-kpi-grid-3" },
      criarKpi("Maior volume de admissões", `Seção ${topAdm.codigo_secao} (${fmtInt(topAdm.admissoes)})`, topAdm.descricao_secao.slice(0, 44)),
      criarKpi("Maior volume de desligamentos", `Seção ${topDesl.codigo_secao} (${fmtInt(topDesl.desligamentos)})`, topDesl.descricao_secao.slice(0, 44)),
      criarKpi("Janela de apuração", p1.inicio ? `${p1.inicio.slice(0, 7)} a ${p1.fim.slice(0, 7)}` : "—", `${p1.competenciasDisponiveis} competências · UF ${p1.uf}`)
    ));

    const top8 = p1.linhas.slice(0, 8).map((s) => ({ ...s, rotulo: `${s.codigo_secao} - ${s.descricao_secao}` }));
    frag.append(el("div", { className: "metra-card" },
      el("h4", { className: "metra-card-title", textContent: `Principais setores por movimentação publicada (${p1.uf})` }),
      criarLegenda([[COR_ACENTO, "Admissões"], [COR_SECUNDARIA, "Desligamentos (barra inferior)"]]),
      graficoBarrasHorizontaisSvg(top8, "admissoes", "rotulo", (v) => fmtInt(v), "desligamentos")
    ));

    frag.append(criarTabelaP1(p1.linhas));
    return frag;
  }

  function criarTabelaP1(linhas) {
    return criarTabela([
      { key: "codigo_secao", label: "Seção" },
      { key: "descricao_secao", label: "Descrição" },
      { key: "admissoes", label: "Admissões", num: true, fmt: (v) => fmtInt(v) },
      { key: "ranking_admissoes", label: "Pos. adm.", num: true, fmt: (v) => `${v}º` },
      { key: "desligamentos", label: "Desligamentos", num: true, fmt: (v) => fmtInt(v) },
      { key: "ranking_desligamentos", label: "Pos. desl.", num: true, fmt: (v) => `${v}º` },
      { key: "saldo", label: "Saldo", num: true, fmt: (v) => fmtInt(v, true) },
      { key: "salario_medio_admissao", label: "Salário médio", num: true, fmt: fmtMoeda },
    ], linhas);
  }

  function renderConteudoP2(p2) {
    const frag = document.createDocumentFragment();
    frag.append(criarCabecalhoPergunta("p2"));
    frag.append(el("div", { className: "metra-two-col" },
      el("div", { className: "metra-card" },
        el("h4", { className: "metra-card-title", textContent: "Série mensal observada" }),
        criarLegenda([[COR_ACENTO, "Admissões"], [COR_SECUNDARIA, "Desligamentos"]]),
        graficoLinhasSerieSvg(p2.serie, "admissoes", "desligamentos", (p) => p.competencia.slice(0, 7))
      ),
      el("div", { className: "metra-card" },
        el("h4", { className: "metra-card-title", textContent: p2.anosCompletos.length ? `Média sazonal (anos completos na base: ${p2.anosCompletos.join(", ")})` : "Média sazonal indisponível" }),
        criarLegenda([[COR_ACENTO, "Média admissões"], [COR_SECUNDARIA, "Média desligamentos"]]),
        p2.anosCompletos.length
          ? graficoLinhasSerieSvg(p2.resumoMensal, "media_admissoes_mes", "media_desligamentos_mes", (m) => m.nome_mes.slice(5))
          : el("p", { className: "metra-source-note", textContent: "Nenhum ano com 12 competências observadas na base para o período selecionado." })
      )
    ));

    frag.append(criarTabelaMediaSazonal(p2.resumoMensal));
    return frag;
  }

  function criarTabelaMediaSazonal(linhas) {
    return criarTabela([
      { key: "nome_mes", label: "Mês" },
      { key: "anos_considerados", label: "Anos na média", num: true, fmt: (v) => fmtInt(v) },
      { key: "media_admissoes_mes", label: "Média admissões", num: true, fmt: fmtMedia },
      { key: "media_desligamentos_mes", label: "Média desligamentos", num: true, fmt: fmtMedia },
      { key: "media_saldo_mes", label: "Média saldo", num: true, fmt: fmtMedia },
      { key: "saldo_obs", label: "Saldo acumulado", num: true, fmt: (v) => fmtInt(v, true) },
    ], linhas);
  }

  function renderConteudoP4(p4) {
    const frag = document.createDocumentFragment();
    frag.append(criarCabecalhoPergunta("p4"));
    const maiorIdx = [...p4.linhas].filter((l) => l.indice_fluxos_pareados_pct !== null).sort((a, b) => b.indice_fluxos_pareados_pct - a.indice_fluxos_pareados_pct)[0];
    frag.append(el("div", { className: "metra-kpi-grid-3" },
      criarKpi("Correlação de Pearson (r)", p4.correlacaoPearson !== null ? p4.correlacaoPearson.toFixed(3).replace(".", ",") : "—", "Índice de fluxos pareados vs. salário"),
      criarKpi("Seções válidas", fmtInt(p4.paresValidos), "Com fluxos pareados e salário divulgado"),
      criarKpi("Maior índice de fluxos", maiorIdx ? `Seção ${maiorIdx.codigo_secao} (${fmtPct(maiorIdx.indice_fluxos_pareados_pct)})` : "—", maiorIdx ? maiorIdx.descricao_secao.slice(0, 42) : "")
    ));

    frag.append(el("div", { className: "metra-card" },
      el("h4", { className: "metra-card-title", textContent: "Dispersão por seção CNAE (quadrantes pela mediana)" }),
      criarLegenda([[COR_ACENTO, "Seção CNAE"], [COR_ALERTA, "Seção filtrada"]]),
      graficoDispersaoP4Svg(p4.linhas, p4.medianaIndice, p4.medianaSalario)
    ));

    frag.append(criarTabela([
      { key: "codigo_secao", label: "Seção" },
      { key: "descricao_secao", label: "Descrição" },
      { key: "indice_fluxos_pareados_pct", label: "Índice (%)", num: true, fmt: (v) => fmtPct(v) },
      { key: "salario_medio_admissao", label: "Salário médio", num: true, fmt: fmtMoeda },
      { key: "quadrante", label: "Quadrante" },
      { key: "saldo", label: "Saldo", num: true, fmt: (v) => fmtInt(v, true) },
    ], p4.linhas));
    return frag;
  }

  function renderConteudoP5(p5, eixoAtual, aoTrocarEixo) {
    const frag = document.createDocumentFragment();
    frag.append(criarCabecalhoPergunta("p5"));
    const seletor = el("div", { className: "metra-segmented", role: "group", "aria-label": "Eixo demográfico" });
    for (const [cod, nome] of Object.entries(window.MetraAgente.EIXOS_DEMOGRAFICOS)) {
      seletor.append(el("button", {
        type: "button",
        className: "metra-seg-btn",
        "aria-pressed": String(cod === eixoAtual),
        textContent: nome,
        onClick: () => aoTrocarEixo(cod),
      }));
    }
    frag.append(seletor);

    if (!p5.linhas.length) {
      frag.append(el("div", { className: "metra-callout metra-callout-warn", textContent: "Nenhuma categoria publicada neste recorte (grupos < 5 são omitidos)." }));
      return frag;
    }

    if (p5.resumoSexo) {
      const s = p5.resumoSexo;
      frag.append(el("div", { className: "metra-kpi-grid-3" },
        criarKpi("Salário médio (Homens)", fmtMoeda(s.homem.salario_medio_admissao), `${fmtInt(s.homem.admissoes)} adm. (${fmtPct(s.homem.participacao_admissoes_pct)})`),
        criarKpi("Salário médio (Mulheres)", fmtMoeda(s.mulher.salario_medio_admissao), `${fmtInt(s.mulher.admissoes)} adm. (${fmtPct(s.mulher.participacao_admissoes_pct)})`),
        criarKpi("Diferença (Homem − Mulher)", fmtMoeda(s.diferenca_reais), `Variação relativa: ${fmtPct(s.variacao_pct, true)}`)
      ));
    } else {
      const validas = [...p5.linhas].filter((l) => l.salario_medio_admissao !== null).sort((a, b) => b.salario_medio_admissao - a.salario_medio_admissao);
      const maiorVol = [...p5.linhas].sort((a, b) => b.admissoes - a.admissoes)[0];
      frag.append(el("div", { className: "metra-kpi-grid-3" },
        criarKpi("Maior média publicada", validas[0] ? fmtMoeda(validas[0].salario_medio_admissao) : "não divulgado", validas[0]?.categoria || ""),
        criarKpi("Menor média publicada", validas.length ? fmtMoeda(validas[validas.length - 1].salario_medio_admissao) : "não divulgado", validas.length ? validas[validas.length - 1].categoria : ""),
        criarKpi("Maior volume", maiorVol ? fmtInt(maiorVol.admissoes) : "—", maiorVol?.categoria || "")
      ));
    }

    frag.append(el("div", { className: "metra-two-col" },
      el("div", { className: "metra-card" },
        el("h4", { className: "metra-card-title", textContent: `Salário médio inicial por ${p5.rotuloEixo}` }),
        graficoBarrasHorizontaisSvg(p5.linhas, "salario_medio_admissao", "categoria", fmtMoedaCurta)
      ),
      el("div", { className: "metra-card" },
        el("h4", { className: "metra-card-title", textContent: "Diferença frente à média do recorte (R$)" }),
        graficoBarrasHorizontaisSvg(p5.linhas, "diferenca_salarial", "categoria", (v) => `${v >= 0 ? "+" : ""}${fmtMoedaCurta(v)}`)
      )
    ));

    frag.append(criarTabela([
      { key: "categoria", label: p5.rotuloEixo },
      { key: "admissoes", label: "Admissões", num: true, fmt: (v) => fmtInt(v) },
      { key: "participacao_admissoes_pct", label: "Part. (%)", num: true, fmt: (v) => fmtPct(v) },
      { key: "saldo", label: "Saldo", num: true, fmt: (v) => fmtInt(v, true) },
      { key: "qtd_salarios_admissao", label: "n Salários", num: true, fmt: (v) => (v ? fmtInt(v) : "não divulgado") },
      { key: "salario_medio_admissao", label: "Salário médio", num: true, fmt: fmtMoeda },
      { key: "diferenca_salarial", label: "Dif. p/ média", num: true, fmt: fmtMoeda },
    ], p5.linhas));
    return frag;
  }

  async function inicializar() {
    const raiz = document.getElementById("metra-painel-app");
    if (!raiz || raiz.dataset.inicializado === "true") return;
    raiz.dataset.inicializado = "true";

    const Agente = window.MetraAgente;
    if (!Agente) {
      raiz.replaceChildren(el("div", { className: "metra-callout metra-callout-danger", textContent: "Módulo MetraAgente não carregado." }));
      return;
    }

    raiz.replaceChildren(el("p", { className: "metra-source-note", textContent: "Carregando snapshot analítico público (`metra.json`)…" }));

    let dados;
    try {
      const resp = await fetch(new URL(raiz.dataset.fonte, document.baseURI));
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      dados = await resp.json();
      if (dados.versao_schema !== 1 || !Array.isArray(dados.setores) || !Array.isArray(dados.geografia) || !Array.isArray(dados.perfis)) {
        throw new Error("Contrato JSON v1 incompatível");
      }
    } catch (erro) {
      raiz.replaceChildren(el("div", { className: "metra-callout metra-callout-warn", textContent: `Não foi possível carregar o snapshot público (${erro.message}).` }));
      return;
    }

    const estado = {
      pergunta: EXEMPLOS_PERGUNTAS[0][1],
      uf: "",
      ano: "",
      secao: "",
      aba: "p1",
      eixoP5: "sexo",
    };

    const obs = (dados.calendario || []).filter((c) => c.tem_dados);
    const faixaComp = obs.length ? `${obs[0].competencia.slice(0, 7)} a ${obs[obs.length - 1].competencia.slice(0, 7)}` : "—";

    const inputPergunta = el("input", {
      type: "search",
      className: "metra-agent-input",
      value: estado.pergunta,
      placeholder: "Pergunte sobre salários, saldo, setores, sazonalidade ou perfil demográfico...",
      "aria-label": "Pergunta em linguagem natural",
    });
    const boxResultadoAgente = el("div", { className: "metra-agent-result" });

    function rodarAgente(texto) {
      estado.pergunta = texto;
      inputPergunta.value = texto;
      const resp = Agente.responderPergunta(dados, texto, {
        sigla_uf: estado.uf || undefined,
        ano: estado.ano ? Number(estado.ano) : undefined,
        codigo_secao: estado.secao || undefined,
        eixo: estado.aba === "p5" ? estado.eixoP5 : undefined,
      });

      boxResultadoAgente.replaceChildren();
      boxResultadoAgente.append(el("h3", { className: "metra-agent-title", textContent: resp.tituloIntencao }));

      if (!resp.suportada) {
        const cls = resp.intencao === "bloqueada_seguranca" ? "metra-callout metra-callout-danger" : "metra-callout metra-callout-warn";
        boxResultadoAgente.append(el("div", { className: cls, textContent: resp.motivoRecusa }));
        if (resp.sugestaoCnae?.perguntaSugerida) {
          boxResultadoAgente.append(el("button", {
            type: "button",
            className: "metra-btn-secondary",
            textContent: `Consultar Seção ${resp.sugestaoCnae.codigo_secao} — ${resp.sugestaoCnae.descricao_secao}`,
            onClick: () => rodarAgente(resp.sugestaoCnae.perguntaSugerida),
          }));
        }
        return;
      }

      boxResultadoAgente.append(el("div", { className: "metra-callout", textContent: resp.resumoExecutivo }));

      if (resp.intencao === "p1_setores_df") {
        boxResultadoAgente.append(criarTabelaP1(resp.dadosAnalise.linhas));
      } else if (resp.intencao === "p3_capitais_interior") {
        boxResultadoAgente.append(criarTabela([
          { key: "recorte", label: "Recorte" },
          { key: "saldo_capital", label: "Saldo Cap.", num: true, fmt: (v) => fmtInt(v, true) },
          { key: "saldo_interior", label: "Saldo Int.", num: true, fmt: (v) => fmtInt(v, true) },
          { key: "salario_capital", label: "Salário Cap.", num: true, fmt: fmtMoeda },
          { key: "salario_interior", label: "Salário Int.", num: true, fmt: fmtMoeda },
          { key: "diferenca_salario", label: "Dif. Salário", num: true, fmt: fmtMoeda },
        ], resp.dadosAnalise.porUf));
      } else if (resp.intencao === "p4_fluxos_salarios") {
        boxResultadoAgente.append(criarTabela([
          { key: "codigo_secao", label: "Seção" },
          { key: "descricao_secao", label: "Descrição" },
          { key: "indice_fluxos_pareados_pct", label: "Índice (%)", num: true, fmt: (v) => fmtPct(v) },
          { key: "salario_medio_admissao", label: "Salário médio", num: true, fmt: fmtMoeda },
          { key: "quadrante", label: "Quadrante" },
        ], resp.dadosAnalise.linhas));
      } else if (resp.intencao === "p5_perfil_remuneracao") {
        boxResultadoAgente.append(criarTabela([
          { key: "categoria", label: resp.dadosAnalise.rotuloEixo },
          { key: "admissoes", label: "Admissões", num: true, fmt: (v) => fmtInt(v) },
          { key: "desligamentos", label: "Desligamentos", num: true, fmt: (v) => fmtInt(v) },
          { key: "saldo", label: "Saldo", num: true, fmt: (v) => fmtInt(v, true) },
          { key: "participacao_admissoes_pct", label: "Part. (%)", num: true, fmt: (v) => fmtPct(v) },
          { key: "salario_medio_admissao", label: "Salário médio", num: true, fmt: fmtMoeda },
          { key: "diferenca_salarial", label: "Dif. p/ média", num: true, fmt: fmtMoeda },
        ], resp.dadosAnalise.linhas));
      } else if (resp.intencao === "p2_sazonalidade") {
        boxResultadoAgente.append(el("h4", { className: "metra-card-title", textContent: "Série mensal publicada" }));
        boxResultadoAgente.append(criarTabela([
          { key: "competencia", label: "Competência", fmt: (v) => v.slice(0, 7) },
          { key: "admissoes", label: "Admissões", num: true, fmt: (v) => fmtInt(v) },
          { key: "desligamentos", label: "Desligamentos", num: true, fmt: (v) => fmtInt(v) },
          { key: "saldo", label: "Saldo", num: true, fmt: (v) => fmtInt(v, true) },
        ], resp.dadosAnalise.serie));
        if (resp.dadosAnalise.resumoMensal.some((mes) => mes.anos_considerados > 0)) {
          boxResultadoAgente.append(
            el("h4", { className: "metra-card-title", textContent: "Média sazonal" }),
            criarTabelaMediaSazonal(resp.dadosAnalise.resumoMensal)
          );
        }
      } else if (resp.intencao === "consulta_semantica") {
        // Colunas declaradas pela resposta, formatadas pelo formato da métrica no catálogo semântico.
        const formatos = { moeda: fmtMoeda, percentual: (v) => fmtPct(v), inteiro: (v) => fmtInt(v) };
        boxResultadoAgente.append(criarTabela(
          resp.dadosAnalise.colunas.map((c) => ({
            ...c,
            fmt: c.key === "saldo" ? (v) => fmtInt(v, true) : formatos[c.formato],
          })),
          resp.dadosAnalise.linhas
        ));
        if (resp.dadosAnalise.totalGrupos > resp.dadosAnalise.linhas.length) {
          boxResultadoAgente.append(el("p", {
            className: "metra-source-note",
            textContent: `Exibindo ${resp.dadosAnalise.linhas.length} de ${resp.dadosAnalise.totalGrupos} grupos publicados.`,
          }));
        }
      }

      const metadadosMetricas = (resp.auditoria.metricas || [])
        .map((m) => dados.metricas?.[m] ? `${dados.metricas[m].label}: ${dados.metricas[m].descricao}` : m)
        .join(" | ");
      boxResultadoAgente.append(el("details", { className: "metra-details" },
        el("summary", { textContent: "Método de cálculo e métricas" }),
        el("p", { textContent: `Intenção: ${resp.intencao} · Coleção: ${resp.colecao} · Filtros: ${JSON.stringify(resp.filtros)}` }),
        el("p", { textContent: `Catálogo semântico: ${metadadosMetricas}` }),
        el("p", { textContent: resp.auditoria.metodo }),
        el("p", { className: "metra-source-note", textContent: resp.auditoria.ressalva })
      ));
    }

    const formAgente = el("form", {
      className: "metra-agent-form",
      onSubmit: (ev) => {
        ev.preventDefault();
        rodarAgente(inputPergunta.value);
      },
    },
      inputPergunta,
      el("button", { type: "submit", className: "metra-btn-primary", textContent: "Perguntar" })
    );

    const chips = el("div", { className: "metra-chips" },
      ...EXEMPLOS_PERGUNTAS.map(([rotulo, perg]) =>
        el("button", { type: "button", className: "metra-chip", textContent: rotulo, onClick: () => rodarAgente(perg) })
      )
    );

    const selUf = el("select", { id: "metra-filtro-uf", className: "metra-select" },
      el("option", { value: "", textContent: "Todas (Centro-Oeste)" }),
      ...(dados.recorte?.ufs || Agente.UFS_VALIDAS).map((u) => el("option", { value: u, textContent: u }))
    );
    const selAno = el("select", { id: "metra-filtro-ano", className: "metra-select" },
      el("option", { value: "", textContent: "Todos (2023–2026)" }),
      ...Agente.ANOS_VALIDOS.slice().reverse().map((a) => el("option", { value: String(a), textContent: String(a) }))
    );
    const selSecao = el("select", { id: "metra-filtro-secao", className: "metra-select" },
      el("option", { value: "", textContent: "Todas as seções (A–U)" }),
      ...Object.entries(Agente.SECOES_CNAE)
        .filter(([c]) => c !== "Z")
        .map(([c, d]) => el("option", { value: c, textContent: `${c} — ${d}` }))
    );
    const btnLimpar = el("button", {
      type: "button",
      className: "metra-btn-secondary",
      textContent: "Limpar filtros",
      onClick: () => {
        estado.uf = "";
        estado.ano = "";
        estado.secao = "";
        selUf.value = "";
        selAno.value = "";
        selSecao.value = "";
        atualizarDashboard();
      },
    });

    const gridKpis = el("div", { className: "metra-kpi-grid" });
    const notaFonte = el("p", { className: "metra-source-note" });
    const barraAbas = el("div", { className: "metra-tabs", role: "tablist" });
    const painelAba = el("div");

    const definicaoAbas = [
      ["p1", "P1 · Setores Econômicos"],
      ["p2", "P2 · Sazonalidade"],
      ["p3", "P3 · Capitais vs. Interior"],
      ["p4", "P4 · Rotatividade e Salário"],
      ["p5", "P5 · Perfil Demográfico"],
    ];

    function atualizarDashboard() {
      const filtros = {
        sigla_uf: estado.uf || null,
        ano: estado.ano ? Number(estado.ano) : null,
        codigo_secao: estado.secao || null,
      };
      const kpis = Agente.calcularKpisRecorte(dados, filtros);
      gridKpis.replaceChildren(
        criarKpi("Saldo líquido", fmtInt(kpis.saldo, true), `Admissões − Desligamentos (${estado.uf || "Centro-Oeste"})`),
        criarKpi("Salário médio de admissão", fmtMoeda(kpis.salario_medio_admissao), kpis.qtd_salarios_admissao ? `n = ${fmtInt(kpis.qtd_salarios_admissao)} salários válidos` : "Sem salários divulgados"),
        criarKpi("Total de admissões", fmtInt(kpis.admissoes), `Período: ${estado.ano || "2023–2026"}`),
        criarKpi("Total de desligamentos", fmtInt(kpis.desligamentos), `Índice de fluxos: ${fmtPct(kpis.indice_fluxos_pareados_pct)}`)
      );
      notaFonte.textContent =
        `Fonte: coleção pública "${kpis.colecaoOrigem}" (${kpis.registrosPublicados} grupos com k >= 5; cobertura ${faixaComp}). ` +
        "Totais recompostos podem ser parciais quando grupos < 5 são omitidos.";

      barraAbas.replaceChildren(
        ...definicaoAbas.map(([id, rotulo]) =>
          el("button", {
            type: "button",
            role: "tab",
            className: "metra-tab",
            "aria-selected": String(estado.aba === id),
            textContent: rotulo,
            onClick: () => {
              estado.aba = id;
              atualizarDashboard();
            },
          })
        )
      );

      painelAba.replaceChildren();
      if (estado.aba === "p1") painelAba.append(renderConteudoP1(Agente.calcularP1(dados, filtros)));
      else if (estado.aba === "p2") painelAba.append(renderConteudoP2(Agente.calcularP2(dados, filtros)));
      else if (estado.aba === "p3") painelAba.append(renderConteudoP3(Agente.calcularP3(dados, filtros)));
      else if (estado.aba === "p4") painelAba.append(renderConteudoP4(Agente.calcularP4(dados, filtros)));
      else if (estado.aba === "p5") {
        painelAba.append(renderConteudoP5(Agente.calcularP5(dados, { ...filtros, eixo: estado.eixoP5 }), estado.eixoP5, (novoEixo) => {
          estado.eixoP5 = novoEixo;
          atualizarDashboard();
        }));
      }
    }

    selUf.addEventListener("change", () => { estado.uf = selUf.value; atualizarDashboard(); });
    selAno.addEventListener("change", () => { estado.ano = selAno.value; atualizarDashboard(); });
    selSecao.addEventListener("change", () => { estado.secao = selSecao.value; atualizarDashboard(); });

    raiz.replaceChildren(
      el("div", { className: "metra-masthead" },
        el("div", { className: "metra-eyebrow", textContent: "METRA · MONITORAMENTO DO EMPREGO FORMAL · CENTRO-OESTE" }),
        el("h2", { textContent: "Painel Analítico Público e Agente de Consultas" }),
        el("p", { className: "metra-subtitle", textContent: `Novo CAGED (${faixaComp}) · Snapshot público da amostra reproduzível (49.178 movimentações) com supressão LGPD (k >= 5), processado localmente no navegador.` })
      ),
      el("section", { className: "metra-agent-box", "aria-label": "Agente de consulta em linguagem natural" },
        el("p", { className: "metra-section-label", textContent: "Agente de consulta sobre o catálogo público (ADR-0007 / ADR-0008)" }),
        formAgente,
        chips,
        boxResultadoAgente
      ),
      el("div", { className: "metra-filter-bar" },
        el("div", { className: "metra-field" }, el("label", { for: "metra-filtro-uf", textContent: "Unidade da Federação" }), selUf),
        el("div", { className: "metra-field" }, el("label", { for: "metra-filtro-ano", textContent: "Ano" }), selAno),
        el("div", { className: "metra-field" }, el("label", { for: "metra-filtro-secao", textContent: "Setor Econômico (CNAE)" }), selSecao),
        btnLimpar
      ),
      gridKpis,
      notaFonte,
      barraAbas,
      painelAba
    );

    rodarAgente(estado.pergunta);
    atualizarDashboard();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", inicializar);
  } else {
    inicializar();
  }
})();
