"""Painel Analítico do METRA (E4) — Mercado de Trabalho Formal no Centro-Oeste (Novo CAGED).

Execução:
    streamlit run src/app/dashboard.py
"""

from __future__ import annotations

from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pandas as pd
import streamlit as st

from src.app.banco_analitico import SECOES_CNAE_OFICIAIS, abrir_conexao_analitica, obter_caminho_duckdb
from src.app.busca_cbo import IndiceVetorialCBO, consultar_indicadores_cbo
from src.app.text_to_sql import AssistenteTextToSQL, RespostaTextToSQL

ATALHOS_PERGUNTAS: tuple[tuple[str, str], ...] = (
    (
        "Homens vs. Mulheres (Salário)",
        "Qual a diferença salarial entre homens e mulheres?",
    ),
    (
        "Salário por Escolaridade",
        "Como a escolaridade impacta o salário médio de admissão?",
    ),
    (
        "Salário por Raça/Cor",
        "Qual a diferença salarial por raça e cor?",
    ),
    (
        "Salário por Faixa Etária",
        "Qual a diferença salarial por faixa etária e idade?",
    ),
    (
        "Capitais vs. Interior (P3)",
        "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?",
    ),
    (
        "Setores no DF (P1)",
        "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?",
    ),
    (
        "Sazonalidade Mensal (P2)",
        "Existe sazonalidade nas contratações e demissões ao longo dos meses do ano?",
    ),
    (
        "Rotatividade vs. Salário (P4)",
        "Os setores com maior rotatividade praticam salários médios mais baixos?",
    ),
    (
        "Homens vs. Mulheres (Professor)",
        "Qual a diferença salarial entre homens e mulheres para o cargo de professor?",
    ),
    (
        "Teste de Bloqueio SQL",
        "DROP TABLE gold.fct_movimentacao;",
    ),
)

ATALHOS_PROFISSOES: tuple[tuple[str, str], ...] = (
    ("Professor", "professor"),
    ("Programador / TI", "desenvolvedor de software"),
    ("Enfermeiro", "enfermeiro"),
    ("Médico", "medico"),
    ("Engenheiro Civil", "engenheiro civil"),
    ("Vendedor", "vendedor"),
    ("Caminhoneiro", "caminhoneiro"),
    ("Pedreiro", "pedreiro"),
)

OPCOES_CARGO_RAPIDO: tuple[tuple[str, str], ...] = (
    ("Todos os cargos (Mercado Geral)", ""),
    ("Professor (Ensino Básico / Médio / Superior)", "professor"),
    ("Desenvolvedor de Software / Programador", "desenvolvedor de software"),
    ("Enfermeiro", "enfermeiro"),
    ("Médico", "medico"),
    ("Engenheiro Civil", "engenheiro civil"),
    ("Vendedor de Comércio", "vendedor"),
    ("Motorista / Caminhoneiro", "motorista"),
    ("Operador de Caixa", "caixa de supermercado"),
    ("Auxiliar / Assistente Administrativo", "assistente administrativo"),
    ("Pedreiro", "pedreiro"),
    ("Trabalhador Rural / Agropecuário", "trabalhador rural"),
)

NOMES_MESES = {
    1: "01 - Janeiro",
    2: "02 - Fevereiro",
    3: "03 - Março",
    4: "04 - Abril",
    5: "05 - Maio",
    6: "06 - Junho",
    7: "07 - Julho",
    8: "08 - Agosto",
    9: "09 - Setembro",
    10: "10 - Outubro",
    11: "11 - Novembro",
    12: "12 - Dezembro",
}

MAPA_EIXOS_DEMOGRAFICOS = {
    "sexo": "Sexo (Homem vs. Mulher)",
    "escolaridade": "Escolaridade",
    "raca_cor": "Raça/Cor",
    "faixa_etaria": "Faixa Etária",
}


def fmt_int(valor: Any, com_sinal: bool = False) -> str:
    """Formata número inteiro no padrão brasileiro (ex.: 49.178 ou +1.472)."""
    if valor is None or pd.isna(valor):
        return "—"
    n = int(round(float(valor)))
    if com_sinal:
        sinal = "+" if n > 0 else ""
        return f"{sinal}{n:,}".replace(",", ".")
    return f"{n:,}".replace(",", ".")


def fmt_moeda(valor: Any) -> str:
    """Formata valor monetário em Reais (ex.: R$ 2.138,54)."""
    if valor is None or pd.isna(valor):
        return "—"
    v = float(valor)
    texto = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def fmt_pct(valor: Any, com_sinal: bool = False) -> str:
    """Formata percentual no padrão brasileiro (ex.: 13,2% ou +13,2%)."""
    if valor is None or pd.isna(valor):
        return "—"
    v = float(valor)
    sinal = "+" if (com_sinal and v > 0) else ""
    return f"{sinal}{v:.1f}%".replace(".", ",")


def descrever_filtros(filtros: dict[str, Any]) -> str:
    """Descreve os filtros aplicados em texto simples."""
    partes: list[str] = []
    partes.append(f"UF: {filtros['sigla_uf']}" if filtros.get("sigla_uf") else "Região: Centro-Oeste (DF, GO, MT, MS)")
    partes.append(f"Ano: {filtros['ano']}" if filtros.get("ano") else "Período: 2023 a 2026")
    if filtros.get("eixo"):
        partes.append(f"Dimensão: {MAPA_EIXOS_DEMOGRAFICOS.get(str(filtros['eixo']), str(filtros['eixo']))}")
    if filtros.get("termo_ocupacao"):
        partes.append(f"Filtro de Cargo: \"{filtros['termo_ocupacao']}\"")
    if filtros.get("codigos_cbo"):
        partes.append(f"CBOs ({len(filtros['codigos_cbo'])}): {', '.join(filtros['codigos_cbo'])}")
    return "  |  ".join(partes)


@st.cache_resource(show_spinner="Carregando banco analítico DuckDB e índice de ocupações CBO...")
def carregar_recursos_analiticos(caminho_str: str) -> tuple[IndiceVetorialCBO, AssistenteTextToSQL, dict[str, Any]]:
    with abrir_conexao_analitica(caminho_str, garantir_construcao=True) as conn:
        indice = IndiceVetorialCBO.de_conexao_duckdb(conn)
        resumo_row = conn.execute("""
            SELECT
                COUNT(*) AS total_movimentacoes,
                COUNT(*) FILTER (WHERE saldo_movimentacao = 1) AS admissoes,
                COUNT(*) FILTER (WHERE saldo_movimentacao = -1) AS desligamentos,
                COALESCE(SUM(saldo_movimentacao), 0) AS saldo,
                SUM(CASE WHEN saldo_movimentacao = 1 AND salario_valido THEN salario_mensal ELSE 0 END)
                    / NULLIF(COUNT(*) FILTER (WHERE saldo_movimentacao = 1 AND salario_valido), 0) AS salario_medio,
                MIN(competencia)::VARCHAR AS comp_min,
                MAX(competencia)::VARCHAR AS comp_max
            FROM gold.fct_movimentacao
            WHERE is_identificado AND is_centro_oeste AND ano BETWEEN 2023 AND 2026
        """).fetchone()
        resumo_geral = {
            "total_movimentacoes": int(resumo_row[0] or 0),
            "admissoes": int(resumo_row[1] or 0),
            "desligamentos": int(resumo_row[2] or 0),
            "saldo": int(resumo_row[3] or 0),
            "salario_medio": float(resumo_row[4]) if resumo_row[4] is not None else None,
            "comp_min": (resumo_row[5] or "2023-01")[:7],
            "comp_max": (resumo_row[6] or "2026-01")[:7],
        }
    assistente = AssistenteTextToSQL(indice_cbo=indice)
    return indice, assistente, resumo_geral


