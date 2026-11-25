"""Testes do catálogo de dados, publicação do dbt docs estático e linhagem ponta a ponta (E4).

Executar na raiz:
    python -m unittest discover -s tests -p 'test_catalogo_linhagem.py' -v
"""

from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from src.catalogo.gerar_dbt_docs import (
    DESTINO_PADRAO_DIR,
    LINHAGEM_CAMADAS_PONTA_A_PONTA,
    gerar_dbt_docs,
)

RAIZ = Path(__file__).resolve().parents[1]


class CatalogoELinhagemTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="metra_test_catalogo_")
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.destino_tmp = Path(cls.tmp.name) / "dbt-docs"
        cls.resumo = gerar_dbt_docs(cls.destino_tmp)

    def test_dbt_docs_estatico_e_json_de_linhagem_sao_gerados(self) -> None:
        html_path = self.destino_tmp / "index.html"
        json_path = self.destino_tmp / "linhagem.json"
        self.assertTrue(html_path.is_file(), "static_index.html (index.html) não foi gerado")
        self.assertGreater(html_path.stat().st_size, 100_000)
        self.assertTrue(json_path.is_file(), "linhagem.json não foi gerado")

        conteudo_html = html_path.read_text(encoding="utf-8", errors="ignore")
        for termo_esperado in (
            "painel_streamlit",
            "assistente_text_to_sql_e_busca_cbo",
            "base_consumo_isolada",
            "etl_reverso_json_publico",
            "fct_movimentacao",
            "setor_mensal",
        ):
            self.assertIn(termo_esperado, conteudo_html)

    def test_todos_os_modelos_e_colunas_possuem_descricao_e_tipo_no_catalogo(self) -> None:
        q = self.resumo["resumo_quantitativo"]
        self.assertEqual(q["fontes_parquet"], 5)
        self.assertEqual(q["modelos_e_snapshots"], 20)  # 4 Silver + 1 Snapshot + 11 Gold/TimeSpine + 4 Consumo
        self.assertEqual(q["metricas_camada_semantica"], 7)
        self.assertEqual(q["analises_p1_a_p5"], 5)
        self.assertEqual(q["exposures_consumo_final"], 4)
        self.assertGreaterEqual(q["testes_declarativos_dbt"], 210)

        for modelo in self.resumo["modelos"]:
            with self.subTest(modelo=modelo["nome"]):
                self.assertTrue(modelo["descricao"], f"Modelo {modelo['nome']} sem descrição")
                self.assertGreater(modelo["quantidade_colunas"], 0)
                for col in modelo["colunas"]:
                    self.assertNotEqual(col["tipo"], "DESCONHECIDO", f"Coluna {col['nome']} sem tipo físico")
                    if modelo["schema"] in ("silver", "gold", "consumo"):
                        self.assertTrue(
                            col["descricao"],
                            f"Coluna {modelo['schema']}.{modelo['nome']}.{col['nome']} sem descrição no catálogo",
                        )

    def test_linhagem_conecta_fontes_ate_painel_e_etl_reverso(self) -> None:
        self.assertEqual(len(LINHAGEM_CAMADAS_PONTA_A_PONTA), 8)
        exposures = {e["nome"]: e for e in self.resumo["exposures"]}
        self.assertEqual(
            set(exposures.keys()),
            {
                "painel_streamlit",
                "assistente_text_to_sql_e_busca_cbo",
                "base_consumo_isolada",
                "etl_reverso_json_publico",
            },
        )
        # Painel depende dos marts Gold e das métricas da camada semântica
        deps_painel = set(exposures["painel_streamlit"]["depende_de"])
        for esperado in (
            "model.metra.fct_setor_mensal",
            "model.metra.fct_geografia_mensal",
            "model.metra.fct_perfil_mensal",
            "model.metra.fct_movimentacao",
            "model.metra.dim_cbo_historico",
            "metric.metra.salario_medio_admissao",
            "metric.metra.indice_fluxos_pareados_pct",
        ):
            self.assertIn(esperado, deps_painel)

        # ETL reverso depende exclusivamente das 4 views de consumo e das métricas semânticas
        deps_etl = set(exposures["etl_reverso_json_publico"]["depende_de"])
        for esperado_etl in (
            "model.metra.setor_mensal",
            "model.metra.geografia_mensal",
            "model.metra.perfil_anual",
            "model.metra.calendario",
            "metric.metra.salario_medio_admissao",
        ):
            self.assertIn(esperado_etl, deps_etl)

        # Confere que o artefato versionado em docs/assets/dbt-docs/linhagem.json está sincronizado
        versionado = DESTINO_PADRAO_DIR / "linhagem.json"
        self.assertTrue(versionado.is_file())
        dados_versionados = json.loads(versionado.read_text(encoding="utf-8"))
        self.assertEqual(dados_versionados["resumo_quantitativo"], self.resumo["resumo_quantitativo"])


if __name__ == "__main__":
    unittest.main()
