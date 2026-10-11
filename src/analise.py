"""Carga PostgreSQL → DuckDB e comparação entre capitais e interior (ADR 0002)."""

from pathlib import Path

import duckdb

BANCO = Path(__file__).resolve().parents[1] / "data" / "metra.duckdb"


def carregar_dados(conn: duckdb.DuckDBPyConnection) -> None:
    """Substitui o recorte local atomicamente, sem escrever na origem."""
    conn.execute("ATTACH '' AS origem (TYPE postgres, READ_ONLY)")
    conn.execute("BEGIN")
    try:
        conn.execute("""
            CREATE OR REPLACE TABLE movimentacao AS
            SELECT m.*, municipio.nome AS nome_municipio,
                   municipio.sigla_uf, municipio.is_capital
            FROM origem.oltp.movimentacao AS m
            JOIN origem.oltp.municipio AS municipio USING (id_municipio)
            WHERE municipio.sigla_uf IN ('DF', 'GO', 'MT', 'MS')
              AND municipio.id_municipio <> '9999999'
              AND m.ano BETWEEN 2023 AND 2026
        """)
        if not conn.execute("SELECT COUNT(*) FROM movimentacao").fetchone()[0]:
            raise ValueError("Nenhuma movimentação identificada no recorte 2023–2026.")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise
    finally:
        conn.execute("DETACH origem")


def consultar_indicadores(conn: duckdb.DuckDBPyConnection) -> duckdb.DuckDBPyRelation:
    """Calcula médias por evento e diferenças antes de qualquer arredondamento."""
    return conn.sql("""
        WITH grupos AS (
            SELECT ano, is_capital,
                   SUM(saldo_movimentacao) AS saldo,
                   AVG(salario_mensal) FILTER (
                       WHERE saldo_movimentacao = 1 AND salario_mensal > 0
                   ) AS salario,
                   COUNT(*) FILTER (
                       WHERE saldo_movimentacao = 1 AND salario_mensal > 0
                   ) AS salarios_considerados
            FROM movimentacao
            GROUP BY GROUPING SETS ((ano, is_capital), (is_capital))
        ), comparacao AS (
            SELECT ano,
                   MAX(saldo) FILTER (WHERE is_capital) AS saldo_capital,
                   MAX(saldo) FILTER (WHERE NOT is_capital) AS saldo_interior,
                   MAX(salario) FILTER (WHERE is_capital) AS salario_capital,
                   MAX(salario) FILTER (WHERE NOT is_capital) AS salario_interior,
                   COALESCE(MAX(salarios_considerados) FILTER (WHERE is_capital), 0) AS n_capital,
                   COALESCE(MAX(salarios_considerados) FILTER (WHERE NOT is_capital), 0) AS n_interior
            FROM grupos
            GROUP BY ano
        )
        SELECT COALESCE(ano::VARCHAR, 'Total') AS periodo,
               saldo_capital, saldo_interior,
               saldo_capital - saldo_interior AS diferenca_saldo,
               salario_capital, salario_interior,
               salario_capital - salario_interior AS diferenca_salario,
               n_capital, n_interior
        FROM comparacao
        ORDER BY ano NULLS LAST
    """)


def apresentar_resultados(conn: duckdb.DuckDBPyConnection) -> None:
    competencias = conn.sql("""
        SELECT DISTINCT make_date(ano, mes, 1) AS competencia
        FROM movimentacao ORDER BY competencia
    """).fetchall()
    print("Competências: " + ", ".join(data.strftime("%Y-%m") for (data,) in competencias))
    print("Resultados dos dados carregados; amostras não representam totais populacionais.")
    indicadores = consultar_indicadores(conn)
    print("\nSaldo de empregos (postos); diferença = capital − interior:")
    indicadores.project("periodo, saldo_capital, saldo_interior, diferenca_saldo").show()
    print("\nSalário médio nominal de admissão (R$); n = salários positivos considerados:")
    indicadores.project("""
        periodo, ROUND(salario_capital, 2) AS salario_capital,
        ROUND(salario_interior, 2) AS salario_interior,
        ROUND(diferenca_salario, 2) AS diferenca_salario, n_capital, n_interior
    """).show(max_width=200)


def main() -> None:
    try:
        with duckdb.connect(str(BANCO)) as conn:
            carregar_dados(conn)
            apresentar_resultados(conn)
    except (duckdb.Error, OSError, ValueError) as erro:
        raise SystemExit(f"Falha na análise: {erro}") from None


if __name__ == "__main__":
    main()