def renderizar_resultado_p5(
    df_bruto: pd.DataFrame,
    filtros: dict[str, Any],
    chave_radio: str = "radio_p5_padrao",
) -> None:
    """Consolida e exibe de forma direta os indicadores sociodemográficos (Sexo, Escolaridade, Raça/Cor, Idade)."""
    eixos_presentes = list(df_bruto["eixo"].unique())
    if len(eixos_presentes) > 1:
        eixo_padrao = filtros.get("eixo") if filtros.get("eixo") in eixos_presentes else eixos_presentes[0]
        eixo_ativo = st.radio(
            "Selecione a dimensão demográfica para visualizar:",
            options=eixos_presentes,
            index=eixos_presentes.index(eixo_padrao),
            format_func=lambda e: MAPA_EIXOS_DEMOGRAFICOS.get(e, e),
            horizontal=True,
            key=chave_radio,
        )
        df_eixo = df_bruto[df_bruto["eixo"] == eixo_ativo].copy()
    else:
        eixo_ativo = eixos_presentes[0] if eixos_presentes else "sexo"
        df_eixo = df_bruto.copy()

    # Consolida por categoria (somando estados e seções CNAE para mostrar o número real direto)
    consolidado = (
        df_eixo.groupby(["codigo_categoria", "categoria"], as_index=False)
        .agg(
            admissoes=("admissoes", "sum"),
            desligamentos=("desligamentos", "sum"),
            saldo=("saldo", "sum"),
            soma_sal=("soma_salarios_admissao", "sum"),
            qtd_sal=("qtd_salarios_admissao", "sum"),
        )
    )
    total_adm = int(consolidado["admissoes"].sum())
    soma_total_sal = float(consolidado["soma_sal"].sum())
    qtd_total_sal = int(consolidado["qtd_sal"].sum())
    media_geral = (soma_total_sal / qtd_total_sal) if qtd_total_sal > 0 else 0.0

    consolidado["salario_medio"] = consolidado.apply(
        lambda r: (float(r["soma_sal"]) / int(r["qtd_sal"])) if int(r["qtd_sal"]) > 0 else None,
        axis=1,
    )
    consolidado["participacao_pct"] = consolidado["admissoes"].map(
        lambda a: (100.0 * float(a) / total_adm) if total_adm > 0 else 0.0
    )
    consolidado["dif_media_pct"] = consolidado["salario_medio"].map(
        lambda s: (100.0 * (float(s) - media_geral) / media_geral) if (s is not None and media_geral > 0) else None
    )

    validos = consolidado[
        ~consolidado["categoria"].str.lower().str.contains("não identificad|não informad")
        & consolidado["salario_medio"].notna()
    ].copy()

    subtitulo_cargo = f" — Cargo: {filtros['termo_ocupacao']}" if filtros.get("termo_ocupacao") else ""

    # Caso especial: SEXO (Homem vs. Mulher) — comparação direta lado a lado
    if eixo_ativo == "sexo" and len(validos) >= 2:
        homens_df = validos[validos["categoria"].str.lower().str.startswith("hom")]
        mulheres_df = validos[validos["categoria"].str.lower().str.startswith("mul")]
        if not homens_df.empty and not mulheres_df.empty:
            linha_h = homens_df.iloc[0]
            linha_m = mulheres_df.iloc[0]
            sal_h = float(linha_h["salario_medio"])
            sal_m = float(linha_m["salario_medio"])
            dif_reais = sal_h - sal_m
            dif_pct_hm = 100.0 * (sal_h - sal_m) / sal_m if sal_m > 0 else 0.0

            with st.container(border=True):
                st.markdown(f"#### Comparativo Direto: Homens vs. Mulheres{subtitulo_cargo}")
                k1, k2, k3 = st.columns(3)
                k1.metric(
                    "Salário Médio Inicial — Homens",
                    fmt_moeda(sal_h),
                    f"{fmt_int(linha_h['admissoes'])} contratações ({fmt_pct(linha_h['participacao_pct'])})",
                    delta_color="off",
                )
                k2.metric(
                    "Salário Médio Inicial — Mulheres",
                    fmt_moeda(sal_m),
                    f"{fmt_int(linha_m['admissoes'])} contratações ({fmt_pct(linha_m['participacao_pct'])})",
                    delta_color="off",
                )
                k3.metric(
                    "Diferença Salarial (Homem - Mulher)",
                    fmt_moeda(dif_reais),
                    f"Homens recebem {fmt_pct(dif_pct_hm, com_sinal=True)} em relação às mulheres",
                    delta_color="off",
                )

        consolidado = consolidado.sort_values("admissoes", ascending=False)
    else:
        validos_ord = validos.sort_values("salario_medio", ascending=False)
        if not validos_ord.empty:
            maior = validos_ord.iloc[0]
            menor = validos_ord.iloc[-1]
            mais_contrata = validos.sort_values("admissoes", ascending=False).iloc[0]
            nome_eixo = MAPA_EIXOS_DEMOGRAFICOS.get(eixo_ativo, eixo_ativo)
            with st.container(border=True):
                st.markdown(f"#### Destaques por {nome_eixo}{subtitulo_cargo}")
                k1, k2, k3 = st.columns(3)
                k1.metric(
                    f"Maior Salário Médio ({maior['categoria']})",
                    fmt_moeda(maior["salario_medio"]),
                    f"{fmt_int(maior['admissoes'])} contratações ({fmt_pct(maior['participacao_pct'])})",
                    delta_color="off",
                )
                k2.metric(
                    f"Menor Salário Médio ({menor['categoria']})",
                    fmt_moeda(menor["salario_medio"]),
                    f"{fmt_int(menor['admissoes'])} contratações ({fmt_pct(menor['participacao_pct'])})",
                    delta_color="off",
                )
                k3.metric(
                    f"Maior Volume ({mais_contrata['categoria']})",
                    f"{fmt_int(mais_contrata['admissoes'])} contratações",
                    f"Salário médio: {fmt_moeda(mais_contrata['salario_medio'])}",
                    delta_color="off",
                )
        consolidado = consolidado.sort_values("salario_medio", ascending=False)

    df_tab = pd.DataFrame({
        "Categoria": consolidado["categoria"],
        "Contratações": consolidado["admissoes"].map(fmt_int),
        "Demissões": consolidado["desligamentos"].map(fmt_int),
        "Saldo de Vagas": consolidado["saldo"].map(lambda v: fmt_int(v, com_sinal=True)),
        "Participação nas Contratações": consolidado["participacao_pct"].map(fmt_pct),
        "Salário Médio Inicial": consolidado["salario_medio"].map(fmt_moeda),
        "Diferença p/ Média do Grupo": consolidado["dif_media_pct"].map(lambda v: fmt_pct(v, com_sinal=True)),
    })

    c_tab, c_graf = st.columns([3, 2])
    with c_tab:
        st.markdown("**Tabela Consolidada por Categoria**")
        st.dataframe(df_tab, width="stretch", hide_index=True)
    with c_graf:
        st.markdown("**Salário Médio Inicial por Categoria (R$)**")
        if not validos.empty:
            df_plot = validos.set_index("categoria")[["salario_medio"]].rename(
                columns={"salario_medio": "Salário Médio (R$)"}
            )
            st.bar_chart(df_plot, color="#2563eb")

    if eixo_ativo == "sexo" and df_eixo["sigla_uf"].nunique() > 1:
        st.markdown("**Comparativo Homens vs. Mulheres por Estado (UF)**")
        uf_sex = (
            df_eixo[df_eixo["categoria"].isin(["Homem", "Mulher"])]
            .groupby(["sigla_uf", "categoria"], as_index=False)
            .agg(
                admissoes=("admissoes", "sum"),
                soma_sal=("soma_salarios_admissao", "sum"),
                qtd_sal=("qtd_salarios_admissao", "sum"),
            )
        )
        uf_sex["sal"] = uf_sex["soma_sal"] / uf_sex["qtd_sal"].replace(0, pd.NA)
        linhas_uf = []
        for uf in sorted(uf_sex["sigla_uf"].unique()):
            sub = uf_sex[uf_sex["sigla_uf"] == uf]
            sh_s = sub[sub["categoria"] == "Homem"]["sal"]
            sm_s = sub[sub["categoria"] == "Mulher"]["sal"]
            sh = float(sh_s.iloc[0]) if (not sh_s.empty and pd.notna(sh_s.iloc[0])) else 0.0
            sm = float(sm_s.iloc[0]) if (not sm_s.empty and pd.notna(sm_s.iloc[0])) else 0.0
            ah = int(sub[sub["categoria"] == "Homem"]["admissoes"].iloc[0]) if not sub[sub["categoria"] == "Homem"].empty else 0
            am = int(sub[sub["categoria"] == "Mulher"]["admissoes"].iloc[0]) if not sub[sub["categoria"] == "Mulher"].empty else 0
            dif_r = sh - sm if (sh > 0 and sm > 0) else None
            dif_p = (100.0 * dif_r / sm) if (dif_r is not None and sm > 0) else None
            linhas_uf.append({
                "Estado (UF)": uf,
                "Salário Médio Homens": fmt_moeda(sh if sh > 0 else None),
                "Salário Médio Mulheres": fmt_moeda(sm if sm > 0 else None),
                "Diferença (R$)": fmt_moeda(dif_r),
                "Diferença (%)": fmt_pct(dif_p, com_sinal=True),
                "Contratações Homens": fmt_int(ah),
                "Contratações Mulheres": fmt_int(am),
            })
        st.dataframe(pd.DataFrame(linhas_uf), width="stretch", hide_index=True)


