from pathlib import Path
import sys

from dagster import Definitions
from dagster_dbt import DbtCliResource, DbtProject, dbt_assets


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
    assets=[metra_dbt_assets],
    resources={
        "dbt": DbtCliResource(
            project_dir=DBT_PROJECT_DIR,
            profiles_dir=DBT_PROJECT_DIR,
            dbt_executable=DBT_EXECUTABLE,
        ),
    },
)

