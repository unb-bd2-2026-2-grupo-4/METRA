"""Salário válido: positivo e até o teto metra_salario_maximo_valido, igual na Gold e na E1.

Executa o dbt real sobre Parquet temporário. Executar no ambiente de requirements-pipeline.txt:
    python -m unittest discover -s tests -p 'test_salario_valido.py' -v
"""

from decimal import Decimal
from pathlib import Path
import unittest

import duckdb
import yaml

from src.analise import consultar_indicadores
from src.metricas.camada_semantica import condicao_salario_valido, salario_maximo_valido
from test_gold import ProjetoTemporario

ROOT = Path(__file__).resolve().parents[1]


class SalarioValidoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.projeto = p = ProjetoTemporario()
        cls.addClassCleanup(p.fechar)
        p.origem.execute("""
            insert into municipio values
                ('5300108', 'Brasília', 'DF', 'Distrito Federal', 'Centro-Oeste', true);
            insert into cnae_secao values ('A', 'Setor A');
            insert into cnae_subclasse values ('0000001', 'Atividade A', 'A');
            insert into cbo_2002 values ('012345', 'Ocupação de teste');
        """)
        # Válidos: 1000 e exatamente o teto. Inválidos: zero, um centavo acima e R$ 1 trilhão.
        for salario in (1000, 150000, 0, Decimal("150000.01"), 1_000_000_000_000):
            p.evento(salario=salario)
        p.exportar()
        p.dbt("build")

    def setUp(self):
        self.conn = duckdb.connect(str(self.projeto.banco), read_only=True)
        self.addCleanup(self.conn.close)

    def test_teto_vem_do_dbt_project(self):
        projeto = yaml.safe_load((ROOT / "dbt_metra/dbt_project.yml").read_text(encoding="utf-8"))
        self.assertEqual(salario_maximo_valido(), projeto["vars"]["metra_salario_maximo_valido"])
        self.assertEqual(salario_maximo_valido(), 150000)

    def test_silver_marca_so_salarios_positivos_ate_o_teto(self):
        validos = dict(self.conn.execute(
            "select salario_mensal, salario_valido from silver.stg_movimentacao").fetchall())
        self.assertEqual(validos, {
            Decimal("1000.00"): True, Decimal("150000.00"): True, Decimal("0.00"): False,
            Decimal("150000.01"): False, Decimal("1000000000000.00"): False,
        })

    def test_media_da_gold_ignora_os_salarios_acima_do_teto(self):
        soma, qtd, media = self.conn.execute("""
            select sum(soma_salarios_admissao), sum(qtd_salarios_admissao),
                   sum(soma_salarios_admissao) / sum(qtd_salarios_admissao)
            from gold.fct_setor_mensal
        """).fetchone()
        self.assertEqual((soma, qtd), (Decimal("151000.00"), 2))
        self.assertEqual(media, Decimal("75500"))

    def test_analise_da_e1_usa_a_mesma_regra(self):
        with duckdb.connect() as conn:
            conn.execute(f"attach '{self.projeto.banco}' as g (read_only)")
            conn.execute("""
                create table movimentacao as
                select ano, is_capital, saldo_movimentacao, salario_mensal from g.gold.fct_movimentacao
            """)
            linhas = {r[0]: r for r in consultar_indicadores(conn).fetchall()}
        # periodo, saldo_capital, saldo_interior, dif, salario_capital, ...
        self.assertEqual(linhas["Total"][4], 75500)
        self.assertEqual(linhas["Total"][7], 2)

    def test_condicao_sql_aplica_o_teto(self):
        self.assertEqual(condicao_salario_valido("m.salario"), "m.salario > 0 and m.salario <= 150000")


if __name__ == "__main__":
    unittest.main()