def renderizar_resultado_p3(df_bruto: pd.DataFrame, filtros: dict[str, Any] | None = None) -> None:
    """Consolida e exibe de forma direta a comparação Capitais vs. Interior."""
    df_tot = df_bruto[df_bruto["nivel"] == "total"].copy()
    if df_tot.empty:
        df_tot = df_bruto.copy()

    linha_co = df_tot[df_tot["recorte"] == "Centro-Oeste"]
    ref = linha_co.iloc[0] if not linha_co.empty else df_tot.iloc[0]
    subtitulo_cargo = f" — Cargo: {filtros['termo_ocupacao']}" if (filtros and filtros.get("termo_ocupacao")) else ""

    with st.container(border=True):
        st.markdown(f"#### Comparativo Direto: Capitais vs. Interior ({ref['recorte']}){subtitulo_cargo}")
        k1, k2, k3 = st.columns(3)
        k1.metric(
            "Salário Médio — Capitais",
            fmt_moeda(ref["salario_capital"]),
            f"Saldo líquido: {fmt_int(ref['saldo_capital'], com_sinal=True)} vagas",
            delta_color="off",
        )
        k2.metric(
            "Salário Médio — Interior",
            fmt_moeda(ref["salario_interior"]),
            f"Saldo líquido: {fmt_int(ref['saldo_interior'], com_sinal=True)} vagas",
            delta_color="off",
        )
        k3.metric(
            "Diferença Salarial (Capital - Interior)",
            fmt_moeda(ref["diferenca_salario"]),
            f"Diferença de saldo: {fmt_int(ref['diferenca_saldo'], com_sinal=True)} vagas",
            delta_color="off",
        )

    df_tab = pd.DataFrame({
        "Recorte Geográfico": df_tot["recorte"],
        "Contratações Capitais": df_tot["admissoes_capital"].map(fmt_int),
        "Contratações Interior": df_tot["admissoes_interior"].map(fmt_int),
        "Saldo Capitais": df_tot["saldo_capital"].map(lambda v: fmt_int(v, com_sinal=True)),
        "Saldo Interior": df_tot["saldo_interior"].map(lambda v: fmt_int(v, com_sinal=True)),
        "Salário Médio Capitais": df_tot["salario_capital"].map(fmt_moeda),
        "Salário Médio Interior": df_tot["salario_interior"].map(fmt_moeda),
        "Diferença Salarial (R$)": df_tot["diferenca_salario"].map(fmt_moeda),
    })

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Tabela Consolidada por Estado (Capitais vs. Interior)**")
        st.dataframe(df_tab, width="stretch", hide_index=True)
    with c2:
        st.markdown("**Salário Médio Inicial: Capitais vs. Interior (R$)**")
        df_plot = df_tot.set_index("recorte")[["salario_capital", "salario_interior"]].rename(
            columns={"salario_capital": "Capitais", "salario_interior": "Interior"}
        )
        st.bar_chart(df_plot)


