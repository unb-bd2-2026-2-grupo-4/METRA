"""Compara codecs Parquet sobre uma unica copia de movimentacao.

python3 -m src.extracao.comparar_compressao  # PostgreSQL, variaveis PG*
python3 -m src.extracao.comparar_compressao --amostra data/caged_centro_oeste_amostra.csv

Resultados e arquivos ficam em um diretorio exclusivo em data/lake/benchmarks/.
A leitura cronometrada varre todas as colunas (hash), sem transferir linhas ao Python.
Nao limpa o cache do SO: resultados sao de cache aquecido, nao de disco frio.
"""

import argparse
import hashlib
import json
import platform
import statistics
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path

import duckdb

from src.extracao.exportar_parquet import LAKE

CODECS = ("uncompressed", "snappy", "zstd")
AMOSTRA_SQL = """
SELECT row_number() OVER ()::BIGINT AS id_movimentacao,
       ano::INTEGER AS ano, mes::INTEGER AS mes,
       coalesce(nullif(id_municipio, ''), '9999999') AS id_municipio,
       coalesce(nullif(lpad(cnae_2_subclasse, 7, '0'), ''), '9999999') AS cnae_2_subclasse,
       lpad(cbo_2002, 6, '0') AS cbo_2002,
       sexo::INTEGER AS sexo, raca_cor::INTEGER AS raca_cor,
       CASE WHEN nullif(idade, '')::INTEGER BETWEEN 10 AND 120
            THEN idade::INTEGER END AS idade,
       grau_instrucao::INTEGER AS grau_instrucao,
       tipo_movimentacao::INTEGER AS tipo_movimentacao,
       saldo_movimentacao::INTEGER AS saldo_movimentacao,
       greatest(coalesce(nullif(salario_mensal, '')::DECIMAL(16,2), 0), 0)::DECIMAL(16,2) AS salario_mensal,
       greatest(coalesce(nullif(horas_contratuais, '')::DECIMAL(5,2), 0), 0)::DECIMAL(5,2) AS horas_contratuais,
       1::BIGINT AS id_ingestao,
       (row_number() OVER () + 1)::BIGINT AS numero_linha,
       TIMESTAMPTZ '2026-10-15 00:00:00+00' AS registrado_em
FROM read_csv(?, header=true, all_varchar=true)
WHERE sigla_uf IN ('DF', 'GO', 'MT', 'MS') AND ano::INTEGER BETWEEN 2023 AND 2026
"""


def literal(valor: Path) -> str:
    """Caminho como literal SQL, inclusive quando contem apostrofos."""
    return "'" + str(valor).replace("'", "''") + "'"


def assinatura(conn: duckdb.DuckDBPyConnection, fonte: str) -> tuple:
    # count(*) sozinho pode ser respondido pelo rodape do Parquet, sem ler dados.
    return conn.execute(
        f"SELECT count(*), sum(hash(COLUMNS(*))) FROM {fonte}"
    ).fetchone()


