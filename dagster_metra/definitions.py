"""Definições do Dagster para o pipeline e as transformações do METRA.

Este módulo reúne os assets Python de ingestão e extração e o asset dbt da
camada analítica. O Dagster usa essas definições para mostrar a linhagem e
permitir a materialização das etapas pela interface ou pela linha de comando.
"""

import json
from pathlib import Path
import sys

from dagster import (
    AssetKey,
    AssetSelection,
    Definitions,
    ScheduleDefinition,
    build_schedule_from_partitioned_job,
    define_asset_job,
)
from dagster_dbt import DagsterDbtTranslator, DbtCliResource, DbtProject, dbt_assets

from dagster_metra.assets import (
    POLITICA_RETRY,
    conciliacao_mensal_asset,
    executar_pipeline_asset,
    exportar_parquet_asset,
)

PROJECT_ROOT = Path(__file__).resolve().parents[1]
DBT_PROJECT_DIR = PROJECT_ROOT / "dbt_metra"
DBT_EXECUTABLE = Path(sys.executable).with_name("dbt")

# O manifest é preparado automaticamente quando o Dagster é iniciado em um clone novo, portanto target/ não precisa ser versionado.
dbt_project = DbtProject(
    project_dir=DBT_PROJECT_DIR,
    profiles_dir=DBT_PROJECT_DIR,
    install_deps=False,
)
dbt_project.prepare_if_dev()
dbt_translator = DagsterDbtTranslator()

# Os sources lake são arquivos Parquet produzidos por exportar_parquet.
# Como eles são sources externos no dbt, foram criadas specs virtuais para explicitar no grafo do Dagster que todos dependem da extração antes de alimentar a Silver.
dbt_manifest = json.loads(dbt_project.manifest_path.read_text(encoding="utf-8"))
metra_lake_source_assets = []
for unique_id in dbt_manifest.get("sources", {}):
    source_spec = dbt_translator.get_asset_spec(dbt_manifest, unique_id, dbt_project)
    metra_lake_source_assets.append(
        source_spec.replace_attributes(
            deps=[*source_spec.deps, AssetKey("exportar_parquet")],
            group_name="extracao",
            is_virtual=True,
            kinds={*source_spec.kinds, "parquet"},
        )
    )


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
    dagster_dbt_translator=dbt_translator,
    retry_policy=POLITICA_RETRY,
)
def metra_dbt_assets(context, dbt: DbtCliResource):
    """Executa o build completo da camada Silver e Gold."""

    yield from dbt.cli(["build"], context=context).stream()


# Pipeline completo: OLTP -> Parquet -> Silver/Gold (inclui o snapshot SCD da CBO).
pipeline_metra_job = define_asset_job(
    "pipeline_metra",
    selection=AssetSelection.assets(executar_pipeline_asset, exportar_parquet_asset, metra_dbt_assets),
    description="Executa a ingestão, a extração para Parquet e o dbt build da Silver e da Gold.",
)

# O Novo CAGED publica uma competência por mês; o pipeline roda no dia 5, às 6h.
pipeline_mensal_schedule = ScheduleDefinition(
    name="pipeline_metra_mensal",
    job=pipeline_metra_job,
    cron_schedule="0 6 5 * *",
    execution_timezone="America/Sao_Paulo",
)

# Conciliação do mês anterior, duas horas depois do pipeline; backfills usam o mesmo job.
conciliacao_mensal_job = define_asset_job(
    "conciliacao_mensal_job",
    selection=AssetSelection.assets(conciliacao_mensal_asset),
    partitions_def=conciliacao_mensal_asset.partitions_def,
)
conciliacao_mensal_schedule = build_schedule_from_partitioned_job(
    conciliacao_mensal_job,
    name="conciliacao_mensal",
    day_of_month=5,
    hour_of_day=8,
)

defs = Definitions(
    assets=[
        executar_pipeline_asset,
        exportar_parquet_asset,
        *metra_lake_source_assets,
        metra_dbt_assets,
        conciliacao_mensal_asset,
    ],
    jobs=[pipeline_metra_job, conciliacao_mensal_job],
    schedules=[pipeline_mensal_schedule, conciliacao_mensal_schedule],
    resources={
        "dbt": DbtCliResource(
            project_dir=DBT_PROJECT_DIR,
            profiles_dir=DBT_PROJECT_DIR,
            dbt_executable=DBT_EXECUTABLE,
        ),
    },
)
