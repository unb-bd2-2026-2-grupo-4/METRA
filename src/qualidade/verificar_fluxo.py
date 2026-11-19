"""Conciliação do fluxo completo: Bronze -> OLTP -> Parquet -> Delta -> Silver -> Gold.

Confere, camada a camada, a quantidade de movimentações e o saldo líquido do recorte
promovido ao OLTP (Centro-Oeste, 2023 a 2026) e se as tabelas Gold lidas pelo painel
têm linhas. Só lê: a origem é aberta em modo somente leitura e o banco analítico com
read_only, então pode rodar com o painel no ar.

Uso, depois do job pipeline_metra e com as variáveis PG* exportadas:
    python -m src.qualidade.verificar_fluxo
"""

import duckdb

from src.app.banco_analitico import obter_caminho_duckdb
from src.extracao.exportar_parquet import leitura_parquet
from src.extracao.materializar_delta import leitura_delta

# Mesmo recorte de carga_oltp.popular_movimentacoes, aplicado à Bronze ainda em texto.
CONSULTA_BRONZE = """
    select count(*), coalesce(sum(saldo_movimentacao::integer), 0)
    from origem.bronze.caged_movimentacao
    where sigla_uf in ('DF', 'GO', 'MT', 'MS') and ano::integer between 2023 and 2026
"""

CAMADAS = {
    "Bronze": CONSULTA_BRONZE,
    "OLTP": "select count(*), coalesce(sum(saldo_movimentacao), 0) from origem.oltp.movimentacao",
    "Parquet": f"select count(*), coalesce(sum(saldo_movimentacao), 0) from {leitura_parquet('movimentacao')}",
    "Delta": f"select count(*), coalesce(sum(saldo_movimentacao), 0) from {leitura_delta()}",
    "Silver": "select count(*), coalesce(sum(saldo_movimentacao), 0) from analitico.silver.stg_movimentacao",
    "Gold": "select count(*), coalesce(sum(saldo_movimentacao), 0) from analitico.gold.fct_movimentacao",
}

# Tabelas consultadas pelo painel e pelo assistente Text-to-SQL.
TABELAS_PAINEL = (
    "gold.dim_cbo",
    "gold.dim_cnae",
    "gold.dim_municipio",
    "gold.fct_movimentacao",
    "gold.fct_setor_mensal",
    "gold.fct_geografia_mensal",
    "gold.fct_perfil_mensal",
)


def medir_camadas(conn: duckdb.DuckDBPyConnection, consultas: dict[str, str] = CAMADAS) -> dict[str, tuple[int, int]]:
    """Quantidade de movimentações e saldo líquido de cada camada."""
    return {camada: tuple(int(v) for v in conn.execute(sql).fetchone()) for camada, sql in consultas.items()}


def divergencias(medidas: dict[str, tuple[int, int]]) -> list[str]:
    """Camadas cuja contagem ou saldo difere da camada anterior do fluxo."""
    erros = []
    camadas = list(medidas)
    for anterior, atual in zip(camadas, camadas[1:]):
        if medidas[atual] != medidas[anterior]:
            erros.append(
                f"{anterior} -> {atual}: {medidas[anterior][0]:,} movimentações e saldo "
                f"{medidas[anterior][1]:+,} viraram {medidas[atual][0]:,} e {medidas[atual][1]:+,}"
            )
    if medidas and not next(iter(medidas.values()))[0]:
        erros.append(f"{camadas[0]}: nenhuma movimentação no recorte; a carga não rodou?")
    return erros


def tabelas_vazias(conn: duckdb.DuckDBPyConnection, esquema: str = "analitico") -> list[str]:
    """Tabelas do painel sem nenhuma linha."""
    return [
        tabela for tabela in TABELAS_PAINEL
        if not conn.execute(f"select count(*) from {esquema}.{tabela}").fetchone()[0]
    ]


def main() -> None:
    try:
        with duckdb.connect() as conn:
            conn.execute("ATTACH '' AS origem (TYPE postgres, READ_ONLY)")
            conn.execute(f"ATTACH '{obter_caminho_duckdb()}' AS analitico (READ_ONLY)")
            medidas = medir_camadas(conn)
            vazias = tabelas_vazias(conn)
    except duckdb.Error as erro:
        raise SystemExit(f"Falha ao ler as camadas do fluxo: {erro}") from None

    for camada, (quantidade, saldo) in medidas.items():
        print(f"{camada:<8} {quantidade:>12,} movimentações  saldo {saldo:+,}")
    erros = divergencias(medidas) + [f"{tabela}: sem linhas" for tabela in vazias]
    if erros:
        raise SystemExit("Fluxo inconsistente:\n- " + "\n- ".join(erros))
    print(f"Fluxo consistente: {len(medidas)} camadas conciliadas e {len(TABELAS_PAINEL)} tabelas do painel com dados.")


if __name__ == "__main__":
    main()
