"""Painel Analítico do METRA (E4) — Monitoramento e Engenharia de Dados do Trabalho.

Interface Executiva de Decisão, Busca Semântica Vetorial (CBO 2002) e Assistente Text-to-SQL.
Execução:
    streamlit run src/app/dashboard.py
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

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
# CONFIGURAÇÕES E ESTILOS VISUAIS MODERNOS
# ==============================================================================

ESTILO_CSS_CUSTOMIZADO = """
<style>
    /* Tipografia e espaçamento geral */
    @import url('https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    }
    
    .block-container {
        padding-top: 1.8rem;
        padding-bottom: 3rem;
        max-width: 1350px;
    }

    /* Cards e Containers */
    .metra-card {
        background: #ffffff;
        border: 1px solid #E2E8F0;
        border-radius: 12px;
        padding: 1.25rem 1.5rem;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.05), 0 1px 2px -1px rgba(0, 0, 0, 0.05);
        margin-bottom: 1rem;
        transition: all 0.2s ease;
    }
    
    .metra-card:hover {
        border-color: #CBD5E1;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.07);
    }

    /* Badges */
    .metra-badge {
        display: inline-block;
        padding: 0.25rem 0.65rem;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.025em;
    }
    
    .badge-primary { background: #EEF2FF; color: #4338CA; border: 1px solid #C7D2FE; }
    .badge-success { background: #ECFDF5; color: #047857; border: 1px solid #A7F3D0; }
    .badge-warning { background: #FFFBEB; color: #B45309; border: 1px solid #FDE68A; }
    .badge-info    { background: #F0F9FF; color: #0369A1; border: 1px solid #BAE6FD; }

    /* KPI Highlights */
    .kpi-container {
        display: flex;
        flex-direction: column;
        justify-content: center;
        padding: 1rem 1.2rem;
        background: #F8FAFC;
        border: 1px solid #E2E8F0;
        border-radius: 10px;
        border-left: 4px solid #3B82F6;
        min-height: 105px;
    }
    .kpi-title {
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        color: #64748B;
        letter-spacing: 0.05em;
        margin-bottom: 0.25rem;
    }
    .kpi-value {
        font-size: 1.55rem;
        font-weight: 700;
        color: #0F172A;
        line-height: 1.2;
    }
    .kpi-sub {
        font-size: 0.78rem;
        color: #64748B;
        margin-top: 0.35rem;
    }

    /* Estilização da Sidebar */
    [data-testid="stSidebar"] {
        background-color: #0F172A;
    }
    [data-testid="stSidebar"] * {
        color: #F1F5F9;
    }
    [data-testid="stSidebar"] hr {
        border-color: #334155;
    }
    [data-testid="stSidebar"] .stSelectbox label, 
    [data-testid="stSidebar"] .stRadio label {
        color: #94A3B8 !important;
        font-weight: 600;
    }
    
    /* Abas customizadas */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
        background-color: #F1F5F9;
        padding: 6px;
        border-radius: 10px;
    }
    .stTabs [data-baseweb="tab"] {
        height: 42px;
        border-radius: 8px;
        padding: 0 16px;
        font-weight: 600;
        font-size: 0.9rem;
        color: #475569;
        background-color: transparent;
        border: none;
    }
    .stTabs [aria-selected="true"] {
        background-color: #FFFFFF !important;
        color: #1E40AF !important;
        box-shadow: 0 1px 3px 0 rgba(0, 0, 0, 0.1);
    }
</style>
"""

NOMES_MESES = {
    1: "Janeiro", 2: "Fevereiro", 3: "Março", 4: "Abril",
    5: "Maio", 6: "Junho", 7: "Julho", 8: "Agosto",
    9: "Setembro", 10: "Outubro", 11: "Novembro", 12: "Dezembro",
}

MAPA_EIXOS_DEMOGRAFICOS = {
    "sexo": "Gênero (Homens vs. Mulheres)",
    "escolaridade": "Nível de Escolaridade",
    "raca_cor": "Raça e Cor",
    "faixa_etaria": "Faixa Etária",
}

SUGESTOES_PROFISSÕES = [
    ("Professor", "professor"),
    ("Programador / Dev", "desenvolvedor de software"),
    ("Enfermeiro", "enfermeiro"),
    ("Médico", "medico"),
    ("Engenheiro Civil", "engenheiro civil"),
    ("Vendedor", "vendedor"),
    ("Caminhoneiro", "caminhoneiro"),
    ("Pedreiro", "pedreiro"),
]

PERGUNTAS_RAPIDAS = [
    ("Gênero", "Qual a diferença salarial entre homens e mulheres?"),
    ("Educação", "Como a escolaridade impacta o salário médio de admissão?"),
    ("Geografia", "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?"),
    ("Setores DF", "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?"),
    ("Sazonalidade", "Existe sazonalidade nas contratações e demissões ao longo dos meses do ano?"),
    ("Rotatividade", "Os setores com maior rotatividade praticam salários médios mais baixos?"),
    ("Profissões", "Qual a diferença salarial entre homens e mulheres para o cargo de professor?"),
    ("Segurança SQL", "DROP TABLE gold.fct_movimentacao;"),
]


# ==============================================================================
# FUNÇÕES DE FORMATAÇÃO NUMÉRICA BRASILEIRA
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
# CARREGAMENTO DOS RECURSOS ANALÍTICOS (CACHE)
# ==============================================================================

@st.cache_resource(show_spinner="Carregando banco analítico DuckDB e índice semântico da CBO...")
def carregar_recursos_analiticos(caminho_str: str) -> tuple[IndiceVetorialCBO, AssistenteTextToSQL, dict[str, Any]]:
    with abrir_conexao_analitica(caminho_str, garantir_construcao=True) as conn:
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


# ==============================================================================
# COMPONENTES VISUAIS (KPI CARDS & AUDITORIA)
# ==============================================================================

def render_kpi(titulo: str, valor: str, subtitulo: str = "", borda_cor: str = "#3B82F6") -> None:
    st.markdown(f"""
        <div class="kpi-container" style="border-left-color: {borda_cor};">
            <div class="kpi-title">{titulo}</div>
            <div class="kpi-value">{valor}</div>
            <div class="kpi-sub">{subtitulo}</div>
        </div>
    """, unsafe_allow_html=True)


def render_auditoria_expander(resposta: RespostaTextToSQL) -> None:
    with st.expander("🛠️ Auditoria Técnica, Fórmula e Consulta SQL (Governança BD2 / ADR-0007)"):
        c1, c2 = st.columns([1, 1])
        with c1:
            st.markdown(f"**Identificador do Contrato:** `{resposta.intencao}`")
            st.markdown(f"**Fórmula da Métrica:** `{resposta.formula_metrica}`")
        with c2:
            st.markdown(f"**Ressalva Metodológica:** {resposta.ressalva_metodologica}")
        
        if resposta.ocupacoes_resolvidas:
            st.markdown("**Ocupações CBO Identificadas pelo Motor Vetorial (384d):**")
            st.dataframe(pd.DataFrame(resposta.ocupacoes_resolvidas), hide_index=True)

        st.markdown("**Consulta SQL Executada em Modo Somente Leitura (`READ_ONLY`) no DuckDB Gold:**")
        st.code(resposta.sql_gerado, language="sql")


# ==============================================================================
# VISUALIZAÇÕES DAS PERGUNTAS DE GESTÃO (P1 A P5)
# ==============================================================================

def render_p3_capitais_interior(df_bruto: pd.DataFrame, cargo_label: str = "") -> None:
    df_tot = df_bruto[df_bruto["nivel"] == "total"].copy()
    if df_tot.empty:
        df_tot = df_bruto.copy()

    linha_co = df_tot[df_tot["recorte"] == "Centro-Oeste"]
    ref = linha_co.iloc[0] if not linha_co.empty else df_tot.iloc[0]
    
    st.markdown(f"### 🏙️ Comparativo: Capitais vs. Interior {f'({cargo_label})' if cargo_label else ''}")
    st.caption("Pergunta Central da Plataforma: Avalia a assimetria salarial e saldo líquido de postos entre as capitais e municípios do interior.")

    c1, c2, c3 = st.columns(3)
    with c1:
        render_kpi("Salário Médio • Capitais", fmt_moeda(ref["salario_capital"]), f"Saldo: {fmt_int(ref['saldo_capital'], True)} vagas", "#2563EB")
    with c2:
        render_kpi("Salário Médio • Interior", fmt_moeda(ref["salario_interior"]), f"Saldo: {fmt_int(ref['saldo_interior'], True)} vagas", "#0D9488")
    with c3:
        render_kpi("Diferença Salarial (Capital - Interior)", fmt_moeda(ref["diferenca_salario"]), f"Diferença de saldo: {fmt_int(ref['diferenca_saldo'], True)} vagas", "#F59E0B")

    st.markdown("<br>", unsafe_allow_html=True)
    col_chart, col_table = st.columns([1, 1])

    with col_chart:
        st.markdown("**Salário Médio Inicial: Capitais vs. Interior (R$)**")
        df_plot = df_tot.set_index("recorte")[["salario_capital", "salario_interior"]].rename(
            columns={"salario_capital": "Capitais", "salario_interior": "Interior"}
        )
        st.bar_chart(df_plot, height=280)

    with col_table:
        st.markdown("**Tabela Discriminada por Estado (UF)**")
        df_exibir = pd.DataFrame({
            "Recorte": df_tot["recorte"],
            "Salário Capital": df_tot["salario_capital"].map(fmt_moeda),
            "Salário Interior": df_tot["salario_interior"].map(fmt_moeda),
            "Diferença (R$)": df_tot["diferenca_salario"].map(fmt_moeda),
            "Saldo Capitais": df_tot["saldo_capital"].map(lambda v: fmt_int(v, True)),
            "Saldo Interior": df_tot["saldo_interior"].map(lambda v: fmt_int(v, True)),
        })
        st.dataframe(df_exibir, hide_index=True)


def render_p1_setores_df(df_bruto: pd.DataFrame, cargo_label: str = "") -> None:
    df_ativos = df_bruto[df_bruto["admissoes"] > 0].copy()
    st.markdown(f"### 🏢 Setores Econômicos no DF (Últimos 12 Meses) {f'({cargo_label})' if cargo_label else ''}")
    st.caption("Pergunta 1: Avalia quais setores mais contrataram e demitiram no Distrito Federal na janela móvel de 12 meses.")

    if not df_ativos.empty:
        mais_adm = df_ativos.sort_values("admissoes", ascending=False).iloc[0]
        maior_saldo = df_ativos.sort_values("saldo", ascending=False).iloc[0]
        
        c1, c2, c3 = st.columns(3)
        with c1:
            render_kpi("Líder de Contratações", f"Seção {mais_adm['codigo_secao']}", str(mais_adm['descricao_secao'])[:40], "#2563EB")
        with c2:
            render_kpi("Maior Saldo Líquido", f"Seção {maior_saldo['codigo_secao']}", f"{fmt_int(maior_saldo['saldo'], True)} postos líquidos", "#10B981")
        with c3:
            render_kpi("Janela Temporal", f"{str(mais_adm['inicio'])[:7]} a {str(mais_adm['fim'])[:7]}", f"{int(mais_adm['competencias_disponiveis'])} meses com dados", "#6366F1")

    st.markdown("<br>", unsafe_allow_html=True)
    c_g, c_t = st.columns([1, 1])

    with c_g:
        st.markdown("**Top 8 Setores em Volume de Contratações**")
        top8 = df_ativos.head(8).copy()
        if not top8.empty:
            top8["Setor"] = top8["codigo_secao"] + " • " + top8["descricao_secao"].str.slice(0, 20)
            st.bar_chart(
                top8.set_index("Setor")[["admissoes", "desligamentos"]].rename(
                    columns={"admissoes": "Contratações", "desligamentos": "Demissões"}
                ),
                height=300
            )

    with c_t:
        st.markdown("**Ranking Completo das Seções CNAE**")
        df_tab = pd.DataFrame({
            "Rank": df_bruto["ranking_admissoes"].map(lambda r: f"{int(r)}º"),
            "Cód": df_bruto["codigo_secao"],
            "Setor": df_bruto["descricao_secao"],
            "Contratações": df_bruto["admissoes"].map(fmt_int),
            "Demissões": df_bruto["desligamentos"].map(fmt_int),
            "Saldo": df_bruto["saldo"].map(lambda v: fmt_int(v, True)),
        })
        st.dataframe(df_tab, hide_index=True, height=300)


def render_p2_sazonalidade(df_bruto: pd.DataFrame, cargo_label: str = "") -> None:
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

    st.markdown(f"### 📅 Padrão Sazonal de Contratações {f'({cargo_label})' if cargo_label else ''}")
    st.caption("Pergunta 2: Identifica variações cíclicas de admissões, desligamentos e saldo ao longo dos meses do ano.")

    if not por_mes.empty:
        melhor = por_mes.sort_values("saldo", ascending=False).iloc[0]
        pior = por_mes.sort_values("saldo", ascending=True).iloc[0]

        c1, c2, c3 = st.columns(3)
        with c1:
            render_kpi("Mês de Maior Saldo (+)", str(melhor["nome_mes"]), f"Saldo acumulado: {fmt_int(melhor['saldo'], True)} vagas", "#10B981")
        with c2:
            render_kpi("Mês de Maior Retração (-)", str(pior["nome_mes"]), f"Saldo acumulado: {fmt_int(pior['saldo'], True)} vagas", "#EF4444")
        with c3:
            render_kpi("Período Consolidado", f"{df_val['competencia'].nunique()} Meses", f"Anos analisados: 2023 a 2026", "#6366F1")

    st.markdown("<br>", unsafe_allow_html=True)
    c_chart, c_table = st.columns([1, 1])

    with c_chart:
        st.markdown("**Saldo Líquido Acumulado por Mês do Ano**")
        st.bar_chart(
            por_mes.set_index("nome_mes")[["saldo"]].rename(columns={"saldo": "Saldo Líquido"}),
            color="#2563EB",
            height=290
        )

    with c_table:
        st.markdown("**Detalhamento Mensal de Fluxos**")
        df_tab = pd.DataFrame({
            "Mês": por_mes["nome_mes"],
            "Contratações": por_mes["admissoes"].map(fmt_int),
            "Demissões": por_mes["desligamentos"].map(fmt_int),
            "Saldo Acumulado": por_mes["saldo"].map(lambda v: fmt_int(v, True)),
            "Média Saldo/Ano": por_mes["media_saldo"].map(lambda v: fmt_int(v, True)),
        })
        st.dataframe(df_tab, hide_index=True, height=290)


def render_p4_rotatividade(df_bruto: pd.DataFrame, cargo_label: str = "") -> None:
    df_val = df_bruto.dropna(subset=["salario_medio_admissao", "indice_fluxos_pareados_pct"]).copy()
    corr_val = df_bruto["correlacao_pearson"].iloc[0] if "correlacao_pearson" in df_bruto.columns else None
    corr_str = f"{float(corr_val):.3f}".replace(".", ",") if (corr_val is not None and not pd.isna(corr_val)) else "N/A"

    st.markdown(f"### 🔄 Rotatividade de Pessoal vs. Salário Médio {f'({cargo_label})' if cargo_label else ''}")
    st.caption("Pergunta 4: Analisa se os setores com maior rotatividade (fluxos pareados de admissão e demissão) praticam salários médios inferiores.")

    if not df_val.empty:
        maior_rot = df_val.sort_values("indice_fluxos_pareados_pct", ascending=False).iloc[0]
        maior_sal = df_val.sort_values("salario_medio_admissao", ascending=False).iloc[0]

        c1, c2, c3 = st.columns(3)
        with c1:
            render_kpi("Correlação de Pearson (r)", corr_str, "Entre taxa de rotatividade e salário médio", "#8B5CF6")
        with c2:
            render_kpi("Maior Rotatividade", f"Seção {maior_rot['codigo_secao']} ({fmt_pct(maior_rot['indice_fluxos_pareados_pct'])})", f"Salário médio: {fmt_moeda(maior_rot['salario_medio_admissao'])}", "#F59E0B")
        with c3:
            render_kpi("Maior Salário Médio", f"Seção {maior_sal['codigo_secao']} ({fmt_moeda(maior_sal['salario_medio_admissao'])})", f"Rotatividade: {fmt_pct(maior_sal['indice_fluxos_pareados_pct'])}", "#10B981")

    st.markdown("<br>", unsafe_allow_html=True)
    c_chart, c_table = st.columns([1, 1])

    with c_chart:
        st.markdown("**Salário Médio Inicial por Setor (R$)**")
        df_plot = df_val.copy()
        df_plot["Setor"] = df_plot["codigo_secao"] + " • " + df_plot["codigo_secao"].map(
            lambda s: SECOES_CNAE_OFICIAIS.get(str(s), str(s))[:20]
        )
        st.bar_chart(
            df_plot.set_index("Setor")[["salario_medio_admissao"]].rename(
                columns={"salario_medio_admissao": "Salário Médio"}
            ),
            color="#2563EB",
            height=300
        )

    with c_table:
        st.markdown("**Tabela Ordenada por Taxa de Rotatividade**")
        df_ord = df_bruto.sort_values("indice_fluxos_pareados_pct", ascending=False)
        df_tab = pd.DataFrame({
            "Seção": df_ord["codigo_secao"],
            "Setor Econômico": df_ord["codigo_secao"].map(lambda s: SECOES_CNAE_OFICIAIS.get(str(s), str(s))),
            "Rotatividade": df_ord["indice_fluxos_pareados_pct"].map(fmt_pct),
            "Salário Inicial": df_ord["salario_medio_admissao"].map(fmt_moeda),
            "Saldo": df_ord["saldo"].map(lambda v: fmt_int(v, True)),
        })
        st.dataframe(df_tab, hide_index=True, height=300)


def render_p5_sociodemografico(
    df_bruto: pd.DataFrame,
    filtros: dict[str, Any],
    caminho_str: str | None = None,
    assistente: AssistenteTextToSQL | None = None,
    chave_prefixo: str = "p5",
) -> None:
    eixos = list(df_bruto["eixo"].unique())
    eixo_atual = filtros.get("eixo") if filtros.get("eixo") in eixos else eixos[0]
    cargo_label = filtros.get("termo_ocupacao", "")

    st.markdown(f"### 👥 Perfil Sociodemográfico e Desigualdades {f'({cargo_label})' if cargo_label else ''}")
    st.caption("Pergunta 5: Avalia os impactos de gênero, raça/cor, escolaridade e faixa etária na remuneração inicial e contratações.")

    # Seletor elegante de dimensão demográfica
    eixos_labels = {
        "sexo": "🚻 Gênero (Homens vs. Mulheres)",
        "escolaridade": "🎓 Escolaridade",
        "raca_cor": "🎨 Raça e Cor",
        "faixa_etaria": "🎂 Faixa Etária",
    }
    
    eixo_selecionado = st.radio(
        "Selecione a Dimensão Sociodemográfica:",
        options=list(eixos_labels.keys()),
        format_func=lambda k: eixos_labels.get(k, k),
        horizontal=True,
        key=f"{chave_prefixo}_radio_eixo",
    )

    if eixo_selecionado != eixo_atual and caminho_str and assistente:
        with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
            resp_nova = assistente.responder(
                conn,
                "Como o perfil sociodemográfico impacta o salário médio de admissão?",
                filtro_cargo=filtros.get("termo_ocupacao"),
                codigos_cbo_override=filtros.get("codigos_cbo"),
                sigla_uf_override=filtros.get("sigla_uf"),
                ano_override=filtros.get("ano"),
                eixo_override=eixo_selecionado,
            )
            df_bruto = pd.DataFrame(resp_nova.linhas, columns=resp_nova.colunas)
            eixo_atual = eixo_selecionado

    df_eixo = df_bruto[df_bruto["eixo"] == eixo_atual].copy()
    if df_eixo.empty:
        st.info("Não há registros para a dimensão selecionada no filtro atual.")
        return

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

    # Destaque de Gênero
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
                render_kpi("Salário Médio • Homens", fmt_moeda(sh), f"{fmt_int(lh['admissoes'])} contratações ({fmt_pct(lh['participacao_pct'])})", "#2563EB")
            with c2:
                render_kpi("Salário Médio • Mulheres", fmt_moeda(sm), f"{fmt_int(lm['admissoes'])} contratações ({fmt_pct(lm['participacao_pct'])})", "#DB2777")
            with c3:
                render_kpi("Diferença Salarial (Homem - Mulher)", fmt_moeda(dif_reais), f"Homens ganham {fmt_pct(dif_pct, True)} a mais", "#F59E0B")
    else:
        validos_ord = validos.sort_values("salario_medio", ascending=False)
        if not validos_ord.empty:
            maior = validos_ord.iloc[0]
            menor = validos_ord.iloc[-1]
            mais_adm = validos.sort_values("admissoes", ascending=False).iloc[0]

            c1, c2, c3 = st.columns(3)
            with c1:
                render_kpi(f"Maior Salário ({maior['categoria'][:18]})", fmt_moeda(maior["salario_medio"]), f"{fmt_int(maior['admissoes'])} contratações", "#10B981")
            with c2:
                render_kpi(f"Menor Salário ({menor['categoria'][:18]})", fmt_moeda(menor["salario_medio"]), f"{fmt_int(menor['admissoes'])} contratações", "#EF4444")
            with c3:
                render_kpi(f"Maior Volume ({mais_adm['categoria'][:18]})", fmt_int(mais_adm["admissoes"]), f"Salário médio: {fmt_moeda(mais_adm['salario_medio'])}", "#6366F1")

    st.markdown("<br>", unsafe_allow_html=True)
    c_tab, c_graf = st.columns([1, 1])

    with c_graf:
        st.markdown("**Salário Médio Inicial por Categoria (R$)**")
        if not validos.empty:
            df_plot = validos.set_index("categoria")[["salario_medio"]].rename(
                columns={"salario_medio": "Salário Médio"}
            )
            st.bar_chart(df_plot, color="#2563EB", height=290)

    with c_tab:
        st.markdown("**Tabela de Distribuição e Médias Salariais**")
        df_tab = pd.DataFrame({
            "Categoria": consolidado["categoria"],
            "Salário Médio": consolidado["salario_medio"].map(fmt_moeda),
            "Diferença p/ Média": consolidado["dif_media_pct"].map(lambda v: fmt_pct(v, True)),
            "Contratações": consolidado["admissoes"].map(fmt_int),
            "Participação": consolidado["participacao_pct"].map(fmt_pct),
        })
        st.dataframe(df_tab, hide_index=True, height=290)


# ==============================================================================
# VISUALIZAÇÃO PRINCIPAL DO DISPATCHER DE RESPOSTAS
# ==============================================================================

def renderizar_resposta_geral(
    resposta: RespostaTextToSQL,
    caminho_str: str,
    assistente: AssistenteTextToSQL,
    chave_prefixo: str = "geral",
) -> None:
    df_bruto = pd.DataFrame(resposta.linhas, columns=resposta.colunas)
    if df_bruto.empty:
        st.warning("Nenhum registro encontrado para a consulta e filtros selecionados.")
        return

    cargo_label = resposta.filtros_aplicados.get("termo_ocupacao", "")
    if resposta.ocupacoes_resolvidas and resposta.intencao != "cbo_ocupacao":
        cbo_tags = " • ".join([f"{o['codigo_cbo']} - {o['titulo_ocupacao']}" for o in resposta.ocupacoes_resolvidas[:2]])
        st.info(f"🎯 **Filtro de Cargo Ativo (CBO):** {cbo_tags}")

    if resposta.intencao == "p3_capitais_interior":
        render_p3_capitais_interior(df_bruto, cargo_label)
    elif resposta.intencao == "p1_setores_df":
        render_p1_setores_df(df_bruto, cargo_label)
    elif resposta.intencao == "p2_sazonalidade":
        render_p2_sazonalidade(df_bruto, cargo_label)
    elif resposta.intencao == "p4_fluxos_salarios":
        render_p4_rotatividade(df_bruto, cargo_label)
    elif resposta.intencao == "p5_perfil_remuneracao":
        render_p5_sociodemografico(df_bruto, resposta.filtros_aplicados, caminho_str, assistente, chave_prefixo)
    elif resposta.intencao == "cbo_ocupacao":
        render_visao_cbo_detalhada(df_bruto, caminho_str, assistente, resposta.filtros_aplicados)
    else:
        st.dataframe(df_bruto, hide_index=True)

    render_auditoria_expander(resposta)


def render_visao_cbo_detalhada(
    df_bruto: pd.DataFrame,
    caminho_str: str,
    assistente: AssistenteTextToSQL,
    filtros: dict[str, Any],
) -> None:
    lider = df_bruto.iloc[0]
    tot_adm = int(df_bruto["admissoes"].sum())
    tot_des = int(df_bruto["desligamentos"].sum())
    tot_saldo = int(df_bruto["saldo"].sum())

    st.markdown(f"### 🎯 Ocupação: {lider['codigo_cbo']} — {lider['titulo_ocupacao']}")
    st.caption("Indicadores agregados no Centro-Oeste obtidos via integração da dimensão CBO com a fato de movimentações.")

    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi("Salário Inicial Médio", fmt_moeda(lider["salario_medio_admissao"]), "Para o cargo principal", "#10B981")
    with c2:
        render_kpi("Contratações (Admissões)", fmt_int(tot_adm), "Volume acumulado", "#2563EB")
    with c3:
        render_kpi("Demissões (Desligamentos)", fmt_int(tot_des), "Volume acumulado", "#EF4444")
    with c4:
        render_kpi("Saldo Líquido", fmt_int(tot_saldo, True), "Geração líquida de vagas", "#6366F1")

    st.markdown("<br>", unsafe_allow_html=True)
    st.markdown("**Ocupações CBO Mais Próximas Identificadas**")
    df_cbo_tab = pd.DataFrame({
        "Código CBO": df_bruto["codigo_cbo"],
        "Título Oficial (MTE)": df_bruto["titulo_ocupacao"],
        "Contratações": df_bruto["admissoes"].map(fmt_int),
        "Demissões": df_bruto["desligamentos"].map(fmt_int),
        "Saldo de Postos": df_bruto["saldo"].map(lambda v: fmt_int(v, True)),
        "Salário Médio": df_bruto["salario_medio_admissao"].map(fmt_moeda),
    })
    st.dataframe(df_cbo_tab, hide_index=True)


# ==============================================================================
# VIEW 1: PAINEL EXECUTIVO (5 PERGUNTAS DE GESTÃO)
# ==============================================================================

def render_view_painel_executivo(
    caminho_str: str,
    assistente: AssistenteTextToSQL,
    indice: IndiceVetorialCBO,
    filtro_uf: str | None,
    filtro_ano: int | None,
    cargo_filtro: str | None,
) -> None:
    st.markdown("## 📊 Painel Executivo do Mercado de Trabalho")
    st.caption("Acompanhamento das 5 Perguntas de Gestão estratégicas formuladas para a Região Centro-Oeste.")

    tab_p3, tab_p1, tab_p2, tab_p4, tab_p5 = st.tabs([
        "🏙️ Capitais vs. Interior (P3)",
        "🏢 Setores no DF (P1)",
        "📅 Sazonalidade (P2)",
        "🔄 Rotatividade & Salário (P4)",
        "👥 Perfil Demográfico (P5)",
    ])

    with tab_p3:
        with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
            resp = assistente.responder(
                conn,
                "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?",
                filtro_cargo=cargo_filtro,
                sigla_uf_override=filtro_uf,
                ano_override=filtro_ano,
            )
        renderizar_resposta_geral(resp, caminho_str, assistente, "painel_p3")

    with tab_p1:
        with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
            resp = assistente.responder(
                conn,
                "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?",
                filtro_cargo=cargo_filtro,
                sigla_uf_override="DF",
                ano_override=filtro_ano,
            )
        renderizar_resposta_geral(resp, caminho_str, assistente, "painel_p1")

    with tab_p2:
        with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
            resp = assistente.responder(
                conn,
                "Existe sazonalidade nas contratações e demissões?",
                filtro_cargo=cargo_filtro,
                sigla_uf_override=filtro_uf,
                ano_override=filtro_ano,
            )
        renderizar_resposta_geral(resp, caminho_str, assistente, "painel_p2")

    with tab_p4:
        with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
            resp = assistente.responder(
                conn,
                "Os setores com maior rotatividade praticam salários médios mais baixos?",
                filtro_cargo=cargo_filtro,
                sigla_uf_override=filtro_uf,
                ano_override=filtro_ano,
            )
        renderizar_resposta_geral(resp, caminho_str, assistente, "painel_p4")

    with tab_p5:
        with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
            resp = assistente.responder(
                conn,
                "Como o perfil sociodemográfico impacta o salário médio de admissão?",
                filtro_cargo=cargo_filtro,
                sigla_uf_override=filtro_uf,
                ano_override=filtro_ano,
                eixo_override="sexo",
            )
        renderizar_resposta_geral(resp, caminho_str, assistente, "painel_p5")


# ==============================================================================
# VIEW 2: EXPLORADOR OCUPACIONAL (BUSCA VETORIAL CBO 2002)
# ==============================================================================

def render_view_busca_cbo(
    caminho_str: str,
    indice: IndiceVetorialCBO,
    assistente: AssistenteTextToSQL,
    filtro_uf: str | None,
    filtro_ano: int | None,
) -> None:
    st.markdown("## 🔍 Explorador Ocupacional (Busca Semântica CBO 2002)")
    st.caption("Motor de busca vetorial híbrido com embeddings de 384 dimensões e similaridade de cosseno via DuckDB.")

    if "busca_termo_ativo" not in st.session_state:
        st.session_state["busca_termo_ativo"] = "professor"

    # Barra de busca proeminente
    col_input, col_btn = st.columns([5, 1])
    with col_input:
        termo_digitado = st.text_input(
            "Buscar cargo ou ocupação:",
            value=st.session_state["busca_termo_ativo"],
            placeholder="Ex.: dev backend, caminhoneiro, professor, enfermeiro, 212405...",
            label_visibility="collapsed",
        )
    with col_btn:
        if st.button("Buscar Ocupação", type="primary", use_container_width=True):
            st.session_state["busca_termo_ativo"] = termo_digitado
            st.rerun()

    # Chips de sugestão rápida
    st.markdown("**Atalhos de Ocupações:**")
    cols_sug = st.columns(len(SUGESTOES_PROFISSÕES))
    for i, (label_sug, val_sug) in enumerate(SUGESTOES_PROFISSÕES):
        if cols_sug[i].button(label_sug, key=f"sug_cbo_{i}", use_container_width=True):
            st.session_state["busca_termo_ativo"] = val_sug
            st.rerun()

    termo_ativo = st.session_state["busca_termo_ativo"].strip()
    if not termo_ativo:
        return

    # Execução da busca vetorial
    resultados = indice.buscar_semantico(termo_ativo, top_k=5, apenas_oficiais=True)
    if not resultados:
        resultados = indice.buscar_semantico(termo_ativo, top_k=5, apenas_oficiais=False)

    if not resultados:
        st.warning(f"Nenhuma ocupação encontrada para o termo '{termo_ativo}'.")
        return

    top1 = resultados[0]
    codigos_encontrados = [r.codigo_cbo for r in resultados]

    # Indicadores reais no DuckDB
    with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
        ind_sel = consultar_indicadores_cbo(conn, codigos_cbo=[top1.codigo_cbo], sigla_uf=filtro_uf, ano=filtro_ano)
        ind_grupo = consultar_indicadores_cbo(conn, codigos_cbo=codigos_encontrados, sigla_uf=filtro_uf, ano=filtro_ano)

    st.markdown(f"### Ocupação Identificada: `{top1.codigo_cbo}` — {top1.titulo_ocupacao}")
    
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        render_kpi("Salário Médio Inicial", fmt_moeda(ind_sel["salario_medio_admissao"]), "Salário oficial de admissão", "#10B981")
    with c2:
        render_kpi("Similaridade Semântica", f"{top1.score * 100:.1f}%", f"Método: {top1.metodo}", "#8B5CF6")
    with c3:
        render_kpi("Total Contratações", fmt_int(ind_sel["admissoes"]), f"Demissões: {fmt_int(ind_sel['desligamentos'])}", "#2563EB")
    with c4:
        render_kpi("Saldo Líquido", fmt_int(ind_sel["saldo"], True), "Postos criados", "#6366F1")

    st.markdown("<br>", unsafe_allow_html=True)
    
    # Abas de detalhamento do cargo
    tab_similares, tab_perfil, tab_geo = st.tabs([
        "📋 Ocupações Relacionadas (Top 5)",
        "👥 Perfil Demográfico do Cargo",
        "📍 Distribuição Geográfica",
    ])

    with tab_similares:
        mapa_ind = {item["codigo_cbo"]: item for item in ind_grupo["por_ocupacao"]}
        linhas_tab = []
        for r in resultados:
            d = mapa_ind.get(r.codigo_cbo, {})
            linhas_tab.append({
                "Código CBO": r.codigo_cbo,
                "Título da Ocupação": r.titulo_ocupacao,
                "Similaridade": f"{r.score * 100:.1f}%",
                "Contratações": fmt_int(d.get("admissoes", 0)),
                "Demissões": fmt_int(d.get("desligamentos", 0)),
                "Saldo de Postos": fmt_int(d.get("saldo", 0), True),
                "Salário Inicial Médio": fmt_moeda(d.get("salario_medio_admissao")),
            })
        st.dataframe(pd.DataFrame(linhas_tab), hide_index=True)

    with tab_perfil:
        with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
            resp_perfil = assistente.responder(
                conn,
                "Como o perfil sociodemográfico impacta o salário médio de admissão?",
                filtro_cargo=termo_ativo,
                codigos_cbo_override=[top1.codigo_cbo],
                sigla_uf_override=filtro_uf,
                ano_override=filtro_ano,
                eixo_override="sexo",
            )
        df_p = pd.DataFrame(resp_perfil.linhas, columns=resp_perfil.colunas)
        if not df_p.empty:
            render_p5_sociodemografico(df_p, resp_perfil.filtros_aplicados, caminho_str, assistente, "cbo_view")
        else:
            st.info("Não há dados demográficos suficientes para esta ocupação no filtro selecionado.")

    with tab_geo:
        with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
            resp_geo = assistente.responder(
                conn,
                "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?",
                filtro_cargo=termo_ativo,
                codigos_cbo_override=[top1.codigo_cbo],
                sigla_uf_override=filtro_uf,
                ano_override=filtro_ano,
            )
        df_g = pd.DataFrame(resp_geo.linhas, columns=resp_geo.colunas)
        if not df_g.empty:
            render_p3_capitais_interior(df_g, top1.titulo_ocupacao)
        else:
            st.info("Não há dados geográficos suficientes para esta ocupação no filtro selecionado.")


# ==============================================================================
# VIEW 3: ASSISTENTE INTELIGENTE TEXT-TO-SQL
# ==============================================================================

def render_view_assistente_sql(
    caminho_str: str,
    assistente: AssistenteTextToSQL,
    indice: IndiceVetorialCBO,
    filtro_uf: str | None,
    filtro_ano: int | None,
    cargo_filtro: str | None,
) -> None:
    st.markdown("## 💬 Assistente Inteligente (Text-to-SQL Governado)")
    st.caption("Tradução determinística de perguntas em linguagem natural para consultas SQL seguras sobre a camada Gold.")

    if "pergunta_input" not in st.session_state:
        st.session_state["pergunta_input"] = "Qual a diferença salarial entre homens e mulheres?"

    col_input, col_btn = st.columns([5, 1])
    with col_input:
        pergunta_digitada = st.text_input(
            "Faça sua pergunta:",
            value=st.session_state["pergunta_input"],
            placeholder="Ex.: Qual a diferença salarial entre homens e mulheres para professor?",
            label_visibility="collapsed",
        )
    with col_btn:
        if st.button("Consultar IA", type="primary", use_container_width=True):
            st.session_state["pergunta_input"] = pergunta_digitada
            st.rerun()

    # Atalhos rápidos de perguntas categorizadas
    st.markdown("**Perguntas Frequentes:**")
    cols_p = st.columns(len(PERGUNTAS_RAPIDAS))
    for i, (categoria, perg) in enumerate(PERGUNTAS_RAPIDAS):
        if cols_p[i].button(categoria, key=f"btn_faq_{i}", use_container_width=True):
            st.session_state["pergunta_input"] = perg
            st.rerun()

    pergunta_ativa = st.session_state["pergunta_input"].strip()
    if not pergunta_ativa:
        return

    with abrir_conexao_analitica(caminho_str, garantir_construcao=False) as conn:
        resposta = assistente.responder(
            conn,
            pergunta_ativa,
            filtro_cargo=cargo_filtro,
            sigla_uf_override=filtro_uf,
            ano_override=filtro_ano,
        )

    if not resposta.suportada:
        if resposta.intencao == "bloqueada_seguranca":
            st.error(f"🛡️ **Consulta Bloqueada pela Camada de Segurança / LGPD**\n\n{resposta.motivo_recusa}")
        else:
            st.warning(f"⚠️ **Consulta Fora do Escopo Metodológico**\n\n{resposta.motivo_recusa}")
        st.caption(f"Nota metodológica: {resposta.ressalva_metodologica}")
        return

    renderizar_resposta_geral(resposta, caminho_str, assistente, "assistente_sql")


# ==============================================================================
# FUNÇÃO PRINCIPAL (APP ENTRYPOINT)
# ==============================================================================

def main() -> None:
    st.set_page_config(
        page_title="METRA — Inteligência e Engenharia do Mercado de Trabalho",
        page_icon="💼",
        layout="wide",
        initial_sidebar_state="expanded",
    )

    st.markdown(ESTILO_CSS_CUSTOMIZADO, unsafe_allow_html=True)

    caminho_duckdb = obter_caminho_duckdb()
    indice, assistente, resumo = carregar_recursos_analiticos(str(caminho_duckdb))

    # --------------------------------------------------------------------------
    # SIDEBAR: IDENTIDADE, NAVEGAÇÃO E FILTROS GLOBAIS
    # --------------------------------------------------------------------------
    with st.sidebar:
        st.markdown("### 💼 METRA")
        st.caption("Monitoramento e Engenharia de Dados do Trabalho  \n**FCTE-UnB • Banco de Dados 2 (Squad G4)**")
        st.markdown('<span class="metra-badge badge-success">● DuckDB Gold Ativo</span>', unsafe_allow_html=True)
        st.divider()

        st.markdown("#### 🧭 Navegação")
        opcao_menu = st.radio(
            "Selecione o Módulo:",
            options=[
                "📊 Painel Executivo (5 Perguntas)",
                "🔍 Explorador de Ocupações (CBO)",
                "💬 Assistente Text-to-SQL",
            ],
            index=0,
            label_visibility="collapsed",
        )
        st.divider()

        st.markdown("#### ⚙️ Filtros Globais")
        uf_selecionada = st.selectbox(
            "Estado (UF):",
            options=["Todas (Centro-Oeste)", "DF", "GO", "MT", "MS"],
            index=0,
        )
        ano_selecionado = st.selectbox(
            "Ano Calendário:",
            options=["Todos (2023–2026)", 2023, 2024, 2025, 2026],
            index=0,
        )

        cargo_global = st.text_input(
            "Filtrar por Cargo (Opcional):",
            value="",
            placeholder="Ex.: professor, enfermeiro...",
            help="Filtra todas as visualizações para este cargo específico através da CBO 2002.",
        )

        filtro_uf_efetivo = None if uf_selecionada.startswith("Todas") else uf_selecionada
        filtro_ano_efetivo = None if str(ano_selecionado).startswith("Todos") else int(ano_selecionado)
        cargo_efetivo = cargo_global.strip() or None

        st.divider()
        st.markdown("#### 📈 Resumo da Base")
        st.markdown(f"""
            - **Movimentações:** `{fmt_int(resumo['total_movimentacoes'])}`
            - **Contratações:** `{fmt_int(resumo['admissoes'])}`
            - **Saldo Líquido:** `{fmt_int(resumo['saldo'], True)}`
            - **Período:** `{resumo['comp_min']} a {resumo['comp_max']}`
        """)

    # --------------------------------------------------------------------------
    # CABEÇALHO SUPERIOR DA PÁGINA
    # --------------------------------------------------------------------------
    col_t1, col_t2 = st.columns([3, 1])
    with col_t1:
        st.markdown(f"# METRA • Monitoramento do Mercado de Trabalho")
        filtros_desc = []
        if filtro_uf_efetivo:
            filtros_desc.append(f"UF: **{filtro_uf_efetivo}**")
        else:
            filtros_desc.append("Região: **Centro-Oeste**")
        if filtro_ano_efetivo:
            filtros_desc.append(f"Ano: **{filtro_ano_efetivo}**")
        else:
            filtros_desc.append("Período: **2023–2026**")
        if cargo_efetivo:
            filtros_desc.append(f"Cargo: **{cargo_efetivo}**")
        
        st.caption("Filtros Ativos: " + "  •  ".join(filtros_desc))

    with col_t2:
        st.markdown("<br>", unsafe_allow_html=True)
        st.markdown(
            f'<div style="text-align: right;"><span class="metra-badge badge-primary">Salário Médio: {fmt_moeda(resumo["salario_medio"])}</span></div>',
            unsafe_allow_html=True,
        )

    st.markdown("---")

    # --------------------------------------------------------------------------
    # RENDERIZAÇÃO DO MÓDULO SELECIONADO
    # --------------------------------------------------------------------------
    if opcao_menu == "📊 Painel Executivo (5 Perguntas)":
        render_view_painel_executivo(
            str(caminho_duckdb),
            assistente,
            indice,
            filtro_uf_efetivo,
            filtro_ano_efetivo,
            cargo_efetivo,
        )
    elif opcao_menu == "🔍 Explorador de Ocupações (CBO)":
        render_view_busca_cbo(
            str(caminho_duckdb),
            indice,
            assistente,
            filtro_uf_efetivo,
            filtro_ano_efetivo,
        )
    elif opcao_menu == "💬 Assistente Text-to-SQL":
        render_view_assistente_sql(
            str(caminho_duckdb),
            assistente,
            indice,
            filtro_uf_efetivo,
            filtro_ano_efetivo,
            cargo_efetivo,
        )


if __name__ == "__main__":
    main()