def renderizar_resultado_p1(df_bruto: pd.DataFrame, filtros: dict[str, Any] | None = None) -> None:
    """Consolida e exibe o ranking de setores econômicos nos últimos 12 meses."""
    df_ativos = df_bruto[df_bruto["admissoes"] > 0].copy()
    subtitulo_cargo = f" — Cargo: {filtros['termo_ocupacao']}" if (filtros and filtros.get("termo_ocupacao")) else ""
    if not df_ativos.empty:
        mais_contrata = df_ativos.sort_values("admissoes", ascending=False).iloc[0]
        maior_saldo = df_ativos.sort_values("saldo", ascending=False).iloc[0]
        ini_s = str(mais_contrata["inicio"])[:7]
        fim_s = str(mais_contrata["fim"])[:7]
        with st.container(border=True):
            st.markdown(f"#### Destaques Setoriais (Janela de 12 meses: {ini_s} a {fim_s}){subtitulo_cargo}")
            k1, k2, k3 = st.columns(3)
            k1.metric(
                "Setor que Mais Contratou",
                f"Seção {mais_contrata['codigo_secao']} ({fmt_int(mais_contrata['admissoes'])})",
                str(mais_contrata["descricao_secao"])[:45],
                delta_color="off",
            )
            k2.metric(
                "Setor com Maior Saldo Líquido",
                f"Seção {maior_saldo['codigo_secao']} ({fmt_int(maior_saldo['saldo'], com_sinal=True)} vagas)",
                str(maior_saldo["descricao_secao"])[:45],
                delta_color="off",
            )
            k3.metric(
                "Total de Setores Ativos",
                f"{len(df_ativos)} seções CNAE",
                f"{int(mais_contrata['competencias_disponiveis'])} meses com dados na janela",
                delta_color="off",
            )

    df_tab = pd.DataFrame({
        "Rank Contratações": df_bruto["ranking_admissoes"].map(lambda r: f"{int(r)}º"),
        "Seção": df_bruto["codigo_secao"],
        "Setor Econômico (CNAE)": df_bruto["descricao_secao"],
        "Contratações (12m)": df_bruto["admissoes"].map(fmt_int),
        "Demissões (12m)": df_bruto["desligamentos"].map(fmt_int),
        "Saldo de Vagas (12m)": df_bruto["saldo"].map(lambda v: fmt_int(v, com_sinal=True)),
        "Rank Demissões": df_bruto["ranking_desligamentos"].map(lambda r: f"{int(r)}º"),
    })

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Ranking dos Setores Econômicos (Últimos 12 Meses)**")
        st.dataframe(df_tab, width="stretch", hide_index=True)
    with c2:
        st.markdown("**Top 10 Setores por Volume de Contratações**")
        top10 = df_ativos.head(10).copy()
        if not top10.empty:
            top10["Setor"] = top10["codigo_secao"] + " - " + top10["descricao_secao"].str.slice(0, 24)
            st.bar_chart(
                top10.set_index("Setor")[["admissoes", "desligamentos"]].rename(
                    columns={"admissoes": "Contratações", "desligamentos": "Demissões"}
                )
            )


def renderizar_resultado_p2(df_bruto: pd.DataFrame, filtros: dict[str, Any] | None = None) -> None:
    """Consolida e exibe o padrão sazonal por mês do ano (Janeiro a Dezembro)."""
    df_val = df_bruto.dropna(subset=["admissoes", "desligamentos", "saldo"]).copy()
    por_mes = (
        df_val.groupby("mes", as_index=False)
        .agg(
            admissoes=("admissoes", "sum"),
            desligamentos=("desligamentos", "sum"),
            saldo=("saldo", "sum"),
            anos=("ano", "nunique"),
        )
        .sort_values("mes")
    )
    por_mes["nome_mes"] = por_mes["mes"].map(lambda m: NOMES_MESES.get(int(m), str(m)))
    por_mes["media_saldo"] = por_mes["saldo"] / por_mes["anos"].replace(0, 1)
    subtitulo_cargo = f" — Cargo: {filtros['termo_ocupacao']}" if (filtros and filtros.get("termo_ocupacao")) else ""

    if not por_mes.empty:
        melhor = por_mes.sort_values("saldo", ascending=False).iloc[0]
        pior = por_mes.sort_values("saldo", ascending=True).iloc[0]
        with st.container(border=True):
            st.markdown(f"#### Comportamento Sazonal Consolidado (Janeiro a Dezembro){subtitulo_cargo}")
            k1, k2, k3 = st.columns(3)
            k1.metric(
                "Mês de Maior Saldo Positivo",
                str(melhor["nome_mes"]),
                f"Saldo acumulado: {fmt_int(melhor['saldo'], com_sinal=True)} vagas",
                delta_color="off",
            )
            k2.metric(
                "Mês de Maior Retração (Demissões)",
                str(pior["nome_mes"]),
                f"Saldo acumulado: {fmt_int(pior['saldo'], com_sinal=True)} vagas",
                delta_color="off",
            )
            k3.metric(
                "Meses Analisados na Série",
                f"{df_val['competencia'].nunique()} competências",
                f"De {str(df_val['competencia'].min())[:7]} a {str(df_val['competencia'].max())[:7]}",
                delta_color="off",
            )

    df_tab = pd.DataFrame({
        "Mês do Ano": por_mes["nome_mes"],
        "Contratações Acumuladas": por_mes["admissoes"].map(fmt_int),
        "Demissões Acumuladas": por_mes["desligamentos"].map(fmt_int),
        "Saldo Líquido Acumulado": por_mes["saldo"].map(lambda v: fmt_int(v, com_sinal=True)),
        "Média de Saldo por Ano": por_mes["media_saldo"].map(lambda v: fmt_int(v, com_sinal=True)),
    })

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Tabela Sazonal Consolidada pelos 12 Meses do Ano**")
        st.dataframe(df_tab, width="stretch", hide_index=True)
    with c2:
        st.markdown("**Saldo Líquido por Mês do Calendário (Jan a Dez)**")
        if not por_mes.empty:
            st.bar_chart(
                por_mes.set_index("nome_mes")[["saldo"]].rename(columns={"saldo": "Saldo Acumulado"}),
                color="#2563eb",
            )


def renderizar_resultado_p4(df_bruto: pd.DataFrame, filtros: dict[str, Any] | None = None) -> None:
    """Consolida e exibe a relação entre rotatividade (fluxos pareados) e salário médio setorial."""
    df_val = df_bruto.dropna(subset=["salario_medio_admissao", "indice_fluxos_pareados_pct"]).copy()
    corr_val = df_bruto["correlacao_pearson"].iloc[0] if "correlacao_pearson" in df_bruto.columns else None
    corr_str = f"{float(corr_val):.3f}".replace(".", ",") if (corr_val is not None and not pd.isna(corr_val)) else "N/A"
    subtitulo_cargo = f" — Cargo: {filtros['termo_ocupacao']}" if (filtros and filtros.get("termo_ocupacao")) else ""

    if not df_val.empty:
        maior_rot = df_val.sort_values("indice_fluxos_pareados_pct", ascending=False).iloc[0]
        maior_sal = df_val.sort_values("salario_medio_admissao", ascending=False).iloc[0]
        with st.container(border=True):
            st.markdown(f"#### Relação entre Rotatividade (Fluxos Pareados) e Salário Inicial{subtitulo_cargo}")
            k1, k2, k3 = st.columns(3)
            k1.metric(
                "Correlação de Pearson (r)",
                corr_str,
                "Entre equilíbrio de fluxos (%) e salário médio (R$)",
                delta_color="off",
            )
            k2.metric(
                f"Maior Rotatividade (Seção {maior_rot['codigo_secao']})",
                fmt_pct(maior_rot["indice_fluxos_pareados_pct"]),
                f"Salário médio: {fmt_moeda(maior_rot['salario_medio_admissao'])}",
                delta_color="off",
            )
            k3.metric(
                f"Maior Salário Médio (Seção {maior_sal['codigo_secao']})",
                fmt_moeda(maior_sal["salario_medio_admissao"]),
                f"Índice de fluxos: {fmt_pct(maior_sal['indice_fluxos_pareados_pct'])}",
                delta_color="off",
            )

    df_ord = df_bruto.sort_values("indice_fluxos_pareados_pct", ascending=False).copy()
    df_tab = pd.DataFrame({
        "Seção": df_ord["codigo_secao"],
        "Setor Econômico (CNAE)": df_ord["codigo_secao"].map(lambda s: SECOES_CNAE_OFICIAIS.get(str(s), str(s))),
        "Índice de Fluxos / Rotatividade (%)": df_ord["indice_fluxos_pareados_pct"].map(fmt_pct),
        "Salário Médio Inicial": df_ord["salario_medio_admissao"].map(fmt_moeda),
        "Contratações": df_ord["admissoes"].map(fmt_int),
        "Demissões": df_ord["desligamentos"].map(fmt_int),
        "Saldo de Vagas": df_ord["saldo"].map(lambda v: fmt_int(v, com_sinal=True)),
    })

    c1, c2 = st.columns([3, 2])
    with c1:
        st.markdown("**Setores Ordenados por Índice de Rotatividade (Fluxos Pareados)**")
        st.dataframe(df_tab, width="stretch", hide_index=True)
    with c2:
        st.markdown("**Salário Médio Inicial por Setor (R$)**")
        if not df_val.empty:
            df_plot = df_val.copy()
            df_plot["Setor"] = df_plot["codigo_secao"] + " - " + df_plot["codigo_secao"].map(
                lambda s: SECOES_CNAE_OFICIAIS.get(str(s), str(s))[:22]
            )
            st.bar_chart(
                df_plot.set_index("Setor")[["salario_medio_admissao"]].rename(
                    columns={"salario_medio_admissao": "Salário Médio (R$)"}
                ),
                color="#2563eb",
            )


