"""Testes unitários e de integração da Busca Semântica CBO e do Assistente Text-to-SQL (ADR 0007).

Executar no ambiente de requirements-pipeline.txt:
    python -m unittest discover -s tests -p 'test_busca_e_text2sql.py' -v
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import duckdb

from src.app.banco_analitico import abrir_conexao_analitica, construir_gold_de_amostra
from src.app.busca_cbo import (
    DIMENSAO_VETOR,
    IndiceVetorialCBO,
    RegistroCBO,
    consultar_indicadores_cbo,
    gerar_embedding_cbo,
)
from src.app.text_to_sql import (
    AssistenteTextToSQL,
    ViolacaoSegurancaSQL,
    _gerar_sql_p1,
    _gerar_sql_p2,
    _gerar_sql_p3,
    _gerar_sql_p4,
    _gerar_sql_p5,
    validar_sql_seguro,
)


class BuscaSemanticaCBOTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.indice = IndiceVetorialCBO.de_catalogo_padrao()

    def test_dimensao_e_normalizacao_l2_dos_embeddings(self) -> None:
        emb = gerar_embedding_cbo("Analista de desenvolvimento de sistemas", "212405")
        self.assertEqual(emb.shape, (DIMENSAO_VETOR,))
        self.assertAlmostEqual(float((emb * emb).sum()), 1.0, places=5)

    def test_codigo_exato_com_zero_a_esquerda_em_primeiro_lugar(self) -> None:
        for codigo in ("010105", "010205", "212405", "782510"):
            res = self.indice.buscar_semantico(codigo, top_k=3)
            self.assertTrue(res, f"Nenhum resultado para {codigo}")
            self.assertEqual(res[0].codigo_cbo, codigo)
            self.assertEqual(res[0].score, 1.0)
            self.assertEqual(res[0].metodo, "codigo_exato")

    def test_sinonimos_superam_busca_lexica_sem_codigos_inexistentes(self) -> None:
        catalogo_valido = {r.codigo_cbo for r in self.indice.registros}
        casos = [
            ("dev backend software", {"212405", "317110", "212205"}),
            ("caminhoneiro carreteiro", {"782510"}),
            ("caixa de supermercado", {"421125"}),
            ("boia fria lavoura", {"622020", "621005"}),
            ("medico do coracao", {"223104"}),
        ]
        for consulta, esperados in casos:
            res_sem = self.indice.buscar_semantico(consulta, top_k=5)
            self.assertTrue(res_sem, f"Busca semântica vazia para '{consulta}'")
            codigos_sem = [r.codigo_cbo for r in res_sem]
            self.assertTrue(all(c in catalogo_valido for c in codigos_sem))
            self.assertTrue(
                any(c in esperados for c in codigos_sem[:3]),
                f"Esperado um de {esperados} no Top-3 para '{consulta}', obtido {codigos_sem[:3]}",
            )

    def test_paridade_busca_vetorial_numpy_e_duckdb_sql(self) -> None:
        with duckdb.connect() as conn:
            res_np = self.indice.buscar_semantico("programador de sistemas", top_k=5)
            res_db = self.indice.buscar_semantico(
                "programador de sistemas", top_k=5, conn_duckdb=conn
            )
            self.assertEqual(
                [r.codigo_cbo for r in res_np],
                [r.codigo_cbo for r in res_db],
            )
            for a, b in zip(res_np, res_db, strict=True):
                self.assertAlmostEqual(a.score, b.score, places=3)

    def test_identificacao_e_filtro_de_cadastro_nao_oficial(self) -> None:
        registros = list(self.indice.registros[:5]) + [
            RegistroCBO(
                codigo_cbo="999999",
                titulo_ocupacao="OCUPACAO CBO 999999 (ATUALIZACAO MTE)",
                codigo_grande_grupo="9",
                is_cadastro_oficial=False,
            )
        ]
        indice_misto = IndiceVetorialCBO(registros)
        res_todos = indice_misto.buscar_semantico("999999", top_k=3, apenas_oficiais=False)
        self.assertEqual(res_todos[0].codigo_cbo, "999999")
        self.assertFalse(res_todos[0].is_cadastro_oficial)

        res_oficiais = indice_misto.buscar_semantico("999999", top_k=3, apenas_oficiais=True)
        self.assertTrue(all(r.is_cadastro_oficial for r in res_oficiais))
        self.assertNotIn("999999", [r.codigo_cbo for r in res_oficiais])


class TextToSQLEIntegracaoGoldTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tmp = tempfile.TemporaryDirectory(prefix="metra_test_adr0007_")
        cls.caminho_banco = Path(cls.tmp.name) / "metra_analitico.duckdb"
        construir_gold_de_amostra(cls.caminho_banco)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.tmp.cleanup()

    def setUp(self) -> None:
        self.conn = abrir_conexao_analitica(self.caminho_banco, garantir_construcao=False)
        self.addCleanup(self.conn.close)
        self.indice = IndiceVetorialCBO.de_conexao_duckdb(self.conn)
        self.assistente = AssistenteTextToSQL(indice_cbo=self.indice)

    def test_igualdade_exata_p1_a_p5_com_sql_referencia(self) -> None:
        casos = [
            (
                "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?",
                "p1_setores_df",
                _gerar_sql_p1({}),
            ),
            (
                "Existe sazonalidade evidente nas contratações e demissões?",
                "p2_sazonalidade",
                _gerar_sql_p2({}),
            ),
            (
                "Qual é a diferença no saldo líquido e no salário médio entre as capitais e os municípios do interior?",
                "p3_capitais_interior",
                _gerar_sql_p3({}),
            ),
            (
                "Os setores com maior taxa de rotatividade praticam salários médios mais baixos?",
                "p4_fluxos_salarios",
                _gerar_sql_p4({}),
            ),
            (
                "Como o perfil sociodemográfico impacta o nível salarial e as movimentações?",
                "p5_perfil_remuneracao",
                _gerar_sql_p5({}),
            ),
        ]
        for pergunta, intencao_esp, sql_ref in casos:
            resp = self.assistente.responder(self.conn, pergunta)
            self.assertTrue(resp.suportada, f"Falha na pergunta: {pergunta}")
            self.assertEqual(resp.intencao, intencao_esp)
            esperado = self.conn.sql(sql_ref).fetchall()
            self.assertEqual(resp.linhas, esperado)

    def test_consulta_integrada_ocupacao_cbo_e_indicadores(self) -> None:
        resp = self.assistente.responder(
            self.conn,
            "Qual o saldo e o salário médio de caminhoneiro no Centro-Oeste?",
        )
        self.assertTrue(resp.suportada)
        self.assertEqual(resp.intencao, "cbo_ocupacao")
        self.assertTrue(resp.ocupacoes_resolvidas)
        codigos = [o["codigo_cbo"] for o in resp.ocupacoes_resolvidas]
        self.assertIn("782510", codigos)

        ind = consultar_indicadores_cbo(self.conn, codigos_cbo=["782510"])
        self.assertGreater(ind["admissoes"] + ind["desligamentos"], 0)
        self.assertEqual(ind["saldo"], ind["admissoes"] - ind["desligamentos"])

    def test_filtro_combinado_cargo_e_perfil_demografico(self) -> None:
        resp_prof = self.assistente.responder(
            self.conn,
            "Qual a diferença salarial entre homens e mulheres para o cargo de professor?",
        )
        self.assertTrue(resp_prof.suportada)
        self.assertEqual(resp_prof.intencao, "p5_perfil_remuneracao")
        self.assertEqual(resp_prof.filtros_aplicados.get("eixo"), "sexo")
        self.assertEqual(resp_prof.filtros_aplicados.get("termo_ocupacao"), "professor")
        self.assertTrue(resp_prof.filtros_aplicados.get("codigos_cbo"))
        self.assertIn("gold.fct_movimentacao", resp_prof.sql_gerado.lower())

        resp_cap_int = self.assistente.responder(
            self.conn,
            "Qual a diferença entre capitais e interior para caminhoneiro?",
        )
        self.assertTrue(resp_cap_int.suportada)
        self.assertEqual(resp_cap_int.intencao, "p3_capitais_interior")
        self.assertIn("782510", resp_cap_int.filtros_aplicados.get("codigos_cbo", []))

    def test_guardrails_bloqueiam_escrita_leitura_externa_e_linhas_individuais(self) -> None:
        proibidos = [
            "DROP TABLE gold.fct_movimentacao",
            "INSERT INTO gold.dim_cbo VALUES ('123456', 'X', '1', true)",
            "SELECT * FROM gold.fct_setor_mensal; DELETE FROM gold.dim_cbo",
            "SELECT * FROM read_parquet('data/lake/parquet/movimentacao/*.parquet')",
            "SELECT * FROM silver.stg_movimentacao",
            "SELECT * FROM gold.fct_movimentacao LIMIT 5",
        ]
        for sql in proibidos:
            with self.assertRaises(ViolacaoSegurancaSQL, msg=f"Deveria bloquear: {sql}"):
                validar_sql_seguro(sql)

        for pergunta_bloqueada in (
            "DROP TABLE gold.fct_movimentacao;",
            "Liste o CPF e o nome do trabalhador de cada registro individual",
        ):
            resp = self.assistente.responder(self.conn, pergunta_bloqueada)
            self.assertFalse(resp.suportada)
            self.assertEqual(resp.intencao, "bloqueada_seguranca")
            self.assertEqual(resp.linhas, [])

        for pergunta_fora_escopo in (
            "Qual a taxa de desemprego oficial da PNAD e o estoque da RAIS?",
            "Qual a probabilidade de eu ser contratado amanhã?",
        ):
            resp = self.assistente.responder(self.conn, pergunta_fora_escopo)
            self.assertFalse(resp.suportada)
            self.assertEqual(resp.intencao, "nao_suportada")
            self.assertEqual(resp.linhas, [])


if __name__ == "__main__":
    unittest.main()
