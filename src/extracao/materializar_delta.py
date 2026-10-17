"""Materializacao da tabela Delta de movimentacoes: Parquet extraido -> Delta Lake.

Regras da materializacao:
- a fonte e o Parquet gerado por src/extracao/exportar_parquet.py (a origem
  transacional nao e consultada de novo);
- a tabela e particionada por ano e gravada com delta-rs (pacote deltalake), sem
  JVM, catalogo ou servico adicional: a tabela e um diretorio com _delta_log/;
- idempotente: cada execucao sobrescreve o conteudo e gera uma nova versao no log,
  sem acumular registros; os arquivos de dados das versoes anteriores sao removidos;
- conciliada: a leitura pelo DuckDB (delta_scan) precisa devolver a mesma
  quantidade de linhas do Parquet de origem.

Uso:
    python3 -m src.extracao.materializar_delta
    python3 -m src.extracao.materializar_delta --compressao zstd
"""

import argparse
import logging
import time
from pathlib import Path

import duckdb
from deltalake import DeltaTable, WriterProperties, write_deltalake
from deltalake.exceptions import DeltaError

from src.extracao.exportar_parquet import (
    COMPRESSAO_PADRAO,
    COMPRESSOES,
    DIRETORIO_PARQUET,
    LAKE,
    TABELAS,
    leitura_parquet,
)

TABELA = "movimentacao"
DIRETORIO_DELTA = LAKE / "delta" / TABELA

log = logging.getLogger("materializar_delta")


def leitura_delta(diretorio: Path = DIRETORIO_DELTA) -> str:
    """Expressao SQL do DuckDB que le a tabela Delta."""
    return f"delta_scan('{diretorio}')"


def materializar(compressao: str = COMPRESSAO_PADRAO, destino: Path = DIRETORIO_DELTA) -> int:
    """Sobrescreve a tabela Delta com o Parquet extraido e devolve a versao gerada."""
    if not (DIRETORIO_PARQUET / TABELA).is_dir():
        raise ValueError(
            f"Parquet de {TABELA} ausente em {DIRETORIO_PARQUET}; "
            "execute antes: python3 -m src.extracao.exportar_parquet"
        )

    with duckdb.connect() as conn:
        origem = conn.sql(f"SELECT * FROM {leitura_parquet(TABELA)}")
        (no_parquet,) = origem.count("*").fetchone()
        write_deltalake(
            destino,
            origem,
            mode="overwrite",
            schema_mode="overwrite",
            partition_by=[TABELAS[TABELA]],
            writer_properties=WriterProperties(compression=compressao.upper()),
        )

        tabela = DeltaTable(destino)
        # Mantem o historico no log, mas nao acumula em disco os dados de versoes antigas.
        tabela.vacuum(retention_hours=0, dry_run=False, enforce_retention_duration=False)

        (no_delta,) = conn.execute(f"SELECT count(*) FROM {leitura_delta(destino)}").fetchone()
    if no_parquet != no_delta:
        raise ValueError(f"{TABELA}: {no_parquet} linhas no Parquet, {no_delta} na tabela Delta.")

    log.info(
        "%s: %s linhas na versao %d da tabela Delta (%s)",
        TABELA, f"{no_delta:,}", tabela.version(), destino,
    )
    return tabela.version()


def main() -> None:
    parser = argparse.ArgumentParser(description="Materializacao Parquet -> Delta Lake (METRA)")
    parser.add_argument(
        "--compressao",
        choices=COMPRESSOES,
        default=COMPRESSAO_PADRAO,
        help=f"Codec de compressao dos arquivos da tabela Delta (padrao: {COMPRESSAO_PADRAO})",
    )
    args = parser.parse_args()

    inicio = time.monotonic()
    try:
        materializar(args.compressao)
    except (duckdb.Error, DeltaError, OSError, ValueError) as erro:
        raise SystemExit(f"Falha na materializacao: {erro}") from None
    log.info("=== Tabela Delta materializada em %.2fs ===", time.monotonic() - inicio)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    main()
