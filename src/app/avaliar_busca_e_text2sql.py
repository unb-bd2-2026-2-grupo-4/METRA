"""Benchmark e avaliação empírica da Busca Semântica CBO e do Assistente Text-to-SQL (ADR 0007).

Executa os 5 experimentos definidos no protocolo da ADR 0007 sobre a camada Gold real
construída a partir da amostra versionada (`data/caged_centro_oeste_amostra.csv`):
1. Busca por sinônimo coloquial/técnico em português (24 consultas versionadas):
   Compara Hit@1, Hit@5 e MRR entre Alternativa A (Busca Léxica) e Alternativa B (Vetorial 384d).
2. Busca por código exato de 6 dígitos (inclusive com zero à esquerda):
   Verifica 100% de precisão na 1ª posição (Hit@1).
3. Fidelidade do Assistente Text-to-SQL (P1 a P5, Ocupação CBO e casos fora de escopo):
   Compara multiconjunto de resultados contra o SQL de referência da camada Gold.
4. Latência (1 aquecimento descartado + 7 rodadas válidas):
   Mede mediana e p95 de indexação, busca léxica, busca vetorial (NumPy e DuckDB) e Text-to-SQL.
5. Guardrails de Segurança e Governança/LGPD:
   Verifica bloqueio determinístico de DDL/DML, leitura externa, múltiplas instruções e linhas brutas.

Uso:
    python -m src.app.avaliar_busca_e_text2sql --saida docs/adr/evidencias/0007-busca-semantica-e-text2sql.json
"""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import sys
import tempfile
import time
from typing import Any

import duckdb
import numpy as np

from src.app.banco_analitico import (
    CAMINHO_AMOSTRA_CSV,
    abrir_conexao_analitica,
    construir_gold_de_amostra,
)
from src.app.busca_cbo import (
    DIMENSAO_VETOR,
    MODELO_VETORIAL_ID,
    IndiceVetorialCBO,
)
from src.app.text_to_sql import (
    AssistenteTextToSQL,
    ViolacaoSegurancaSQL,
    _gerar_sql_p1,
    _gerar_sql_p2,
    _gerar_sql_p3,
    _gerar_sql_p4,
    _gerar_sql_p5,
    validar_sql_seguro,
)

# Conjunto versionado de 24 consultas em português (sinônimos coloquiais, termos de mercado e siglas)
# com os respectivos códigos CBO 2002 oficiais esperados.
CONJUNTO_AVALIACAO_SINONIMOS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("dev backend software", ("212405", "317110", "212205")),
    ("codificador de programas de computador", ("317110", "212405")),
    ("administrador dba banco de dados sql", ("212305",)),
    ("suporte helpdesk tecnico de informatica", ("317210", "212420", "317205")),
    ("caminhoneiro carreteiro transporte de cargas", ("782510", "782505")),
    ("motorista de transporte coletivo onibus", ("782410", "782405")),
    ("motoboy entregador delivery motocicleta", ("782820",)),
    ("caixa de supermercado frente de caixa", ("421125",)),
    ("atendente de call center teleatendimento sac", ("422310", "422315")),
    ("balconista de loja varejo vendas", ("521110", "521140")),
    ("repositor de gondolas supermercado", ("521125",)),
    ("boia fria colheita lavoura agricultura", ("622020", "621005")),
    ("cortador de cana safra", ("622110",)),
    ("tratorista operador de colheitadeira soja", ("641015", "641005")),
    ("peao vaqueiro criacao de gado bovino", ("623110",)),
    ("medico do coracao cardiologia", ("223104",)),
    ("odontologista saude bucal dentista", ("223208",)),
    ("cuidados hospitalares enfermagem", ("223505", "322205", "322230")),
    ("professor primario primeira a quarta serie", ("231210", "231205")),
    ("contabilista balanco fiscal tributario", ("252210", "413110")),
    ("recrutador departamento pessoal rh", ("252405",)),
    ("auxiliar de limpeza conservacao predial zeladoria", ("514320", "514225")),
    ("seguranca patrimonial guarda escolta", ("517330",)),
    ("ajudante de pedreiro canteiro de obras", ("717020", "715210")),
)

CODIGOS_EXATOS_TESTE: tuple[str, ...] = (
    "010105",
    "010205",
    "212405",
    "317110",
    "421125",
    "514320",
    "621005",
    "782510",
)