def comparar(amostra: Path | None = None, repeticoes: int = 7, threads: int = 1) -> Path:
    if repeticoes < 3 or threads < 1:
        raise ValueError("Use pelo menos 3 repeticoes e 1 thread.")
    raiz = LAKE / "benchmarks"
    raiz.mkdir(parents=True, exist_ok=True)
    destino = Path(tempfile.mkdtemp(prefix="compressao-", dir=raiz))
    with duckdb.connect(config={"threads": threads}) as conn:
        conn.execute("SET TimeZone='UTC'")
        if amostra is None:
            conn.execute("ATTACH '' AS origem (TYPE postgres, READ_ONLY)")
            conn.execute("BEGIN")
            conn.execute("CREATE TABLE movimentacao AS SELECT * FROM origem.oltp.movimentacao")
            conn.execute("COMMIT")
            fonte = {"tipo": "PostgreSQL oltp.movimentacao"}
        else:
            conn.execute("CREATE TABLE movimentacao AS " + AMOSTRA_SQL, [str(amostra)])
            fonte = {
                "tipo": "CSV amostral tipado; linhagem reconstruida, sem PostgreSQL",
                "arquivo": amostra.name,
                "sha256": hashlib.sha256(amostra.read_bytes()).hexdigest(),
                "linhagem": "IDs sequenciais; id_ingestao=1; registrado_em=2026-10-15T00:00:00Z",
            }
        esperado = assinatura(conn, "movimentacao")
        if esperado[0] == 0:
            raise ValueError("A origem nao contem movimentacoes; benchmark cancelado.")
        schema = conn.execute("DESCRIBE movimentacao").fetchall()
        medicoes = {codec: [] for codec in CODECS}
        # Rodada 0 aquece os codecs; a ordem rotaciona para reduzir vies de execucao.
        for rodada in range(repeticoes + 1):
            ordem = CODECS[rodada % 3:] + CODECS[:rodada % 3]
            for codec in ordem:
                pasta = destino / codec / f"rodada-{rodada}"
                pasta.parent.mkdir(exist_ok=True)
                inicio = time.perf_counter()
                conn.execute(
                    f"COPY movimentacao TO {literal(pasta)} (FORMAT parquet, "
                    f"COMPRESSION {codec}, PARTITION_BY (ano), WRITE_PARTITION_COLUMNS true)"
                )
                escrita = time.perf_counter() - inicio
                arquivos = sorted(pasta.rglob("*.parquet"))
                tamanho = sum(p.stat().st_size for p in arquivos)
                leitura = f"read_parquet({literal(pasta / '**/*.parquet')}, hive_partitioning=false)"
                inicio = time.perf_counter()
                obtido = assinatura(conn, leitura)
                tempo_leitura = time.perf_counter() - inicio
                if obtido != esperado:
                    raise ValueError(f"Conteudo divergente: {codec}, rodada {rodada}")
                # Comparacao exata de multiconjuntos e tipos, fora do cronometro.
                if conn.execute(f"DESCRIBE SELECT * FROM {leitura}").fetchall() != schema:
                    raise ValueError(f"Schema divergente: {codec}")
                for esquerda, direita in (("movimentacao", leitura), (leitura, "movimentacao")):
                    if conn.execute(
                        f"SELECT EXISTS(SELECT * FROM {esquerda} EXCEPT ALL SELECT * FROM {direita})"
                    ).fetchone()[0]:
                        raise ValueError(f"Linhas divergentes: {codec}")
                if rodada:
                    medicoes[codec].append({
                        "rodada": rodada, "bytes": tamanho, "arquivos": len(arquivos),
                        "escrita_s": escrita, "leitura_s": tempo_leitura,
                    })
        resumo = {
            codec: {chave: statistics.median(m[chave] for m in valores)
                    for chave in ("bytes", "escrita_s", "leitura_s")}
            for codec, valores in medicoes.items()
        }
        # Criterio declarado antes das medicoes: menor tamanho entre codecs cujo
        # custo combinado de escrita+leitura nao ultrapasse Snappy em mais de 25%.
        limite = (resumo["snappy"]["escrita_s"] + resumo["snappy"]["leitura_s"]) * 1.25
        elegiveis = [c for c in CODECS if resumo[c]["escrita_s"] + resumo[c]["leitura_s"] <= limite]
        vencedor = min(elegiveis, key=lambda c: (resumo[c]["bytes"], resumo[c]["leitura_s"]))
        resultado = {
            "data_utc": datetime.now(timezone.utc).isoformat(),
            "ambiente": {"python": platform.python_version(), "duckdb": duckdb.__version__,
                         "plataforma": platform.platform(), "threads": threads},
            "fonte": fonte, "linhas": esperado[0], "schema": schema,
            "particoes": conn.execute("SELECT ano, count(*) FROM movimentacao GROUP BY ano ORDER BY ano").fetchall(),
            "metodo": "1 aquecimento + repeticoes; ordem rotativa; hash de todas as colunas; cache SO nao limpo; sem fsync",
            "criterio": "menor tamanho com mediana escrita + mediana leitura <= 1.25 vezes Snappy",
            "medicoes": medicoes, "medianas": resumo, "vencedor": vencedor,
        }
    relatorio = destino / "resultados.json"
    relatorio.write_text(json.dumps(resultado, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(json.dumps({"medianas": resumo, "vencedor": vencedor}, indent=2))
    print(f"Relatorio e arquivos: {destino}")
    return relatorio


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--amostra", type=Path, help="CSV versionado; alternativa local ao PostgreSQL")
    parser.add_argument("--repeticoes", type=int, default=7)
    parser.add_argument("--threads", type=int, default=1)
    args = parser.parse_args()
    try:
        comparar(args.amostra, args.repeticoes, args.threads)
    except (duckdb.Error, OSError, ValueError) as erro:
        raise SystemExit(f"Falha no benchmark: {erro}") from None


if __name__ == "__main__":
    main()
