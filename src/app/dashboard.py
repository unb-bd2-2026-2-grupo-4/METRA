"""Painel Analítico do METRA (E4) — Monitoramento e Engenharia de Dados do Trabalho.

Interface de Análise do Mercado de Trabalho, Busca Vetorial (CBO 2002) e Consultas SQL.
Execução:
    streamlit run src/app/dashboard.py
"""

from __future__ import annotations

import html
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import duckdb
import pandas as pd
import streamlit as st

from src.app.banco_analitico import (
    SECOES_CNAE_OFICIAIS,
    abrir_conexao_analitica,
    obter_caminho_duckdb,
)
from src.app.busca_cbo import IndiceVetorialCBO, consultar_indicadores_cbo
from src.app.text_to_sql import AssistenteTextToSQL, RespostaTextToSQL

# ==============================================================================
# ESTILO SÓBRIO E INSTITUCIONAL
# ==============================================================================

ESTILO_CSS = """
<style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

    html, body, [class*="css"] {
        font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
    }

    .block-container {
        padding-top: 1.5rem;
        padding-bottom: 2.5rem;
        max-width: 1320px;
    }

    /* Cartões de métricas sóbrios */
    .kpi-box {
        padding: 0.95rem 1.15rem;
        background: rgba(148, 163, 184, 0.06);
        border: 1px solid rgba(148, 163, 184, 0.22);
        border-radius: 6px;
        min-height: 96px;
    }
    .kpi-label {
        font-size: 0.75rem;
        font-weight: 500;
        color: #64748b;
        margin-bottom: 0.3rem;
    }
    .kpi-number {
        font-size: 1.45rem;
        font-weight: 600;
        line-height: 1.2;
        font-variant-numeric: tabular-nums;
        letter-spacing: -0.02em;
    }
    .kpi-meta {
        font-size: 0.76rem;
        color: #64748b;
        margin-top: 0.3rem;
        font-variant-numeric: tabular-nums;
    }

    /* Cabeçalho discreto */
    .header-meta {
        font-size: 0.82rem;
        color: #64748b;
        margin-top: -0.4rem;
        margin-bottom: 1rem;
    }

    /* Abas limpas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 1.25rem;
        border-bottom: 1px solid rgba(148, 163, 184, 0.25);
        padding-bottom: 0;
        background: transparent;
    }
    .stTabs [data-baseweb="tab"] {
        height: 38px;
        padding: 0 4px;
        font-weight: 500;
        font-size: 0.88rem;
        background: transparent;
    }
</style>
"""

NOMES_MESES = {
    1: "Jan", 2: "Fev", 3: "Mar", 4: "Abr",
    5: "Mai", 6: "Jun", 7: "Jul", 8: "Ago",
    9: "Set", 10: "Out", 11: "Nov", 12: "Dez",
}

MAPA_EIXOS_DEMOGRAFICOS = {
    "sexo": "Sexo",
    "escolaridade": "Escolaridade",
    "raca_cor": "Raça/Cor",
    "faixa_etaria": "Faixa Etária",
}

SUGESTOES_PROFISSOES = [
    ("Professor", "professor"),
    ("Desenvolvedor", "desenvolvedor de software"),
    ("Enfermeiro", "enfermeiro"),
    ("Médico", "medico"),
    ("Engenheiro Civil", "engenheiro civil"),
    ("Vendedor", "vendedor"),
    ("Caminhoneiro", "caminhoneiro"),
    ("Pedreiro", "pedreiro"),
]

PERGUNTAS_EXEMPLO = [
    ("Diferença por sexo", "Qual a diferença salarial entre homens e mulheres?"),
    ("Escolaridade", "Como a escolaridade impacta o salário médio de admissão?"),
    ("Capitais vs. Interior", "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?"),
    ("Setores no DF", "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?"),
    ("Sazonalidade", "Existe sazonalidade nas contratações e demissões ao longo dos meses do ano?"),
    ("Rotatividade", "Os setores com maior rotatividade praticam salários médios mais baixos?"),
    ("Recorte por cargo", "Qual a diferença salarial entre homens e mulheres para o cargo de professor?"),
    ("Teste de bloqueio", "DROP TABLE gold.fct_movimentacao;"),
]


# ==============================================================================
# FORMATAÇÃO NUMÉRICA (PADRÃO BRASILEIRO)
# ==============================================================================

def fmt_int(valor: Any, com_sinal: bool = False) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    n = int(round(float(valor)))
    if com_sinal:
        sinal = "+" if n > 0 else ""
        return f"{sinal}{n:,}".replace(",", ".")
    return f"{n:,}".replace(",", ".")


def fmt_moeda(valor: Any) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    v = float(valor)
    texto = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def fmt_pct(valor: Any, com_sinal: bool = False) -> str:
    if valor is None or pd.isna(valor):
        return "—"
    v = float(valor)
    sinal = "+" if (com_sinal and v > 0) else ""
    return f"{sinal}{v:.1f}%".replace(".", ",")


# ==============================================================================
# RECURSOS E CACHE DE CONSULTAS (STREAMLIT CACHE)
# ==============================================================================

@st.cache_resource(show_spinner="Conectando ao banco analítico (DuckDB Gold)...")
def obter_conexao_cached(caminho_str: str) -> duckdb.DuckDBPyConnection:
    """Mantém conexão somente leitura (`read_only=True`) compartilhada na sessão."""
    return abrir_conexao_analitica(caminho_str)


@st.cache_resource(show_spinner="Carregando índice vetorial CBO e resumo da camada Gold...")
def carregar_recursos_analiticos(caminho_str: str) -> tuple[IndiceVetorialCBO, AssistenteTextToSQL, dict[str, Any]]:
    conn = obter_conexao_cached(caminho_str)
    indice = IndiceVetorialCBO.de_conexao_duckdb(conn)
    row = conn.execute("""
        SELECT
            COUNT(*) AS total_mov,
            COUNT(*) FILTER (WHERE saldo_movimentacao = 1) AS admissoes,
            COUNT(*) FILTER (WHERE saldo_movimentacao = -1) AS desligamentos,
            COALESCE(SUM(saldo_movimentacao), 0) AS saldo,
            SUM(CASE WHEN saldo_movimentacao = 1 AND salario_valido THEN salario_mensal ELSE 0 END)
                / NULLIF(COUNT(*) FILTER (WHERE saldo_movimentacao = 1 AND salario_valido), 0) AS sal_medio,
            MIN(competencia)::VARCHAR AS comp_min,
            MAX(competencia)::VARCHAR AS comp_max
        FROM gold.fct_movimentacao
        WHERE is_identificado AND is_centro_oeste AND ano BETWEEN 2023 AND 2026
    """).fetchone()

    resumo = {
        "total_movimentacoes": int(row[0] or 0),
        "admissoes": int(row[1] or 0),
        "desligamentos": int(row[2] or 0),
        "saldo": int(row[3] or 0),
        "salario_medio": float(row[4]) if row[4] is not None else None,
        "comp_min": (row[5] or "2023-01")[:7],
        "comp_max": (row[6] or "2026-01")[:7],
    }
    assistente = AssistenteTextToSQL(indice_cbo=indice)
    return indice, assistente, resumo


