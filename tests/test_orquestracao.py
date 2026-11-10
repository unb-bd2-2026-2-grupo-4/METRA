"""Contratos da orquestração Dagster: retry, schedules e partições para backfill.

Executar no ambiente de requirements-pipeline.txt:
    python -m unittest discover -s tests -p 'test_orquestracao.py' -v
"""

from datetime import date
from pathlib import Path
import subprocess
import sys
import unittest

from dagster import BackfillPolicy

ROOT = Path(__file__).resolve().parents[1]
PROJECT = ROOT / "dbt_metra"


class OrquestracaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # O dbt_assets lê o manifest; em um clone novo ele ainda não existe.
        if not (PROJECT / "target" / "manifest.json").exists():
            subprocess.run(
                [sys.executable, "-c", "from dbt.cli.main import cli; cli()", "parse",
                 "--project-dir", str(PROJECT), "--profiles-dir", str(PROJECT)],
                cwd=ROOT, check=True, capture_output=True,
            )
        from dagster_metra import assets, definitions

        cls.assets = assets
        cls.defs = definitions.defs
        cls.grafo = cls.defs.resolve_asset_graph()

    def test_todos_os_assets_materializaveis_tem_retry(self):
        sem_retry = []
        for chave in self.grafo.materializable_asset_keys:
            politica = self.defs.resolve_assets_def(chave).op.retry_policy
            if politica != self.assets.POLITICA_RETRY:
                sem_retry.append(chave.to_user_string())
        self.assertEqual(sem_retry, [])
        self.assertEqual(self.assets.POLITICA_RETRY.max_retries, 3)

    def test_schedules_mensais(self):
        schedules = {s.name: s for s in self.defs.schedules}
        pipeline = schedules["pipeline_metra_mensal"]
        self.assertEqual(pipeline.cron_schedule, "0 6 5 * *")
        self.assertEqual(pipeline.execution_timezone, "America/Sao_Paulo")
        self.assertEqual(pipeline.job_name, "pipeline_metra")
        self.assertEqual(schedules["conciliacao_mensal"].job_name, "conciliacao_mensal_job")

    def test_conciliacao_particionada_por_mes_com_backfill_em_execucao_unica(self):
        conciliacao = self.defs.resolve_assets_def("conciliacao_mensal")
        chaves = conciliacao.partitions_def.get_partition_keys()
        self.assertEqual(chaves[0], "2023-01-01")
        self.assertEqual(conciliacao.backfill_policy, BackfillPolicy.single_run())

    def test_competencias_da_janela(self):
        self.assertEqual(
            self.assets.competencias_da_janela(date(2025, 11, 1), date(2026, 2, 1)),
            [date(2025, 11, 1), date(2025, 12, 1), date(2026, 1, 1)],
        )


if __name__ == "__main__":
    unittest.main()
