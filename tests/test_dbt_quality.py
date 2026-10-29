"""Integração real dbt + DuckDB, com Parquet sintético em diretório temporário.

Executar na raiz: python -m unittest discover -s tests -p 'test_dbt_quality.py' -v
Exige as dependências de requirements-pipeline.txt. Não lê nem modifica data/lake.
"""

import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

import duckdb


ROOT = Path(__file__).resolve().parents[1]


def criar_lake(destino: Path) -> None:
    """12 movimentos em três meses; sentinelas, zeros à esquerda e nulos válidos."""
    with duckdb.connect() as conn:
        conn.execute("""
            CREATE TABLE municipio AS SELECT * FROM (VALUES
                ('5300108', 'Brasília', 'DF', 'Distrito Federal', 'Centro-Oeste', true),
                ('5200050', 'Abadia de Goiás', 'GO', 'Goiás', 'Centro-Oeste', false),
                ('9999999', 'MUNICIPIO NAO IDENTIFICADO', 'NI', 'Nao Identificado', 'Centro-Oeste', false)
            ) t(id_municipio, nome, sigla_uf, nome_uf, regiao, is_capital);
            CREATE TABLE cbo_2002 AS SELECT * FROM (VALUES
                ('010105', 'Oficial'),
                ('123456', 'OCUPACAO CBO 123456 (ATUALIZACAO MTE)')
            ) t(codigo, titulo);
            CREATE TABLE cnae_secao AS SELECT * FROM (VALUES
                ('A', 'AGRICULTURA'), ('Z', 'NAO IDENTIFICADA')
            ) t(codigo, descricao);
            CREATE TABLE cnae_subclasse AS SELECT * FROM (VALUES
                ('0111301', 'Cultivo de arroz', 'A'),
                ('9999999', 'ATIVIDADES ECONOMICAS NAO IDENTIFICADAS', 'Z')
            ) t(codigo, descricao, codigo_secao);
            CREATE TABLE movimentacao AS
            SELECT i::bigint AS id_movimentacao,
                   2025::integer AS ano,
                   ((i - 1) // 4 + 1)::integer AS mes,
                   CASE WHEN i % 4 = 0 THEN '9999999'
                        WHEN i % 2 = 0 THEN '5200050' ELSE '5300108' END AS id_municipio,
                   CASE WHEN i % 4 = 0 THEN '9999999' ELSE '0111301' END AS cnae_2_subclasse,
                   CASE WHEN i % 4 = 0 THEN '123456' ELSE '010105' END AS cbo_2002,
                   CASE WHEN i % 3 = 0 THEN 9 WHEN i % 2 = 0 THEN 3 ELSE 1 END::integer AS sexo,
                   CASE WHEN i % 2 = 0 THEN 3 ELSE 1 END::integer AS raca_cor,
                   CASE WHEN i = 1 THEN NULL WHEN i = 2 THEN 10
                        WHEN i = 3 THEN 120 ELSE 30 END::integer AS idade,
                   7::integer AS grau_instrucao,
                   CASE WHEN i % 2 = 0 THEN 40 ELSE 20 END::integer AS tipo_movimentacao,
                   CASE WHEN i % 2 = 0 THEN -1 ELSE 1 END::integer AS saldo_movimentacao,
                   CASE WHEN i = 1 THEN NULL WHEN i = 2 THEN 0 ELSE 2500 END::decimal(16,2) AS salario_mensal,
                   CASE WHEN i = 1 THEN NULL WHEN i = 2 THEN 0 ELSE 40 END::decimal(5,2) AS horas_contratuais,
                   1::bigint AS id_ingestao,
                   (i + 1)::bigint AS numero_linha,
                   TIMESTAMPTZ '2026-10-29 00:00:00+00' AS registrado_em
            FROM range(1, 13) t(i);
        """)
        for tabela in ['municipio', 'cbo_2002', 'cnae_secao', 'cnae_subclasse', 'movimentacao']:
            pasta = destino / tabela
            pasta.mkdir(parents=True)
            # O caminho temporário é um valor SQL, nunca parte de um identificador.
            conn.execute(f"COPY {tabela} TO ? (FORMAT PARQUET)", [str(pasta / 'dados.parquet')])


class DbtQualityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory(prefix='metra-qualidade-')
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.base = Path(cls.tmp.name)
        cls.project = cls.base / 'dbt_metra'
        shutil.copytree(ROOT / 'dbt_metra', cls.project,
                        ignore=shutil.ignore_patterns('target', 'logs', 'dbt_packages', '.user.yml'))
        cls.lake = cls.base / 'parquet'
        criar_lake(cls.lake)
        cls.db = cls.base / 'analitico.duckdb'
        cls.env = dict(os.environ, METRA_LAKE_PARQUET=str(cls.lake),
                       METRA_DUCKDB=str(cls.db), DBT_SEND_ANONYMOUS_USAGE_STATS='false',
                       DBT_USE_COLORS='false')
        cls.dbt = Path(sys.executable).parent / ('dbt.exe' if os.name == 'nt' else 'dbt')
        cls.build = cls.run_dbt('build')
        if cls.build.returncode:
            raise AssertionError(cls.build.stdout)
        cls.baseline_results = cls.results()
        cls.backup = cls.base / 'baseline.duckdb'
        shutil.copy2(cls.db, cls.backup)
        cls.manifest = json.loads((cls.project / 'target/manifest.json').read_text())

    @classmethod
    def run_dbt(cls, command, *args):
        return subprocess.run(
            [str(cls.dbt), command, '--profiles-dir', str(cls.project), *args],
            cwd=cls.project, env=cls.env, text=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, timeout=180, check=False,
        )

    @classmethod
    def results(cls):
        return json.loads((cls.project / 'target/run_results.json').read_text())['results']

    def setUp(self):
        shutil.copy2(self.backup, self.db)

    def alter(self, sql):
        with duckdb.connect(str(self.db)) as conn:
            conn.execute(sql)

    def assert_failed(self, result, names):
        self.assertNotEqual(result.returncode, 0, result.stdout)
        failed = {self.manifest['nodes'][r['unique_id']]['name']
                  for r in self.results() if r['status'] == 'fail'}
        for name in names:
            self.assertTrue(any(n.startswith(name) for n in failed),
                            f'{name} não falhou. Falhas: {sorted(failed)}\n{result.stdout}')
        # Erro de compilação/execução não conta como detecção de dados inválidos.
        self.assertFalse([r for r in self.results() if r['status'] == 'error'], result.stdout)

    def test_valid_build_and_types(self):
        self.assertTrue(all(r['status'] in ('pass', 'success') for r in self.baseline_results))
        with duckdb.connect(str(self.db), read_only=True) as conn:
            types = {r[0]: r[1] for r in conn.execute('describe silver.stg_movimentacao').fetchall()}
            self.assertEqual(types['id_movimentacao'], 'BIGINT')
            self.assertEqual(types['codigo_cbo'], 'VARCHAR')
            self.assertEqual(types['competencia'], 'DATE')
            self.assertEqual(types['salario_mensal'], 'DECIMAL(16,2)')
            self.assertEqual(conn.execute('select count(*) from silver.stg_movimentacao').fetchone()[0], 12)

    def test_invalid_values_references_and_lineage(self):
        self.alter("""
            UPDATE silver.stg_movimentacao SET codigo_cbo = '000000',
                id_municipio = '0000000', codigo_cnae_subclasse = '0000000',
                salario_mensal = -1, horas_contratuais = -1, idade = 9,
                codigo_sexo = 2, codigo_raca_cor = 8, saldo_movimentacao = 0,
                competencia = DATE '2024-01-01', id_ingestao = 0
            WHERE id_movimentacao = 3;
            UPDATE silver.stg_movimentacao SET numero_linha = 3 WHERE id_movimentacao = 1;
            UPDATE silver.stg_movimentacao SET codigo_grau_instrucao = NULL WHERE id_movimentacao = 4;
            INSERT INTO silver.stg_movimentacao SELECT * FROM silver.stg_movimentacao WHERE id_movimentacao = 2;
        """)
        self.assert_failed(self.run_dbt('test'), [
            'relationships_stg_movimentacao_codigo_cbo',
            'relationships_stg_movimentacao_id_municipio',
            'relationships_stg_movimentacao_codigo_cnae_subclasse',
            'stg_movimentacao_salario_nao_negativo', 'stg_movimentacao_horas_nao_negativas',
            'stg_movimentacao_idade_valida', 'stg_movimentacao_competencia_coerente',
            'stg_movimentacao_linhagem_positiva', 'stg_movimentacao_tipo_evento_coerente',
            'accepted_values_stg_movimentacao_codigo_sexo',
            'accepted_values_stg_movimentacao_codigo_raca_cor',
            'not_null_stg_movimentacao_codigo_grau_instrucao',
            'unique_stg_movimentacao_id_movimentacao',
            'metra_unique_combination_stg_movimentacao',
        ])

    def test_distribution_changes_without_changing_total(self):
        self.alter("""
            UPDATE silver.stg_movimentacao
            SET id_municipio = '5200050', codigo_sexo = 3, mes = 2,
                competencia = DATE '2025-02-01' WHERE id_movimentacao = 1;
        """)
        self.assert_failed(self.run_dbt('test', '--select', 'silver_distribuicao_*'),
                           ['silver_distribuicao_competencia', 'silver_distribuicao_geografia',
                            'silver_distribuicao_perfil'])

    def test_empty_table(self):
        self.alter('delete from silver.stg_movimentacao')
        self.assert_failed(self.run_dbt('test', '--select', 'test_name:metra_not_empty'),
                           ['metra_not_empty_stg_movimentacao'])

    def test_schema_type_drift(self):
        self.alter('alter table silver.stg_movimentacao alter salario_mensal type double')
        self.assert_failed(self.run_dbt('test', '--select', 'test_name:metra_column_types'),
                           ['metra_column_types_stg_movimentacao'])

    def test_missing_month_warns(self):
        self.alter('delete from silver.stg_movimentacao where mes = 2')
        result = self.run_dbt('test', '--select', 'silver_volume_mensal')
        self.assertEqual(result.returncode, 0, result.stdout)
        self.assertEqual([r['status'] for r in self.results()], ['warn'])

    def test_source_duplicate_and_missing_cnae_section(self):
        # O lake sintético é restaurado mesmo se uma asserção falhar.
        mov = self.lake / 'movimentacao/dados.parquet'
        sec = self.lake / 'cnae_secao/dados.parquet'
        backup_mov, backup_sec = mov.read_bytes(), sec.read_bytes()
        try:
            with duckdb.connect() as conn:
                conn.execute('create table mov as select * from read_parquet(?)', [str(mov)])
                conn.execute('insert into mov select * from mov where id_movimentacao = 1')
                conn.execute('copy mov to ? (format parquet)', [str(mov)])
                conn.execute("create table sec as select * from read_parquet(?) where codigo <> 'A'", [str(sec)])
                conn.execute('copy sec to ? (format parquet)', [str(sec)])
            self.assert_failed(self.run_dbt('test', '--select', 'source:lake'), [
                'source_unique_lake_movimentacao_id_movimentacao',
                'source_relationships_lake_cnae_subclasse_codigo_secao',
            ])
        finally:
            mov.write_bytes(backup_mov)
            sec.write_bytes(backup_sec)


if __name__ == '__main__':
    unittest.main()