@st.cache_data(show_spinner=False)
def _executar_consulta_dict_cached(
    caminho_str: str,
    pergunta: str,
    filtro_cargo: str | None = None,
    codigos_cbo_override: tuple[str, ...] | None = None,
    sigla_uf_override: str | None = None,
    ano_override: int | None = None,
    eixo_override: str | None = None,
    codigo_secao_override: str | None = None,
) -> dict[str, Any]:
    conn = obter_conexao_cached(caminho_str)
    _, assistente, _ = carregar_recursos_analiticos(caminho_str)
    resp = assistente.responder(
        conn,
        pergunta,
        filtro_cargo=filtro_cargo,
        codigos_cbo_override=list(codigos_cbo_override) if codigos_cbo_override else None,
        sigla_uf_override=sigla_uf_override,
        ano_override=ano_override,
        eixo_override=eixo_override,
        codigo_secao_override=codigo_secao_override,
    )
    return resp.to_dict()


def obter_resposta_cached(
    caminho_str: str,
    pergunta: str,
    filtro_cargo: str | None = None,
    codigos_cbo_override: list[str] | None = None,
    sigla_uf_override: str | None = None,
    ano_override: int | None = None,
    eixo_override: str | None = None,
    codigo_secao_override: str | None = None,
) -> RespostaTextToSQL:
    dados = _executar_consulta_dict_cached(
        caminho_str=caminho_str,
        pergunta=pergunta,
        filtro_cargo=filtro_cargo,
        codigos_cbo_override=tuple(codigos_cbo_override) if codigos_cbo_override else None,
        sigla_uf_override=sigla_uf_override,
        ano_override=ano_override,
        eixo_override=eixo_override,
        codigo_secao_override=codigo_secao_override,
    )
    return RespostaTextToSQL(
        pergunta_original=dados["pergunta_original"],
        suportada=dados["suportada"],
        intencao=dados["intencao"],
        titulo_intencao=dados["titulo_intencao"],
        filtros_aplicados=dict(dados["filtros_aplicados"]),
        formula_metrica=dados["formula_metrica"],
        ressalva_metodologica=dados["ressalva_metodologica"],
        sql_gerado=dados["sql_gerado"],
        colunas=list(dados["colunas"]),
        linhas=[tuple(r) for r in dados["linhas"]],
        ocupacoes_resolvidas=list(dados["ocupacoes_resolvidas"]),
        motivo_recusa=dados["motivo_recusa"],
    )


@st.cache_data(show_spinner=False)
def consultar_indicadores_cbo_cached(
    caminho_str: str,
    codigos_cbo: tuple[str, ...],
    sigla_uf: str | None = None,
    ano: int | None = None,
) -> dict[str, Any]:
    conn = obter_conexao_cached(caminho_str)
    return consultar_indicadores_cbo(
        conn,
        codigos_cbo=list(codigos_cbo),
        sigla_uf=sigla_uf,
        ano=ano,
    )


@st.cache_data(show_spinner=False)
def consultar_kpis_recorte_cached(
    caminho_str: str,
    sigla_uf: str | None = None,
    ano: int | None = None,
    codigo_secao: str | None = None,
) -> dict[str, Any]:
    """Consulta os KPIs globais de saldo líquido e salário médio diretamente em gold.fct_setor_mensal."""
    conn = obter_conexao_cached(caminho_str)
    clausulas: list[str] = ["1 = 1"]
    if sigla_uf and sigla_uf in ("DF", "GO", "MT", "MS"):
        clausulas.append(f"sigla_uf = '{sigla_uf}'")
    if ano and int(ano) in (2023, 2024, 2025, 2026):
        clausulas.append(f"year(competencia) = {int(ano)}")
    if codigo_secao and str(codigo_secao).upper() in SECOES_CNAE_OFICIAIS:
        clausulas.append(f"codigo_secao = '{str(codigo_secao).upper()}'")
    where_sql = " AND ".join(clausulas)

    row = conn.execute(f"""
        SELECT
            COALESCE(SUM(admissoes), 0) AS admissoes,
            COALESCE(SUM(desligamentos), 0) AS desligamentos,
            COALESCE(SUM(saldo), 0) AS saldo,
            SUM(soma_salarios_admissao) / NULLIF(SUM(qtd_salarios_admissao), 0) AS salario_medio,
            COALESCE(SUM(qtd_salarios_admissao), 0) AS qtd_salarios
        FROM gold.fct_setor_mensal
        WHERE {where_sql}
    """).fetchone()

    return {
        "admissoes": int(row[0] or 0),
        "desligamentos": int(row[1] or 0),
        "saldo": int(row[2] or 0),
        "salario_medio": float(row[3]) if row[3] is not None else None,
        "qtd_salarios": int(row[4] or 0),
    }


# ==============================================================================
# COMPONENTES AUXILIARES
# ==============================================================================

def render_kpi(titulo: str, valor: str, detalhe: str = "") -> None:
    t_esc = html.escape(str(titulo))
    v_esc = html.escape(str(valor))
    d_esc = html.escape(str(detalhe))
    st.markdown(f"""
        <div class="kpi-box">
            <div class="kpi-label">{t_esc}</div>
            <div class="kpi-number">{v_esc}</div>
            <div class="kpi-meta">{d_esc}</div>
        </div>
    """, unsafe_allow_html=True)


def render_auditoria_expander(resposta: RespostaTextToSQL) -> None:
    with st.expander("Especificação técnica e consulta SQL executada"):
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown(f"**Contrato:** `{resposta.intencao}`")
            st.markdown(f"**Fórmula:** `{resposta.formula_metrica}`")
        with c2:
            st.markdown(f"**Nota metodológica:** {resposta.ressalva_metodologica}")

        if resposta.ocupacoes_resolvidas:
            st.markdown("**Códigos CBO associados:**")
            st.dataframe(pd.DataFrame(resposta.ocupacoes_resolvidas), hide_index=True)

        st.markdown("**SQL executado (`READ_ONLY` no schema `gold`):**")
        st.code(resposta.sql_gerado, language="sql")


# ==============================================================================
# PAINÉIS POR PERGUNTA DE GESTÃO (P1 A P5)
# ==============================================================================

