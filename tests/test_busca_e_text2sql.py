"""Testes unitários e de integração da Busca Semântica CBO e do Assistente Text-to-SQL (ADR 0007).

Executar no ambiente de requirements-pipeline.txt:
    python -m unittest discover -s tests -p 'test_busca_e_text2sql.py' -v
"""

from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb

from src.app.avaliar_busca_e_text2sql import (
    CONJUNTO_AVALIACAO_SINONIMOS,
    SQL_REF_P1_DF_2024,
    _carregar_sql_analise_dbt,
)
from src.app.banco_analitico import (
    CAMINHO_PADRAO_DUCKDB,
    DBT_PROJECT_DIR,
    abrir_conexao_analitica,
    construir_gold_de_amostra,
    obter_caminho_duckdb,
)
from src.app.busca_cbo import (
    DIMENSAO_VETOR,
    SINONIMOS_CBO_OFICIAIS,
    IndiceVetorialCBO,
    RegistroCBO,
    consultar_indicadores_cbo,
    gerar_embedding_cbo,
    normalizar_texto,
)
from src.app.text_to_sql import (
    AssistenteTextToSQL,
    ViolacaoSegurancaSQL,
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

    def test_consultas_fora_do_dicionario_superam_busca_lexica(self) -> None:
        sinonimos_norm = [normalizar_texto(v) for v in SINONIMOS_CBO_OFICIAIS.values()]
        for consulta, _ in CONJUNTO_AVALIACAO_SINONIMOS:
            q_norm = normalizar_texto(consulta)
            self.assertFalse(
                any(q_norm in s_val or s_val in q_norm for s_val in sinonimos_norm if s_val),
                f"Consulta de avaliação '{consulta}' não deve estar copiada em SINONIMOS_CBO_OFICIAIS",
            )

        catalogo_valido = {r.codigo_cbo for r in self.indice.registros}
        casos = [
            ("programacao backend de aplicativos web", {"212405", "317110", "212205"}),
            ("carreteiro de caminhao pesado e bitrem", {"782510"}),
            ("frente de caixa de supermercado e hipermercado", {"421125"}),
            ("boia fria na colheita de lavoura", {"622020", "621005"}),
            ("doutor especialista do coracao", {"223104"}),
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

    def test_paridade_busca_vetorial_numpy_e_duckdb_sql_com_acesso_externo_bloqueado(self) -> None:
        with duckdb.connect() as conn:
            conn.execute("SET enable_external_access = false; SET lock_configuration = true;")
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


class BancoAnaliticoSegurancaTest(unittest.TestCase):
    def test_metra_duckdb_relativo_alinhado_com_dbt_profiles(self) -> None:
        with patch.dict(os.environ, {"METRA_DUCKDB": "../data/metra_analitico.duckdb"}):
            resolvido = obter_caminho_duckdb()
            esperado_dbt = (DBT_PROJECT_DIR / "../data/metra_analitico.duckdb").resolve()
            self.assertEqual(resolvido, esperado_dbt)
            self.assertEqual(resolvido, CAMINHO_PADRAO_DUCKDB.resolve())

    def test_abrir_conexao_analitica_nao_reconstroi_nem_apaga_banco(self) -> None:
        with tempfile.TemporaryDirectory(prefix="metra_no_rebuild_") as tmp:
            inexistente = Path(tmp) / "nao_existe.duckdb"
            with self.assertRaises(FileNotFoundError):
                abrir_conexao_analitica(inexistente)
            self.assertFalse(inexistente.exists())

    def test_construir_gold_de_amostra_recusa_caminho_padrao_e_arquivo_existente(self) -> None:
        with self.assertRaises(PermissionError):
            construir_gold_de_amostra(CAMINHO_PADRAO_DUCKDB)

        with tempfile.TemporaryDirectory(prefix="metra_existing_") as tmp:
            existente = Path(tmp) / "ja_existe.duckdb"
            existente.write_bytes(b"conteudo_protegido")
            with self.assertRaises(FileExistsError):
                construir_gold_de_amostra(existente)
            self.assertEqual(existente.read_bytes(), b"conteudo_protegido")


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
        self.conn = abrir_conexao_analitica(self.caminho_banco)
        self.addCleanup(self.conn.close)
        self.indice = IndiceVetorialCBO.de_conexao_duckdb(self.conn)
        self.assistente = AssistenteTextToSQL(indice_cbo=self.indice)

    def test_igualdade_exata_p1_a_p5_contra_dbt_analyses_oficiais(self) -> None:
        casos = [
            (
                "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?",
                "p1_setores_df",
                _carregar_sql_analise_dbt("p1_setores_df"),
            ),
            (
                "Existe sazonalidade evidente nas contratações e demissões?",
                "p2_sazonalidade",
                _carregar_sql_analise_dbt("p2_sazonalidade"),
            ),
            (
                "Qual é a diferença no saldo líquido e no salário médio entre as capitais e os municípios do interior?",
                "p3_capitais_interior",
                _carregar_sql_analise_dbt("p3_capitais_interior"),
            ),
            (
                "Os setores com maior taxa de rotatividade praticam salários médios mais baixos?",
                "p4_fluxos_salarios",
                _carregar_sql_analise_dbt("p4_fluxos_salarios"),
            ),
            (
                "Como o perfil sociodemográfico impacta o nível salarial e as movimentações?",
                "p5_perfil_remuneracao",
                _carregar_sql_analise_dbt("p5_perfil_remuneracao"),
            ),
        ]
        for pergunta, intencao_esp, sql_ref in casos:
            resp = self.assistente.responder(self.conn, pergunta)
            self.assertTrue(resp.suportada, f"Falha na pergunta: {pergunta}")
            self.assertEqual(resp.intencao, intencao_esp)
            esperado = self.conn.sql(sql_ref).fetchall()
            self.assertEqual(resp.linhas, esperado)

    def test_p1_respeita_filtro_de_ano(self) -> None:
        resp_padrao = self.assistente.responder(
            self.conn,
            "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?",
        )
        resp_2024 = self.assistente.responder(
            self.conn,
            "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?",
            ano_override=2024,
        )
        esperado_2024 = self.conn.sql(SQL_REF_P1_DF_2024).fetchall()
        self.assertEqual(resp_2024.linhas, esperado_2024)
        self.assertNotEqual(resp_padrao.linhas, resp_2024.linhas)

    def test_palavras_inteiras_nao_confundem_rurais_com_rais_nem_coracao_com_cor(self) -> None:
        resp_rural = self.assistente.responder(
            self.conn,
            "Qual o saldo e o salário médio de trabalhadores rurais no Centro-Oeste?",
        )
        self.assertTrue(resp_rural.suportada)
        self.assertEqual(resp_rural.intencao, "cbo_ocupacao")

        resp_coracao = self.assistente.responder(
            self.conn,
            "Qual o salário médio de médico do coração no Centro-Oeste?",
        )
        self.assertTrue(resp_coracao.suportada)
        self.assertEqual(resp_coracao.intencao, "cbo_ocupacao")
        self.assertNotIn("eixo", resp_coracao.filtros_aplicados)
        self.assertIn("223104", [o["codigo_cbo"] for o in resp_coracao.ocupacoes_resolvidas])

    def test_consulta_integrada_ocupacao_cbo_e_auditoria_consistente_com_override(self) -> None:
        resp = self.assistente.responder(
            self.conn,
            "Qual o saldo e o salário médio de caminhoneiro no Centro-Oeste?",
            codigos_cbo_override=["782510"],
        )
        self.assertTrue(resp.suportada)
        self.assertEqual(resp.intencao, "cbo_ocupacao")
        self.assertEqual(resp.filtros_aplicados.get("codigos_cbo"), ["782510"])
        self.assertEqual([o["codigo_cbo"] for o in resp.ocupacoes_resolvidas], ["782510"])

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

    def test_guardrails_bloqueiam_bypasses_de_arquivos_locais_e_linhas_individuais(self) -> None:
        proibidos = [
            "DROP TABLE gold.fct_movimentacao",
            "INSERT INTO gold.dim_cbo VALUES ('123456', 'X', '1', true)",
            "SELECT * FROM gold.fct_setor_mensal; DELETE FROM gold.dim_cbo",
            "SELECT * FROM read_parquet('data/lake/parquet/movimentacao/*.parquet')",
            "SELECT count(*) FROM '/etc/passwd', gold.dim_cbo",
            "SELECT * FROM gold.fct_movimentacao WHERE 'count(' <> ''",
            "SELECT salario_mensal FROM gold.fct_movimentacao WHERE (SELECT count(*) FROM gold.dim_cbo) > 0",
            "SELECT id_movimentacao, COUNT(*) FROM gold.fct_movimentacao GROUP BY id_movimentacao",
            "SELECT * FROM silver.stg_movimentacao",
            "SELECT * FROM gold.fct_movimentacao LIMIT 5",
        ]
        for sql in proibidos:
            with self.assertRaises(ViolacaoSegurancaSQL, msg=f"Deveria bloquear: {sql}"):
                validar_sql_seguro(sql)

        # Mesmo em execução direta na conexão analítica, o acesso externo está travado
        with self.assertRaises(duckdb.Error):
            self.conn.execute("SELECT * FROM 'data/caged_centro_oeste_amostra.csv'")

        for pergunta_bloqueada in (
            "DROP TABLE gold.fct_movimentacao;",
            "SELECT * FROM gold.fct_movimentacao",
            "SELECT * FROM gold.fct_movimentacao WHERE 'count(' <> ''",
            "SELECT count(*) FROM '/etc/passwd', gold.dim_cbo",
            "Liste o CPF e o nome do trabalhador de cada registro individual",
        ):
            resp = self.assistente.responder(self.conn, pergunta_bloqueada)
            self.assertFalse(resp.suportada, f"Deveria bloquear pergunta: {pergunta_bloqueada}")
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
