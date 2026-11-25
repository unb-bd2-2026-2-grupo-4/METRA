"""Benchmark reproduzível para a ADR-0008 (disponibilização de métricas e dados públicos).

Compara três alternativas sobre o snapshot real publicado (`docs/assets/dados/metra.json`,
derivado das views `consumo.*` com supressão k >= 5):
  A. Opção nula: exportação em 4 arquivos CSV agendados + leitura/cálculo em Python.
  B. Escolhida: snapshot JSON v1 (`metra.json`) no GitHub Pages + agente JavaScript no navegador.
  C. Consultas SQL em DuckDB como referência para uma implantação com Metabase.

Verifica a paridade de P3 (capitais vs. interior) entre os três caminhos,
com igualdade para contagens e saldo e tolerância absoluta para salários.

Uso, na raiz do repositório:
    python -m src.consumo.avaliar_disponibilizacao --saida docs/adr/evidencias/0008-disponibilizacao.json
"""

from __future__ import annotations

import argparse
import csv
from datetime import date, datetime, timezone
import gzip
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import statistics
import subprocess
import tempfile
import time
from typing import Any

import duckdb

RAIZ = Path(__file__).resolve().parents[2]
FONTE_PADRAO = RAIZ / "docs" / "assets" / "dados" / "metra.json"
AGENTE_JS = RAIZ / "docs" / "javascripts" / "metra-agente.js"
SAIDA_PADRAO = RAIZ / "docs" / "adr" / "evidencias" / "0008-disponibilizacao.json"
TOLERANCIA_SALARIAL_P3 = 1e-6


def _resumo_tempos(tempos_ms: list[float]) -> dict[str, float]:
    ordenado = sorted(tempos_ms)
    idx_95 = max(0, min(len(ordenado) - 1, math.ceil(0.95 * len(ordenado)) - 1))
    return {
        "rodadas": [round(t, 3) for t in tempos_ms],
        "mediana_ms": round(statistics.median(tempos_ms), 3),
        "p95_ms": round(ordenado[idx_95], 3),
    }


def _popular_duckdb_consumo(dados: dict[str, Any], conn: duckdb.DuckDBPyConnection) -> None:
    conn.execute("CREATE SCHEMA consumo")
    conn.execute("""
        CREATE TABLE consumo.setor_mensal (
            competencia DATE, sigla_uf VARCHAR, codigo_secao VARCHAR,
            admissoes INTEGER, desligamentos INTEGER, saldo INTEGER,
            soma_salarios_admissao DOUBLE, qtd_salarios_admissao INTEGER,
            salario_medio_admissao DOUBLE, indice_fluxos_pareados_pct DOUBLE
        )
    """)
    conn.executemany(
        "INSERT INTO consumo.setor_mensal VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                date.fromisoformat(r["competencia"]), r["sigla_uf"], r["codigo_secao"],
                r["admissoes"], r["desligamentos"], r["saldo"],
                (r["salario_medio_admissao"] * r["qtd_salarios_admissao"])
                if r["salario_medio_admissao"] is not None and r["qtd_salarios_admissao"]
                else None,
                r["qtd_salarios_admissao"], r["salario_medio_admissao"],
                r["indice_fluxos_pareados_pct"],
            )
            for r in dados["setores"]
        ],
    )

    conn.execute("""
        CREATE TABLE consumo.geografia_mensal (
            competencia DATE, sigla_uf VARCHAR, is_capital BOOLEAN,
            admissoes INTEGER, desligamentos INTEGER, saldo INTEGER,
            soma_salarios_admissao DOUBLE, qtd_salarios_admissao INTEGER,
            salario_medio_admissao DOUBLE, indice_fluxos_pareados_pct DOUBLE
        )
    """)
    conn.executemany(
        "INSERT INTO consumo.geografia_mensal VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                date.fromisoformat(r["competencia"]), r["sigla_uf"], r["is_capital"],
                r["admissoes"], r["desligamentos"], r["saldo"],
                (r["salario_medio_admissao"] * r["qtd_salarios_admissao"])
                if r["salario_medio_admissao"] is not None and r["qtd_salarios_admissao"]
                else None,
                r["qtd_salarios_admissao"], r["salario_medio_admissao"],
                r["indice_fluxos_pareados_pct"],
            )
            for r in dados["geografia"]
        ],
    )

    conn.execute("""
        CREATE TABLE consumo.perfil_anual (
            ano INTEGER, sigla_uf VARCHAR, is_capital BOOLEAN, codigo_secao VARCHAR,
            eixo VARCHAR, codigo_categoria INTEGER, categoria VARCHAR,
            admissoes INTEGER, desligamentos INTEGER, saldo INTEGER,
            soma_salarios_admissao DOUBLE, qtd_salarios_admissao INTEGER,
            salario_medio_admissao DOUBLE, indice_fluxos_pareados_pct DOUBLE
        )
    """)
    conn.executemany(
        "INSERT INTO consumo.perfil_anual VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                r["ano"], r["sigla_uf"], r["is_capital"], r["codigo_secao"],
                r["eixo"], r["codigo_categoria"], r["categoria"],
                r["admissoes"], r["desligamentos"], r["saldo"],
                (r["salario_medio_admissao"] * r["qtd_salarios_admissao"])
                if r["salario_medio_admissao"] is not None and r["qtd_salarios_admissao"]
                else None,
                r["qtd_salarios_admissao"], r["salario_medio_admissao"],
                r["indice_fluxos_pareados_pct"],
            )
            for r in dados["perfis"]
        ],
    )

    conn.execute("CREATE TABLE consumo.calendario (competencia DATE, tem_dados BOOLEAN)")
    conn.executemany(
        "INSERT INTO consumo.calendario VALUES (?, ?)",
        [(date.fromisoformat(r["competencia"]), r["tem_dados"]) for r in dados["calendario"]],
    )