def renderizar_drilldown_profissao(
    caminho_str: str,
    assistente: AssistenteTextToSQL,
    codigos_cbo: list[str],
    rotulo_cargo: str,
    uf_filtro: str | None,
    ano_filtro: int | None,
    chave_prefixo: str,
) -> None:
    """Exibe o detalhamento (drill-down) de uma profissão por Sexo, Escolaridade, Raça/Cor, Idade e Capital/Interior."""
    st.markdown(f"#### Detalhamento de Perfil e Geografia para: {rotulo_cargo}")
    opcoes_visao = {
        "sexo": "Sexo (Homem vs. Mulher)",
        "escolaridade": "Escolaridade",
        "raca_cor": "Raça/Cor",
        "faixa_etaria": "Faixa Etária",
        "capital_interior": "Capitais vs. Interior",
        "sazonalidade": "Sazonalidade Mensal (Jan–Dez)",
    }
    visao_escolhida = st.radio(
        "Selecione o recorte para detalhar esta profissão:",
        options=list(opcoes_visao.keys()),
        format_func=lambda k: opcoes_visao[k],
        horizontal=True,
        key=f"{chave_prefixo}_visao",
    )

    with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
        if visao_escolhida in ("sexo", "escolaridade", "raca_cor", "faixa_etaria"):
            resp_sub = assistente.responder(
                conn,
                "Como o perfil sociodemográfico impacta o salário médio de admissão?",
                filtro_cargo=rotulo_cargo,
                codigos_cbo_override=codigos_cbo,
                sigla_uf_override=uf_filtro,
                ano_override=ano_filtro,
                eixo_override=visao_escolhida,
            )
            df_sub = pd.DataFrame(resp_sub.linhas, columns=resp_sub.colunas)
            if df_sub.empty:
                st.info("Não há movimentações registradas para este cargo no recorte selecionado.")
            else:
                renderizar_resultado_p5(
                    df_sub,
                    resp_sub.filtros_aplicados,
                    chave_radio=f"{chave_prefixo}_p5_eixo",
                )
        elif visao_escolhida == "capital_interior":
            resp_sub = assistente.responder(
                conn,
                "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?",
                filtro_cargo=rotulo_cargo,
                codigos_cbo_override=codigos_cbo,
                sigla_uf_override=uf_filtro,
                ano_override=ano_filtro,
            )
            df_sub = pd.DataFrame(resp_sub.linhas, columns=resp_sub.colunas)
            if df_sub.empty:
                st.info("Não há movimentações registradas para este cargo no recorte selecionado.")
            else:
                renderizar_resultado_p3(df_sub, resp_sub.filtros_aplicados)
        elif visao_escolhida == "sazonalidade":
            resp_sub = assistente.responder(
                conn,
                "Existe sazonalidade nas contratações e demissões ao longo dos meses do ano?",
                filtro_cargo=rotulo_cargo,
                codigos_cbo_override=codigos_cbo,
                sigla_uf_override=uf_filtro,
                ano_override=ano_filtro,
            )
            df_sub = pd.DataFrame(resp_sub.linhas, columns=resp_sub.colunas)
            if df_sub.empty:
                st.info("Não há movimentações registradas para este cargo no recorte selecionado.")
            else:
                renderizar_resultado_p2(df_sub, resp_sub.filtros_aplicados)


def renderizar_resultado_cbo(
    df_bruto: pd.DataFrame,
    caminho_str: str | None = None,
    assistente: AssistenteTextToSQL | None = None,
    filtros: dict[str, Any] | None = None,
) -> None:
    """Exibe de forma direta os indicadores para profissões CBO consultadas."""
    tot_adm = int(df_bruto["admissoes"].sum())
    tot_des = int(df_bruto["desligamentos"].sum())
    tot_saldo = int(df_bruto["saldo"].sum())
    lider = df_bruto.iloc[0]

    with st.container(border=True):
        st.markdown(f"#### Indicadores para a Profissão: {lider['codigo_cbo']} — {lider['titulo_ocupacao']}")
        k1, k2, k3, k4 = st.columns(4)
        k1.metric("Contratações (Soma Top CBOs)", fmt_int(tot_adm))
        k2.metric("Demissões (Soma Top CBOs)", fmt_int(tot_des))
        k3.metric("Saldo de Vagas", fmt_int(tot_saldo, com_sinal=True))
        k4.metric("Salário Médio (Cargo Principal)", fmt_moeda(lider["salario_medio_admissao"]))

    df_tab = pd.DataFrame({
        "Código CBO": df_bruto["codigo_cbo"],
        "Profissão Oficial (CBO 2002)": df_bruto["titulo_ocupacao"],
        "Contratações": df_bruto["admissoes"].map(fmt_int),
        "Demissões": df_bruto["desligamentos"].map(fmt_int),
        "Saldo de Vagas": df_bruto["saldo"].map(lambda v: fmt_int(v, com_sinal=True)),
        "Salário Médio Inicial": df_bruto["salario_medio_admissao"].map(fmt_moeda),
        "Amostra de Salários (n)": df_bruto["qtd_salarios_admissao"].map(fmt_int),
    })
    st.markdown("**Cargos CBO Encontrados e Seus Indicadores**")
    st.dataframe(df_tab, width="stretch", hide_index=True)

    if caminho_str and assistente and filtros and filtros.get("codigos_cbo"):
        st.divider()
        renderizar_drilldown_profissao(
            caminho_str=caminho_str,
            assistente=assistente,
            codigos_cbo=list(filtros["codigos_cbo"]),
            rotulo_cargo=str(filtros.get("termo_ocupacao") or lider["titulo_ocupacao"]),
            uf_filtro=filtros.get("sigla_uf"),
            ano_filtro=filtros.get("ano"),
            chave_prefixo="drill_aba1_cbo",
        )


