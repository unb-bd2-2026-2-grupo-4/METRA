"""Validacao de consulta: a pergunta central respondida sobre Parquet e Delta.

Executa a consulta de indicadores de src/analise.py (saldo de empregos e salario
medio de admissao, capitais x interior) sobre tres fontes e exige resultados identicos:
1. PostgreSQL (origem transacional, somente leitura);
2. arquivos Parquet extraidos;
3. tabela Delta de movimentacoes.

Uso:
    python3 -m src.extracao.validar_lake

A conexao usa as variaveis padrao do libpq (PGHOST, PGPORT, PGDATABASE, PGUSER, PGPASSWORD).
"""

import duckdb

from src.analise import consultar_indicadores
from src.extracao.exportar_parquet import leitura_parquet
from src.extracao.materializar_delta import leitura_delta


def criar_visao_movimentacao(
    conn: duckdb.DuckDBPyConnection, movimentacao: str, municipio: str
) -> None:
    """Expoe como `movimentacao` o mesmo recorte carregado por src/analise.py."""
    conn.execute(f"""
        CREATE OR REPLACE TEMP VIEW movimentacao AS
        SELECT m.*, municipio.nome AS nome_municipio,
               municipio.sigla_uf, municipio.is_capital
        FROM {movimentacao} AS m
        JOIN {municipio} AS municipio USING (id_municipio)
        WHERE municipio.sigla_uf IN ('DF', 'GO', 'MT', 'MS')
          AND municipio.id_municipio <> '9999999'
          AND m.ano BETWEEN 2023 AND 2026
    """)


def main() -> None:
    try:
        with duckdb.connect() as conn:
            conn.execute("ATTACH '' AS origem (TYPE postgres, READ_ONLY)")
            fontes = {
                "PostgreSQL": ("origem.oltp.movimentacao", "origem.oltp.municipio"),
                "Parquet": (leitura_parquet("movimentacao"), leitura_parquet("municipio")),
                "Delta": (leitura_delta(), leitura_parquet("municipio")),
            }
            resultados = {}
            for fonte, (movimentacao, municipio) in fontes.items():
                criar_visao_movimentacao(conn, movimentacao, municipio)
                resultados[fonte] = consultar_indicadores(conn).fetchall()
                if not resultados[fonte]:
                    raise ValueError(f"{fonte}: a consulta nao devolveu linhas.")

            divergentes = [f for f in fontes if resultados[f] != resultados["PostgreSQL"]]
            if divergentes:
                raise ValueError(
                    "Indicadores divergem da origem em: " + ", ".join(divergentes)
                )

            print("Indicadores identicos em: " + ", ".join(fontes))
            print("\nPergunta central consultada na tabela Delta (capital − interior):")
            consultar_indicadores(conn).project("""
                periodo, saldo_capital, saldo_interior, diferenca_saldo,
                ROUND(salario_capital, 2) AS salario_capital,
                ROUND(salario_interior, 2) AS salario_interior,
                ROUND(diferenca_salario, 2) AS diferenca_salario
            """).show(max_width=200)
    except (duckdb.Error, OSError, ValueError) as erro:
        raise SystemExit(f"Falha na validacao: {erro}") from None


if __name__ == "__main__":
    main()
