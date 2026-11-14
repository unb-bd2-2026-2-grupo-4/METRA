"""Testes das visões P1 a P5, sem acesso ao banco de produção."""

from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch

import altair as alt
import pandas as pd
from streamlit.testing.v1 import AppTest

from src.app import dashboard


def dados_p1() -> pd.DataFrame:
    return pd.DataFrame({
        "codigo_secao": list("ABCDEFGHIJ"),
        "descricao_secao": [f"Setor {secao}" for secao in "ABCDEFGHIJ"],
        "admissoes": [100, 90, 80, 70, 60, 50, 40, 30, 20, 0],
        "desligamentos": [110, 50, 70, 60, 50, 40, 30, 20, 10, 5],
        "saldo": [-10, 40, 10, 10, 10, 10, 10, 10, 10, -5],
        "ranking_admissoes": list(range(1, 11)),
        "inicio": ["2024-01-01"] * 10,
        "fim": ["2024-12-01"] * 10,
        "competencias_disponiveis": [12] * 10,
    })


def dados_p2() -> pd.DataFrame:
    linhas = []
    for ano, meses in ((2023, range(1, 13)), (2026, (1, 2))):
        for mes in meses:
            for secao, media in (("A", 10), ("B", 20)):
                media_mes = media if mes == 1 else 0
                admissoes = media_mes if ano == 2023 else (media * 10 if mes == 1 else None)
                linhas.append({
                    "ano": ano, "mes": mes, "competencia": f"{ano}-{mes:02d}-01",
                    "sigla_uf": "GO", "codigo_secao": secao,
                    "admissoes": admissoes, "desligamentos": 0 if admissoes is not None else None,
                    "saldo": admissoes, "anos_considerados": 1,
                    "media_admissoes_mes": media_mes, "media_desligamentos_mes": 0,
                    "media_saldo_mes": media_mes,
                })
    return pd.DataFrame(linhas)


def dados_p3() -> pd.DataFrame:
    linhas = []
    for recorte, fator in (("GO", 1), ("DF", 2), ("Centro-Oeste", 3)):
        for nivel, ano, saldo in (("anual", 2024, 20), ("anual", 2023, 10), ("total", None, 30)):
            saldo *= fator
            interior = None if recorte == "DF" else saldo // 2
            linhas.append({
                "recorte": recorte, "nivel": nivel, "ano": ano,
                "saldo_capital": saldo, "saldo_interior": interior,
                "diferenca_saldo": saldo - interior if interior is not None else None,
                "salario_capital": 3000, "salario_interior": 2000 if interior is not None else None,
                "diferenca_salario": 1000 if interior is not None else None,
                "n_capital": saldo, "n_interior": interior or 0,
            })
    return pd.DataFrame(linhas)


def dados_p4() -> pd.DataFrame:
    return pd.DataFrame({
        "codigo_secao": list("ABCDEF"),
        "indice_fluxos_pareados_pct": [20, 20, 80, 80, 50, None],
        "salario_medio_admissao": [1000, 3000, 1000, 3000, 2000, 9000],
        "saldo": [1, 2, -1, -2, 0, 0],
        "correlacao_pearson": [0.0] * 6,
    })


def dados_p5(eixo: str = "sexo") -> pd.DataFrame:
    return pd.DataFrame({
        "eixo": [eixo] * 5,
        "codigo_categoria": [1, 1, 2, 3, 9],
        "categoria": ["Homens", "Homens", "Mulheres", "Sem salário", "Não informado"],
        "admissoes": [1, 2, 2, 1, 1],
        "desligamentos": [0, 0, 3, 0, 0],
        "saldo": [1, 2, -1, 1, 1],
        "soma_salarios_admissao": [1000, 2000, 6000, 0, 3000],
        "qtd_salarios_admissao": [1, 2, 2, 0, 1],
    })