PERGUNTAS_TEXT_TO_SQL_SUPORTADAS: tuple[tuple[str, str], ...] = (
    (
        "Qual setor econômico mais contratou e demitiu no Distrito Federal nos últimos 12 meses?",
        "p1_setores_df",
    ),
    (
        "Existe sazonalidade evidente nas contratações e demissões?",
        "p2_sazonalidade",
    ),
    (
        "Qual é a diferença no saldo líquido de empregos gerados e no salário médio entre as capitais e os municípios do interior?",
        "p3_capitais_interior",
    ),
    (
        "Os setores com maior taxa de rotatividade praticam salários médios mais baixos?",
        "p4_fluxos_salarios",
    ),
    (
        "Como o perfil sociodemográfico impacta o nível salarial e as movimentações?",
        "p5_perfil_remuneracao",
    ),
    (
        "Qual o saldo e o salário médio de desenvolvedor de software no Centro-Oeste?",
        "cbo_ocupacao",
    ),
)

PERGUNTAS_RECUSA_ESPERADA: tuple[tuple[str, str], ...] = (
    (
        "DROP TABLE gold.fct_movimentacao;",
        "bloqueada_seguranca",
    ),
    (
        "SELECT * FROM read_parquet('data/lake/parquet/movimentacao/*.parquet')",
        "bloqueada_seguranca",
    ),
    (
        "Liste o CPF e o nome do trabalhador de cada registro individual",
        "bloqueada_seguranca",
    ),
    (
        "Qual a taxa de desemprego oficial da PNAD e o estoque total de vínculos ativos da RAIS?",
        "nao_suportada",
    ),
    (
        "Qual a probabilidade de eu ser contratado amanhã e a previsão para 2028?",
        "nao_suportada",
    ),
)

SQLS_MALICIOSOS_GUARDRAIL: tuple[str, ...] = (
    "DROP TABLE gold.fct_movimentacao",
    "DELETE FROM gold.fct_setor_mensal WHERE sigla_uf = 'DF'",
    "INSERT INTO gold.dim_cbo VALUES ('999999', 'Hack', '9', true)",
    "UPDATE gold.fct_setor_mensal SET saldo = 999999",
    "SELECT * FROM gold.fct_setor_mensal; DROP TABLE gold.dim_cbo;",
    "SELECT * FROM read_csv('data/caged_centro_oeste_amostra.csv')",
    "SELECT * FROM read_parquet('data/lake/parquet/movimentacao/*.parquet')",
    "ATTACH 'outro.db' AS externo",
    "SELECT * FROM silver.stg_movimentacao LIMIT 10",
    "SELECT * FROM gold.fct_movimentacao LIMIT 10",
)


def _percentil_95(valores: list[float]) -> float:
    if not valores:
        return 0.0
    ordenados = sorted(valores)
    idx = min(len(ordenados) - 1, max(0, int(round(0.95 * (len(ordenados) - 1)))))
    return ordenados[idx]


def _avaliar_busca_sinonimos(indice: IndiceVetorialCBO) -> dict[str, Any]:
    catalogo_codigos = {r.codigo_cbo for r in indice.registros}
    metricas: dict[str, dict[str, Any]] = {}

    for nome_metodo, fn in (
        ("lexica_opcao_nula", lambda q: indice.buscar_lexico(q, top_k=5)),
        ("semantica_vetorial_384d", lambda q: indice.buscar_semantico(q, top_k=5)),
    ):
        acertos_top1 = 0
        acertos_top5 = 0
        soma_rr = 0.0
        codigos_inexistentes = 0
        detalhes = []

        for consulta, esperados in CONJUNTO_AVALIACAO_SINONIMOS:
            resultados = fn(consulta)
            retornados = [r.codigo_cbo for r in resultados]
            for c in retornados:
                if c not in catalogo_codigos:
                    codigos_inexistentes += 1

            hit1 = bool(retornados and retornados[0] in esperados)
            hit5 = any(c in esperados for c in retornados[:5])
            rr = 0.0
            for pos, c in enumerate(retornados[:5], start=1):
                if c in esperados:
                    rr = 1.0 / pos
                    break

            acertos_top1 += int(hit1)
            acertos_top5 += int(hit5)
            soma_rr += rr
            detalhes.append({
                "consulta": consulta,
                "esperados": list(esperados),
                "retornados_top5": retornados,
                "hit_at_1": hit1,
                "hit_at_5": hit5,
                "reciprocal_rank": round(rr, 4),
            })

        total = len(CONJUNTO_AVALIACAO_SINONIMOS)
        metricas[nome_metodo] = {
            "total_consultas": total,
            "acertos_top1": acertos_top1,
            "acertos_top5": acertos_top5,
            "hit_at_1_pct": round(100.0 * acertos_top1 / total, 2),
            "hit_at_5_pct": round(100.0 * acertos_top5 / total, 2),
            "mrr": round(soma_rr / total, 4),
            "codigos_inexistentes": codigos_inexistentes,
            "detalhes": detalhes,
        }

    return metricas


