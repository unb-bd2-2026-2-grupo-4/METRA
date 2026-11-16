"""Verificador do fluxo completo: detecta camadas divergentes e tabelas do painel vazias.

Executar no ambiente de requirements-pipeline.txt:
    python -m unittest discover -s tests -p 'test_verificar_fluxo.py' -v
"""

import unittest

import duckdb

from src.qualidade.verificar_fluxo import TABELAS_PAINEL, divergencias, medir_camadas, tabelas_vazias

CAMADAS = ("Bronze", "OLTP", "Parquet", "Delta", "Silver", "Gold")


class VerificarFluxoTest(unittest.TestCase):
    def setUp(self):
        self.conn = duckdb.connect()
        self.addCleanup(self.conn.close)
        self.conn.execute("attach ':memory:' as analitico")
        self.conn.execute("create schema analitico.gold")
        for tabela in TABELAS_PAINEL:
            self.conn.execute(f"create table analitico.{tabela} as select 1 as linha")
        # Uma tabela de movimentações por camada, todas com as mesmas 3 linhas.
        for camada in CAMADAS:
            self.conn.execute(
                f"create table {camada} as select * from (values (1), (1), (-1)) t(saldo_movimentacao)"
            )
        self.consultas = {
            camada: f"select count(*), coalesce(sum(saldo_movimentacao), 0) from {camada}"
            for camada in CAMADAS
        }

    def test_fluxo_consistente_nao_aponta_divergencia(self):
        medidas = medir_camadas(self.conn, self.consultas)
        self.assertEqual(list(medidas), list(CAMADAS))
        self.assertEqual(set(medidas.values()), {(3, 1)})
        self.assertEqual(divergencias(medidas), [])
        self.assertEqual(tabelas_vazias(self.conn), [])

    def test_linha_perdida_entre_camadas_aponta_a_transicao(self):
        self.conn.execute("delete from Delta where saldo_movimentacao = -1")
        erros = divergencias(medir_camadas(self.conn, self.consultas))
        # A Delta difere do Parquet e a Silver difere da Delta.
        self.assertEqual(len(erros), 2)
        self.assertIn("Parquet -> Delta: 3 movimentações e saldo +1 viraram 2 e +2", erros[0])
        self.assertTrue(erros[1].startswith("Delta -> Silver"))

    def test_saldo_alterado_com_mesma_contagem_e_detectado(self):
        self.conn.execute("update Gold set saldo_movimentacao = 1")
        erros = divergencias(medir_camadas(self.conn, self.consultas))
        self.assertEqual(erros, ["Silver -> Gold: 3 movimentações e saldo +1 viraram 3 e +3"])

    def test_fluxo_vazio_e_tabela_do_painel_vazia_falham(self):
        for camada in CAMADAS:
            self.conn.execute(f"delete from {camada}")
        self.assertEqual(
            divergencias(medir_camadas(self.conn, self.consultas)),
            ["Bronze: nenhuma movimentação no recorte; a carga não rodou?"],
        )
        self.conn.execute("delete from analitico.gold.fct_setor_mensal")
        self.assertEqual(tabelas_vazias(self.conn), ["gold.fct_setor_mensal"])


if __name__ == "__main__":
    unittest.main()
