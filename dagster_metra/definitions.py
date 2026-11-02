"""Definições do Dagster para o pipeline e as transformações do METRA.

Este módulo reúne os assets Python de ingestão e extração e o asset dbt da
camada analítica. O Dagster usa essas definições para mostrar a linhagem e
permitir a materialização das etapas pela interface ou pela linha de comando.
"""

from pathlib import Path
import sys

from dagster import Definitions
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets

from dagster_metra.assets import executar_pipeline_asset, exportar_parquet_asset

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


@dbt_assets(
    manifest=dbt_project.manifest_path,
    project=dbt_project,
)
def metra_dbt_assets(context, dbt: DbtCliResource):
    """Executa o build completo da camada Silver e Gold."""

    yield from dbt.cli(["build"], context=context).stream()


defs = Definitions(
    assets=[executar_pipeline_asset, exportar_parquet_asset, metra_dbt_assets],
    resources={
        "dbt": DbtCliResource(
            project_dir=DBT_PROJECT_DIR,
            profiles_dir=DBT_PROJECT_DIR,
            dbt_executable=DBT_EXECUTABLE,
        ),
    },
)

