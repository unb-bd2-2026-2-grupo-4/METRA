"""Regras de negócio Gold: Parquet temporário -> dbt real -> DuckDB isolado.

Executar no ambiente de requirements-pipeline.txt:
    python -m unittest discover -s tests -p 'test_gold.py' -v
"""

import csv
from datetime import date
from decimal import Decimal
import json
import os
from pathlib import Path
import statistics
import subprocess
import sys
import tempfile
import unittest

import duckdb

from src.analise import consultar_indicadores

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "dbt_metra"
CAPITAIS = {"5300108", "5208707", "5103403", "5002704"}


class ProjetoTemporario:
    def __init__(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="metra_gold_")
        self.pasta = Path(self.tmp.name)
        self.lake = self.pasta / "parquet"
        self.banco = self.pasta / "metra_teste.duckdb"
        self.target = self.pasta / "target"
        self.origem = duckdb.connect()
        self.origem.execute("""
            create table movimentacao (
                id_movimentacao bigint, ano integer, mes integer, id_municipio varchar,
                cnae_2_subclasse varchar, cbo_2002 varchar, sexo integer, raca_cor integer,
                idade integer, grau_instrucao integer, tipo_movimentacao integer,
                saldo_movimentacao integer, salario_mensal decimal(16,2),
                horas_contratuais decimal(5,2), id_ingestao bigint, numero_linha bigint,
                registrado_em timestamptz
            );
            create table municipio (
                id_municipio varchar, nome varchar, sigla_uf varchar,
                nome_uf varchar, regiao varchar, is_capital boolean
            );
            create table cnae_secao (codigo varchar, descricao varchar);
            create table cnae_subclasse (codigo varchar, descricao varchar, codigo_secao varchar);
            create table cbo_2002 (codigo varchar, titulo varchar);
        """)

    def fechar(self):
        self.origem.close()
        self.tmp.cleanup()

    def evento(self, ano=2025, mes=1, municipio="5300108", cnae="0000001",
               saldo=1, salario=1000, idade=30, sexo=1, raca=1, escolaridade=7):
        numero = self.origem.execute("select count(*) + 1 from movimentacao").fetchone()[0]
        self.origem.execute("""
            insert into movimentacao values
            (?, ?, ?, ?, ?, '012345', ?, ?, ?, ?, 10, ?, ?, 44, 1, ?, '2026-10-30 12:00:00+00')
        """, [numero, ano, mes, municipio, cnae, sexo, raca, idade, escolaridade,
              saldo, salario, numero])

    def exportar(self):
        for tabela in ("movimentacao", "municipio", "cnae_secao", "cnae_subclasse", "cbo_2002"):
            pasta = self.lake / tabela
            pasta.mkdir(parents=True, exist_ok=True)
            arquivo = str(pasta / "dados.parquet").replace("'", "''")
            self.origem.execute(f"copy {tabela} to '{arquivo}' (format parquet)")

    def dbt(self, comando):
        env = {**os.environ, "METRA_LAKE_PARQUET": str(self.lake),
               "METRA_DUCKDB": str(self.banco), "DBT_SEND_ANONYMOUS_USAGE_STATS": "false"}
        resultado = subprocess.run(
            [sys.executable, "-c", "from dbt.cli.main import cli; cli()",
             "--no-use-colors", "--log-path", str(self.pasta / "logs"), comando,
             "--project-dir", str(PROJECT), "--profiles-dir", str(PROJECT),
             "--target-path", str(self.target)],
            env=env, cwd=ROOT, text=True, capture_output=True, timeout=120,
        )
        if resultado.returncode:
            raise AssertionError(resultado.stdout + resultado.stderr)

    def construir(self):
        self.exportar()
        self.dbt("build")
        self.dbt("compile")
        self.manifest = json.loads((self.target / "manifest.json").read_text())

    def sql(self, nome, substituicoes=None):
        sql = (self.target / "compiled" / "metra" / "analyses" / f"{nome}.sql").read_text()
        for modelo, tabela in (substituicoes or {}).items():
            relacao = self.manifest["nodes"][f"model.metra.{modelo}"]["relation_name"]
            sql = sql.replace(relacao, tabela)
        return sql


class GoldRegrasTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.projeto = p = ProjetoTemporario()
        cls.addClassCleanup(p.fechar)
        p.origem.execute("""
            insert into municipio values
                ('5300108', 'Brasília', 'DF', 'Distrito Federal', 'Centro-Oeste', true),
                ('5208707', 'Goiânia', 'GO', 'Goiás', 'Centro-Oeste', true),
                ('5201108', 'Anápolis', 'GO', 'Goiás', 'Centro-Oeste', false),
                ('9999999', 'Não identificado', 'NI', 'NI', 'Centro-Oeste', false),
                ('3550308', 'São Paulo', 'SP', 'São Paulo', 'Sudeste', false);
            insert into cnae_secao values ('A', 'Setor A'), ('B', 'Setor B'),
                ('C', 'Setor C'), ('D', 'Setor D'), ('Z', 'Não identificado');
            insert into cnae_subclasse values
                ('0000001', 'Atividade A', 'A'),
                ('0000002', 'Atividade B (REGISTRO ADMINISTRATIVO)', 'B'),
                ('0000003', 'Atividade C', 'C'), ('0000004', 'Atividade D', 'D'),
                ('9999999', 'Não identificado', 'Z');
            insert into cbo_2002 values ('012345', 'Ocupação de teste'),
                ('999999', 'Ocupação (ATUALIZACAO MTE)');
        """)
        for salario in (1000, 3000, 0):
            p.evento(salario=salario, sexo=3 if salario == 3000 else 1,
                     raca=2 if salario == 3000 else 1)
        p.evento(saldo=-1, salario=5000)
        for salario in (6000, 10000):
            p.evento(cnae="0000002", salario=salario)
        p.evento(cnae="0000003", salario=4000)
        p.evento(cnae="0000003", saldo=-1, salario=3000)
        p.evento(cnae="0000004", saldo=-1, salario=None)
        p.evento(municipio="5208707", salario=3000)
        for _ in range(3):
            p.evento(municipio="5201108")
        # 2024 é o único ano com 12 competências; fevereiro/2023 está ausente no recorte.
        for mes in range(1, 13):
            p.evento(ano=2024, mes=mes, municipio="5208707", cnae="0000003", salario=2000)
        for idade in (17, 18, 24, 25, 29, 30, 39, 40, 49, 50, 64, 65, None):
            p.evento(ano=2023, municipio="5201108", cnae="0000002", idade=idade,
                     escolaridade=80 if idade is not None else 901, sexo=9, raca=6)
        p.evento(ano=2023, mes=2, municipio="9999999")
        p.evento(ano=2023, mes=3, municipio="3550308")
        for _ in range(2):
            p.evento(mes=2)
            p.evento(mes=12, cnae="0000002")
        p.evento(mes=2, saldo=-1)
        p.evento(ano=2026, saldo=-1)
        p.evento(ano=2026, cnae="0000002", saldo=-1)
        p.evento(ano=2026, cnae="9999999")
        p.construir()

    def setUp(self):
        self.conn = duckdb.connect(str(self.projeto.banco))
        self.addCleanup(self.conn.close)
        for nome in ("p1_setores_df", "p2_sazonalidade", "p3_capitais_interior",
                     "p4_fluxos_salarios", "p5_perfil_remuneracao"):
            self.conn.execute(f"create temp view {nome} as {self.projeto.sql(nome)}")

    def test_cardinalidade_dimensoes_e_conciliacao(self):
        self.assertEqual(self.conn.execute("""
            select count(*), count(distinct id_movimentacao) from gold.fct_movimentacao
        """).fetchone(), (48, 48))
        self.assertEqual(self.conn.execute("""
            (select id_movimentacao from silver.stg_movimentacao
             except all select id_movimentacao from gold.fct_movimentacao)
            union all
            (select id_movimentacao from gold.fct_movimentacao
             except all select id_movimentacao from silver.stg_movimentacao)
        """).fetchall(), [])
        esperado = self.conn.execute("""
            select count(*) filter(where saldo_movimentacao = 1),
                   count(*) filter(where saldo_movimentacao = -1), sum(saldo_movimentacao),
                   sum(case when saldo_movimentacao=1 and salario_mensal>0 then salario_mensal else 0 end),
                   count(*) filter(where saldo_movimentacao=1 and salario_mensal>0)
            from gold.fct_movimentacao
            where is_identificado and is_centro_oeste and ano between 2023 and 2026
        """).fetchone()
        for tabela in ("fct_setor_mensal", "fct_geografia_mensal", "fct_perfil_mensal"):
            self.assertEqual(self.conn.execute(f"""
                select sum(admissoes), sum(desligamentos), sum(saldo),
                       sum(soma_salarios_admissao), sum(qtd_salarios_admissao)
                from gold.{tabela}
            """).fetchone(), esperado)
        self.assertEqual(self.conn.execute("""
            select count(*) from gold.fct_movimentacao f
            join gold.dim_competencia using (competencia)
            join gold.dim_municipio using (id_municipio)
            join gold.dim_cnae using (codigo_cnae_subclasse)
            join gold.dim_cbo using (codigo_cbo)
            join gold.dim_perfil_demografico using (id_perfil_demografico)
        """).fetchone()[0], 48)
        self.assertEqual(self.conn.execute("""
            select codigo_cbo, codigo_cnae_subclasse from gold.fct_movimentacao
            where id_movimentacao=1
        """).fetchone(), ("012345", "0000001"))

    def test_salario_denominador_e_recomposicao(self):
        self.assertEqual(self.conn.execute("""
            select admissoes, desligamentos, saldo, soma_salarios_admissao,
                   qtd_salarios_admissao, salario_medio_admissao
            from gold.fct_setor_mensal
            where competencia='2025-01-01' and sigla_uf='DF' and codigo_secao='A'
        """).fetchone(), (3, 1, 2, Decimal("4000"), 2, 2000))
        self.assertAlmostEqual(self.conn.execute("""
            select sum(soma_salarios_admissao)/sum(qtd_salarios_admissao)
            from gold.fct_setor_mensal
            where competencia='2025-01-01' and codigo_secao='A'
        """).fetchone()[0], 10000 / 6)
        self.assertIsNone(self.conn.execute("""
            select salario_medio_admissao from gold.fct_setor_mensal where codigo_secao='D'
        """).fetchone()[0])

    def test_perfis_faixas_e_sentinelas(self):
        self.assertEqual(self.conn.execute("""
            select distinct idade, codigo_faixa_etaria from gold.fct_movimentacao
            where codigo_sexo=9 order by idade nulls last
        """).fetchall(), [(17, 1), (18, 2), (24, 2), (25, 3), (29, 3), (30, 4),
                           (39, 4), (40, 5), (49, 5), (50, 6), (64, 6), (65, 7), (None, 0)])
        self.assertEqual(self.conn.execute("""
            select distinct codigo_grau_instrucao, escolaridade from gold.dim_perfil_demografico
            where codigo_grau_instrucao in (80,901) order by codigo_grau_instrucao
        """).fetchall(), [(80, "Pós-graduação completa"), (901, "Código não mapeado")])
        self.assertFalse(self.conn.execute("""
            select is_identificado from gold.dim_municipio where id_municipio='9999999'
        """).fetchone()[0])
        self.assertFalse(self.conn.execute("""
            select is_cadastro_oficial from gold.dim_cnae where codigo_secao='B'
        """).fetchone()[0])

    def test_p1_janela_calendario_empates_e_setor_desconhecido(self):
        self.assertEqual(self.conn.execute("""
            select codigo_secao, admissoes, desligamentos, ranking_admissoes,
                   ranking_desligamentos, inicio, fim, competencias_disponiveis
            from p1_setores_df order by codigo_secao
        """).fetchall(), [
            ("A", 2, 2, 1, 1, date(2025, 2, 1), date(2026, 1, 1), 3),
            ("B", 2, 1, 1, 2, date(2025, 2, 1), date(2026, 1, 1), 3),
        ])

    def test_p2_mes_ausente_zero_observado_e_ano_parcial(self):
        self.assertEqual(self.conn.execute("""
            select tem_dados, admissoes, desligamentos, saldo
            from p2_sazonalidade
            where competencia='2023-02-01' and sigla_uf='DF' and codigo_secao='A'
        """).fetchone(), (False, None, None, None))
        self.assertEqual(self.conn.execute("""
            select ano_completo_na_base, admissoes, anos_considerados, media_admissoes_mes
            from p2_sazonalidade
            where competencia='2024-01-01' and sigla_uf='DF' and codigo_secao='A'
        """).fetchone(), (True, 0, 1, 0))
        self.assertEqual(self.conn.execute("""
            select distinct ano from p2_sazonalidade where ano_completo_na_base
        """).fetchall(), [(2024,)])

    def test_p3_df_sem_interior_e_compatibilidade_analise(self):
        self.assertEqual(self.conn.execute("""
            select saldo_interior, salario_interior, n_interior, diferenca_saldo
            from p3_capitais_interior where recorte='DF' and nivel='total'
        """).fetchone(), (None, None, 0, None))
        self.conn.execute("""
            create temp view movimentacao as
            select * from gold.fct_movimentacao
            where is_identificado and is_centro_oeste and ano between 2023 and 2026
        """)
        esperado = consultar_indicadores(self.conn).fetchall()
        atual = self.conn.execute("""
            select coalesce(ano::varchar,'Total'), saldo_capital, saldo_interior,
                   diferenca_saldo, salario_capital, salario_interior, diferenca_salario,
                   n_capital, n_interior
            from p3_capitais_interior where recorte='Centro-Oeste' and nivel in ('anual','total')
            order by ano nulls last
        """).fetchall()
        for a, b in zip(atual, esperado, strict=True):
            for x, y in zip(a, b, strict=True):
                if isinstance(x, float):
                    self.assertAlmostEqual(x, y)
                else:
                    self.assertEqual(x, y)

    def test_p4_proxy_pares_correla_e_denominadores(self):
        self.conn.execute("""
            create temp table setores_teste as
            select * from gold.fct_setor_mensal
            where competencia='2025-01-01' and sigla_uf='DF'
        """)
        sql = self.projeto.sql("p4_fluxos_salarios", {"fct_setor_mensal": "setores_teste"})
        linhas = self.conn.sql(sql).fetchall()
        # Consultar via relação preserva a ordem declarada da projeção.
        resultado = {r[0]: dict(zip(self.conn.sql(sql).columns, r)) for r in linhas}
        for setor, valor in (("A", 50), ("B", 0), ("C", 100), ("D", 0)):
            self.assertEqual(resultado[setor]["indice_fluxos_pareados_pct"], valor)
        self.assertIsNone(resultado["D"]["salario_medio_admissao"])
        self.assertEqual(resultado["A"]["pares_validos"], 3)
        self.assertAlmostEqual(resultado["A"]["correlacao_pearson"],
                               statistics.correlation([50, 0, 100], [2000, 8000, 4000]))
        self.conn.execute("delete from setores_teste where codigo_secao='C'")
        self.assertIsNone(self.conn.sql(sql).fetchone()[-1])
        self.conn.execute("""
            update setores_teste set admissoes=2, desligamentos=2;
            insert into setores_teste select competencia, sigla_uf, 'C', admissoes,
                desligamentos, saldo, soma_salarios_admissao, qtd_salarios_admissao,
                salario_medio_admissao from setores_teste limit 1;
        """)
        self.assertIsNone(self.conn.sql(sql).fetchone()[-1])
        self.conn.execute("""
            update setores_teste set soma_salarios_admissao=2000, qtd_salarios_admissao=1;
            update setores_teste set desligamentos=0 where codigo_secao='B';
        """)
        self.assertIsNone(self.conn.sql(sql).fetchone()[-1])
        self.conn.execute("update setores_teste set admissoes=0, desligamentos=0, qtd_salarios_admissao=0")
        vazio = self.conn.sql(sql).fetchone()
        self.assertIsNone(vazio[-3])  # índice sem denominador
        self.assertEqual(vazio[-2], 0)
        self.assertIsNone(vazio[-1])

    def test_p5_eixos_participacoes_e_media_ponderada(self):
        self.assertEqual(self.conn.execute("""
            select distinct eixo from p5_perfil_remuneracao order by eixo
        """).fetchall(), [("escolaridade",), ("faixa_etaria",), ("raca_cor",), ("sexo",)])
        for total, in self.conn.execute("""
            select sum(participacao_admissoes_pct) from p5_perfil_remuneracao
            group by sigla_uf,is_capital,codigo_secao,eixo
        """).fetchall():
            if total is not None:
                self.assertAlmostEqual(total, 100)
        self.assertEqual(self.conn.execute("""
            select distinct salario_medio_recorte from p5_perfil_remuneracao
            where sigla_uf='GO' and not is_capital and codigo_secao='B'
        """).fetchall(), [(1000,)])
        self.assertEqual(self.conn.execute("""
            select codigo_categoria, admissoes, salario_medio_admissao,
                   qtd_salarios_admissao, salario_medio_recorte,
                   participacao_admissoes_pct, diferenca_salarial
            from p5_perfil_remuneracao
            where sigla_uf='DF' and codigo_secao='A' and eixo='sexo'
            order by codigo_categoria
        """).fetchall(), [(1, 4, 1000, 3, 1500, 80, -500),
                           (3, 1, 3000, 1, 1500, 20, 1500)])

    def test_z_reexecucao_e_evento_atrasado(self):
        antes = self.conn.execute("select * from gold.fct_setor_mensal order by all").fetchall()
        self.conn.close()
        self.projeto.dbt("build")
        with duckdb.connect(str(self.projeto.banco)) as c:
            self.assertEqual(c.execute("select * from gold.fct_setor_mensal order by all").fetchall(), antes)
        self.projeto.evento(ano=2024, mes=6, salario=7000)
        self.projeto.exportar()
        self.projeto.dbt("build")
        with duckdb.connect(str(self.projeto.banco)) as c:
            depois = c.execute("select * from gold.fct_setor_mensal order by all").fetchall()
            novo = [r for r in depois if r not in antes]
            self.assertEqual(len(novo), 1)
            self.assertEqual(novo[0][:3], (date(2024, 6, 1), 'DF', 'A'))
            self.assertEqual(novo[0][3:], (1, 0, 1, Decimal("7000"), 1, 7000))
            self.assertTrue(all(r in depois for r in antes))


