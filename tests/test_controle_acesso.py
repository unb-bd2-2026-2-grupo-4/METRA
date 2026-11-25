"""Controle de acesso: supressão nas views de consumo e base de consumo isolada.

Executa o dbt real sobre Parquet temporário. Executar no ambiente de requirements-pipeline.txt:
    python -m unittest discover -s tests -p 'test_controle_acesso.py' -v
"""

from decimal import Decimal
from pathlib import Path
import unittest

import duckdb

from src.acesso.base_consumo import RELACOES_CONSUMO, conectar_consumidor, publicar
from src.acesso.demonstrar_acesso import executar, tentativas
from test_gold import ProjetoTemporario


class ControleAcessoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.projeto = p = ProjetoTemporario()
        cls.addClassCleanup(p.fechar)
        p.origem.execute("""
            insert into municipio values
                ('5300108', 'Brasília', 'DF', 'Distrito Federal', 'Centro-Oeste', true),
                ('5208707', 'Goiânia', 'GO', 'Goiás', 'Centro-Oeste', true);
            insert into cnae_secao values ('A', 'Setor A'), ('B', 'Setor B');
            insert into cnae_subclasse values ('0000001', 'Atividade A', 'A'), ('0000002', 'Atividade B', 'B');
            insert into cbo_2002 values ('012345', 'Ocupação de teste');
        """)
        # DF, seção A: 6 admissões com salário (publicado); 5 homens e 1 mulher.
        for salario in (1000, 2000, 3000, 4000, 5000):
            p.evento(salario=salario, sexo=1)
        p.evento(salario=6000, sexo=3)
        # DF, seção B: 3 admissões com salário e 2 desligamentos: fluxos publicados, salário não.
        for salario in (1000, 2000, 3000):
            p.evento(cnae="0000002", salario=salario)
        for _ in range(2):
            p.evento(cnae="0000002", saldo=-1)
        # GO: 4 movimentações, abaixo do limite em setores e geografia.
        for _ in range(4):
            p.evento(municipio="5208707")
        p.exportar()
        p.dbt("build")
        cls.base = p.pasta / "metra_consumo.duckdb"
        cls.linhas_publicadas = publicar(p.banco, cls.base)

    def setUp(self):
        self.analitico = duckdb.connect(str(self.projeto.banco), read_only=True)
        self.addCleanup(self.analitico.close)

    def linhas(self, sql):
        cursor = self.analitico.execute(sql)
        nomes = [c[0] for c in cursor.description]
        return [dict(zip(nomes, linha)) for linha in cursor.fetchall()]

    def test_grupo_pequeno_omitido_em_todas_as_views(self):
        self.assertEqual(
            [(r["sigla_uf"], r["codigo_secao"]) for r in self.linhas(
                "select * from consumo.setor_mensal order by codigo_secao")],
            [("DF", "A"), ("DF", "B")],
        )
        self.assertEqual(
            [r["sigla_uf"] for r in self.linhas("select * from consumo.geografia_mensal")], ["DF"],
        )
        # Na Gold, os grupos de GO existem; a view é que os omite.
        self.assertEqual(self.analitico.execute(
            "select sum(admissoes) from gold.fct_setor_mensal where sigla_uf = 'GO'").fetchone(), (4,))

    def test_categoria_pequena_omitida_dentro_de_grupo_publicado(self):
        sexo = self.linhas("""
            select categoria, admissoes from consumo.perfil_anual
            where eixo = 'sexo' and codigo_secao = 'A'
        """)
        self.assertEqual(sexo, [{"categoria": "Homem", "admissoes": 5}])

    def test_salario_suprimido_mantendo_os_fluxos(self):
        (secao_b,) = self.linhas("select * from consumo.setor_mensal where codigo_secao = 'B'")
        self.assertEqual((secao_b["admissoes"], secao_b["desligamentos"], secao_b["saldo"]), (3, 2, 1))
        self.assertIsNone(secao_b["qtd_salarios_admissao"])
        self.assertIsNone(secao_b["soma_salarios_admissao"])

    def test_grupo_publicado_tem_os_valores_da_gold(self):
        (secao_a,) = self.linhas("select * from consumo.setor_mensal where codigo_secao = 'A'")
        self.assertEqual(
            (secao_a["admissoes"], secao_a["qtd_salarios_admissao"], secao_a["soma_salarios_admissao"]),
            (6, 6, Decimal("21000.00")),
        )

    def test_base_de_consumo_contem_so_as_relacoes_de_consumo(self):
        self.assertEqual(self.linhas_publicadas["setor_mensal"], 2)
        with conectar_consumidor(self.base) as conn:
            relacoes = conn.execute(
                "select table_schema, table_name from information_schema.tables order by table_name"
            ).fetchall()
        self.assertEqual(sorted(relacoes), sorted(("consumo", r) for r in RELACOES_CONSUMO))

    def test_consumidor_negado_ao_detalhe_e_analista_sem_escrita(self):
        conexoes = {"consumidor": conectar_consumidor(self.base), "analista": self.analitico}
        self.addCleanup(conexoes["consumidor"].close)
        lista = tentativas(self.projeto.banco)
        self.assertEqual({t.perfil for t in lista if not t.permitida}, {"consumidor", "analista"})
        for tentativa in lista:
            with self.subTest(perfil=tentativa.perfil, tentativa=tentativa.descricao):
                permitida, resultado = executar(tentativa, conexoes)
                self.assertEqual(permitida, tentativa.permitida, resultado)

    def test_falha_na_publicacao_preserva_a_base_anterior(self):
        destino = self.projeto.pasta / "preservada.duckdb"
        publicar(self.projeto.banco, destino)
        sem_consumo = self.projeto.pasta / "sem_consumo.duckdb"
        duckdb.connect(str(sem_consumo)).close()
        with self.assertRaises(duckdb.Error):
            publicar(sem_consumo, destino)
        with conectar_consumidor(destino) as conn:
            self.assertEqual(conn.execute("select count(*) from consumo.setor_mensal").fetchone(), (2,))
        self.assertEqual(list(Path(destino.parent).glob(".metra_consumo-*")), [])

    def test_base_ausente_nao_e_criada_pelo_consumidor(self):
        ausente = self.projeto.pasta / "ausente.duckdb"
        with self.assertRaises(FileNotFoundError):
            conectar_consumidor(ausente)
        self.assertFalse(ausente.exists())


if __name__ == "__main__":
    unittest.main()