def render_p3_capitais_interior(
    df_bruto: pd.DataFrame,
    cargo_label: str = "",
    filtros: dict[str, Any] | None = None,
) -> None:
    uf_filtro = (filtros or {}).get("sigla_uf")
    recorte_alvo = (
        uf_filtro
        if uf_filtro and uf_filtro in df_bruto["recorte"].values
        else ("Centro-Oeste" if "Centro-Oeste" in df_bruto["recorte"].values else str(df_bruto["recorte"].iloc[0]))
    )

    df_tot = df_bruto[df_bruto["nivel"] == "total"].copy()
    df_anual_recorte = (
        df_bruto[(df_bruto["nivel"] == "anual") & (df_bruto["recorte"] == recorte_alvo)]
        .sort_values("ano")
        .copy()
    )
    df_tot_recorte = df_tot[df_tot["recorte"] == recorte_alvo].copy()

    if not df_tot_recorte.empty:
        ref = df_tot_recorte.iloc[0]
    elif not df_tot.empty:
        ref = df_tot.iloc[0]
    elif not df_anual_recorte.empty:
        ref = df_anual_recorte.iloc[-1]
    else:
        ref = df_bruto.iloc[0]

    sufixo = f" — {cargo_label}" if cargo_label else ""
    st.markdown(f"#### Capitais vs. Interior ({recorte_alvo}){sufixo}")
    st.caption(
        "Comparação de saldo líquido de empregos e salário médio nominal de admissão "
        "entre capitais e municípios do interior (diferença = capital − interior)."
    )

    c1, c2, c3 = st.columns(3)
    with c1:
        render_kpi(
            "Salário médio (Capitais)",
            fmt_moeda(ref["salario_capital"]),
            f"Saldo: {fmt_int(ref['saldo_capital'], True)} vínculos · n = {fmt_int(ref.get('n_capital', 0))}",
        )
    with c2:
        render_kpi(
            "Salário médio (Interior)",
            fmt_moeda(ref["salario_interior"]),
            f"Saldo: {fmt_int(ref['saldo_interior'], True)} vínculos · n = {fmt_int(ref.get('n_interior', 0))}",
        )
    with c3:
        render_kpi(
            "Diferença (Capital − Interior)",
            fmt_moeda(ref["diferenca_salario"]),
            f"Diferença de saldo: {fmt_int(ref['diferenca_saldo'], True)} vínculos",
        )

    # Série anual 2023–2026 + Total (conciliada com python3 -m src.analise)
    partes_serie: list[pd.DataFrame] = []
    if not df_anual_recorte.empty:
        df_a = df_anual_recorte.copy()
        df_a["periodo"] = df_a["ano"].map(lambda a: str(int(a)) if pd.notna(a) else "—")
        partes_serie.append(df_a)
    if not df_tot_recorte.empty:
        df_t = df_tot_recorte.copy()
        df_t["periodo"] = "Total"
        partes_serie.append(df_t)

    if partes_serie:
        df_serie = pd.concat(partes_serie, ignore_index=True)
        st.write("")
        st.markdown(f"**Série anual 2023–2026 e consolidado ({recorte_alvo}) — Pergunta Central E1**")
        df_tabela_anual = pd.DataFrame({
            "Período": df_serie["periodo"],
            "Saldo Capital": df_serie["saldo_capital"].map(lambda v: fmt_int(v, True)),
            "Saldo Interior": df_serie["saldo_interior"].map(lambda v: fmt_int(v, True)),
            "Dif. Saldo (Cap. − Int.)": df_serie["diferenca_saldo"].map(lambda v: fmt_int(v, True)),
            "Salário Capital": df_serie["salario_capital"].map(fmt_moeda),
            "Salário Interior": df_serie["salario_interior"].map(fmt_moeda),
            "Dif. Salário (Cap. − Int.)": df_serie["diferenca_salario"].map(fmt_moeda),
            "n Capital": df_serie["n_capital"].map(fmt_int),
            "n Interior": df_serie["n_interior"].map(fmt_int),
        })
        st.dataframe(df_tabela_anual, hide_index=True)

    if not df_anual_recorte.empty and len(df_anual_recorte) > 1:
        st.write("")
        col_g_sal, col_g_saldo = st.columns([1, 1])
        df_plot_ano = df_anual_recorte.copy()
        df_plot_ano["Ano"] = df_plot_ano["ano"].map(lambda a: str(int(a)))
        df_plot_ano = df_plot_ano.set_index("Ano")

        with col_g_sal:
            st.markdown("**Salário médio de admissão por ano (R$)**")
            st.bar_chart(
                df_plot_ano[["salario_capital", "salario_interior"]].rename(
                    columns={"salario_capital": "Capitais", "salario_interior": "Interior"}
                ),
                height=260,
            )

        with col_g_saldo:
            st.markdown("**Saldo líquido de empregos por ano (vínculos)**")
            st.bar_chart(
                df_plot_ano[["saldo_capital", "saldo_interior"]].rename(
                    columns={"saldo_capital": "Capitais", "saldo_interior": "Interior"}
                ),
                height=260,
            )

    if not df_tot.empty:
        st.write("")
        col_chart, col_table = st.columns([1, 1])

        with col_chart:
            st.markdown("**Salário médio de admissão por UF (R$)**")
            df_plot = df_tot.set_index("recorte")[["salario_capital", "salario_interior"]].rename(
                columns={"salario_capital": "Capitais", "salario_interior": "Interior"}
            )
            st.bar_chart(df_plot, height=280)

        with col_table:
            st.markdown("**Resumo por Unidade da Federação**")
            df_exibir = pd.DataFrame({
                "Recorte": df_tot["recorte"],
                "Saldo Capital": df_tot["saldo_capital"].map(lambda v: fmt_int(v, True)),
                "Saldo Interior": df_tot["saldo_interior"].map(lambda v: fmt_int(v, True)),
                "Dif. Saldo": df_tot["diferenca_saldo"].map(lambda v: fmt_int(v, True)),
                "Salário Capital": df_tot["salario_capital"].map(fmt_moeda),
                "Salário Interior": df_tot["salario_interior"].map(fmt_moeda),
                "Dif. Salário (R$)": df_tot["diferenca_salario"].map(fmt_moeda),
            })
            st.dataframe(df_exibir, hide_index=True)


def render_p1_setores_df(
    df_bruto: pd.DataFrame,
    cargo_label: str = "",
    filtros: dict[str, Any] | None = None,
) -> None:
    df_ativos = df_bruto[df_bruto["admissoes"] > 0].copy()
    sufixo = f" — {cargo_label}" if cargo_label else ""
    uf_label = (filtros or {}).get("sigla_uf", "DF")
    ano_label = f"Ano {filtros['ano']}" if (filtros and filtros.get("ano")) else "12 meses"
    st.markdown(f"#### Setores econômicos em {uf_label} ({ano_label}){sufixo}")
    st.caption("Volume de admissões, desligamentos e saldo líquido por seção da CNAE 2.0.")

    if not df_ativos.empty:
        mais_adm = df_ativos.sort_values("admissoes", ascending=False).iloc[0]
        maior_saldo = df_ativos.sort_values("saldo", ascending=False).iloc[0]

        c1, c2, c3 = st.columns(3)
        with c1:
            render_kpi("Maior volume de admissões", f"Seção {mais_adm['codigo_secao']} ({fmt_int(mais_adm['admissoes'])})", str(mais_adm["descricao_secao"])[:42])
        with c2:
            render_kpi("Maior saldo líquido", f"Seção {maior_saldo['codigo_secao']} ({fmt_int(maior_saldo['saldo'], True)})", str(maior_saldo["descricao_secao"])[:42])
        with c3:
            render_kpi("Janela de apuração", f"{str(mais_adm['inicio'])[:7]} a {str(mais_adm['fim'])[:7]}", f"{int(mais_adm['competencias_disponiveis'])} competências")

    st.write("")
    c_g, c_t = st.columns([1, 1])

    with c_g:
        st.markdown("**8 setores com mais movimentações**")
        top8 = df_ativos.head(8).copy()
        if not top8.empty:
            top8["Setor"] = top8["codigo_secao"] + " - " + top8["descricao_secao"].str.slice(0, 22)
            st.bar_chart(
                top8.set_index("Setor")[["admissoes", "desligamentos"]].rename(
                    columns={"admissoes": "Admissões", "desligamentos": "Desligamentos"}
                ),
                height=300,
            )

    with c_t:
        st.markdown("**Classificação por seção CNAE**")
        df_tab = pd.DataFrame({
            "Pos.": df_bruto["ranking_admissoes"].map(lambda r: f"{int(r)}º"),
            "Seção": df_bruto["codigo_secao"],
            "Descrição": df_bruto["descricao_secao"],
            "Admissões": df_bruto["admissoes"].map(fmt_int),
            "Desligamentos": df_bruto["desligamentos"].map(fmt_int),
            "Saldo": df_bruto["saldo"].map(lambda v: fmt_int(v, True)),
        })
        st.dataframe(df_tab, hide_index=True, height=300)


