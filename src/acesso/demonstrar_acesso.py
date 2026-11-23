"""Demonstração do controle de acesso: o que cada perfil consegue ler.

- consumidor: abre só a base de consumo isolada (src/acesso/base_consumo.py). Lê os
  agregados com supressão; não alcança o detalhe da Gold por nenhum caminho.
- analista: perfil interno do painel e do dbt, sobre o banco analítico somente leitura.
  Lê o detalhe, mas não escreve.

Cada tentativa tem um resultado esperado. A execução falha se um acesso negado passar
ou um permitido for bloqueado, então serve também como verificação na CI.

Uso, depois de publicar a base de consumo:
    python -m src.acesso.demonstrar_acesso
"""

from dataclasses import dataclass
from pathlib import Path

import duckdb

from src.acesso.base_consumo import caminho_base_consumo, conectar_consumidor
from src.app.banco_analitico import obter_caminho_duckdb
from src.extracao.exportar_parquet import leitura_parquet


@dataclass(frozen=True)
class Tentativa:
    perfil: str
    descricao: str
    sql: str
    permitida: bool


def tentativas(analitico: Path) -> list[Tentativa]:
    # Contagem sobre a fato: exige acesso ao detalhe sem imprimir nenhum registro individual.
    detalhe = "select count(distinct id_movimentacao) from {}"
    return [
        Tentativa("consumidor", "agregado por setor", "select count(*) from consumo.setor_mensal", True),
        Tentativa("consumidor", "perfis um eixo por vez", "select count(*) from consumo.perfil_mensal", True),
        Tentativa("consumidor", "detalhe da Gold", detalhe.format("gold.fct_movimentacao"), False),
        Tentativa("consumidor", "anexar o banco analítico", f"attach '{analitico}' as analitico (read_only)", False),
        Tentativa("consumidor", "ler o lake Parquet", f"select count(*) from {leitura_parquet('movimentacao')}", False),
        Tentativa("consumidor", "religar o acesso externo", "set enable_external_access = true", False),
        Tentativa("consumidor", "exportar para arquivo", "copy consumo.setor_mensal to 'consumo.csv'", False),
        Tentativa("analista", "detalhe da Gold", detalhe.format("gold.fct_movimentacao"), True),
        Tentativa("analista", "alterar a Gold", "delete from gold.fct_movimentacao", False),
    ]


def executar(tentativa: Tentativa, conexoes: dict[str, duckdb.DuckDBPyConnection]) -> tuple[bool, str]:
    """Executa a tentativa; devolve se foi permitida e o resultado ou o erro resumido."""
    try:
        linhas = conexoes[tentativa.perfil].execute(tentativa.sql).fetchall()
    except duckdb.Error as erro:
        return False, f"{type(erro).__name__}: {str(erro).splitlines()[0]}"
    return True, f"{len(linhas)} linha(s)" if len(linhas) != 1 else str(linhas[0])


def main() -> None:
    analitico = obter_caminho_duckdb()
    conexoes = {
        "consumidor": conectar_consumidor(),
        "analista": duckdb.connect(str(analitico), read_only=True),
    }
    print(f"Base de consumo: {caminho_base_consumo()}\nBanco analítico: {analitico}\n")
    divergentes = []
    try:
        for tentativa in tentativas(analitico):
            permitida, resultado = executar(tentativa, conexoes)
            situacao = "PERMITIDO" if permitida else "NEGADO"
            esperado = "ok" if permitida == tentativa.permitida else "INESPERADO"
            print(f"[{esperado:^10}] {tentativa.perfil:<10} {tentativa.descricao:<26} {situacao:<9} {resultado[:90]}")
            if permitida != tentativa.permitida:
                divergentes.append(f"{tentativa.perfil}: {tentativa.descricao}")
    finally:
        for conn in conexoes.values():
            conn.close()
    if divergentes:
        raise SystemExit("Controle de acesso divergente do esperado: " + "; ".join(divergentes))
    print("\nControle de acesso conforme o esperado.")


if __name__ == "__main__":
    main()