class DashboardTest(unittest.TestCase):
    def setUp(self) -> None:
        st_patch = patch.object(dashboard, "st")
        self.st = st_patch.start()
        self.addCleanup(st_patch.stop)
        self.st.columns.side_effect = lambda larguras: [
            MagicMock() for _ in range(larguras if isinstance(larguras, int) else len(larguras))
        ]
        self.st.radio.return_value = "sexo"

    def test_p1_ranking_top8_kpis_e_filtros(self) -> None:
        with patch.object(dashboard, "render_kpi") as kpi:
            dashboard.render_p1_setores_df(dados_p1(), "professor", {"sigla_uf": "GO", "ano": 2024})
        self.assertIn("GO (Ano 2024) — professor", self.st.markdown.call_args_list[0].args[0])
        self.assertEqual(kpi.call_args_list[0].args[1], "Seção A (100)")
        self.assertEqual(kpi.call_args_list[1].args[1], "Seção B (+40)")
        self.assertEqual(kpi.call_args_list[2].args[1:], ("2024-01 a 2024-12", "12 competências"))
        grafico = self.st.bar_chart.call_args.args[0]
        self.assertEqual(grafico.index.tolist(), [f"{secao} - Setor {secao}" for secao in "ABCDEFGH"])
        self.assertEqual(grafico.loc["A - Setor A"].tolist(), [100, 110])
        tabela = self.st.dataframe.call_args.args[0].set_index("Seção")
        self.assertEqual(len(tabela), 10)
        self.assertEqual(tabela.loc["A", "Pos."], "1º")
        self.assertEqual(tabela.loc["J", "Saldo"], "-5")

    def test_p1_sem_admissoes_mantem_tabela_sem_grafico(self) -> None:
        with patch.object(dashboard, "render_kpi") as kpi:
            dashboard.render_p1_setores_df(dados_p1().iloc[-1:])
        kpi.assert_not_called()
        self.st.bar_chart.assert_not_called()
        self.assertEqual(self.st.dataframe.call_args.args[0]["Desligamentos"].tolist(), ["5"])

    def test_p2_curvas_medias_sem_duplicar_setores_nem_incluir_ano_parcial(self) -> None:
        dashboard.render_p2_sazonalidade(dados_p2(), filtros={"codigo_secao": "A"})
        historico, sazonal = [chamada.args[0] for chamada in self.st.line_chart.call_args_list]
        self.assertEqual(len(historico), 13)
        self.assertEqual(historico.loc["2023-01", "Admissões"], 30)
        self.assertEqual(historico.loc["2026-01", "Admissões"], 300)
        self.assertNotIn("2026-02", historico.index)
        self.assertEqual(sazonal.loc["01 - Jan", "Média admissões"], 30)
        self.assertEqual(sazonal.loc["02 - Fev", "Média admissões"], 0)
        tabela = self.st.dataframe.call_args.args[0].set_index("Mês")
        self.assertEqual(tabela.loc["01 - Jan", "Média saldo (anos compl.)"], "+30")
        self.assertEqual(tabela.loc["01 - Jan", "Saldo acumulado (série total)"], "+330")
        self.assertIn("Seção A", self.st.markdown.call_args_list[0].args[0])

    def test_p2_ano_parcial_preserva_mes_ausente_e_zero_observado(self) -> None:
        df = dados_p2().query("ano == 2026").copy()
        df[["media_admissoes_mes", "media_desligamentos_mes", "media_saldo_mes"]] = None
        df["anos_considerados"] = 0
        for zero_observado in (False, True):
            with self.subTest(zero_observado=zero_observado):
                if zero_observado:
                    df.loc[df["mes"] == 2, ["admissoes", "desligamentos", "saldo"]] = 0
                self.st.reset_mock()
                dashboard.render_p2_sazonalidade(df)
                sazonal = self.st.line_chart.call_args.args[0]
                self.assertEqual(sazonal.loc["01 - Jan", "Saldo"], 300)
                tabela = self.st.dataframe.call_args.args[0].set_index("Mês")
                self.assertTrue(tabela["Média saldo (anos compl.)"].eq("—").all())
                self.assertEqual(tabela.loc["02 - Fev", "Saldo acumulado (série total)"], "0" if zero_observado else "—")

    def test_p3_recorte_serie_anual_total_e_df_sem_interior(self) -> None:
        for filtros, recorte in (({}, "Centro-Oeste"), ({"sigla_uf": "GO"}, "GO"), ({"sigla_uf": "DF"}, "DF")):
            with self.subTest(recorte=recorte):
                fator = {"GO": 1, "DF": 2, "Centro-Oeste": 3}[recorte]
                self.st.reset_mock()
                with patch.object(dashboard, "render_kpi") as kpi:
                    dashboard.render_p3_capitais_interior(dados_p3(), filtros=filtros)
                self.assertIn(f"({recorte})", self.st.markdown.call_args_list[0].args[0])
                tabela = self.st.dataframe.call_args_list[0].args[0].set_index("Período")
                self.assertEqual(tabela.index.tolist(), ["2023", "2024", "Total"])
                self.assertEqual(tabela["Saldo Capital"].tolist(), [f"+{saldo * fator}" for saldo in (10, 20, 30)])
                salarios = self.st.bar_chart.call_args_list[0].args[0]
                self.assertEqual(salarios.index.tolist(), ["2023", "2024"])
                saldos = self.st.bar_chart.call_args_list[1].args[0]
                self.assertEqual(saldos["Capitais"].tolist(), [10 * fator, 20 * fator])
                if recorte == "DF":
                    self.assertTrue(tabela["Salário Interior"].eq("—").all())
                    self.assertTrue(tabela["n Interior"].eq("0").all())
                    self.assertTrue(salarios["Interior"].isna().all())
                    self.assertEqual(kpi.call_args_list[1].args[1], "—")
                else:
                    self.assertEqual(tabela.loc["Total", "Dif. Saldo (Cap. − Int.)"], f"+{15 * fator}")
                    self.assertEqual(tabela.loc["Total", "Dif. Salário (Cap. − Int.)"], "R$ 1.000,00")
                self.assertIn(f"+{30 * fator}", kpi.call_args_list[0].args[2])

    def test_p4_quadrantes_mediana_destaque_e_dados_ausentes(self) -> None:
        df = dados_p4()
        original = df.copy(deep=True)
        dashboard.render_p4_rotatividade(df, filtros={"codigo_secao": "B"})
        pontos, spec = self.st.vega_lite_chart.call_args.args
        alt.LayerChart.from_dict(spec, validate=True)
        self.assertEqual(pontos["Quadrante"].tolist(), [
            "Índice baixo / salário baixo", "Índice baixo / salário alto",
            "Índice alto / salário baixo", "Índice alto / salário alto",
            "Índice alto / salário alto",
        ])
        self.assertEqual(pontos.loc[pontos["Selecionada"], "codigo_secao"].tolist(), ["B"])
        tabela = self.st.dataframe.call_args.args[0].set_index("Seção")
        self.assertEqual(tabela.loc["F", "Quadrante"], "Sem dados")
        pd.testing.assert_frame_equal(df, original)

    def test_p4_sem_filtro_sem_pares_e_secao_indisponivel(self) -> None:
        dashboard.render_p4_rotatividade(dados_p4())
        self.assertFalse(self.st.vega_lite_chart.call_args.args[0]["Selecionada"].any())
        for df in (dados_p4().iloc[5:], dados_p4().iloc[:0]):
            with self.subTest(vazio=df.empty):
                self.st.reset_mock()
                dashboard.render_p4_rotatividade(df, filtros={"codigo_secao": "F"})
                self.st.vega_lite_chart.assert_not_called()
                self.assertIn("Seção F", self.st.info.call_args.args[0])
                self.assertEqual(len(self.st.dataframe.call_args.args[0]), len(df))

    def test_p5_media_ponderada_hiatos_e_saldo_nos_quatro_eixos(self) -> None:
        for eixo in dashboard.MAPA_EIXOS_DEMOGRAFICOS:
            with self.subTest(eixo=eixo):
                self.st.reset_mock()
                self.st.radio.return_value = eixo
                dashboard.render_p5_sociodemografico(dados_p5(eixo), {"eixo": eixo, "codigo_secao": "C"})
                grafico, spec = self.st.vega_lite_chart.call_args.args
                alt.LayerChart.from_dict(spec, validate=True)
                grafico = grafico.set_index("categoria")
                # A média inclui a categoria não informada: 12000 / 6 = 2000.
                self.assertEqual(grafico.loc["Homens", "dif_media_reais"], -1000)
                self.assertEqual(grafico.loc["Mulheres", "dif_media_reais"], 1000)
                self.assertEqual(grafico.loc["Homens", "dif_media_pct"], -50)
                self.assertEqual(set(grafico.index), {"Homens", "Mulheres"})
                tabela = self.st.dataframe.call_args.args[0].set_index("Categoria")
                self.assertEqual(tabela.loc["Homens", "Saldo líquido"], "+3")
                self.assertEqual(tabela.loc["Mulheres", "Saldo líquido"], "-1")
                self.assertEqual(tabela.loc["Homens", "Diferença salarial (R$)"], "R$ -1.000,00")
                self.assertEqual(tabela.loc["Sem salário", "Diferença salarial (R$)"], "—")
                self.assertIn("Não informado", tabela.index)
                self.assertTrue(any("CNAE C" in call.args[0] for call in self.st.caption.call_args_list))
                self.st.bar_chart.assert_called_once()

    def test_p5_sem_salarios_e_sem_registros(self) -> None:
        df = dados_p5()
        df[["soma_salarios_admissao", "qtd_salarios_admissao"]] = 0
        dashboard.render_p5_sociodemografico(df, {"eixo": "sexo"})
        tabela = self.st.dataframe.call_args.args[0]
        for coluna in ("Salário médio", "Diferença salarial (R$)", "Dif. p/ média"):
            self.assertTrue(tabela[coluna].eq("—").all())
        self.st.vega_lite_chart.assert_not_called()
        self.st.bar_chart.assert_not_called()
        self.st.info.assert_called_once()
        self.st.reset_mock()
        dashboard.render_p5_sociodemografico(pd.DataFrame(), {})
        self.st.radio.assert_not_called()
        self.st.info.assert_called_once()

    def test_p5_troca_de_dimensao_preserva_filtros_e_resposta(self) -> None:
        self.st.radio.return_value = "raca_cor"
        novo_df = dados_p5("raca_cor")
        resposta = SimpleNamespace(linhas=novo_df.values.tolist(), colunas=list(novo_df.columns))
        filtros = {
            "eixo": "sexo", "codigo_secao": "C", "sigla_uf": "GO", "ano": 2024,
            "termo_ocupacao": "professor", "codigos_cbo": ["231205"],
        }
        with patch.object(dashboard, "obter_resposta_cached", return_value=resposta) as consulta:
            resultado = dashboard.render_p5_sociodemografico(dados_p5(), filtros, "teste.duckdb")
        self.assertIs(resultado, resposta)
        self.assertEqual(consulta.call_args.kwargs, {
            "filtro_cargo": "professor", "codigos_cbo_override": ["231205"],
            "sigla_uf_override": "GO", "ano_override": 2024,
            "eixo_override": "raca_cor", "codigo_secao_override": "C",
        })
        self.assertEqual(set(self.st.vega_lite_chart.call_args.args[0]["categoria"]), {"Homens", "Mulheres"})


class DashboardStreamlitTest(unittest.TestCase):
    def test_renderizacao_real_p1_a_p5(self) -> None:
        app = AppTest.from_string("""
from src.app.dashboard import (
    render_p1_setores_df, render_p2_sazonalidade, render_p3_capitais_interior,
    render_p4_rotatividade, render_p5_sociodemografico,
)
from tests.test_dashboard import dados_p1, dados_p2, dados_p3, dados_p4, dados_p5
render_p1_setores_df(dados_p1(), filtros={"sigla_uf": "GO", "ano": 2024})
render_p2_sazonalidade(dados_p2())
render_p3_capitais_interior(dados_p3(), filtros={"sigla_uf": "DF"})
render_p4_rotatividade(dados_p4(), filtros={"codigo_secao": "B"})
render_p5_sociodemografico(dados_p5(), {"eixo": "sexo", "codigo_secao": "C"})
""").run()
        self.assertEqual(len(app.exception), 0, str(app.exception))
        self.assertEqual(len(app.dataframe), 6)
        self.assertEqual(len(app.get("vega_lite_chart")), 10)


if __name__ == "__main__":
    unittest.main()