def render_p2_sazonalidade(
    df_bruto: pd.DataFrame,
    cargo_label: str = "",
    filtros: dict[str, Any] | None = None,
) -> None:
    df_val = df_bruto.dropna(subset=["admissoes", "desligamentos", "saldo"]).copy()
    observado_mes = (
        df_val.groupby("mes", as_index=False)
        .agg(
            admissoes_obs=("admissoes", "sum"),
            desligamentos_obs=("desligamentos", "sum"),
            saldo_obs=("saldo", "sum"),
        )
    )

    # Usa as colunas media_* calculadas pelo SQL sobre os anos completos (12 competências),
    # evitando distorção por anos parciais (como 2026).
    resumo_sql = (
        df_bruto.drop_duplicates(subset=["sigla_uf", "codigo_secao", "mes"])
        .groupby("mes", as_index=False)
        .agg(
            anos_completos=("anos_considerados", "max"),
            media_admissoes=("media_admissoes_mes", lambda s: s.dropna().sum() if s.notna().any() else None),
            media_desligamentos=("media_desligamentos_mes", lambda s: s.dropna().sum() if s.notna().any() else None),
            media_saldo=("media_saldo_mes", lambda s: s.dropna().sum() if s.notna().any() else None),
        )
    )

    por_mes = pd.merge(resumo_sql, observado_mes, on="mes", how="outer").sort_values("mes")
    por_mes["nome_mes"] = por_mes["mes"].map(lambda m: f"{int(m):02d} - {NOMES_MESES.get(int(m), str(m))}")

    tem_anos_completos = bool(por_mes["media_saldo"].notna().any())
    coluna_criterio = "media_saldo" if tem_anos_completos else "saldo_obs"
    rotulo_criterio = "Média (anos completos)" if tem_anos_completos else "Saldo observado (ano parcial)"

    secao_filtro = (filtros or {}).get("codigo_secao")
    sufixo_secao = f" · Seção {secao_filtro}" if secao_filtro else ""
    sufixo = f" — {cargo_label}" if cargo_label else ""
    st.markdown(f"#### Sazonalidade mensal das movimentações{sufixo_secao}{sufixo}")
    st.caption(
        "Curva sazonal (média mensal sobre anos completos de 12 competências) e evolução histórica mensal "
        "de contratações, desligamentos e saldo líquido."
    )

    df_criterio = por_mes.dropna(subset=[coluna_criterio])
    if not df_criterio.empty:
        melhor = df_criterio.sort_values(coluna_criterio, ascending=False).iloc[0]
        pior = df_criterio.sort_values(coluna_criterio, ascending=True).iloc[0]
        qtd_anos_comp = int(por_mes["anos_completos"].max() or 0)

        c1, c2, c3 = st.columns(3)
        with c1:
            render_kpi(
                "Mês de maior expansão",
                str(melhor["nome_mes"]),
                f"{rotulo_criterio}: {fmt_int(melhor[coluna_criterio], True)}",
            )
        with c2:
            render_kpi(
                "Mês de maior retração",
                str(pior["nome_mes"]),
                f"{rotulo_criterio}: {fmt_int(pior[coluna_criterio], True)}",
            )
        with c3:
            render_kpi(
                "Cobertura temporal",
                f"{df_val['competencia'].nunique()} competências",
                f"{qtd_anos_comp} ano(s) completo(s) na média sazonal",
            )

    # Curva histórica por competência (YYYY-MM) + Curva sazonal média (Jan-Dez)
    serie_comp = (
        df_val.groupby("competencia", as_index=False)
        .agg(
            admissoes=("admissoes", "sum"),
            desligamentos=("desligamentos", "sum"),
            saldo=("saldo", "sum"),
        )
        .sort_values("competencia")
    )
    serie_comp["Competência"] = serie_comp["competencia"].map(lambda c: str(c)[:7])

    st.write("")
    col_curva_hist, col_curva_saz = st.columns([1, 1])

    with col_curva_hist:
        st.markdown("**Curva histórica mensal (Admissões vs. Desligamentos)**")
        if not serie_comp.empty:
            st.line_chart(
                serie_comp.set_index("Competência")[["admissoes", "desligamentos", "saldo"]].rename(
                    columns={
                        "admissoes": "Admissões",
                        "desligamentos": "Desligamentos",
                        "saldo": "Saldo líquido",
                    }
                ),
                height=280,
            )

    with col_curva_saz:
        st.markdown(f"**Curva sazonal por mês do calendário ({rotulo_criterio})**")
        cols_saz = (
            ["media_admissoes", "media_desligamentos", "media_saldo"]
            if tem_anos_completos
            else ["admissoes_obs", "desligamentos_obs", "saldo_obs"]
        )
        nomes_saz = (
            {
                "media_admissoes": "Média admissões",
                "media_desligamentos": "Média desligamentos",
                "media_saldo": "Média saldo",
            }
            if tem_anos_completos
            else {
                "admissoes_obs": "Admissões",
                "desligamentos_obs": "Desligamentos",
                "saldo_obs": "Saldo",
            }
        )
        st.line_chart(
            por_mes.set_index("nome_mes")[cols_saz].rename(columns=nomes_saz),
            height=280,
        )

    st.write("")
    c_chart, c_table = st.columns([1, 1])

    with c_chart:
        st.markdown(f"**Saldo por mês do ano ({rotulo_criterio})**")
        st.bar_chart(
            por_mes.set_index("nome_mes")[[coluna_criterio]].rename(
                columns={coluna_criterio: rotulo_criterio}
            ),
            height=270,
        )

    with c_table:
        st.markdown("**Série mensal consolidada**")
        df_tab = pd.DataFrame({
            "Mês": por_mes["nome_mes"],
            "Média admissões (anos compl.)": por_mes["media_admissoes"].map(fmt_int),
            "Média deslig. (anos compl.)": por_mes["media_desligamentos"].map(fmt_int),
            "Média saldo (anos compl.)": por_mes["media_saldo"].map(lambda v: fmt_int(v, True)),
            "Saldo acumulado (série total)": por_mes["saldo_obs"].map(lambda v: fmt_int(v, True)),
        })
        st.dataframe(df_tab, hide_index=True, height=270)


