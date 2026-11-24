"""Testes automatizados da governança LGPD, retenção, pequenos grupos e descarte de microdados (E4).

Executar na raiz:
    python -m unittest discover -s tests -p 'test_lgpd_descarte.py' -v
"""

from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

import duckdb

from src.lgpd.descarte import (
    ENQUADRAMENTO_LGPD,
    LIMIAR_K_ANONIMATO,
    auditar_pequenos_grupos_e_diferenca,
    executar_descarte,
    inventariar_artefatos,
)


def _criar_banco_gold_sintetico(caminho_banco: Path) -> None:
    """Cria um banco DuckDB sintético com as tabelas gold necessárias para a auditoria LGPD."""
    with duckdb.connect(str(caminho_banco)) as conn:
        conn.execute("CREATE SCHEMA silver; CREATE SCHEMA gold")
        conn.execute("""
            CREATE TABLE gold.dim_perfil_demografico AS
            SELECT * FROM (VALUES
                ('1-1-7-3', 1, 'Homem',  1, 'Branca', 7, 'Médio Completo', 3, '25 a 34 anos'),
                ('3-3-9-3', 3, 'Mulher', 3, 'Parda',  9, 'Superior Completo', 3, '25 a 34 anos')
            ) AS t(
                id_perfil_demografico,
                codigo_sexo, sexo,
                codigo_raca_cor, raca_cor,
                codigo_grau_instrucao, escolaridade,
                codigo_faixa_etaria, faixa_etaria
            )
        """)
        # 7 movimentações em 2025-01 no DF:
        # - 5 na seção A com a mesma combinação (k = 5)
        # - 2 na seção B com combinações únicas (k = 1) -> seção B omitida (< 5) e única omitida na UF/mês!
        conn.execute("""
            CREATE TABLE gold.fct_movimentacao AS
            SELECT * FROM (VALUES
                (1, '5300108', DATE '2025-01-01', 2025, 1, 'DF', TRUE, TRUE, TRUE, '212405', '6201501', 'A', 30, '1-1-7-3', 1, 3000.00::DECIMAL(16,2), TRUE),
                (2, '5300108', DATE '2025-01-01', 2025, 1, 'DF', TRUE, TRUE, TRUE, '212405', '6201501', 'A', 30, '1-1-7-3', 1, 3200.00::DECIMAL(16,2), TRUE),
                (3, '5300108', DATE '2025-01-01', 2025, 1, 'DF', TRUE, TRUE, TRUE, '212405', '6201501', 'A', 30, '1-1-7-3', 1, 3400.00::DECIMAL(16,2), TRUE),
                (4, '5300108', DATE '2025-01-01', 2025, 1, 'DF', TRUE, TRUE, TRUE, '212405', '6201501', 'A', 30, '1-1-7-3', 1, 3600.00::DECIMAL(16,2), TRUE),
                (5, '5300108', DATE '2025-01-01', 2025, 1, 'DF', TRUE, TRUE, TRUE, '212405', '6201501', 'A', 30, '1-1-7-3', 1, 3800.00::DECIMAL(16,2), TRUE),
                (6, '5300108', DATE '2025-01-01', 2025, 1, 'DF', TRUE, TRUE, TRUE, '223505', '8610101', 'B', 28, '3-3-9-3', 1, 4500.00::DECIMAL(16,2), TRUE),
                (7, '5300108', DATE '2025-01-01', 2025, 1, 'DF', TRUE, TRUE, TRUE, '223505', '8610101', 'B', 41, '3-3-9-3', -1, 0.00::DECIMAL(16,2), FALSE)
            ) AS t(
                id_movimentacao, id_municipio, competencia, ano, mes, sigla_uf,
                is_capital, is_identificado, is_centro_oeste, codigo_cbo,
                codigo_cnae_subclasse, codigo_secao, idade, id_perfil_demografico,
                saldo_movimentacao, salario_mensal, salario_valido
            )
        """)
        conn.execute("""
            CREATE TABLE gold.fct_setor_mensal AS
            SELECT * FROM (VALUES
                (DATE '2025-01-01', 'DF', 'A', 5, 0, 5, 17000.00::DECIMAL(16,2), 5),
                (DATE '2025-01-01', 'DF', 'B', 1, 1, 0, 4500.00::DECIMAL(16,2), 1)
            ) AS t(competencia, sigla_uf, codigo_secao, admissoes, desligamentos, saldo, soma_salarios_admissao, qtd_salarios_admissao)
        """)
        conn.execute("""
            CREATE TABLE gold.fct_geografia_mensal AS
            SELECT * FROM (VALUES
                (DATE '2025-01-01', 'DF', TRUE, 6, 1, 5, 21500.00::DECIMAL(16,2), 6)
            ) AS t(competencia, sigla_uf, is_capital, admissoes, desligamentos, saldo, soma_salarios_admissao, qtd_salarios_admissao)
        """)
        conn.execute("""
            CREATE TABLE gold.fct_perfil_mensal AS
            SELECT * FROM (VALUES
                (DATE '2025-01-01', 'DF', TRUE, 'A', '1-1-7-3', 5, 0, 5, 17000.00::DECIMAL(16,2), 5),
                (DATE '2025-01-01', 'DF', TRUE, 'A', '3-3-9-3', 1, 0, 1, 2500.00::DECIMAL(16,2), 1)
            ) AS t(competencia, sigla_uf, is_capital, codigo_secao, id_perfil_demografico, admissoes, desligamentos, saldo, soma_salarios_admissao, qtd_salarios_admissao)
        """)


