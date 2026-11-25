"""Gera o catálogo estático do `dbt docs` para o GitHub Pages e extrai a linhagem ponta a ponta (E4).

Constrói uma instância DuckDB temporária com todas as camadas do projeto (`silver`, `gold`,
`snapshots` e `consumo`), executa `dbt docs generate --static` para produzir o portal
interativo `docs/assets/dbt-docs/index.html` (com `manifest.json` e `catalog.json` embutidos)
e grava o resumo auditável do catálogo e da linhagem da fonte até o painel e o ETL reverso
em `docs/assets/dbt-docs/linhagem.json`.

Uso:
    python -m src.catalogo.gerar_dbt_docs
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from typing import Any

import duckdb

RAIZ = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = RAIZ / "dbt_metra"
DESTINO_PADRAO_DIR = RAIZ / "docs" / "assets" / "dbt-docs"

# Mapeamento formal da linhagem física de ponta a ponta (das fontes externas até o consumo final)
LINHAGEM_CAMADAS_PONTA_A_PONTA: list[dict[str, Any]] = [
    {
        "ordem": 1,
        "camada": "Fontes Públicas Oficiais",
        "tecnologia": "CSV / APIs REST HTTPS",
        "objetos": [
            "Novo CAGED / MTE (data/caged_centro_oeste_amostra.csv ou CSVs brutos 2023–2026)",
            "API IBGE Localidades (/api/v1/localidades/municipios)",
            "API IBGE CNAE 2.0 (/api/v2/cnae/subclasses)",
            "Catálogo Oficial CBO 2002 (MTE)",
        ],
        "responsavel_codigo": "src/ingestao/carga_bronze.py, carga_ibge.py, carga_cbo.py",
    },
    {
        "ordem": 2,
        "camada": "Camada Bronze (Staging Bruto e Linhagem de Lote)",
        "tecnologia": "PostgreSQL 16 (schema bronze)",
        "objetos": [
            "bronze.arquivos_ingeridos",
            "bronze.caged_movimentacao",
            "bronze.ibge_municipio",
            "bronze.ibge_cnae_subclasse",
            "bronze.cbo_ocupacao",
        ],
        "responsavel_codigo": "src/db/migracoes/0001_camada_bronze.sql, 0002_camada_bronze_referencias.sql",
    },
    {
        "ordem": 3,
        "camada": "Origem Transacional OLTP (3FN Insert-Only e CDC)",
        "tecnologia": "PostgreSQL 16 (schema oltp + WAL lógico)",
        "objetos": [
            "oltp.movimentacao",
            "oltp.municipio",
            "oltp.cbo_2002",
            "oltp.cnae_secao",
            "oltp.cnae_subclasse",
            "oltp.cdc_probe (slot lógico metra_cdc_slot -> data/cdc/eventos.log -> replay.sqlite3)",
        ],
        "responsavel_codigo": "src/ingestao/carga_oltp.py, src/cdc/01..04",
    },
    {
        "ordem": 4,
        "camada": "Armazenamento Colunar Aberto (Lake Parquet e Delta Lake)",
        "tecnologia": "Apache Parquet (Snappy) + Delta Lake (delta-rs)",
        "objetos": [
            "source.metra.lake.movimentacao (data/lake/parquet/movimentacao/ano=AAAA/*.parquet)",
            "source.metra.lake.municipio (data/lake/parquet/municipio/*.parquet)",
            "source.metra.lake.cbo_2002 (data/lake/parquet/cbo_2002/*.parquet)",
            "source.metra.lake.cnae_subclasse (data/lake/parquet/cnae_subclasse/*.parquet)",
            "source.metra.lake.cnae_secao (data/lake/parquet/cnae_secao/*.parquet)",
            "data/lake/delta/movimentacao/ (_delta_log/)",
        ],
        "responsavel_codigo": "src/extracao/exportar_parquet.py, src/extracao/materializar_delta.py",
    },
    {
        "ordem": 5,
        "camada": "Camada Silver (Padronização, Tipagem e Guardas de Qualidade)",
        "tecnologia": "DuckDB + dbt-duckdb (schema silver em data/metra_analitico.duckdb)",
        "objetos": [
            "silver.stg_movimentacao",
            "silver.stg_municipio",
            "silver.stg_cbo",
            "silver.stg_cnae",
        ],
        "responsavel_codigo": "dbt_metra/models/staging/",
    },
    {
        "ordem": 6,
        "camada": "Camada Gold, Histórico SCD2 e Camada Semântica Única",
        "tecnologia": "DuckDB + dbt-duckdb (schemas snapshots e gold + semantic_models/metrics)",
        "objetos": [
            "snapshots.snp_cbo -> gold.dim_cbo_historico (SCD Tipo 2)",
            "gold.dim_competencia",
            "gold.dim_municipio",
            "gold.dim_cbo",
            "gold.dim_cnae",
            "gold.dim_perfil_demografico",
            "gold.fct_movimentacao",
            "gold.fct_setor_mensal",
            "gold.fct_geografia_mensal",
            "gold.fct_perfil_mensal",
            "gold.metricflow_time_spine",
            "dbt_metra/models/semantic/metricas.yml (7 métricas compiladas por dbt e Python)",
        ],
        "responsavel_codigo": "dbt_metra/models/marts/, dbt_metra/snapshots/, dbt_metra/models/semantic/, src/metricas/camada_semantica.py",
    },
    {
        "ordem": 7,
        "camada": "Camada de Controle de Acesso e Supressão LGPD (k >= 5)",
        "tecnologia": "Views dbt (schema consumo) + Base DuckDB Isolada (data/metra_consumo.duckdb)",
        "objetos": [
            "consumo.setor_mensal",
            "consumo.geografia_mensal",
            "consumo.perfil_anual",
            "consumo.calendario",
            "data/metra_consumo.duckdb (somente leitura, enable_external_access = false)",
        ],
        "responsavel_codigo": "dbt_metra/models/consumo/, src/acesso/base_consumo.py",
    },
    {
        "ordem": 8,
        "camada": "Consumo Final: Painel Streamlit, Agente Text-to-SQL/CBO e ETL Reverso JSON",
        "tecnologia": "Streamlit (Docker porta 8501) + Índice Vetorial 384d + JSON estático no GitHub Pages",
        "objetos": [
            "exposure.metra.painel_streamlit (src/app/dashboard.py)",
            "exposure.metra.assistente_text_to_sql_e_busca_cbo (src/app/busca_cbo.py, src/app/text_to_sql.py)",
            "exposure.metra.base_consumo_isolada (src/acesso/base_consumo.py)",
            "exposure.metra.etl_reverso_json_publico (src/consumo/exportar_json.py -> docs/assets/dados/metra.json -> docs/consumo-json.md)",
        ],
        "responsavel_codigo": "src/app/, src/consumo/exportar_json.py, docs/consumo-json.md",
    },
]


def _criar_lake_sintetico_para_catalogo(destino: Path) -> None:
    """Cria um lake Parquet mínimo para materializar todos os schemas no DuckDB e popular o catalog.json."""
    with duckdb.connect() as conn:
        conn.execute("""
            CREATE TABLE municipio AS SELECT * FROM (VALUES
                ('5300108', 'Brasília', 'DF', 'Distrito Federal', 'Centro-Oeste', true),
                ('5200050', 'Abadia de Goiás', 'GO', 'Goiás', 'Centro-Oeste', false),
                ('9999999', 'MUNICIPIO NAO IDENTIFICADO', 'NI', 'Nao Identificado', 'Centro-Oeste', false)
            ) t(id_municipio, nome, sigla_uf, nome_uf, regiao, is_capital);
            CREATE TABLE cbo_2002 AS SELECT * FROM (VALUES
                ('010105', 'Oficial General'),
                ('212405', 'Analista de Desenvolvimento de Sistemas')
            ) t(codigo, titulo);
            CREATE TABLE cnae_secao AS SELECT * FROM (VALUES
                ('A', 'AGRICULTURA, PECUARIA E SERVICOS RELACIONADOS'),
                ('J', 'INFORMACAO E COMUNICACAO'),
                ('Z', 'NAO IDENTIFICADA')
            ) t(codigo, descricao);
            CREATE TABLE cnae_subclasse AS SELECT * FROM (VALUES
                ('0111301', 'Cultivo de arroz', 'A'),
                ('6201501', 'Desenvolvimento de programas de computador sob encomenda', 'J'),
                ('9999999', 'ATIVIDADES ECONOMICAS NAO IDENTIFICADAS', 'Z')
            ) t(codigo, descricao, codigo_secao);
            CREATE TABLE movimentacao AS
            SELECT i::bigint AS id_movimentacao,
                   2025::integer AS ano,
                   ((i - 1) // 4 + 1)::integer AS mes,
                   CASE WHEN i % 4 = 0 THEN '9999999'
                        WHEN i % 2 = 0 THEN '5200050' ELSE '5300108' END AS id_municipio,
                   CASE WHEN i % 4 = 0 THEN '9999999' ELSE '6201501' END AS cnae_2_subclasse,
                   '212405' AS cbo_2002,
                   CASE WHEN i % 2 = 0 THEN 3 ELSE 1 END::integer AS sexo,
                   CASE WHEN i % 2 = 0 THEN 3 ELSE 1 END::integer AS raca_cor,
                   30::integer AS idade,
                   9::integer AS grau_instrucao,
                   20::integer AS tipo_movimentacao,
                   CASE WHEN i % 3 = 0 THEN -1 ELSE 1 END::integer AS saldo_movimentacao,
                   3500.00::decimal(16,2) AS salario_mensal,
                   40.00::decimal(5,2) AS horas_contratuais,
                   1::bigint AS id_ingestao,
                   (i + 1)::bigint AS numero_linha,
                   TIMESTAMPTZ '2026-11-01 00:00:00+00' AS registrado_em
            FROM range(1, 13) t(i);
        """)
        for tabela in ("municipio", "cbo_2002", "cnae_secao", "cnae_subclasse", "movimentacao"):
            pasta = destino / tabela
            pasta.mkdir(parents=True, exist_ok=True)
            conn.execute(f"COPY {tabela} TO ? (FORMAT PARQUET)", [str(pasta / "dados.parquet")])


def _extrair_resumo_catalogo(manifest: dict[str, Any], catalog: dict[str, Any]) -> dict[str, Any]:
    """Extrai o catálogo estruturado e as arestas de linhagem a partir do manifest.json e catalog.json."""
    catalog_nodes = catalog.get("nodes", {})
    catalog_sources = catalog.get("sources", {})

    sources_lista = []
    for uid, src in sorted(manifest.get("sources", {}).items()):
        cat_cols = catalog_sources.get(uid, {}).get("columns", {})
        colunas = []
        for col_name, col_meta in src.get("columns", {}).items():
            colunas.append({
                "nome": col_name,
                "tipo": cat_cols.get(col_name, {}).get("type") or col_meta.get("data_type") or "VARCHAR",
                "descricao": col_meta.get("description", ""),
            })
        sources_lista.append({
            "unique_id": uid,
            "nome": f"{src['source_name']}.{src['name']}",
            "descricao": (src.get("description") or "").strip(),
            "colunas_documentadas": len(colunas),
            "colunas": colunas,
        })

    modelos_lista = []
    testes_por_no: dict[str, int] = {}
    for uid, node in manifest.get("nodes", {}).items():
        if node.get("resource_type") == "test":
            for dep in node.get("depends_on", {}).get("nodes", []):
                testes_por_no[dep] = testes_por_no.get(dep, 0) + 1

    for uid, node in sorted(manifest.get("nodes", {}).items()):
        rtype = node.get("resource_type")
        if rtype not in ("model", "snapshot"):
            continue
        cat_cols = catalog_nodes.get(uid, {}).get("columns", {})
        colunas_manifest = node.get("columns", {})
        nomes_colunas = list(colunas_manifest.keys()) or list(cat_cols.keys())
        colunas = []
        for col_name in nomes_colunas:
            c_meta = colunas_manifest.get(col_name, {})
            c_cat = cat_cols.get(col_name, {})
            colunas.append({
                "nome": col_name,
                "tipo": c_cat.get("type") or c_meta.get("data_type") or "DESCONHECIDO",
                "descricao": (c_meta.get("description") or "").strip(),
            })
        modelos_lista.append({
            "unique_id": uid,
            "nome": node["name"],
            "schema": node.get("schema", ""),
            "materializacao": node.get("config", {}).get("materialized", rtype),
            "descricao": (node.get("description") or "").strip(),
            "depende_de": sorted(node.get("depends_on", {}).get("nodes", [])),
            "quantidade_colunas": len(colunas),
            "quantidade_testes_dbt": testes_por_no.get(uid, 0),
            "colunas": colunas,
        })

    metricas_lista = []
    for uid, met in sorted(manifest.get("metrics", {}).items()):
        metricas_lista.append({
            "unique_id": uid,
            "nome": met["name"],
            "label": met.get("label", ""),
            "tipo": met.get("type", ""),
            "descricao": (met.get("description") or "").strip(),
            "depende_de": sorted(met.get("depends_on", {}).get("nodes", [])),
        })

    analises_lista = []
    for uid, ana in sorted(manifest.get("nodes", {}).items()):
        if ana.get("resource_type") != "analysis":
            continue
        analises_lista.append({
            "unique_id": uid,
            "nome": ana["name"],
            "caminho": ana.get("original_file_path", ""),
            "depende_de": sorted(ana.get("depends_on", {}).get("nodes", [])),
        })

    exposures_lista = []
    for uid, exp in sorted(manifest.get("exposures", {}).items()):
        exposures_lista.append({
            "unique_id": uid,
            "nome": exp["name"],
            "label": exp.get("label", ""),
            "tipo": exp.get("type", ""),
            "url": exp.get("url", ""),
            "descricao": (exp.get("description") or "").strip(),
            "depende_de": sorted(exp.get("depends_on", {}).get("nodes", [])),
        })

    return {
        "projeto": "metra",
        "versao_dbt": manifest.get("metadata", {}).get("dbt_version", "1.12.6"),
        "resumo_quantitativo": {
            "fontes_parquet": len(sources_lista),
            "modelos_e_snapshots": len(modelos_lista),
            "metricas_camada_semantica": len(metricas_lista),
            "analises_p1_a_p5": len(analises_lista),
            "exposures_consumo_final": len(exposures_lista),
            "testes_declarativos_dbt": sum(
                1 for n in manifest.get("nodes", {}).values() if n.get("resource_type") == "test"
            ),
        },
        "linhagem_camadas_ponta_a_ponta": LINHAGEM_CAMADAS_PONTA_A_PONTA,
        "fontes": sources_lista,
        "modelos": modelos_lista,
        "metricas": metricas_lista,
        "analises": analises_lista,
        "exposures": exposures_lista,
    }


def gerar_dbt_docs(destino_dir: Path | None = None) -> dict[str, Any]:
    """Executa o build em ambiente temporário e gera `index.html` (dbt docs) e `linhagem.json`."""
    destino = Path(destino_dir or DESTINO_PADRAO_DIR).resolve()
    destino.mkdir(parents=True, exist_ok=True)

    executavel_dbt = Path(sys.executable).parent / ("dbt.exe" if os.name == "nt" else "dbt")

    with tempfile.TemporaryDirectory(prefix="metra_dbt_docs_") as tmp:
        base = Path(tmp)
        projeto_tmp = base / "dbt_metra"
        shutil.copytree(
            DBT_PROJECT_DIR,
            projeto_tmp,
            ignore=shutil.ignore_patterns("target", "logs", "dbt_packages", ".user.yml"),
        )
        lake_tmp = base / "parquet"
        _criar_lake_sintetico_para_catalogo(lake_tmp)
        banco_tmp = base / "metra_analitico.duckdb"

        env = dict(
            os.environ,
            METRA_LAKE_PARQUET=str(lake_tmp),
            METRA_DUCKDB=str(banco_tmp),
            DBT_SEND_ANONYMOUS_USAGE_STATS="false",
            DBT_USE_COLORS="false",
        )

        # 1. Materializa modelos e snapshots no DuckDB temporário para que o catalog.json contenha os tipos físicos
        for cmd in (["build"], ["docs", "generate", "--static", "--no-compile"]):
            proc = subprocess.run(
                [str(executavel_dbt), *cmd, "--profiles-dir", str(projeto_tmp)],
                cwd=projeto_tmp,
                env=env,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=180,
                check=False,
            )
            if proc.returncode != 0:
                raise RuntimeError(f"Falha ao executar dbt {' '.join(cmd)}:\n{proc.stdout}")

        static_html = projeto_tmp / "target" / "static_index.html"
        manifest_path = projeto_tmp / "target" / "manifest.json"
        catalog_path = projeto_tmp / "target" / "catalog.json"

        shutil.copy2(static_html, destino / "index.html")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        catalog = json.loads(catalog_path.read_text(encoding="utf-8"))

        # Atualiza também o manifest local de dbt_metra/target se a pasta puder ser escrita
        target_local = DBT_PROJECT_DIR / "target"
        try:
            target_local.mkdir(parents=True, exist_ok=True)
            shutil.copy2(manifest_path, target_local / "manifest.json")
            shutil.copy2(catalog_path, target_local / "catalog.json")
        except OSError:
            pass

    resumo = _extrair_resumo_catalogo(manifest, catalog)
    caminho_json = destino / "linhagem.json"
    caminho_json.write_text(json.dumps(resumo, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return resumo


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Gera o portal estático do dbt docs e o JSON de linhagem ponta a ponta do METRA."
    )
    parser.add_argument(
        "--destino",
        type=Path,
        default=DESTINO_PADRAO_DIR,
        help="Diretório de saída (padrão: docs/assets/dbt-docs).",
    )
    args = parser.parse_args()
    resumo = gerar_dbt_docs(args.destino)
    q = resumo["resumo_quantitativo"]
    print(
        f"dbt docs estático e catálogo gerados em {args.destino}:\n"
        f"  Fontes: {q['fontes_parquet']} | Modelos/Snapshots: {q['modelos_e_snapshots']} | "
        f"Métricas: {q['metricas_camada_semantica']} | Exposures: {q['exposures_consumo_final']} | "
        f"Testes dbt: {q['testes_declarativos_dbt']}"
    )


if __name__ == "__main__":
    main()