def _medir_alternativa_csv(
    conn: duckdb.DuckDBPyConnection, tmp: Path, repeticoes: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    tabelas = ("setor_mensal", "geografia_mensal", "perfil_anual", "calendario")
    pasta_csv = tmp / "csv"
    pasta_csv.mkdir(parents=True, exist_ok=True)
    caminhos = {t: pasta_csv / f"{t}.csv" for t in tabelas}

    def exportar_csv() -> None:
        for t, arq in caminhos.items():
            conn.execute(f"COPY consumo.{t} TO '{arq.as_posix()}' (FORMAT CSV, HEADER)")

    exportar_csv()  # aquecimento
    tempos_escrita: list[float] = []
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        exportar_csv()
        tempos_escrita.append((time.perf_counter() - t0) * 1000.0)

    tamanho_bruto = sum(arq.stat().st_size for arq in caminhos.values())
    tamanho_gzip = sum(len(gzip.compress(arq.read_bytes(), compresslevel=6)) for arq in caminhos.values())
    inicio, fim = conn.execute("""
        select (max(competencia) - interval '11 months')::date, max(competencia)
        from consumo.calendario where tem_dados
    """).fetchone()
    inicio_p1, fim_p1 = inicio.isoformat(), fim.isoformat()

    def ler_e_calcular_csv() -> dict[str, Any]:
        saldo_cap = saldo_int = qtd_cap = qtd_int = 0
        soma_cap = soma_int = 0.0
        with open(caminhos["geografia_mensal"], encoding="utf-8", newline="") as f:
            for row in csv.DictReader(f):
                is_cap = row["is_capital"].lower() == "true"
                s = int(row["saldo"])
                soma = float(row["soma_salarios_admissao"]) if row["soma_salarios_admissao"] else 0.0
                qtd = int(row["qtd_salarios_admissao"]) if row["qtd_salarios_admissao"] else 0
                if is_cap:
                    saldo_cap += s
                    soma_cap += soma
                    qtd_cap += qtd
                else:
                    saldo_int += s
                    soma_int += soma
                    qtd_int += qtd

        with open(caminhos["setor_mensal"], encoding="utf-8", newline="") as f:
            por_sec: dict[str, list[int]] = {}
            for row in csv.DictReader(f):
                if row["sigla_uf"] == "DF" and row["codigo_secao"] != "Z" and inicio_p1 <= row["competencia"] <= fim_p1:
                    totais = por_sec.setdefault(row["codigo_secao"], [0, 0, 0])
                    for i, metrica in enumerate(("admissoes", "desligamentos", "saldo")):
                        totais[i] += int(row[metrica])

        return {
            "saldo_capital": saldo_cap,
            "saldo_interior": saldo_int,
            "n_capital": qtd_cap,
            "n_interior": qtd_int,
            "salario_capital": soma_cap / qtd_cap if qtd_cap else None,
            "salario_interior": soma_int / qtd_int if qtd_int else None,
        }

    p3_csv = ler_e_calcular_csv()  # aquecimento
    tempos_leitura: list[float] = []
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        p3_csv = ler_e_calcular_csv()
        tempos_leitura.append((time.perf_counter() - t0) * 1000.0)

    return {
        "tamanho_bruto_bytes": tamanho_bruto,
        "tamanho_gzip_bytes": tamanho_gzip,
        "escrita": _resumo_tempos(tempos_escrita),
        "leitura_e_consulta_python": _resumo_tempos(tempos_leitura),
    }, p3_csv


def _medir_alternativa_json_js(
    dados: dict[str, Any], tmp: Path, repeticoes: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    arq_json = tmp / "metra.json"

    def escrever_json() -> bytes:
        conteudo = (json.dumps(dados, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        arq_json.write_bytes(conteudo)
        return conteudo

    conteudo_identado = escrever_json()  # aquecimento
    tempos_escrita: list[float] = []
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        escrever_json()
        tempos_escrita.append((time.perf_counter() - t0) * 1000.0)

    conteudo_compacto = json.dumps(dados, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")
    gzip_identado = len(gzip.compress(conteudo_identado, compresslevel=6))
    gzip_compacto = len(gzip.compress(conteudo_compacto, compresslevel=6))

    node = shutil.which("node")
    if not node:
        raise RuntimeError("Instale o Node.js para medir o agente JavaScript.")
    script_node = f"""
const fs = require("node:fs");
const agente = require({json.dumps(str(AGENTE_JS.resolve()))});
const caminho = {json.dumps(str(arq_json.resolve()))};
const perguntas = [
  ["p1_setores_df", "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?"],
  ["p2_sazonalidade", "Existe sazonalidade evidente nas contratações e demissões?"],
  ["p3_capitais_interior", "Qual é a diferença no saldo líquido e no salário médio entre as capitais e o interior?"],
  ["p4_fluxos_salarios", "Os setores com maior rotatividade praticam salários médios mais baixos?"],
  ["p5_perfil_remuneracao", "Como a escolaridade impacta o salário médio de admissão?"]
];
function rodarUmaVez() {{
  const t0 = performance.now();
  const dados = JSON.parse(fs.readFileSync(caminho, "utf8"));
  let p3;
  for (const [intencao, pergunta] of perguntas) {{
    const resposta = agente.responderPergunta(dados, pergunta);
    if (!resposta.suportada || resposta.intencao !== intencao) {{
      throw new Error(`Resposta inesperada para ${{intencao}}`);
    }}
    if (intencao === "p3_capitais_interior") p3 = resposta.dadosAnalise.consolidado;
  }}
  return {{ ms: performance.now() - t0, p3 }};
}}
rodarUmaVez();
const tempos = [];
let ultimo = null;
for (let i = 0; i < {repeticoes}; i++) {{
  const r = rodarUmaVez();
  tempos.push(r.ms);
  ultimo = r.p3;
}}
console.log(JSON.stringify({{ versaoNode: process.version, tempos, p3: ultimo }}));
"""
    proc = subprocess.run([node, "-e", script_node], stdout=subprocess.PIPE, text=True, check=True)
    saida_js = json.loads(proc.stdout)
    p3_js = {
        chave: saida_js["p3"][chave]
        for chave in ("saldo_capital", "saldo_interior", "n_capital", "n_interior", "salario_capital", "salario_interior")
    }

    return {
        "tamanho_bruto_bytes": len(conteudo_identado),
        "tamanho_gzip_bytes": gzip_identado,
        "tamanho_compacto_bytes": len(conteudo_compacto),
        "tamanho_compacto_gzip_bytes": gzip_compacto,
        "escrita": _resumo_tempos(tempos_escrita),
        "motor_execucao": f"Node.js {saida_js['versaoNode']} (leitura local, V8 JSON.parse e agente JS P1-P5)",
        "leitura_parse_e_p1_a_p5": _resumo_tempos(saida_js["tempos"]),
    }, p3_js


def _medir_alternativa_duckdb_bi(
    conn: duckdb.DuckDBPyConnection, repeticoes: int
) -> tuple[dict[str, Any], dict[str, Any]]:
    sql_p3 = """
        select
            sum(saldo) filter (where is_capital) as saldo_capital,
            sum(saldo) filter (where not is_capital) as saldo_interior,
            sum(qtd_salarios_admissao) filter (where is_capital) as n_capital,
            sum(qtd_salarios_admissao) filter (where not is_capital) as n_interior,
            sum(soma_salarios_admissao) filter (where is_capital)
                / nullif(sum(qtd_salarios_admissao) filter (where is_capital), 0) as salario_capital,
            sum(soma_salarios_admissao) filter (where not is_capital)
                / nullif(sum(qtd_salarios_admissao) filter (where not is_capital), 0) as salario_interior
        from consumo.geografia_mensal
    """
    sql_p1 = """
        with janela as (select (max(competencia) - interval '11 months')::date as inicio, max(competencia) as fim from consumo.calendario where tem_dados)
        select codigo_secao, sum(admissoes), sum(desligamentos), sum(saldo)
        from consumo.setor_mensal, janela
        where sigla_uf = 'DF' and codigo_secao <> 'Z' and competencia between inicio and fim
        group by codigo_secao
        order by 2 desc
    """

    def rodar() -> dict[str, Any]:
        row = conn.execute(sql_p3).fetchone()
        conn.execute(sql_p1).fetchall()
        return {
            "saldo_capital": int(row[0]),
            "saldo_interior": int(row[1]),
            "n_capital": int(row[2]),
            "n_interior": int(row[3]),
            "salario_capital": float(row[4]),
            "salario_interior": float(row[5]),
        }

    p3_sql = rodar()  # aquecimento
    tempos: list[float] = []
    for _ in range(repeticoes):
        t0 = time.perf_counter()
        p3_sql = rodar()
        tempos.append((time.perf_counter() - t0) * 1000.0)

    return {
        "consulta_sql_p1_e_p3_duckdb": _resumo_tempos(tempos),
        "restricoes_metabase_documentadas": (
            "Não sobe um servidor Metabase completo sem infraestrutura externa: exige JVM + banco de metadados "
            "(~1 a 2 GB de RAM em repouso), driver comunitário adicional para DuckDB e hospedagem pública paga ou túnel para terceiros."
        ),
    }, p3_sql


def _paridade_p3(a: dict[str, Any], b: dict[str, Any], c: dict[str, Any]) -> bool:
    for chave in ("saldo_capital", "saldo_interior", "n_capital", "n_interior"):
        if not (a[chave] == b[chave] == c[chave]):
            return False
    for chave in ("salario_capital", "salario_interior"):
        salarios = (a[chave], b[chave], c[chave])
        if all(salario is None for salario in salarios):
            continue
        if any(salario is None for salario in salarios) or max(salarios) - min(salarios) > TOLERANCIA_SALARIAL_P3:
            return False
    return True


def avaliar(fonte: Path, repeticoes: int = 7, threads: int = 1) -> dict[str, Any]:
    bruto = fonte.read_bytes().replace(b"\r\n", b"\n")
    dados = json.loads(bruto.decode("utf-8"))
    if dados.get("versao_schema") != 1:
        raise ValueError("Esperado snapshot JSON v1 em docs/assets/dados/metra.json.")

    with tempfile.TemporaryDirectory(prefix="metra_disp_") as tmp_str:
        tmp = Path(tmp_str)
        with duckdb.connect(str(tmp / "banco_consumo_bench.duckdb"), config={"threads": threads}) as conn:
            conn.begin()
            _popular_duckdb_consumo(dados, conn)
            conn.commit()
            alt_a, p3_a = _medir_alternativa_csv(conn, tmp, repeticoes)
            alt_b, p3_b = _medir_alternativa_json_js(dados, tmp, repeticoes)
            alt_c, p3_c = _medir_alternativa_duckdb_bi(conn, repeticoes)

    paridade = _paridade_p3(p3_a, p3_b, p3_c)
    if not paridade:
        raise AssertionError(f"Divergência numérica em P3: CSV={p3_a}, JSON={p3_b}, DuckDB={p3_c}")

    return {
        "executado_em_utc": datetime.now(timezone.utc).isoformat(),
        "ambiente": {
            "python": platform.python_version(),
            "duckdb": duckdb.__version__,
            "sistema": platform.platform(),
            "threads_duckdb": threads,
            "aquecimento_descartado": 1,
            "repeticoes_validas": repeticoes,
        },
        "fonte": {
            "arquivo": (fonte.relative_to(RAIZ) if fonte.is_relative_to(RAIZ) else fonte).as_posix(),
            "sha256_lf": hashlib.sha256(bruto).hexdigest(),
            "registros": {k: len(dados[k]) for k in ("setores", "geografia", "perfis", "calendario")},
            "total_registros": sum(len(dados[k]) for k in ("setores", "geografia", "perfis", "calendario")),
        },
        "alternativas": {
            "A_csv_agendado": alt_a,
            "B_json_pages_e_agente_js": alt_b,
            "C_duckdb_sql_referencia_bi": alt_c,
        },
        "paridade_p3_identica": paridade,
        "tolerancia_absoluta_salario_p3": TOLERANCIA_SALARIAL_P3,
        "p3_consolidado_observado": {k: (round(v, 2) if isinstance(v, float) else v) for k, v in p3_b.items()},
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fonte", type=Path, default=FONTE_PADRAO)
    parser.add_argument("--repeticoes", type=int, default=7)
    parser.add_argument("--threads", type=int, default=1)
    parser.add_argument("--saida", type=Path, default=SAIDA_PADRAO)
    args = parser.parse_args()

    resultado = avaliar(args.fonte.resolve(), repeticoes=args.repeticoes, threads=args.threads)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(resultado, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(resultado["alternativas"], ensure_ascii=False, indent=2))
    print(f"Evidência gravada em {args.saida} (paridade_p3_identica={resultado['paridade_p3_identica']})")


if __name__ == "__main__":
    main()