class GoldAmostraTest(unittest.TestCase):
    def test_amostra_versionada_com_referencias_sinteticas(self):
        p = ProjetoTemporario()
        self.addCleanup(p.fechar)
        arquivo = str(ROOT / "data" / "caged_centro_oeste_amostra.csv").replace("'", "''")
        p.origem.execute(f"""
            insert into movimentacao
            select row_number() over (), ano::integer, mes::integer, id_municipio,
                   lpad(cnae_2_subclasse,7,'0'), lpad(cbo_2002,6,'0'), sexo::integer,
                   raca_cor::integer, case when idade::integer between 10 and 120 then idade::integer end,
                   grau_instrucao::integer, tipo_movimentacao::integer, saldo_movimentacao::integer,
                   greatest(coalesce(salario_mensal::decimal(16,2),0),0),
                   greatest(coalesce(horas_contratuais::decimal(5,2),0),0),
                   1, row_number() over (), '2026-10-30 12:00:00+00'::timestamptz
            from read_csv('{arquivo}', all_varchar=true)
        """)
        # Referências sintéticas validam as métricas sem depender das APIs IBGE/CBO.
        with (ROOT / "data" / "caged_centro_oeste_amostra.csv").open() as f:
            linhas = list(csv.DictReader(f))
        municipios = {(r['id_municipio'], r['sigla_uf']) for r in linhas}
        p.origem.executemany("insert into municipio values (?, 'Teste', ?, 'Teste', 'Centro-Oeste', ?)",
                             [(m, uf, m in CAPITAIS) for m, uf in sorted(municipios)])
        p.origem.executemany("insert into cnae_secao values (?, 'Teste')",
                             [(s,) for s in sorted({r['cnae_2_secao'] for r in linhas})])
        subclasses = {(r['cnae_2_subclasse'].zfill(7), r['cnae_2_secao']) for r in linhas}
        p.origem.executemany("insert into cnae_subclasse values (?, 'Teste', ?)", sorted(subclasses))
        p.origem.execute("insert into cbo_2002 select distinct cbo_2002, 'Teste' from movimentacao")
        p.construir()
        with duckdb.connect(str(p.banco)) as c:
            self.assertEqual(c.execute("""
                select count(*), count(*) filter(where saldo_movimentacao=1),
                       count(*) filter(where saldo_movimentacao=-1), sum(saldo_movimentacao)
                from gold.fct_movimentacao
            """).fetchone(), (49178, 25325, 23853, 1472))
            self.assertEqual(c.execute("""
                select sum(admissoes), sum(desligamentos), sum(saldo) from gold.fct_setor_mensal
            """).fetchone(), (25325, 23853, 1472))
            for nome in ("p1_setores_df", "p2_sazonalidade", "p3_capitais_interior",
                         "p4_fluxos_salarios", "p5_perfil_remuneracao"):
                self.assertTrue(c.sql(p.sql(nome)).fetchall(), nome)


if __name__ == "__main__":
    unittest.main()
