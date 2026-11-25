"""Base de consumo isolada: o único banco que consumidores externos abrem.

O DuckDB não tem usuários nem GRANT, e `read_only` só impede escrita: quem abre o
banco analítico lê toda a Gold, inclusive a fato com uma linha por movimentação.
Por isso o acesso é separado por arquivo. `data/metra_consumo.duckdb` contém só as
relações do schema `consumo` (agregadas e com supressão de pequenos grupos), e o
consumidor o abre somente para leitura, sem acesso externo e com a configuração
travada: não consegue anexar o banco analítico nem ler o lake Parquet.

Uso, depois do dbt build:
    python -m src.acesso.base_consumo
"""

import os
from pathlib import Path
import tempfile

import duckdb

from src.app.banco_analitico import DBT_PROJECT_DIR, obter_caminho_duckdb

RAIZ = Path(__file__).resolve().parents[2]
CAMINHO_PADRAO_CONSUMO = RAIZ / "data" / "metra_consumo.duckdb"
RELACOES_CONSUMO = ("setor_mensal", "geografia_mensal", "perfil_anual", "calendario")


def caminho_base_consumo() -> Path:
    """METRA_DUCKDB_CONSUMO, relativo a dbt_metra/ como METRA_DUCKDB, ou o padrão em data/."""
    valor = os.environ.get("METRA_DUCKDB_CONSUMO")
    if not valor:
        return CAMINHO_PADRAO_CONSUMO
    caminho = Path(valor)
    return caminho if caminho.is_absolute() else (DBT_PROJECT_DIR / caminho).resolve()


def publicar(analitico: Path | None = None, destino: Path | None = None) -> dict[str, int]:
    """Copia as views de consumo para a base isolada e a troca atomicamente."""
    analitico = Path(analitico or obter_caminho_duckdb()).resolve()
    destino = Path(destino or caminho_base_consumo()).resolve()
    if analitico == destino:
        raise ValueError("A base de consumo não pode sobrescrever o banco analítico.")
    destino.parent.mkdir(parents=True, exist_ok=True)

    descritor, nome = tempfile.mkstemp(dir=destino.parent, prefix=".metra_consumo-", suffix=".duckdb")
    os.close(descritor)
    temporario = Path(nome)
    temporario.unlink()  # o DuckDB precisa criar o arquivo
    try:
        with duckdb.connect(str(temporario)) as conn:
            # As views do dbt nomeiam o catálogo pelo nome do arquivo; o alias precisa ser o mesmo.
            catalogo = analitico.stem
            conn.execute(f"ATTACH '{analitico}' AS \"{catalogo}\" (READ_ONLY)")
            conn.execute("CREATE SCHEMA consumo")
            linhas = {}
            for relacao in RELACOES_CONSUMO:
                conn.execute(
                    f'CREATE TABLE consumo.{relacao} AS SELECT * FROM "{catalogo}".consumo.{relacao}'
                )
                (linhas[relacao],) = conn.execute(f"SELECT count(*) FROM consumo.{relacao}").fetchone()
            conn.execute(f'DETACH "{catalogo}"')
            conn.execute("CHECKPOINT")
        os.chmod(temporario, 0o644)
        temporario.replace(destino)
    finally:
        temporario.unlink(missing_ok=True)
        temporario.with_name(temporario.name + ".wal").unlink(missing_ok=True)
    return linhas


def conectar_consumidor(caminho: Path | None = None) -> duckdb.DuckDBPyConnection:
    """Conexão do perfil consumidor: só a base de consumo, sem escrita nem acesso externo."""
    caminho = Path(caminho or caminho_base_consumo())
    if not caminho.is_file():
        raise FileNotFoundError(
            f"Base de consumo ausente em {caminho}; execute antes: python -m src.acesso.base_consumo"
        )
    return duckdb.connect(
        str(caminho),
        read_only=True,
        config={"enable_external_access": False, "lock_configuration": True},
    )


def main() -> None:
    linhas = publicar()
    print(f"Base de consumo publicada em {caminho_base_consumo()}:")
    for relacao, total in linhas.items():
        print(f"  consumo.{relacao}: {total:,} linhas")


if __name__ == "__main__":
    main()