def renderizar_resposta_consolidada(
    resposta: RespostaTextToSQL,
    caminho_str: str | None = None,
    assistente: AssistenteTextToSQL | None = None,
    chave_prefixo: str = "resp_padrao",
) -> None:
    """Direciona a resposta do assistente para a visualização consolidada correta."""
    df_bruto = pd.DataFrame(resposta.linhas, columns=resposta.colunas)
    if df_bruto.empty:
        st.warning("Nenhum dado encontrado para os filtros informados.")
        return

    st.caption(f"Contrato acionado: **{resposta.titulo_intencao}**  |  {descrever_filtros(resposta.filtros_aplicados)}")

    if resposta.ocupacoes_resolvidas and resposta.intencao != "cbo_ocupacao":
        nomes_cbo = [f"{o['codigo_cbo']} ({o['titulo_ocupacao']})" for o in resposta.ocupacoes_resolvidas]
        st.info(f"**Recorte de Cargo Ativo (CBO 2002):** {'  |  '.join(nomes_cbo)}")

    if resposta.intencao == "p5_perfil_remuneracao":
        # Se a consulta retornou apenas 1 eixo, permite trocar para qualquer eixo demográfico mantendo o mesmo cargo/UF/ano
        if caminho_str and assistente:
            eixo_inicial = resposta.filtros_aplicados.get("eixo", "sexo")
            opcoes_eixo = ["sexo", "escolaridade", "raca_cor", "faixa_etaria"]
            idx_eixo = opcoes_eixo.index(eixo_inicial) if eixo_inicial in opcoes_eixo else 0
            eixo_escolhido = st.radio(
                "Dimensão demográfica exibida (clique para alternar mantendo o mesmo filtro de cargo/UF/ano):",
                options=opcoes_eixo,
                index=idx_eixo,
                format_func=lambda e: MAPA_EIXOS_DEMOGRAFICOS.get(e, e),
                horizontal=True,
                key=f"{chave_prefixo}_seletor_eixo_p5",
            )
            if eixo_escolhido != eixo_inicial:
                with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
                    resposta = assistente.responder(
                        conn,
                        resposta.pergunta_original,
                        filtro_cargo=resposta.filtros_aplicados.get("termo_ocupacao"),
                        codigos_cbo_override=resposta.filtros_aplicados.get("codigos_cbo"),
                        sigla_uf_override=resposta.filtros_aplicados.get("sigla_uf"),
                        ano_override=resposta.filtros_aplicados.get("ano"),
                        eixo_override=eixo_escolhido,
                    )
                    df_bruto = pd.DataFrame(resposta.linhas, columns=resposta.colunas)
        renderizar_resultado_p5(df_bruto, resposta.filtros_aplicados, chave_radio=f"{chave_prefixo}_p5_interno")
    elif resposta.intencao == "p3_capitais_interior":
        renderizar_resultado_p3(df_bruto, resposta.filtros_aplicados)
    elif resposta.intencao == "p1_setores_df":
        renderizar_resultado_p1(df_bruto, resposta.filtros_aplicados)
    elif resposta.intencao == "p2_sazonalidade":
        renderizar_resultado_p2(df_bruto, resposta.filtros_aplicados)
    elif resposta.intencao == "p4_fluxos_salarios":
        renderizar_resultado_p4(df_bruto, resposta.filtros_aplicados)
    elif resposta.intencao == "cbo_ocupacao":
        renderizar_resultado_cbo(df_bruto, caminho_str, assistente, resposta.filtros_aplicados)
    else:
        st.dataframe(df_bruto, width="stretch", hide_index=True)

    with st.expander("Detalhes Técnicos, Fórmula e SQL Executado (Auditoria BD2 / ADR-0007)"):
        st.markdown(f"- **Identificador do contrato:** `{resposta.intencao}`")
        st.markdown(f"- **Fórmula da métrica:** `{resposta.formula_metrica}`")
        st.markdown(f"- **Ressalva metodológica:** {resposta.ressalva_metodologica}")
        if resposta.ocupacoes_resolvidas:
            st.markdown("**Ocupações CBO resolvidas pelo índice vetorial (384d):**")
            st.dataframe(pd.DataFrame(resposta.ocupacoes_resolvidas), width="stretch", hide_index=True)
        st.markdown("**Consulta SQL executada em modo somente leitura (`READ_ONLY`) sobre o schema `gold`:**")
        st.code(resposta.sql_gerado, language="sql")