# TODO (Tiago): Completar a Matriz Interativa de Turnover (dispersão st.scatter_chart de
# indice_fluxos_pareados_pct vs. salario_medio_admissao, quadrantes pela mediana e destaque de codigo_secao)
def render_p4_rotatividade(
    df_bruto: pd.DataFrame,
    cargo_label: str = "",
    filtros: dict[str, Any] | None = None,
) -> None:
    df_val = df_bruto.dropna(subset=["salario_medio_admissao", "indice_fluxos_pareados_pct"]).copy()
    corr_val = df_bruto["correlacao_pearson"].iloc[0] if "correlacao_pearson" in df_bruto.columns else None
    corr_str = f"{float(corr_val):.3f}".replace(".", ",") if (corr_val is not None and not pd.isna(corr_val)) else "N/A"

    sufixo = f" — {cargo_label}" if cargo_label else ""
    st.markdown(f"#### Rotatividade setorial e remuneração{sufixo}")
    st.caption("Relação entre o índice de fluxos pareados (substituição de postos) e o salário médio inicial por seção CNAE.")

    if not df_val.empty:
        maior_rot = df_val.sort_values("indice_fluxos_pareados_pct", ascending=False).iloc[0]
        maior_sal = df_val.sort_values("salario_medio_admissao", ascending=False).iloc[0]

        c1, c2, c3 = st.columns(3)
        with c1:
            render_kpi("Correlação de Pearson (r)", corr_str, "Índice de fluxos vs. salário médio")
        with c2:
            render_kpi("Maior índice de rotatividade", f"Seção {maior_rot['codigo_secao']} ({fmt_pct(maior_rot['indice_fluxos_pareados_pct'])})", f"Salário médio: {fmt_moeda(maior_rot['salario_medio_admissao'])}")
        with c3:
            render_kpi("Maior salário médio", f"Seção {maior_sal['codigo_secao']} ({fmt_moeda(maior_sal['salario_medio_admissao'])})", f"Índice de fluxos: {fmt_pct(maior_sal['indice_fluxos_pareados_pct'])}")

    st.write("")
    c_chart, c_table = st.columns([1, 1])

    with c_chart:
        st.markdown("**Salário médio inicial por seção CNAE (R$)**")
        df_plot = df_val.copy()
        df_plot["Setor"] = df_plot["codigo_secao"] + " - " + df_plot["codigo_secao"].map(
            lambda s: SECOES_CNAE_OFICIAIS.get(str(s), str(s))[:20]
        )
        st.bar_chart(
            df_plot.set_index("Setor")[["salario_medio_admissao"]].rename(
                columns={"salario_medio_admissao": "Salário médio (R$)"}
            ),
            height=300,
        )

    with c_table:
        st.markdown("**Seções ordenadas por índice de rotatividade**")
        df_ord = df_bruto.sort_values("indice_fluxos_pareados_pct", ascending=False)
        df_tab = pd.DataFrame({
            "Seção": df_ord["codigo_secao"],
            "Setor econômico": df_ord["codigo_secao"].map(lambda s: SECOES_CNAE_OFICIAIS.get(str(s), str(s))),
            "Índice fluxos": df_ord["indice_fluxos_pareados_pct"].map(fmt_pct),
            "Salário médio": df_ord["salario_medio_admissao"].map(fmt_moeda),
            "Saldo": df_ord["saldo"].map(lambda v: fmt_int(v, True)),
        })
        st.dataframe(df_tab, hide_index=True, height=300)


# TODO (Tiago): Completar o painel de Disparidades Sociodemográficas (gráfico comparativo de hiato salarial
# e saldo líquido por categoria demográfica, colunas de diferença salarial em R$ e saldo na tabela e destaque por seção CNAE)
def render_p5_sociodemografico(
    df_bruto: pd.DataFrame,
    filtros: dict[str, Any],
    caminho_str: str | None = None,
    chave_prefixo: str = "p5",
    resposta_original: RespostaTextToSQL | None = None,
) -> RespostaTextToSQL | None:
    eixos = list(df_bruto["eixo"].unique())
    eixo_atual = filtros.get("eixo") if filtros.get("eixo") in eixos else eixos[0]
    cargo_label = filtros.get("termo_ocupacao", "")
    resposta_efetiva = resposta_original

    sufixo = f" — {cargo_label}" if cargo_label else ""
    st.markdown(f"#### Perfil sociodemográfico e remuneração{sufixo}")
    st.caption("Recorte de admissões, desligamentos e salário médio inicial por sexo, escolaridade, raça/cor e faixa etária.")

    eixo_selecionado = st.radio(
        "Dimensão:",
        options=list(MAPA_EIXOS_DEMOGRAFICOS.keys()),
        index=list(MAPA_EIXOS_DEMOGRAFICOS.keys()).index(eixo_atual) if eixo_atual in MAPA_EIXOS_DEMOGRAFICOS else 0,
        format_func=lambda k: MAPA_EIXOS_DEMOGRAFICOS.get(k, k),
        horizontal=True,
        key=f"{chave_prefixo}_radio_eixo",
    )

    if eixo_selecionado != eixo_atual and caminho_str:
        resp_nova = obter_resposta_cached(
            caminho_str,
            "Como o perfil sociodemográfico impacta o salário médio de admissão?",
            filtro_cargo=filtros.get("termo_ocupacao"),
            codigos_cbo_override=filtros.get("codigos_cbo"),
            sigla_uf_override=filtros.get("sigla_uf"),
            ano_override=filtros.get("ano"),
            eixo_override=eixo_selecionado,
            codigo_secao_override=filtros.get("codigo_secao"),
        )
        df_bruto = pd.DataFrame(resp_nova.linhas, columns=resp_nova.colunas)
        eixo_atual = eixo_selecionado
        resposta_efetiva = resp_nova

    df_eixo = df_bruto[df_bruto["eixo"] == eixo_atual].copy()
    if df_eixo.empty:
        st.info("Sem registros para a dimensão selecionada neste recorte.")
        return resposta_efetiva

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
    soma_sal = float(consolidado["soma_sal"].sum())
    qtd_sal = int(consolidado["qtd_sal"].sum())
    media_geral = (soma_sal / qtd_sal) if qtd_sal > 0 else 0.0

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

    if eixo_atual == "sexo" and len(validos) >= 2:
        homens_df = validos[validos["categoria"].str.lower().str.startswith("hom")]
        mulheres_df = validos[validos["categoria"].str.lower().str.startswith("mul")]
        if not homens_df.empty and not mulheres_df.empty:
            lh = homens_df.iloc[0]
            lm = mulheres_df.iloc[0]
            sh = float(lh["salario_medio"])
            sm = float(lm["salario_medio"])
            dif_reais = sh - sm
            dif_pct = (100.0 * dif_reais / sm) if sm > 0 else 0.0

            c1, c2, c3 = st.columns(3)
            with c1:
                render_kpi("Salário médio (Homens)", fmt_moeda(sh), f"{fmt_int(lh['admissoes'])} admissões ({fmt_pct(lh['participacao_pct'])})")
            with c2:
                render_kpi("Salário médio (Mulheres)", fmt_moeda(sm), f"{fmt_int(lm['admissoes'])} admissões ({fmt_pct(lm['participacao_pct'])})")
            with c3:
                render_kpi("Diferença (Homem - Mulher)", fmt_moeda(dif_reais), f"Variação relativa: {fmt_pct(dif_pct, True)}")
    else:
        validos_ord = validos.sort_values("salario_medio", ascending=False)
        if not validos_ord.empty:
            maior = validos_ord.iloc[0]
            menor = validos_ord.iloc[-1]
            mais_adm = validos.sort_values("admissoes", ascending=False).iloc[0]

            c1, c2, c3 = st.columns(3)
            with c1:
                render_kpi(f"Maior média ({maior['categoria'][:22]})", fmt_moeda(maior["salario_medio"]), f"{fmt_int(maior['admissoes'])} admissões")
            with c2:
                render_kpi(f"Menor média ({menor['categoria'][:22]})", fmt_moeda(menor["salario_medio"]), f"{fmt_int(menor['admissoes'])} admissões")
            with c3:
                render_kpi(f"Maior volume ({mais_adm['categoria'][:22]})", fmt_int(mais_adm["admissoes"]), f"Média salarial: {fmt_moeda(mais_adm['salario_medio'])}")

    st.write("")
    c_tab, c_graf = st.columns([1, 1])

    with c_graf:
        st.markdown("**Salário médio inicial por categoria (R$)**")
        if not validos.empty:
            df_plot = validos.set_index("categoria")[["salario_medio"]].rename(
                columns={"salario_medio": "Salário médio (R$)"}
            )
            st.bar_chart(df_plot, height=290)

    with c_tab:
        st.markdown("**Distribuição por categoria**")
        df_tab = pd.DataFrame({
            "Categoria": consolidado["categoria"],
            "Salário médio": consolidado["salario_medio"].map(fmt_moeda),
            "Dif. p/ média": consolidado["dif_media_pct"].map(lambda v: fmt_pct(v, True)),
            "Admissões": consolidado["admissoes"].map(fmt_int),
            "Participação": consolidado["participacao_pct"].map(fmt_pct),
        })
        st.dataframe(df_tab, hide_index=True, height=290)

    return resposta_efetiva


