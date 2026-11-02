"""Assets do Dagster para a ingestão e a extração do METRA.

Os scripts em `src` continuam disponíveis para execução pela linha de
comando. Estes assets apenas os orquestram pelo Dagster, mantendo uma única
implementação para cada etapa do pipeline.
"""

from dagster import AssetExecutionContext, MaterializeResult, asset

from src.extracao.exportar_parquet import exportar
from src.ingestao.executar_pipeline import main as executar_pipeline_main


@asset(
    name="executar_pipeline",
    group_name="ingestao",
    description=(
        "Executa as migrações, as cargas Bronze e a promoção para o OLTP 3FN."
    ),
    kinds={"python", "postgres"},
)
def executar_pipeline_asset(context: AssetExecutionContext) -> MaterializeResult:
    """Materializa a origem transacional do METRA."""

    context.log.info("Iniciando o pipeline E1 pelo Dagster")
    executar_pipeline_main()
    return MaterializeResult(metadata={"destino": "PostgreSQL / schema oltp"})


@asset(
    name="exportar_parquet",
    deps=[executar_pipeline_asset],
    group_name="extracao",
    description=(
        "Exporta as tabelas do OLTP para o lake Parquet particionado e conciliado."
    ),
    kinds={"python", "duckdb", "parquet"},
)
def exportar_parquet_asset(context: AssetExecutionContext) -> MaterializeResult:
    """Materializa o lake Parquet depois da atualização do OLTP."""

    context.log.info("Iniciando a exportação OLTP -> Parquet pelo Dagster")
    exportar()
    return MaterializeResult(metadata={"destino": "data/lake/parquet"})