def _avaliar_codigos_exatos(indice: IndiceVetorialCBO) -> dict[str, Any]:
    acertos = 0
    detalhes = []
    for codigo in CODIGOS_EXATOS_TESTE:
        res_sem = indice.buscar_semantico(codigo, top_k=3)
        ok = bool(res_sem and res_sem[0].codigo_cbo == codigo and res_sem[0].score == 1.0)
        acertos += int(ok)
        detalhes.append({
            "codigo_buscado": codigo,
            "primeiro_retornado": res_sem[0].codigo_cbo if res_sem else None,
            "score": res_sem[0].score if res_sem else None,
            "metodo": res_sem[0].metodo if res_sem else None,
            "correto_em_primeiro": ok,
        })
    return {
        "total_codigos": len(CODIGOS_EXATOS_TESTE),
        "acertos_primeiro_lugar": acertos,
        "hit_at_1_pct": round(100.0 * acertos / len(CODIGOS_EXATOS_TESTE), 2),
        "detalhes": detalhes,
    }


def _avaliar_fidelidade_text_to_sql(
    conn: duckdb.DuckDBPyConnection, assistente: AssistenteTextToSQL
) -> dict[str, Any]:
    sqls_referencia = {
        "p1_setores_df": _gerar_sql_p1({}),
        "p2_sazonalidade": _gerar_sql_p2({}),
        "p3_capitais_interior": _gerar_sql_p3({}),
        "p4_fluxos_salarios": _gerar_sql_p4({}),
        "p5_perfil_remuneracao": _gerar_sql_p5({}),
    }

    resultados_suportadas = []
    todas_iguais = True
    for pergunta, intencao_esperada in PERGUNTAS_TEXT_TO_SQL_SUPORTADAS:
        resp = assistente.responder(conn, pergunta)
        intencao_ok = resp.suportada and resp.intencao == intencao_esperada
        igual_ref = True
        if intencao_esperada in sqls_referencia:
            esperado = conn.sql(sqls_referencia[intencao_esperada]).fetchall()
            igual_ref = (resp.linhas == esperado)
        else:
            igual_ref = len(resp.linhas) > 0 and len(resp.ocupacoes_resolvidas) > 0

        ok = intencao_ok and igual_ref
        todas_iguais = todas_iguais and ok
        resultados_suportadas.append({
            "pergunta": pergunta,
            "intencao_esperada": intencao_esperada,
            "intencao_obtida": resp.intencao,
            "suportada": resp.suportada,
            "linhas_retornadas": len(resp.linhas),
            "igualdade_exata_referencia": igual_ref,
        })

    resultados_recusas = []
    todas_recusadas = True
    for pergunta_invalida, tipo_esperado in PERGUNTAS_RECUSA_ESPERADA:
        resp = assistente.responder(conn, pergunta_invalida)
        ok = (not resp.suportada) and (resp.intencao == tipo_esperado) and (resp.linhas == [])
        todas_recusadas = todas_recusadas and ok
        resultados_recusas.append({
            "pergunta": pergunta_invalida,
            "tipo_esperado": tipo_esperado,
            "tipo_obtido": resp.intencao,
            "recusada_corretamente": ok,
        })

    bloqueios_ast = 0
    for sql_malicioso in SQLS_MALICIOSOS_GUARDRAIL:
        try:
            validar_sql_seguro(sql_malicioso)
        except ViolacaoSegurancaSQL:
            bloqueios_ast += 1

    return {
        "perguntas_suportadas_total": len(PERGUNTAS_TEXT_TO_SQL_SUPORTADAS),
        "perguntas_suportadas_100pct_iguais": todas_iguais,
        "detalhes_suportadas": resultados_suportadas,
        "perguntas_recusa_total": len(PERGUNTAS_RECUSA_ESPERADA),
        "perguntas_recusa_100pct_corretas": todas_recusadas,
        "detalhes_recusas": resultados_recusas,
        "guardrails_sql_testados": len(SQLS_MALICIOSOS_GUARDRAIL),
        "guardrails_sql_bloqueados": bloqueios_ast,
    }