# ==============================================================================
# ROTEADOR DE RESPOSTAS
# ==============================================================================

def renderizar_resposta_geral(
    resposta: RespostaTextToSQL,
    caminho_str: str,
    chave_prefixo: str = "geral",
) -> None:
    df_bruto = pd.DataFrame(resposta.linhas, columns=resposta.colunas)
    if df_bruto.empty:
        st.warning("Nenhum registro encontrado para os filtros selecionados.")
        return

    resposta_auditoria = resposta
    cargo_label = resposta.filtros_aplicados.get("termo_ocupacao", "")
    if resposta.ocupacoes_resolvidas and resposta.intencao != "cbo_ocupacao":
        cbo_tags = ", ".join([f"{o['codigo_cbo']} ({o['titulo_ocupacao']})" for o in resposta.ocupacoes_resolvidas[:3]])
        st.caption(f"Filtro ocupacional aplicado (CBO 2002): {cbo_tags}")

    if resposta.intencao == "p3_capitais_interior":
        render_p3_capitais_interior(df_bruto, cargo_label, resposta.filtros_aplicados)
    elif resposta.intencao == "p1_setores_df":
        render_p1_setores_df(df_bruto, cargo_label, resposta.filtros_aplicados)
    elif resposta.intencao == "p2_sazonalidade":
        render_p2_sazonalidade(df_bruto, cargo_label, resposta.filtros_aplicados)
    elif resposta.intencao == "p4_fluxos_salarios":
        render_p4_rotatividade(df_bruto, cargo_label, resposta.filtros_aplicados)
    elif resposta.intencao == "p5_perfil_remuneracao":
        nova_resp = render_p5_sociodemografico(
            df_bruto,
            resposta.filtros_aplicados,
            caminho_str,
            chave_prefixo,
            resposta,
        )
        if nova_resp is not None:
            resposta_auditoria = nova_resp
    elif resposta.intencao == "cbo_ocupacao":
        render_visao_cbo_detalhada(df_bruto)
    else:
        st.dataframe(df_bruto, hide_index=True)

    render_auditoria_expander(resposta_auditoria)


def render_visao_cbo_detalhada(df_bruto: pd.DataFrame) -> None:
    lider = df_bruto.iloc[0]
    tot_adm = int(df_bruto["admissoes"].sum())
    tot_des = int(df_bruto["desligamentos"].sum())
    tot_saldo = int(df_bruto["saldo"].sum())

    st.markdown(f"#### Ocupação: {lider['codigo_cbo']} — {lider['titulo_ocupacao']}")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi("Salário médio inicial", fmt_moeda(lider["salario_medio_admissao"]), "Ocupação principal")
    with c2:
        render_kpi("Admissões", fmt_int(tot_adm), "Total no grupo")
    with c3:
        render_kpi("Desligamentos", fmt_int(tot_des), "Total no grupo")
    with c4:
        render_kpi("Saldo líquido", fmt_int(tot_saldo, True), "Variação de vínculos")

    st.write("")
    df_cbo_tab = pd.DataFrame({
        "Código CBO": df_bruto["codigo_cbo"],
        "Título oficial (MTE)": df_bruto["titulo_ocupacao"],
        "Admissões": df_bruto["admissoes"].map(fmt_int),
        "Desligamentos": df_bruto["desligamentos"].map(fmt_int),
        "Saldo": df_bruto["saldo"].map(lambda v: fmt_int(v, True)),
        "Salário médio": df_bruto["salario_medio_admissao"].map(fmt_moeda),
    })
    st.dataframe(df_cbo_tab, hide_index=True)


# ==============================================================================
# SEÇÃO 1: PAINEL DAS 5 PERGUNTAS DE GESTÃO
# ==============================================================================

def render_view_painel_executivo(
    caminho_str: str,
    filtro_uf: str | None,
    filtro_ano: int | None,
    filtro_secao: str | None,
    cargo_filtro: str | None,
) -> None:
    kpis_recorte = consultar_kpis_recorte_cached(
        caminho_str,
        sigla_uf=filtro_uf,
        ano=filtro_ano,
        codigo_secao=filtro_secao,
    )
    k1, k2, k3, k4 = st.columns(4)
    with k1:
        render_kpi(
            "Saldo líquido no recorte",
            fmt_int(kpis_recorte["saldo"], True),
            f"Admissões − Desligamentos ({filtro_uf or 'Centro-Oeste'})",
        )
    with k2:
        render_kpi(
            "Salário médio de admissão",
            fmt_moeda(kpis_recorte["salario_medio"]),
            f"n = {fmt_int(kpis_recorte['qtd_salarios'])} salários válidos",
        )
    with k3:
        render_kpi(
            "Total de admissões",
            fmt_int(kpis_recorte["admissoes"]),
            f"Período: {filtro_ano or '2023–2026'}",
        )
    with k4:
        render_kpi(
            "Total de desligamentos",
            fmt_int(kpis_recorte["desligamentos"]),
            f"Setor: {f'Seção {filtro_secao}' if filtro_secao else 'Todas as seções'}",
        )

    st.write("")
    tab_p3, tab_p1, tab_p2, tab_p4, tab_p5 = st.tabs([
        "Capitais vs. Interior (P3)",
        "Setores Econômicos (P1)",
        "Sazonalidade (P2)",
        "Rotatividade e Salário (P4)",
        "Perfil Demográfico (P5)",
    ])

    with tab_p3:
        resp_p3 = obter_resposta_cached(
            caminho_str,
            "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?",
            filtro_cargo=cargo_filtro,
            sigla_uf_override=filtro_uf,
            ano_override=filtro_ano,
            codigo_secao_override=filtro_secao,
        )
        renderizar_resposta_geral(resp_p3, caminho_str, "painel_p3")

    with tab_p1:
        resp_p1 = obter_resposta_cached(
            caminho_str,
            "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?",
            filtro_cargo=cargo_filtro,
            sigla_uf_override=filtro_uf or "DF",
            ano_override=filtro_ano,
            codigo_secao_override=filtro_secao,
        )
        renderizar_resposta_geral(resp_p1, caminho_str, "painel_p1")

    with tab_p2:
        resp_p2 = obter_resposta_cached(
            caminho_str,
            "Existe sazonalidade nas contratações e demissões?",
            filtro_cargo=cargo_filtro,
            sigla_uf_override=filtro_uf,
            ano_override=filtro_ano,
            codigo_secao_override=filtro_secao,
        )
        renderizar_resposta_geral(resp_p2, caminho_str, "painel_p2")

    with tab_p4:
        resp_p4 = obter_resposta_cached(
            caminho_str,
            "Os setores com maior rotatividade praticam salários médios mais baixos?",
            filtro_cargo=cargo_filtro,
            sigla_uf_override=filtro_uf,
            ano_override=filtro_ano,
            codigo_secao_override=filtro_secao,
        )
        renderizar_resposta_geral(resp_p4, caminho_str, "painel_p4")

    with tab_p5:
        resp_p5 = obter_resposta_cached(
            caminho_str,
            "Como o perfil sociodemográfico impacta o salário médio de admissão?",
            filtro_cargo=cargo_filtro,
            sigla_uf_override=filtro_uf,
            ano_override=filtro_ano,
            eixo_override="sexo",
            codigo_secao_override=filtro_secao,
        )
        renderizar_resposta_geral(resp_p5, caminho_str, "painel_p5")