def renderizar_aba_assistente(caminho_str: str, assistente: AssistenteTextToSQL, indice: IndiceVetorialCBO) -> None:
    if "pergunta_ativa" not in st.session_state:
        st.session_state["pergunta_ativa"] = "Qual a diferença salarial entre homens e mulheres?"
    if "filtro_cargo_aba1" not in st.session_state:
        st.session_state["filtro_cargo_aba1"] = ""

    with st.container(border=True):
        st.markdown("#### Faça uma pergunta em português sobre empregos, salários, setores ou profissões")
        with st.form("form_assistente", clear_on_submit=False, border=False):
            c_input, c_btn = st.columns([5, 1])
            with c_input:
                texto_digitado = st.text_input(
                    "Digite sua pergunta:",
                    value=st.session_state["pergunta_ativa"],
                    placeholder="Ex.: Qual a diferença salarial entre homens e mulheres para professor?",
                    label_visibility="collapsed",
                )
            with c_btn:
                enviado = st.form_submit_button("Consultar", type="primary", width="stretch")
            if enviado:
                st.session_state["pergunta_ativa"] = texto_digitado

        st.markdown("**Filtrar / Detalhar a Consulta Atual por Cargo (CBO), Estado (UF) e Ano:**")
        f1, f2, f3, f4 = st.columns([2, 2, 1, 1])
        with f1:
            mapa_rapido = dict(OPCOES_CARGO_RAPIDO)
            escolha_rapida = st.selectbox(
                "Seleção rápida de cargo:",
                options=list(mapa_rapido.keys()),
                index=0,
                key="sel_cargo_rapido_aba1",
            )
        with f2:
            valor_padrao_cargo = mapa_rapido[escolha_rapida] if mapa_rapido[escolha_rapida] else st.session_state["filtro_cargo_aba1"]
            cargo_digitado = st.text_input(
                "Ou digite qualquer cargo / profissão / CBO:",
                value=valor_padrao_cargo,
                placeholder="Ex.: professor, enfermeiro, motorista, 231210...",
            )
            st.session_state["filtro_cargo_aba1"] = cargo_digitado.strip()
        with f3:
            uf_aba1 = st.selectbox(
                "Estado (UF):",
                options=["Todos", "DF", "GO", "MT", "MS"],
                index=0,
                key="sel_uf_aba1",
            )
        with f4:
            ano_aba1 = st.selectbox(
                "Ano:",
                options=["Todos", 2023, 2024, 2025, 2026],
                index=0,
                key="sel_ano_aba1",
            )

        st.caption("Atalhos rápidos de perguntas (funcionam tanto para o Mercado Geral quanto para o Cargo selecionado acima):")
        cols_a1 = st.columns(5)
        for i in range(5):
            rotulo, perg = ATALHOS_PERGUNTAS[i]
            if cols_a1[i].button(rotulo, key=f"btn_p_{i}", width="stretch"):
                st.session_state["pergunta_ativa"] = perg
                st.rerun()

        cols_a2 = st.columns(5)
        for j in range(5):
            rotulo, perg = ATALHOS_PERGUNTAS[5 + j]
            if cols_a2[j].button(rotulo, key=f"btn_p_{5 + j}", width="stretch"):
                st.session_state["pergunta_ativa"] = perg
                st.rerun()

    pergunta_atual = st.session_state["pergunta_ativa"].strip()
    if not pergunta_atual:
        return

    filtro_cargo_efetivo = cargo_digitado.strip() or None
    uf_override = None if uf_aba1 == "Todos" else uf_aba1
    ano_override = None if ano_aba1 == "Todos" else int(ano_aba1)

    # Se houver um filtro de cargo explícito na caixa de filtro, permite refinar os códigos CBO exatos
    codigos_cbo_override: list[str] | None = None
    if filtro_cargo_efetivo:
        candidatos_cbo = indice.buscar_semantico(filtro_cargo_efetivo, top_k=5, apenas_oficiais=True)
        if not candidatos_cbo:
            candidatos_cbo = indice.buscar_semantico(filtro_cargo_efetivo, top_k=5, apenas_oficiais=False)
        if candidatos_cbo:
            opcoes_c = [r.codigo_cbo for r in candidatos_cbo]
            mapa_t = {r.codigo_cbo: r.titulo_ocupacao for r in candidatos_cbo}
            codigos_cbo_override = st.multiselect(
                f"Ocupações CBO consideradas para o cargo \"{filtro_cargo_efetivo}\" (você pode marcar/desmarcar para isolar um CBO específico):",
                options=opcoes_c,
                default=opcoes_c[:3],
                format_func=lambda c: f"{c} — {mapa_t.get(c, c)}",
                key=f"multi_cbo_aba1_{filtro_cargo_efetivo}",
            )

    with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
        resposta = assistente.responder(
            conn,
            pergunta_atual,
            filtro_cargo=filtro_cargo_efetivo,
            codigos_cbo_override=codigos_cbo_override,
            sigla_uf_override=uf_override,
            ano_override=ano_override,
        )

    if not resposta.suportada:
        with st.container(border=True):
            if resposta.intencao == "bloqueada_seguranca":
                st.error(f"**Consulta Bloqueada pela Camada de Segurança / LGPD**\n\n{resposta.motivo_recusa}")
            else:
                st.warning(f"**Consulta Fora do Escopo Metodológico**\n\n{resposta.motivo_recusa}")
            st.caption(f"Nota metodológica: {resposta.ressalva_metodologica}")
        return

    renderizar_resposta_consolidada(resposta, caminho_str, assistente, chave_prefixo="aba1")


def renderizar_aba_busca_cbo(caminho_str: str, indice: IndiceVetorialCBO, assistente: AssistenteTextToSQL) -> None:
    if "busca_cbo_termo" not in st.session_state:
        st.session_state["busca_cbo_termo"] = "professor"

    with st.container(border=True):
        st.markdown("#### Pesquisar Profissão e Analisar Perfil Completo (CBO 2002)")
        st.caption(
            "Pesquise por nome popular, sinônimo ou código CBO de 6 dígitos "
            "(ex.: professor, programador, caminhoneiro, caixa de supermercado, enfermeiro, 231210)."
        )
        c_busca, c_uf, c_ano = st.columns([3, 1, 1])
        with c_busca:
            termo_cbo = st.text_input(
                "Profissão ou código CBO:",
                value=st.session_state["busca_cbo_termo"],
                label_visibility="collapsed",
            )
            st.session_state["busca_cbo_termo"] = termo_cbo
        with c_uf:
            uf_sel = st.selectbox(
                "Estado (UF):",
                options=["Todos (Centro-Oeste)", "DF", "GO", "MT", "MS"],
                index=0,
                label_visibility="collapsed",
            )
        with c_ano:
            ano_sel = st.selectbox(
                "Ano:",
                options=["Todos (2023–2026)", 2023, 2024, 2025, 2026],
                index=0,
                label_visibility="collapsed",
            )

        st.caption("Atalhos de profissões:")
        cols_p = st.columns(len(ATALHOS_PROFISSOES))
        for idx, (rot, val) in enumerate(ATALHOS_PROFISSOES):
            if cols_p[idx].button(rot, key=f"btn_cbo_{idx}", width="stretch"):
                st.session_state["busca_cbo_termo"] = val
                st.rerun()

    consulta_limpa = st.session_state["busca_cbo_termo"].strip()
    if not consulta_limpa:
        return

    uf_filtro = None if uf_sel.startswith("Todos") else uf_sel
    ano_filtro = None if str(ano_sel).startswith("Todos") else int(ano_sel)

    resultados_sem = indice.buscar_semantico(consulta_limpa, top_k=5, apenas_oficiais=True)
    if not resultados_sem:
        resultados_sem = indice.buscar_semantico(consulta_limpa, top_k=5, apenas_oficiais=False)
    resultados_lex = indice.buscar_lexico(consulta_limpa, top_k=5, apenas_oficiais=True)

    if not resultados_sem:
        st.warning("Nenhuma ocupação CBO encontrada para o termo informado.")
        return

    opcoes_cod = [r.codigo_cbo for r in resultados_sem]
    mapa_tit = {r.codigo_cbo: r.titulo_ocupacao for r in resultados_sem}

    codigos_escolhidos = st.multiselect(
        "Ocupações CBO selecionadas para cálculo dos indicadores e perfil demográfico (marque uma ou mais):",
        options=opcoes_cod,
        default=opcoes_cod[:3],
        format_func=lambda c: f"{c} — {mapa_tit.get(c, c)}",
        key=f"multi_aba2_{consulta_limpa}",
    )

    if codigos_escolhidos:
        with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
            ind_sel = consultar_indicadores_cbo(
                conn,
                codigos_cbo=codigos_escolhidos,
                sigla_uf=uf_filtro,
                ano=ano_filtro,
            )
            ind_top5 = consultar_indicadores_cbo(
                conn,
                codigos_cbo=opcoes_cod,
                sigla_uf=uf_filtro,
                ano=ano_filtro,
            )

        with st.container(border=True):
            st.markdown(f"#### Indicadores Consolidados da Profissão: \"{consulta_limpa}\"")
            k1, k2, k3, k4 = st.columns(4)
            k1.metric("Contratações (Admissões)", fmt_int(ind_sel["admissoes"]))
            k2.metric("Demissões (Desligamentos)", fmt_int(ind_sel["desligamentos"]))
            k3.metric("Saldo Líquido de Vagas", fmt_int(ind_sel["saldo"], com_sinal=True))
            k4.metric("Salário Médio Inicial", fmt_moeda(ind_sel["salario_medio_admissao"]))

        mapa_ind = {item["codigo_cbo"]: item for item in ind_top5["por_ocupacao"]}
        linhas_cbo = []
        for r in resultados_sem:
            d = mapa_ind.get(r.codigo_cbo, {})
            linhas_cbo.append({
                "Código CBO": r.codigo_cbo,
                "Título Oficial da Ocupação (MTE)": r.titulo_ocupacao,
                "Similaridade": f"{r.score:.3f}",
                "Contratações": fmt_int(d.get("admissoes", 0)),
                "Demissões": fmt_int(d.get("desligamentos", 0)),
                "Saldo de Vagas": fmt_int(d.get("saldo", 0), com_sinal=True),
                "Salário Médio Inicial": fmt_moeda(d.get("salario_medio_admissao")),
            })

        c_t, c_g = st.columns([3, 2])
        with c_t:
            st.markdown("**Top 5 Ocupações Encontradas por Similaridade Semântica**")
            st.dataframe(pd.DataFrame(linhas_cbo), width="stretch", hide_index=True)
        with c_g:
            if ind_sel["por_uf"]:
                st.markdown("**Salário Médio Inicial por Estado (UF)**")
                df_uf = pd.DataFrame(ind_sel["por_uf"])
                st.bar_chart(
                    df_uf.set_index("sigla_uf")[["salario_medio_admissao"]].rename(
                        columns={"salario_medio_admissao": "Salário Médio (R$)"}
                    ),
                    color="#2563eb",
                )

        st.divider()
        renderizar_drilldown_profissao(
            caminho_str=caminho_str,
            assistente=assistente,
            codigos_cbo=codigos_escolhidos,
            rotulo_cargo=consulta_limpa,
            uf_filtro=uf_filtro,
            ano_filtro=ano_filtro,
            chave_prefixo="drill_aba2",
        )

        with st.expander("Auditoria Técnica: Comparação com Busca Léxica Tradicional (ADR-0007)"):
            st.markdown(
                f"- **Índice vetorial:** `{indice.versao_indice}` (`384 dimensões L2`)\n"
                f"- **Ocupações indexadas em `gold.dim_cbo`:** `{fmt_int(len(indice.registros))}`"
            )
            if not resultados_lex:
                st.info(
                    "A busca textual tradicional (`ILIKE` por palavras exatas) retornou 0 resultados para este termo, "
                    "enquanto a busca vetorial de 384 dimensões recuperou as ocupações por proximidade semântica."
                )
            else:
                st.dataframe(
                    pd.DataFrame([
                        {
                            "Código CBO": r.codigo_cbo,
                            "Título Oficial": r.titulo_ocupacao,
                            "Score Léxico": f"{r.score:.3f}",
                        }
                        for r in resultados_lex
                    ]),
                    width="stretch",
                    hide_index=True,
                )