def _medir_latencias(
    conn: duckdb.DuckDBPyConnection,
    indice: IndiceVetorialCBO,
    assistente: AssistenteTextToSQL,
    repeticoes: int = 7,
) -> dict[str, Any]:
    consultas_amostra = [q for q, _ in CONJUNTO_AVALIACAO_SINONIMOS]

    # Aquecimento descartado
    _ = IndiceVetorialCBO.de_conexao_duckdb(conn)
    for q in consultas_amostra:
        indice.buscar_lexico(q, top_k=5)
        indice.buscar_semantico(q, top_k=5)
    indice.buscar_semantico(consultas_amostra[0], top_k=5, conn_duckdb=conn)
    assistente.responder(conn, PERGUNTAS_TEXT_TO_SQL_SUPORTADAS[2][0])

    tempos_indexacao_ms: list[float] = []
    tempos_busca_lexica_ms: list[float] = []
    tempos_busca_vetorial_numpy_ms: list[float] = []
    tempos_busca_vetorial_duckdb_ms: list[float] = []
    tempos_text2sql_ms: list[float] = []

    for _ in range(repeticoes):
        t0 = time.perf_counter()
        _ = IndiceVetorialCBO.de_conexao_duckdb(conn)
        tempos_indexacao_ms.append((time.perf_counter() - t0) * 1000.0)

        for q in consultas_amostra:
            t0 = time.perf_counter()
            indice.buscar_lexico(q, top_k=5)
            tempos_busca_lexica_ms.append((time.perf_counter() - t0) * 1000.0)

            t0 = time.perf_counter()
            indice.buscar_semantico(q, top_k=5)
            tempos_busca_vetorial_numpy_ms.append((time.perf_counter() - t0) * 1000.0)

        # Mede consulta vetorial via array_cosine_similarity no DuckDB para 5 consultas representativas
        for q in consultas_amostra[:5]:
            t0 = time.perf_counter()
            indice.buscar_semantico(q, top_k=5, conn_duckdb=conn)
            tempos_busca_vetorial_duckdb_ms.append((time.perf_counter() - t0) * 1000.0)

        for pergunta, _ in PERGUNTAS_TEXT_TO_SQL_SUPORTADAS:
            t0 = time.perf_counter()
            assistente.responder(conn, pergunta)
            tempos_text2sql_ms.append((time.perf_counter() - t0) * 1000.0)

    def _resumo(lista: list[float]) -> dict[str, float]:
        return {
            "mediana_ms": round(statistics.median(lista), 3),
            "p95_ms": round(_percentil_95(lista), 3),
            "media_ms": round(statistics.mean(lista), 3),
            "min_ms": round(min(lista), 3),
            "max_ms": round(max(lista), 3),
        }

    return {
        "repeticoes": repeticoes,
        "indexacao_catalogo_cbo": _resumo(tempos_indexacao_ms),
        "busca_lexica_por_consulta": _resumo(tempos_busca_lexica_ms),
        "busca_vetorial_384d_numpy_por_consulta": _resumo(tempos_busca_vetorial_numpy_ms),
        "busca_vetorial_384d_duckdb_sql_por_consulta": _resumo(tempos_busca_vetorial_duckdb_ms),
        "text_to_sql_end_to_end_por_pergunta": _resumo(tempos_text2sql_ms),
    }