# ==============================================================================
# SEÇÃO 2: CONSULTA DE OCUPAÇÕES (CBO 2002)
# ==============================================================================

def render_view_busca_cbo(
    caminho_str: str,
    indice: IndiceVetorialCBO,
    filtro_uf: str | None,
    filtro_ano: int | None,
) -> None:
    st.markdown("#### Consulta de Ocupações (CBO 2002)")
    st.caption("Busca vetorial semântica (384 dimensões) sobre o catálogo de ocupações do Ministério do Trabalho.")

    if "busca_termo_ativo" not in st.session_state:
        st.session_state["busca_termo_ativo"] = "professor"

    col_input, col_btn = st.columns([5, 1])
    with col_input:
        termo_digitado = st.text_input(
            "Ocupação ou código CBO:",
            value=st.session_state["busca_termo_ativo"],
            placeholder="Digite o nome da função, sinônimo ou código CBO de 6 dígitos...",
            label_visibility="collapsed",
        )
    with col_btn:
        if st.button("Pesquisar", type="primary", use_container_width=True):
            st.session_state["busca_termo_ativo"] = termo_digitado
            st.rerun()

    cols_sug = st.columns(len(SUGESTOES_PROFISSOES))
    for i, (label_sug, val_sug) in enumerate(SUGESTOES_PROFISSOES):
        if cols_sug[i].button(label_sug, key=f"sug_cbo_{i}", use_container_width=True):
            st.session_state["busca_termo_ativo"] = val_sug
            st.rerun()

    termo_ativo = st.session_state["busca_termo_ativo"].strip()
    if not termo_ativo:
        return

    resultados = indice.buscar_semantico(termo_ativo, top_k=5, apenas_oficiais=True)
    if not resultados:
        resultados = indice.buscar_semantico(termo_ativo, top_k=5, apenas_oficiais=False)

    if not resultados:
        st.warning(f"Nenhuma ocupação localizada para '{termo_ativo}'.")
        return

    top1 = resultados[0]
    codigos_encontrados = tuple(r.codigo_cbo for r in resultados)

    ind_sel = consultar_indicadores_cbo_cached(
        caminho_str,
        codigos_cbo=(top1.codigo_cbo,),
        sigla_uf=filtro_uf,
        ano=filtro_ano,
    )
    ind_grupo = consultar_indicadores_cbo_cached(
        caminho_str,
        codigos_cbo=codigos_encontrados,
        sigla_uf=filtro_uf,
        ano=filtro_ano,
    )

    st.write("")
    st.markdown(f"**Ocupação principal:** `{top1.codigo_cbo}` — {top1.titulo_ocupacao}")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi("Salário médio inicial", fmt_moeda(ind_sel["salario_medio_admissao"]), f"CBO {top1.codigo_cbo}")
    with c2:
        render_kpi("Admissões", fmt_int(ind_sel["admissoes"]), f"Desligamentos: {fmt_int(ind_sel['desligamentos'])}")
    with c3:
        render_kpi("Saldo líquido", fmt_int(ind_sel["saldo"], True), "Variação no período")
    with c4:
        render_kpi("Score de similaridade", f"{top1.score:.3f}", f"Método: {top1.metodo}")

    st.write("")
    tab_similares, tab_perfil, tab_geo = st.tabs([
        "Ocupações correspondentes (Top 5)",
        "Recorte demográfico",
        "Distribuição geográfica",
    ])

    with tab_similares:
        mapa_ind = {item["codigo_cbo"]: item for item in ind_grupo["por_ocupacao"]}
        linhas_tab = []
        for r in resultados:
            d = mapa_ind.get(r.codigo_cbo, {})
            linhas_tab.append({
                "Código CBO": r.codigo_cbo,
                "Título oficial": r.titulo_ocupacao,
                "Score": f"{r.score:.3f}",
                "Admissões": fmt_int(d.get("admissoes", 0)),
                "Desligamentos": fmt_int(d.get("desligamentos", 0)),
                "Saldo": fmt_int(d.get("saldo", 0), True),
                "Salário médio": fmt_moeda(d.get("salario_medio_admissao")),
            })
        st.dataframe(pd.DataFrame(linhas_tab), hide_index=True)

    with tab_perfil:
        resp_perfil = obter_resposta_cached(
            caminho_str,
            "Como o perfil sociodemográfico impacta o salário médio de admissão?",
            filtro_cargo=termo_ativo,
            codigos_cbo_override=[top1.codigo_cbo],
            sigla_uf_override=filtro_uf,
            ano_override=filtro_ano,
            eixo_override="sexo",
        )
        df_p = pd.DataFrame(resp_perfil.linhas, columns=resp_perfil.colunas)
        if not df_p.empty:
            render_p5_sociodemografico(df_p, resp_perfil.filtros_aplicados, caminho_str, "cbo_view", resp_perfil)
        else:
            st.info("Sem registros demográficos para esta ocupação no filtro atual.")

    with tab_geo:
        resp_geo = obter_resposta_cached(
            caminho_str,
            "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?",
            filtro_cargo=termo_ativo,
            codigos_cbo_override=[top1.codigo_cbo],
            sigla_uf_override=filtro_uf,
            ano_override=filtro_ano,
        )
        df_g = pd.DataFrame(resp_geo.linhas, columns=resp_geo.colunas)
        if not df_g.empty:
            render_p3_capitais_interior(df_g, top1.titulo_ocupacao, resp_geo.filtros_aplicados)
        else:
            st.info("Sem registros geográficos para esta ocupação no filtro atual.")


# ==============================================================================
# SEÇÃO 3: CONSULTA EM LINGUAGEM NATURAL (TEXT-TO-SQL)
# ==============================================================================

