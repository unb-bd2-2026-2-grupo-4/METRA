"""Conciliação dos agregados na Gold real, sem criar ou alterar o banco.

Executar após scripts/metra-do-zero.sh, na imagem do Dagster:
    python -m unittest discover -s tests -p 'test_gold_integracao.py' -v

Sem data/metra_analitico.duckdb, os testes são pulados. METRA_DUCKDB permite
usar o mesmo caminho configurado para o pipeline, inclusive no container.
"""

import os
from pathlib import Path
import unittest

import duckdb


ROOT = Path(__file__).resolve().parents[1]


class GoldIntegracaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        banco = Path(os.environ.get(
            "METRA_DUCKDB", str(ROOT / "data" / "metra_analitico.duckdb")
        ))
        if not banco.is_file():
            raise unittest.SkipTest(
                f"Banco analítico ausente: {banco}. Execute scripts/metra-do-zero.sh."
            )
        cls.conn = duckdb.connect(str(banco), read_only=True)
        cls.addClassCleanup(cls.conn.close)

    def conferir_agregado(self, tabela, dimensoes):
        # Mesmo recorte de negócio dos marts; a referência é calculada a partir
        # dos eventos, sem reutilizar a macro dbt que produz os agregados.
        chaves = ", ".join(dimensoes)
        medidas = (
            "admissoes, desligamentos, saldo, "
            "soma_salarios_admissao, qtd_salarios_admissao"
        )
        sql = f"""
            with esperado as (
                select {chaves},
                    count(*) filter (where saldo_movimentacao = 1) as admissoes,
                    count(*) filter (where saldo_movimentacao = -1) as desligamentos,
                    sum(saldo_movimentacao) as saldo,
                    sum(case when saldo_movimentacao = 1 and salario_valido
                        then salario_mensal else 0 end) as soma_salarios_admissao,
                    count(*) filter (
                        where saldo_movimentacao = 1 and salario_valido
                    ) as qtd_salarios_admissao
                from gold.fct_movimentacao
                where is_identificado and is_centro_oeste
                    and ano between 2023 and 2026
                group by {chaves}
            ), atual as (
                select {chaves}, {medidas} from gold.{tabela}
            ), faltantes as (
                select * from esperado except all select * from atual
            ), excedentes as (
                select * from atual except all select * from esperado
            )
            select 'faltante ou divergente' as problema, * from faltantes
            union all
            select 'excedente ou divergente' as problema, * from excedentes
            limit 10
        """
        self.assertGreater(
            self.conn.execute(f"select count(*) from gold.{tabela}").fetchone()[0],
            0, f"gold.{tabela} está vazio; a conciliação exige dados reais.",
        )
        self.assertEqual(
            self.conn.execute(sql).fetchall(), [],
            f"gold.{tabela} diverge da soma de gold.fct_movimentacao "
            f"por {chaves} (amostra de até 10 divergências).",
        )

    def test_setor_mensal_bate_com_movimentacao(self):
        self.conferir_agregado(
            "fct_setor_mensal", ("competencia", "sigla_uf", "codigo_secao")
        )

    def test_geografia_mensal_bate_com_movimentacao(self):
        self.conferir_agregado(
            "fct_geografia_mensal", ("competencia", "sigla_uf", "is_capital")
        )

    def test_perfil_mensal_bate_com_movimentacao(self):
        self.conferir_agregado(
            "fct_perfil_mensal",
            ("competencia", "sigla_uf", "is_capital", "codigo_secao",
             "id_perfil_demografico"),
        )


if __name__ == "__main__":
    unittest.main()