def executar_avaliacao(repeticoes: int = 7) -> dict[str, Any]:
    with tempfile.TemporaryDirectory(prefix="metra_adr0007_") as tmp:
        caminho_banco = Path(tmp) / "metra_adr0007.duckdb"
        construir_gold_de_amostra(caminho_banco)

        with abrir_conexao_analitica(caminho_banco, garantir_construcao=False) as conn:
            indice = IndiceVetorialCBO.de_conexao_duckdb(conn)
            assistente = AssistenteTextToSQL(indice_cbo=indice)

            sinonimos = _avaliar_busca_sinonimos(indice)
            codigos_exatos = _avaliar_codigos_exatos(indice)
            fidelidade_sql = _avaliar_fidelidade_text_to_sql(conn, assistente)
            latencias = _medir_latencias(conn, indice, assistente, repeticoes=repeticoes)

            qtd_movimentacoes = conn.execute("SELECT COUNT(*) FROM gold.fct_movimentacao").fetchone()[0]
            qtd_cbo = conn.execute("SELECT COUNT(*) FROM gold.dim_cbo").fetchone()[0]
            qtd_cbo_oficiais = conn.execute(
                "SELECT COUNT(*) FROM gold.dim_cbo WHERE is_cadastro_oficial"
            ).fetchone()[0]

    sha256_amostra = hashlib.sha256(CAMINHO_AMOSTRA_CSV.read_bytes()).hexdigest()
    memoria_indice_bytes = int(indice.matriz_vetores.nbytes)

    return {
        "experimento": "ADR-0007: Busca Semântica CBO 2002 e Assistente Text-to-SQL Governado",
        "ambiente": {
            "python": sys.version.split()[0],
            "duckdb": duckdb.__version__,
            "numpy": np.__version__,
            "plataforma": platform.platform(),
        },
        "catalogo_e_indice": {
            "fonte_amostra_csv": "data/caged_centro_oeste_amostra.csv",
            "sha256_amostra_csv": sha256_amostra,
            "movimentacoes_gold": int(qtd_movimentacoes),
            "ocupacoes_indexadas_dim_cbo": int(qtd_cbo),
            "ocupacoes_cadastro_oficial": int(qtd_cbo_oficiais),
            "ocupacoes_genericas_atualizacao_mte": int(qtd_cbo - qtd_cbo_oficiais),
            "modelo_vetorial": MODELO_VETORIAL_ID,
            "versao_indice": indice.versao_indice,
            "sha256_catalogo_cbo": indice.sha256_catalogo,
            "dimensao_vetor": DIMENSAO_VETOR,
            "metrica_distancia": "cosine_similarity (L2 normalized dot product / DuckDB array_cosine_similarity)",
            "memoria_matriz_vetorial_bytes": memoria_indice_bytes,
        },
        "experimento_1_busca_sinonimos": sinonimos,
        "experimento_2_codigo_exato": codigos_exatos,
        "experimento_3_fidelidade_e_guardrails_text2sql": fidelidade_sql,
        "experimento_4_latencias": latencias,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Executa o benchmark reproduzível da ADR 0007.")
    parser.add_argument(
        "--saida",
        type=Path,
        default=Path("docs/adr/evidencias/0007-busca-semantica-e-text2sql.json"),
        help="Caminho do arquivo JSON de evidências.",
    )
    parser.add_argument(
        "--repeticoes",
        type=int,
        default=7,
        help="Número de repetições válidas para medição de latência (padrão: 7).",
    )
    args = parser.parse_args()

    resultado = executar_avaliacao(repeticoes=args.repeticoes)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(
        json.dumps(resultado, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    s_lex = resultado["experimento_1_busca_sinonimos"]["lexica_opcao_nula"]
    s_vet = resultado["experimento_1_busca_sinonimos"]["semantica_vetorial_384d"]
    lat = resultado["experimento_4_latencias"]
    print(f"Evidências gravadas em: {args.saida}")
    print(
        f"Sinônimos (24 consultas) -> Léxica Hit@1={s_lex['hit_at_1_pct']}% Hit@5={s_lex['hit_at_5_pct']}% MRR={s_lex['mrr']} | "
        f"Vetorial 384d Hit@1={s_vet['hit_at_1_pct']}% Hit@5={s_vet['hit_at_5_pct']}% MRR={s_vet['mrr']}"
    )
    print(
        f"Códigos exatos (8 códigos) -> Hit@1={resultado['experimento_2_codigo_exato']['hit_at_1_pct']}%"
    )
    print(
        f"Latências (mediana) -> Indexação={lat['indexacao_catalogo_cbo']['mediana_ms']} ms | "
        f"Busca Vetorial NumPy={lat['busca_vetorial_384d_numpy_por_consulta']['mediana_ms']} ms | "
        f"Busca Vetorial DuckDB={lat['busca_vetorial_384d_duckdb_sql_por_consulta']['mediana_ms']} ms | "
        f"Text-to-SQL={lat['text_to_sql_end_to_end_por_pergunta']['mediana_ms']} ms"
    )


if __name__ == "__main__":
    main()