def render_view_assistente_sql(
    caminho_str: str,
    filtro_uf: str | None,
    filtro_ano: int | None,
    cargo_filtro: str | None,
) -> None:
    st.markdown("#### Consulta em Linguagem Natural (Text-to-SQL)")
    st.caption("Tradução de perguntas para SQL somente leitura sobre os contratos da camada Gold.")

    if "pergunta_input" not in st.session_state:
        st.session_state["pergunta_input"] = "Qual a diferença salarial entre homens e mulheres?"

    col_input, col_btn = st.columns([5, 1])
    with col_input:
        pergunta_digitada = st.text_input(
            "Pergunta:",
            value=st.session_state["pergunta_input"],
            placeholder="Ex.: Qual a diferença salarial entre homens e mulheres para professor?",
            label_visibility="collapsed",
        )
    with col_btn:
        if st.button("Executar", type="primary", use_container_width=True):
            st.session_state["pergunta_input"] = pergunta_digitada
            st.rerun()

    cols_p = st.columns(len(PERGUNTAS_EXEMPLO))
    for i, (rotulo, perg) in enumerate(PERGUNTAS_EXEMPLO):
        if cols_p[i].button(rotulo, key=f"btn_faq_{i}", use_container_width=True):
            st.session_state["pergunta_input"] = perg
            st.rerun()

    pergunta_ativa = st.session_state["pergunta_input"].strip()
    if not pergunta_ativa:
        return

    resposta = obter_resposta_cached(
        caminho_str,
        pergunta_ativa,
        filtro_cargo=cargo_filtro,
        sigla_uf_override=filtro_uf,
        ano_override=filtro_ano,
    )

    if not resposta.suportada:
        if resposta.intencao == "bloqueada_seguranca":
            st.error(f"**Consulta recusada pelo validador de segurança**\n\n{resposta.motivo_recusa}")
        else:
            st.warning(f"**Consulta fora do escopo suportado**\n\n{resposta.motivo_recusa}")
        st.caption(f"Nota metodológica: {resposta.ressalva_metodologica}")
        return

    st.write("")
    renderizar_resposta_geral(resposta, caminho_str, "assistente_sql")


# ==============================================================================
# ENTRYPOINT
# ==============================================================================

def main() -> None:
    st.set_page_config(
        page_title="METRA — Painel Analítico",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(ESTILO_CSS, unsafe_allow_html=True)

    caminho_duckdb = obter_caminho_duckdb()
    try:
        indice, _, resumo = carregar_recursos_analiticos(str(caminho_duckdb))
    except (FileNotFoundError, RuntimeError, duckdb.Error) as exc:
        st.markdown("## METRA — Mercado de Trabalho Formal no Centro-Oeste")
        st.error(
            "**Camada analítica Gold indisponível para leitura**\n\n"
            f"{exc}\n\n"
            "O painel opera exclusivamente em modo leitura (`READ_ONLY`) e não reconstrói o banco analítico "
            "automaticamente. Materialize a camada Gold pelo pipeline oficial:\n"
            "```bash\n"
            "cd dbt_metra\n"
            "dbt build --profiles-dir .\n"
            "```\n"
            "Ou execute o job de materialização no Dagster (`dagster dev -w workspace.yaml`)."
        )
        st.stop()

    with st.sidebar:
        st.markdown("### METRA")
        st.caption("Monitoramento e Engenharia de Dados do Trabalho · UnB/FCTE (Grupo 4)")
        st.divider()

        opcao_menu = st.radio(
            "Visualização",
            options=[
                "Perguntas de Gestão (P1–P5)",
                "Busca de Ocupações (CBO 2002)",
                "Consulta Text-to-SQL",
            ],
            index=0,
        )
        st.divider()

        st.markdown("**Filtros de recorte**")
        uf_selecionada = st.selectbox(
            "Unidade da Federação",
            options=["Todas (Centro-Oeste)", "DF", "GO", "MT", "MS"],
            index=0,
        )
        ano_selecionado = st.selectbox(
            "Ano",
            options=["Todos (2023–2026)", 2023, 2024, 2025, 2026],
            index=0,
        )
        opcoes_secao = ["Todas as seções (A–U)"] + [
            f"{cod} - {desc}"
            for cod, desc in SECOES_CNAE_OFICIAIS.items()
            if cod != "Z"
        ]
        secao_selecionada = st.selectbox(
            "Setor Econômico (Seção CNAE)",
            options=opcoes_secao,
            index=0,
        )
        cargo_global = st.text_input(
            "Ocupação / CBO (opcional)",
            value="",
            placeholder="Ex.: professor, enfermeiro, 212405",
        )

        filtro_uf_efetivo = None if uf_selecionada.startswith("Todas") else uf_selecionada
        filtro_ano_efetivo = None if str(ano_selecionado).startswith("Todos") else int(ano_selecionado)
        filtro_secao_efetivo = (
            None if secao_selecionada.startswith("Todas") else secao_selecionada.split(" - ", 1)[0].strip()
        )
        cargo_efetivo = cargo_global.strip() or None

        st.divider()
        st.caption(
            f"Base: Novo CAGED ({resumo['comp_min']} a {resumo['comp_max']})  \n"
            f"Registros: {fmt_int(resumo['total_movimentacoes'])} · "
            f"Saldo: {fmt_int(resumo['saldo'], True)}"
        )

    # Cabeçalho principal (com html.escape em todas as variáveis interpoladas)
    st.markdown("## METRA — Mercado de Trabalho Formal no Centro-Oeste")
    filtros_ativos = [
        f"UF: {filtro_uf_efetivo}" if filtro_uf_efetivo else "Região: Centro-Oeste (DF, GO, MT, MS)",
        f"Ano: {filtro_ano_efetivo}" if filtro_ano_efetivo else "Período: 2023–2026",
        (
            f"Setor: Seção {filtro_secao_efetivo} ({SECOES_CNAE_OFICIAIS.get(filtro_secao_efetivo, '')[:28]})"
            if filtro_secao_efetivo
            else "Setor: Todas as seções CNAE"
        ),
    ]
    if cargo_efetivo:
        filtros_ativos.append(f"Ocupação: {cargo_efetivo}")
    filtros_ativos.append(f"Salário médio na base: {fmt_moeda(resumo['salario_medio'])}")

    texto_cabecalho = html.escape(" · ".join(filtros_ativos))
    st.markdown(f'<div class="header-meta">{texto_cabecalho}</div>', unsafe_allow_html=True)

    if opcao_menu == "Perguntas de Gestão (P1–P5)":
        render_view_painel_executivo(
            str(caminho_duckdb),
            filtro_uf_efetivo,
            filtro_ano_efetivo,
            filtro_secao_efetivo,
            cargo_efetivo,
        )
    elif opcao_menu == "Busca de Ocupações (CBO 2002)":
        render_view_busca_cbo(
            str(caminho_duckdb),
            indice,
            filtro_uf_efetivo,
            filtro_ano_efetivo,
        )
    elif opcao_menu == "Consulta Text-to-SQL":
        render_view_assistente_sql(
            str(caminho_duckdb),
            filtro_uf_efetivo,
            filtro_ano_efetivo,
            cargo_efetivo,
        )


if __name__ == "__main__":
    main()
