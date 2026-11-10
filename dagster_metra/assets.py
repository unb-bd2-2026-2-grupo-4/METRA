"""Assets do Dagster para a ingestão e a extração do METRA.

Os scripts em `src` continuam disponíveis para execução pela linha de
comando. Estes assets apenas os orquestram pelo Dagster, mantendo uma única
implementação para cada etapa do pipeline.
"""

from datetime import date
import os
from pathlib import Path

from dagster import (
    AssetExecutionContext,
    AssetKey,
    Backoff,
    BackfillPolicy,
    Failure,
    Jitter,
    MaterializeResult,
    MonthlyPartitionsDefinition,
    RetryPolicy,
    asset,
)
import duckdb
import psycopg

from src.extracao.exportar_parquet import exportar
from src.ingestao.executar_pipeline import main as executar_pipeline_main

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Falhas transitórias (PostgreSQL reiniciando, arquivo DuckDB ocupado) são repetidas até
# 3 vezes, com espera exponencial a partir de 10 s. Todas as etapas são idempotentes:
# a carga ignora arquivos já ingeridos, a extração troca o lake atomicamente e o dbt
# reconstrói os modelos, então repetir uma etapa não duplica dados.
POLITICA_RETRY = RetryPolicy(
    max_retries=3,
    delay=10,
    backoff=Backoff.EXPONENTIAL,
    jitter=Jitter.PLUS_MINUS,
)

# Competências do Novo CAGED no recorte do projeto: uma partição por mês desde jan/2023.
PARTICOES_COMPETENCIA = MonthlyPartitionsDefinition(start_date="2023-01-01")


@asset(
    name="executar_pipeline",
    group_name="ingestao",
    description=(
        "Executa as migrações, as cargas Bronze e a promoção para o OLTP 3FN."
    ),
    kinds={"python", "postgres"},
    retry_policy=POLITICA_RETRY,
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
    retry_policy=POLITICA_RETRY,
)
def exportar_parquet_asset(context: AssetExecutionContext) -> MaterializeResult:
    """Materializa o lake Parquet depois da atualização do OLTP."""

    context.log.info("Iniciando a exportação OLTP -> Parquet pelo Dagster")
    exportar()
    return MaterializeResult(metadata={"destino": "data/lake/parquet"})


def caminho_banco_analitico() -> Path:
    """Banco DuckDB da Gold; METRA_DUCKDB relativo parte de dbt_metra/, como no profiles.yml."""
    valor = os.environ.get("METRA_DUCKDB")
    if not valor:
        return PROJECT_ROOT / "data" / "metra_analitico.duckdb"
    caminho = Path(valor)
    return caminho if caminho.is_absolute() else (PROJECT_ROOT / "dbt_metra" / caminho).resolve()


def competencias_da_janela(inicio: date, fim: date) -> list[date]:
    """Primeiro dia de cada mês no intervalo semiaberto [inicio, fim)."""
    meses, atual = [], date(inicio.year, inicio.month, 1)
    while atual < fim:
        meses.append(atual)
        atual = date(atual.year + atual.month // 12, atual.month % 12 + 1, 1)
    return meses


@asset(
    name="conciliacao_mensal",
    deps=[AssetKey(["gold", "fct_movimentacao"])],
    group_name="qualidade",
    description=(
        "Concilia, por competência, a contagem e o saldo de movimentações do OLTP "
        "com a fato Gold. Particionado por mês para permitir backfill de competências."
    ),
    kinds={"python", "postgres", "duckdb"},
    partitions_def=PARTICOES_COMPETENCIA,
    # Um intervalo de meses é reprocessado em uma única execução.
    backfill_policy=BackfillPolicy.single_run(),
    retry_policy=POLITICA_RETRY,
)
def conciliacao_mensal_asset(context: AssetExecutionContext) -> MaterializeResult:
    """Falha se alguma competência da janela divergir entre a origem e a Gold."""

    janela = context.partition_time_window
    competencias = competencias_da_janela(janela.start.date(), janela.end.date())
    context.log.info(
        "Conciliando %d competência(s): %s a %s",
        len(competencias), competencias[0], competencias[-1],
    )

    with psycopg.connect() as origem:
        oltp = {
            (ano, mes): (qtd, saldo)
            for ano, mes, qtd, saldo in origem.execute(
                """
                SELECT ano, mes, count(*), coalesce(sum(saldo_movimentacao), 0)
                FROM oltp.movimentacao
                WHERE make_date(ano, mes, 1) >= %s AND make_date(ano, mes, 1) < %s
                GROUP BY ano, mes
                """,
                (janela.start.date(), janela.end.date()),
            ).fetchall()
        }
    with duckdb.connect(str(caminho_banco_analitico()), read_only=True) as gold:
        fato = {
            (competencia.year, competencia.month): (qtd, saldo)
            for competencia, qtd, saldo in gold.execute(
                """
                SELECT competencia, count(*), coalesce(sum(saldo_movimentacao), 0)
                FROM gold.fct_movimentacao
                WHERE competencia >= ? AND competencia < ?
                GROUP BY competencia
                """,
                [janela.start.date(), janela.end.date()],
            ).fetchall()
        }

    divergencias = []
    for competencia in competencias:
        chave = (competencia.year, competencia.month)
        na_origem, na_gold = oltp.get(chave, (0, 0)), fato.get(chave, (0, 0))
        if na_origem != na_gold:
            divergencias.append(
                f"{competencia:%Y-%m}: OLTP {na_origem[0]} linhas/saldo {na_origem[1]}, "
                f"Gold {na_gold[0]} linhas/saldo {na_gold[1]}"
            )
    if divergencias:
        raise Failure(
            description="Competências divergentes entre OLTP e Gold:\n" + "\n".join(divergencias),
            allow_retries=False,
        )

    return MaterializeResult(
        metadata={
            "competencias_conciliadas": len(competencias),
            "competencias_com_dados": sum(1 for c in competencias if (c.year, c.month) in oltp),
            "movimentacoes": sum(qtd for qtd, _ in oltp.values()),
        }
    )
