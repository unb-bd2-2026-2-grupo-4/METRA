"""EXPLAIN ANALYZE antes e depois da otimização de uma consulta de consumo da Gold.

Pergunta P1 (setores no DF nos últimos 12 meses), respondida de três formas:
- origem: PostgreSQL, sobre o OLTP 3FN, com EXPLAIN (ANALYZE, BUFFERS);
- antes: DuckDB, agregando a fato detalhada gold.fct_movimentacao;
- depois: DuckDB, somando o agregado mensal gold.fct_setor_mensal.

As três respostas precisam ser idênticas. O DuckDB não tem a opção BUFFERS: para ele,
o plano do EXPLAIN ANALYZE e as linhas lidas por operador são a evidência equivalente.

Uso, com o banco analítico construído e as variáveis PG* exportadas:
    python -m src.qualidade.comparar_explain --saida docs/adr/evidencias/0005-explain-amostra.json
Em um banco DuckDB sem a origem correspondente no PostgreSQL (ex.: base completa):
    python -m src.qualidade.comparar_explain --banco <arquivo.duckdb> --sem-origem --saida <arquivo.json>
"""

import argparse
from datetime import date
import json
import os
from pathlib import Path
import platform
import statistics
import time

import duckdb
import psycopg

ROOT = Path(__file__).resolve().parents[2]

# Mesmas métricas da macro metricas_movimentacao, por seção CNAE.
CONSULTA_ANTES = """
select codigo_secao,
       count(*) filter (where saldo_movimentacao = 1) as admissoes,
       count(*) filter (where saldo_movimentacao = -1) as desligamentos,
       sum(saldo_movimentacao) as saldo,
       sum(case when saldo_movimentacao = 1 and salario_valido then salario_mensal else 0 end) as soma_salarios_admissao,
       count(*) filter (where saldo_movimentacao = 1 and salario_valido) as qtd_salarios_admissao
from gold.fct_movimentacao
where is_identificado and is_centro_oeste and ano between 2023 and 2026
  and sigla_uf = 'DF' and competencia between $inicio and $fim
group by codigo_secao
order by codigo_secao
"""

CONSULTA_DEPOIS = """
select codigo_secao,
       sum(admissoes) as admissoes,
       sum(desligamentos) as desligamentos,
       sum(saldo) as saldo,
       sum(soma_salarios_admissao) as soma_salarios_admissao,
       sum(qtd_salarios_admissao) as qtd_salarios_admissao
from gold.fct_setor_mensal
where sigla_uf = 'DF' and competencia between $inicio and $fim
group by codigo_secao
order by codigo_secao
"""

# Mesma pergunta na origem transacional, com os joins da 3FN.
CONSULTA_ORIGEM = """
select s.codigo_secao,
       count(*) filter (where m.saldo_movimentacao = 1) as admissoes,
       count(*) filter (where m.saldo_movimentacao = -1) as desligamentos,
       sum(m.saldo_movimentacao) as saldo,
       sum(case when m.saldo_movimentacao = 1 and m.salario_mensal > 0 then m.salario_mensal else 0 end) as soma_salarios_admissao,
       count(*) filter (where m.saldo_movimentacao = 1 and m.salario_mensal > 0) as qtd_salarios_admissao
from oltp.movimentacao m
join oltp.municipio mu using (id_municipio)
join oltp.cnae_subclasse s on s.codigo = m.cnae_2_subclasse
where mu.sigla_uf = 'DF' and mu.id_municipio <> '9999999'
  and make_date(m.ano, m.mes, 1) between %(inicio)s and %(fim)s
group by s.codigo_secao
order by s.codigo_secao
"""


def caminho_banco() -> Path:
    valor = os.environ.get("METRA_DUCKDB")
    if not valor:
        return ROOT / "data" / "metra_analitico.duckdb"
    caminho = Path(valor)
    return caminho if caminho.is_absolute() else (ROOT / "dbt_metra" / caminho).resolve()


def janela_12_meses(conn: duckdb.DuckDBPyConnection) -> tuple[date, date]:
    (fim,) = conn.execute("select max(competencia) from gold.fct_setor_mensal").fetchone()
    inicio = date(fim.year - 1 + (fim.month == 12), fim.month % 12 + 1, 1)
    return inicio, fim


def medir_duckdb(conn, consulta: str, parametros: dict, repeticoes: int) -> dict:
    for _ in range(3):  # aquecimento
        conn.execute(consulta, parametros).fetchall()
    tempos = []
    for _ in range(repeticoes):
        inicio = time.perf_counter()
        conn.execute(consulta, parametros).fetchall()
        tempos.append((time.perf_counter() - inicio) * 1000)
    plano = conn.execute("explain analyze " + consulta, parametros).fetchone()[1]
    return {"mediana_ms": statistics.median(tempos), "tempos_ms": tempos, "explain_analyze": plano}


