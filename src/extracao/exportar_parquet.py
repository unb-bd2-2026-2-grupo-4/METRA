"""Extracao em lote da origem transacional: PostgreSQL (schema oltp) -> Parquet.

Regras da extracao:
- a origem e lida em modo somente leitura, dentro de uma unica transacao;
- cada tabela do schema oltp vira um conjunto Parquet 1:1, sem joins nem filtros
  (a modelagem dimensional fica para a camada transformada da E3);
- oltp.movimentacao e particionada por ano (estilo Hive: ano=2023/, ano=2024/, ...);
- conciliada: a contagem de linhas de cada Parquet precisa bater com a da origem;
- idempotente e atomica: a extracao e gravada em um diretorio temporario e so
  substitui a anterior depois de conciliada; uma falha preserva a extracao anterior.

Uso:
    python3 -m src.extracao.exportar_parquet                    # compressao padrao
    python3 -m src.extracao.exportar_parquet --compressao zstd

A conexao usa as variaveis padrao do libpq (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD).
"""

import argparse
import logging
import shutil
import time
from pathlib import Path

import duckdb

LAKE = Path(__file__).resolve().parents[2] / "data" / "lake"
DIRETORIO_PARQUET = LAKE / "parquet"

COMPRESSOES = ("snappy", "zstd", "uncompressed")
# Snappy venceu no recorte amostral pelo criterio de tamanho e tempo medidos.
# Evidencias e gatilhos de revisao: docs/adr/0003-compressao-parquet.md.
COMPRESSAO_PADRAO = "snappy"

# Tabela -> coluna de particionamento (None = arquivo unico).
TABELAS = {
    "municipio": None,
    "cnae_secao": None,
    "cnae_subclasse": None,
    "cbo_2002": None,
    "movimentacao": "ano",
}

log = logging.getLogger("exportar_parquet")


def leitura_parquet(tabela: str, diretorio: Path = DIRETORIO_PARQUET) -> str:
    """Expressao SQL do DuckDB que le o Parquet de uma tabela extraida."""
    # A coluna de particao tambem e gravada nos arquivos; ler sem a inferencia Hive
    # preserva o tipo da origem (ano INTEGER) em vez do tipo inferido do caminho.
    return f"read_parquet('{diretorio / tabela}/**/*.parquet', hive_partitioning = false)"


def exportar_tabela(
    conn: duckdb.DuckDBPyConnection, tabela: str, destino: Path, compressao: str
) -> int:
    particao = TABELAS[tabela]
    inicio = time.monotonic()
    if particao:
        caminho = destino / tabela
        opcoes = f", PARTITION_BY ({particao}), WRITE_PARTITION_COLUMNS true"
    else:
        (destino / tabela).mkdir(parents=True)
        caminho = destino / tabela / f"{tabela}.parquet"
        opcoes = ""
    conn.execute(
        f"COPY (SELECT * FROM origem.oltp.{tabela}) TO '{caminho}' "
        f"(FORMAT parquet, COMPRESSION {compressao}{opcoes})"
    )

    (na_origem,) = conn.execute(f"SELECT count(*) FROM origem.oltp.{tabela}").fetchone()
    (no_parquet,) = conn.execute(
        f"SELECT count(*) FROM {leitura_parquet(tabela, destino)}"
    ).fetchone()
    if na_origem != no_parquet:
        raise ValueError(
            f"oltp.{tabela}: {na_origem} linhas na origem, {no_parquet} no Parquet."
        )

    tamanho = sum(f.stat().st_size for f in (destino / tabela).rglob("*.parquet"))
    log.info(
        "oltp.%s: %s linhas, %.2f MB em %.2fs",
        tabela, f"{no_parquet:,}", tamanho / 1024**2, time.monotonic() - inicio,
    )
    return no_parquet


def exportar(compressao: str = COMPRESSAO_PADRAO, destino: Path = DIRETORIO_PARQUET) -> None:
    """Extrai todas as tabelas e substitui a extracao anterior somente ao final."""
    temporario = destino.with_name(destino.name + ".tmp")
    shutil.rmtree(temporario, ignore_errors=True)
    temporario.mkdir(parents=True)

    log.info("Extraindo oltp -> %s (compressao=%s)", destino, compressao)
    try:
        with duckdb.connect() as conn:
            conn.execute("ATTACH '' AS origem (TYPE postgres, READ_ONLY)")
            # Uma transacao unica: todas as tabelas e contagens saem da mesma leitura.
            conn.execute("BEGIN")
            for tabela in TABELAS:
                exportar_tabela(conn, tabela, temporario, compressao)
            conn.execute("COMMIT")
        shutil.rmtree(destino, ignore_errors=True)
        temporario.rename(destino)
    finally:
        shutil.rmtree(temporario, ignore_errors=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Extracao PostgreSQL (oltp) -> Parquet (METRA)")
    parser.add_argument(
        "--compressao",
        choices=COMPRESSOES,
        default=COMPRESSAO_PADRAO,
        help=f"Codec de compressao dos arquivos Parquet (padrao: {COMPRESSAO_PADRAO})",
    )
    args = parser.parse_args()

    inicio = time.monotonic()
    try:
        exportar(args.compressao)
    except (duckdb.Error, OSError, ValueError) as erro:
        raise SystemExit(f"Falha na extracao: {erro}") from None
    log.info("=== Extracao para Parquet concluida em %.2fs ===", time.monotonic() - inicio)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
    main()