class GovernancaLGPDDescarteTest(unittest.TestCase):
    def test_enquadramento_nomeia_dados_base_legal_e_prazo_de_retencao(self) -> None:
        dados = ENQUADRAMENTO_LGPD["dados_nomeados"]
        self.assertEqual(dados["identificadores_diretos"], [])
        for campo_qi in (
            "id_municipio",
            "competencia",
            "codigo_cbo",
            "codigo_cnae_subclasse",
            "idade",
            "codigo_sexo",
            "codigo_grau_instrucao",
            "salario_mensal",
            "id_ingestao",
            "numero_linha",
        ):
            self.assertIn(campo_qi, dados["quase_identificadores"])
        self.assertIn("codigo_raca_cor", dados["dados_pessoais_sensiveis"])
        self.assertIn("raca_cor", dados["dados_pessoais_sensiveis"])

        base_legal = ENQUADRAMENTO_LGPD["base_legal"]
        self.assertIn("Art. 7º, inciso IV", base_legal["hipotese_dados_pessoais"])
        self.assertIn("Art. 11, inciso II, alínea 'c'", base_legal["hipotese_dados_sensiveis"])

        retencao = ENQUADRAMENTO_LGPD["retencao"]
        self.assertEqual(retencao["prazo_dias_apos_encerramento"], 30)
        self.assertEqual(LIMIAR_K_ANONIMATO, 5)

    def test_auditoria_quantifica_pequenos_grupos_e_ataque_por_diferenca(self) -> None:
        with tempfile.TemporaryDirectory(prefix="metra_lgpd_audit_") as tmp:
            banco = Path(tmp) / "metra_analitico.duckdb"
            _criar_banco_gold_sintetico(banco)

            relatorio = auditar_pequenos_grupos_e_diferenca(banco, limiar_k=5)
            risco = relatorio["risco_reidentificacao_microdado_gold"]
            self.assertEqual(risco["total_movimentacoes_recorte"], 7)
            self.assertEqual(risco["combinacoes_distintas_quase_identificadores"], 3)
            self.assertEqual(risco["combinacoes_unicas_k1"], 2)
            self.assertEqual(risco["combinacoes_abaixo_k5"], 2)

            sup = relatorio["efeito_supressao_views_consumo"]
            self.assertEqual(sup["setor_mensal"]["grupos_publicados"], 1)
            self.assertEqual(sup["setor_mensal"]["grupos_omitidos_fluxo_menor_k"], 1)

            dif = relatorio["auditoria_ataque_por_diferenca"]
            self.assertEqual(dif["uf_competencia_com_exatamente_1_setor_omitido"], 1)
            self.assertEqual(dif["uf_competencia_com_residuo_entre_1_e_k_menos_1"], 1)
            self.assertEqual(dif["particoes_perfil_com_exatamente_1_categoria_omitida"], 3)

    def test_simulacao_nao_apaga_arquivos_e_execucao_elimina_todos_os_microdados(self) -> None:
        with tempfile.TemporaryDirectory(prefix="metra_lgpd_discard_") as tmp:
            dir_dados = Path(tmp) / "data"
            (dir_dados / "lake" / "parquet" / "movimentacao" / "ano=2025").mkdir(parents=True)
            (dir_dados / "lake" / "delta" / "movimentacao").mkdir(parents=True)
            (dir_dados / "cdc").mkdir(parents=True)

            # Cria artefatos com microdados individuais
            (dir_dados / "metra_analitico.duckdb").write_bytes(b"duckdb_analitico_microdados")
            (dir_dados / "metra_analitico.duckdb.wal").write_bytes(b"wal_analitico")
            (dir_dados / "metra.duckdb").write_bytes(b"duckdb_e2_microdados")
            (dir_dados / "lake" / "parquet" / "movimentacao" / "ano=2025" / "part.parquet").write_bytes(b"parquet")
            (dir_dados / "lake" / "delta" / "movimentacao" / "part.parquet").write_bytes(b"delta")
            (dir_dados / "cdc" / "eventos.log").write_text("INSERT id_movimentacao=1\n", encoding="utf-8")
            (dir_dados / "cdc" / "replay.sqlite3").write_bytes(b"sqlite3")
            (dir_dados / "caged_bruto_2025.csv").write_text("id;salario\n1;2000\n", encoding="utf-8")

            # Cria base de consumo agregada (k >= 5) e amostra versionada no Git
            (dir_dados / "metra_consumo.duckdb").write_bytes(b"duckdb_consumo_agregado_k5")
            (dir_dados / "caged_centro_oeste_amostra.csv").write_text("amostra_git\n", encoding="utf-8")

            # 1. Modo simular (dry-run) não remove nenhum arquivo
            sim = executar_descarte(dir_dados, modo="simular", incluir_agregados=False)
            self.assertEqual(sim["modo"], "simular")
            self.assertEqual(sim["resumo_descarte"]["artefatos_descartados"], 7)
            self.assertTrue((dir_dados / "metra_analitico.duckdb").exists())
            self.assertTrue((dir_dados / "lake" / "parquet").exists())
            self.assertTrue((dir_dados / "cdc" / "eventos.log").exists())

            # 2. Modo executar remove 100% dos artefatos de microdados individuais locais
            real = executar_descarte(dir_dados, modo="executar", incluir_agregados=False)
            self.assertEqual(real["modo"], "executar")
            self.assertTrue(real["resumo_descarte"]["verificacao_pos_descarte_ok"])
            self.assertEqual(real["resumo_descarte"]["microdados_individuais_residuais"], 0)
            self.assertFalse((dir_dados / "metra_analitico.duckdb").exists())
            self.assertFalse((dir_dados / "metra_analitico.duckdb.wal").exists())
            self.assertFalse((dir_dados / "metra.duckdb").exists())
            self.assertFalse((dir_dados / "lake").exists())
            self.assertFalse((dir_dados / "cdc").exists())
            self.assertFalse((dir_dados / "caged_bruto_2025.csv").exists())

            # Base de consumo agregada (k >= 5) permanece íntegra quando incluir_agregados=False
            self.assertTrue((dir_dados / "metra_consumo.duckdb").exists())

            # 3. Se incluir_agregados=True e incluir_amostra_versionada=True, remove tudo
            total = executar_descarte(
                dir_dados,
                modo="executar",
                incluir_agregados=True,
                incluir_amostra_versionada=True,
            )
            self.assertTrue(total["resumo_descarte"]["verificacao_pos_descarte_ok"])
            self.assertFalse((dir_dados / "metra_consumo.duckdb").exists())
            self.assertFalse((dir_dados / "caged_centro_oeste_amostra.csv").exists())
            inv_final = inventariar_artefatos(dir_dados)
            self.assertTrue(all(not item["existe"] for item in inv_final))


if __name__ == "__main__":
    unittest.main()
