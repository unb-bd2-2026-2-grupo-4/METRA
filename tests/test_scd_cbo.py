"""SCD tipo 2 da CBO: o snapshot preserva o histórico quando um título muda na fonte.

Executar no ambiente de requirements-pipeline.txt:
    python -m unittest discover -s tests -p 'test_scd_cbo.py' -v
"""

import unittest

import duckdb

from test_gold import ProjetoTemporario


class ScdCboTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.projeto = p = ProjetoTemporario()
        cls.addClassCleanup(p.fechar)
        p.origem.execute("""
            insert into municipio values
                ('5300108', 'Brasília', 'DF', 'Distrito Federal', 'Centro-Oeste', true);
            insert into cnae_secao values ('A', 'Setor A');
            insert into cnae_subclasse values ('0000001', 'Atividade A', 'A');
            insert into cbo_2002 values
                ('012345', 'Analista de dados'),
                ('067890', 'Técnico de enfermagem');
        """)
        p.evento()

        # 1ª execução: carga inicial do snapshot.
        p.exportar()
        p.dbt("build")

        # 2ª execução: o título de 012345 muda na fonte; 067890 continua igual.
        p.origem.execute("update cbo_2002 set titulo = 'Cientista de dados' where codigo = '012345'")
        p.exportar()
        p.dbt("build")

        with duckdb.connect(str(p.banco), read_only=True) as conn:
            cls.historico = conn.sql("""
                select codigo_cbo, titulo_ocupacao, observado_desde, observado_ate, is_versao_vigente
                from gold.dim_cbo_historico
                order by codigo_cbo, observado_desde
            """).fetchall()
            cls.atual = dict(conn.sql("select codigo_cbo, titulo_ocupacao from gold.dim_cbo").fetchall())

    def versoes(self, codigo):
        return [linha for linha in self.historico if linha[0] == codigo]

    def test_mudanca_de_titulo_abre_nova_versao_e_preserva_a_anterior(self):
        antiga, nova = self.versoes("012345")
        self.assertEqual(antiga[1], "Analista de dados")
        self.assertFalse(antiga[4])
        self.assertEqual(nova[1], "Cientista de dados")
        self.assertTrue(nova[4])
        self.assertIsNone(nova[3])
        # Períodos encadeados: a versão antiga termina quando a nova começa.
        self.assertEqual(antiga[3], nova[2])

    def test_ocupacao_sem_mudanca_mantem_versao_unica(self):
        (versao,) = self.versoes("067890")
        self.assertTrue(versao[4])
        self.assertIsNone(versao[3])

    def test_dim_cbo_mantem_apenas_a_versao_vigente(self):
        self.assertEqual(self.atual["012345"], "Cientista de dados")
        self.assertEqual(len(self.atual), 2)


if __name__ == "__main__":
    unittest.main()