def main() -> None:
    parser = argparse.ArgumentParser(description="EXPLAIN ANALYZE antes e depois (METRA)")
    parser.add_argument("--saida", type=Path, help="Arquivo JSON de evidência")
    parser.add_argument("--repeticoes", type=int, default=30)
    parser.add_argument("--banco", type=Path, help="Banco DuckDB da Gold (padrão: METRA_DUCKDB)")
    parser.add_argument(
        "--sem-origem", action="store_true",
        help="Não consulta o PostgreSQL (quando ele não contém os mesmos dados do banco DuckDB)",
    )
    args = parser.parse_args()

    with duckdb.connect(str(args.banco or caminho_banco()), read_only=True) as conn:
        conn.execute("set threads = 1")  # tempos comparáveis entre execuções
        inicio, fim = janela_12_meses(conn)
        parametros = {"inicio": inicio, "fim": fim}
        linhas_fato = conn.execute("select count(*) from gold.fct_movimentacao").fetchone()[0]
        linhas_agregado = conn.execute("select count(*) from gold.fct_setor_mensal").fetchone()[0]
        antes = medir_duckdb(conn, CONSULTA_ANTES, parametros, args.repeticoes)
        depois = medir_duckdb(conn, CONSULTA_DEPOIS, parametros, args.repeticoes)
        resultado_antes = conn.execute(CONSULTA_ANTES, parametros).fetchall()
        resultado_depois = conn.execute(CONSULTA_DEPOIS, parametros).fetchall()

    plano_origem = versao_pg = None
    iguais = resultado_antes == resultado_depois
    if not args.sem_origem:
        with psycopg.connect() as pg:
            resultado_origem = pg.execute(CONSULTA_ORIGEM, parametros).fetchall()
            plano_origem = "\n".join(
                linha for (linha,) in pg.execute(
                    "explain (analyze, buffers) " + CONSULTA_ORIGEM, parametros
                ).fetchall()
            )
            (versao_pg,) = pg.execute("show server_version").fetchone()
        iguais = iguais and resultado_antes == [tuple(r) for r in resultado_origem]
    evidencia = {
        "pergunta": "P1: admissões, desligamentos, saldo e salários por seção CNAE no DF, últimos 12 meses",
        "janela": [inicio.isoformat(), fim.isoformat()],
        "ambiente": {
            "python": platform.python_version(),
            "duckdb": duckdb.__version__,
            "postgresql": versao_pg,
            "plataforma": platform.platform(),
            "threads_duckdb": 1,
            "repeticoes": args.repeticoes,
        },
        "limites": (
            f"{linhas_fato:,} movimentações na fato; cache aquecido; host compartilhado. "
            "O DuckDB não oferece BUFFERS; o PostgreSQL, quando incluído, é medido uma vez, "
            "como referência da origem."
        ),
        "resultados_identicos": iguais,
        "linhas_lidas": {"antes_fct_movimentacao": linhas_fato, "depois_fct_setor_mensal": linhas_agregado},
        "antes": {"consulta": CONSULTA_ANTES.strip(), **antes},
        "depois": {"consulta": CONSULTA_DEPOIS.strip(), **depois},
    }
    if plano_origem:
        evidencia["origem_postgresql"] = {
            "consulta": CONSULTA_ORIGEM.strip(), "explain_analyze_buffers": plano_origem,
        }

    formas = "antes e depois" if args.sem_origem else "origem, antes e depois"
    print(f"Janela: {inicio} a {fim}; resultados idênticos ({formas}): {iguais}")
    print(f"Antes  (fct_movimentacao, {linhas_fato:,} linhas): mediana {antes['mediana_ms']:.3f} ms")
    print(f"Depois (fct_setor_mensal, {linhas_agregado:,} linhas): mediana {depois['mediana_ms']:.3f} ms")
    print(f"Ganho: {antes['mediana_ms'] / depois['mediana_ms']:.1f}x")
    if plano_origem:
        print("\nPostgreSQL (origem) EXPLAIN (ANALYZE, BUFFERS):\n" + plano_origem)
    if args.saida:
        args.saida.write_text(json.dumps(evidencia, ensure_ascii=False, indent=2) + "\n")
    if not iguais:
        raise SystemExit("As respostas divergem entre as formas da consulta.")


if __name__ == "__main__":
    main()