def renderizar_aba_perguntas_gestao(caminho_str: str, assistente: AssistenteTextToSQL, indice: IndiceVetorialCBO) -> None:
    st.markdown("#### Painel Direto das 5 Perguntas Estratégicas do Projeto")
    mapa_p = {
        "P3 (Central) — Capitais vs. Interior": "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?",
        "P1 — Setores Econômicos no DF (12 Meses)": "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?",
        "P2 — Sazonalidade Mensal": "Existe sazonalidade nas contratações e demissões?",
        "P4 — Rotatividade vs. Salários": "Os setores com maior rotatividade praticam salários médios mais baixos?",
        "P5 — Perfil Sociodemográfico e Remuneração": "Como o perfil sociodemográfico impacta o salário médio de admissão?",
    }

    with st.container(border=True):
        escolha = st.radio(
            "Selecione a pergunta de gestão:",
            options=list(mapa_p.keys()),
            horizontal=True,
        )
        p1, p2, p3 = st.columns([2, 1, 1])
        with p1:
            cargo_p = st.text_input(
                "Filtrar por Cargo / Profissão (opcional):",
                value="",
                placeholder="Deixe em branco para Mercado Geral ou digite ex.: professor, enfermeiro, motorista...",
                key="cargo_aba3",
            )
        with p2:
            uf_p = st.selectbox(
                "Estado (UF):",
                options=["Todos", "DF", "GO", "MT", "MS"],
                index=0,
                key="uf_aba3",
            )
        with p3:
            ano_p = st.selectbox(
                "Ano:",
                options=["Todos", 2023, 2024, 2025, 2026],
                index=0,
                key="ano_aba3",
            )

    with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
        resp = assistente.responder(
            conn,
            mapa_p[escolha],
            filtro_cargo=cargo_p.strip() or None,
            sigla_uf_override=None if uf_p == "Todos" else uf_p,
            ano_override=None if ano_p == "Todos" else int(ano_p),
        )
    renderizar_resposta_consolidada(resp, caminho_str, assistente, chave_prefixo="aba3")


def main() -> None:
    st.set_page_config(
        page_title="METRA — Painel Analítico do Mercado de Trabalho (Centro-Oeste)",
        layout="wide",
    )

    st.markdown("## METRA — Monitoramento e Engenharia de Dados do Trabalho")
    st.caption(
        "Universidade de Brasília (FCTE/UnB) — Banco de Dados 2 (Squad G4)  |  "
        "Base: Novo CAGED (Centro-Oeste: DF, GO, MT e MS)  |  Motor Analítico: DuckDB (Camada Gold)"
    )

    caminho_duckdb = obter_caminho_duckdb()
    indice, assistente, resumo_geral = carregar_recursos_analiticos(str(caminho_duckdb))

    with st.container(border=True):
        m1, m2, m3, m4 = st.columns(4)
        m1.metric(
            "Movimentações Analisadas (2023–2026)",
            fmt_int(resumo_geral["total_movimentacoes"]),
        )
        m2.metric("Total de Contratações", fmt_int(resumo_geral["admissoes"]))
        m3.metric("Total de Demissões", fmt_int(resumo_geral["desligamentos"]))
        m4.metric(
            "Salário Médio Inicial (Centro-Oeste)",
            fmt_moeda(resumo_geral["salario_medio"]),
            f"Saldo acumulado: {fmt_int(resumo_geral['saldo'], com_sinal=True)} vagas",
            delta_color="off",
        )

    aba_consulta, aba_cbo, aba_painel = st.tabs([
        "1. Consulta em Linguagem Natural (Text-to-SQL)",
        "2. Busca de Profissões e Salários (CBO 2002)",
        "3. Painel das 5 Perguntas do Projeto",
    ])

    with aba_consulta:
        renderizar_aba_assistente(str(caminho_duckdb), assistente, indice)
    with aba_cbo:
        renderizar_aba_busca_cbo(str(caminho_duckdb), indice, assistente)
    with aba_painel:
        renderizar_aba_perguntas_gestao(str(caminho_duckdb), assistente, indice)


if __name__ == "__main__":
    main()
