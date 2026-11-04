"""Gerenciamento de conexão somente leitura e bootstrap reproduzível do DuckDB analítico (Gold)."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import duckdb

from src.app.busca_cbo import CATALOGO_CBO_PADRAO

ROOT = Path(__file__).resolve().parents[2]
DBT_PROJECT_DIR = ROOT / "dbt_metra"
CAMINHO_PADRAO_DUCKDB = ROOT / "data" / "metra_analitico.duckdb"
CAMINHO_AMOSTRA_CSV = ROOT / "data" / "caged_centro_oeste_amostra.csv"
CAMINHOS_COMPLETOS_CSV = (
    ROOT / "data" / "caged_2023_2024.csv",
    ROOT / "data" / "caged_2025_2026.csv",
)
CAMINHO_REFERENCIAS_JSON = Path(__file__).resolve().parent / "referencias_oficiais.json"

CAPITAIS_CO = {
    "5300108": ("Brasília", "DF", "Distrito Federal"),
    "5208707": ("Goiânia", "GO", "Goiás"),
    "5103403": ("Cuiabá", "MT", "Mato Grosso"),
    "5002704": ("Campo Grande", "MS", "Mato Grosso do Sul"),
}

NOMES_UF_CO = {
    "DF": "Distrito Federal",
    "GO": "Goiás",
    "MT": "Mato Grosso",
    "MS": "Mato Grosso do Sul",
}

SECOES_CNAE_OFICIAIS = {
    "A": "Agricultura, pecuária, produção florestal, pesca e aquicultura",
    "B": "Indústrias extrativas",
    "C": "Indústrias de transformação",
    "D": "Eletricidade e gás",
    "E": "Água, esgoto, atividades de gestão de resíduos e descontaminação",
    "F": "Construção",
    "G": "Comércio; reparação de veículos automotores e motocicletas",
    "H": "Transporte, armazenagem e correio",
    "I": "Alojamento e alimentação",
    "J": "Informação e comunicação",
    "K": "Atividades financeiras, de seguros e serviços relacionados",
    "L": "Atividades imobiliárias",
    "M": "Atividades profissionais, científicas e técnicas",
    "N": "Atividades administrativas e serviços complementares",
    "O": "Administração pública, defesa e seguridade social",
    "P": "Educação",
    "Q": "Saúde humana e serviços sociais",
    "R": "Artes, cultura, esporte e recreação",
    "S": "Outras atividades de serviços",
    "T": "Serviços domésticos",
    "U": "Organismos internacionais e outras instituições extraterritoriais",
    "Z": "Atividades não identificadas ou não especificadas",
}


def obter_caminho_duckdb(caminho: str | Path | None = None) -> Path:
    """Resolve o caminho do banco DuckDB analítico a partir de parâmetro ou variável `METRA_DUCKDB`."""
    if caminho is not None:
        return Path(caminho).resolve()
    env_val = os.environ.get("METRA_DUCKDB")
    if env_val:
        p = Path(env_val)
        return p.resolve() if p.is_absolute() else (ROOT / p).resolve()
    return CAMINHO_PADRAO_DUCKDB.resolve()


def banco_possui_camada_gold(caminho_banco: Path) -> bool:
    """Verifica se o arquivo DuckDB existe e já possui as 9 tabelas do schema `gold`."""
    if not caminho_banco.exists():
        return False
    try:
        with duckdb.connect(str(caminho_banco), read_only=True) as conn:
            qtd = conn.execute("""
                SELECT COUNT(*)
                FROM information_schema.tables
                WHERE table_schema = 'gold'
                  AND table_name IN (
                      'dim_cbo', 'dim_cnae', 'dim_municipio', 'dim_competencia',
                      'dim_perfil_demografico', 'fct_movimentacao',
                      'fct_setor_mensal', 'fct_geografia_mensal', 'fct_perfil_mensal'
                  )
            """).fetchone()[0]
            return int(qtd) == 9
    except Exception:
        return False


def construir_gold_de_amostra(
    caminho_banco: Path,
    usar_arquivos_completos: bool = False,
) -> None:
    """Materializa a camada Silver e Gold via `dbt build` a partir da amostra ou dos CSVs completos."""
    caminho_banco.parent.mkdir(parents=True, exist_ok=True)
    if caminho_banco.exists():
        caminho_banco.unlink()

    arquivos_completos_existem = all(p.exists() for p in CAMINHOS_COMPLETOS_CSV)
    if usar_arquivos_completos and arquivos_completos_existem:
        lista_csv = [str(p).replace("'", "''") for p in CAMINHOS_COMPLETOS_CSV]
    else:
        lista_csv = [str(CAMINHO_AMOSTRA_CSV).replace("'", "''")]

    lit_csv = "[" + ", ".join(f"'{c}'" for c in lista_csv) + "]"

    with tempfile.TemporaryDirectory(prefix="metra_bootstrap_") as tmp_dir:
        pasta_tmp = Path(tmp_dir)
        pasta_lake = pasta_tmp / "parquet"
        pasta_target = pasta_tmp / "target"
        pasta_logs = pasta_tmp / "logs"

        with duckdb.connect(str(pasta_tmp / "staging_lake.duckdb")) as origem:
            origem.execute("""
                CREATE TABLE municipio (
                    id_municipio VARCHAR, nome VARCHAR, sigla_uf VARCHAR,
                    nome_uf VARCHAR, regiao VARCHAR, is_capital BOOLEAN
                );
                CREATE TABLE cnae_secao (codigo VARCHAR, descricao VARCHAR);
                CREATE TABLE cnae_subclasse (codigo VARCHAR, descricao VARCHAR, codigo_secao VARCHAR);
                CREATE TABLE cbo_2002 (codigo VARCHAR, titulo VARCHAR);
            """)

            pasta_mov = pasta_lake / "movimentacao"
            pasta_mov.mkdir(parents=True, exist_ok=True)
            arq_mov_parquet = str(pasta_mov / "dados.parquet").replace("'", "''")

            origem.execute(f"""
                COPY (
                    SELECT
                        row_number() OVER ()::BIGINT AS id_movimentacao,
                        ano::INTEGER AS ano,
                        mes::INTEGER AS mes,
                        lpad(COALESCE(NULLIF(id_municipio, ''), '9999999'), 7, '0') AS id_municipio,
                        lpad(COALESCE(NULLIF(cnae_2_subclasse, ''), '9999999'), 7, '0') AS cnae_2_subclasse,
                        lpad(COALESCE(NULLIF(cbo_2002, ''), '999999'), 6, '0') AS cbo_2002,
                        sexo::INTEGER AS sexo,
                        raca_cor::INTEGER AS raca_cor,
                        CASE WHEN idade::INTEGER BETWEEN 10 AND 120 THEN idade::INTEGER END AS idade,
                        grau_instrucao::INTEGER AS grau_instrucao,
                        tipo_movimentacao::INTEGER AS tipo_movimentacao,
                        saldo_movimentacao::INTEGER AS saldo_movimentacao,
                        CASE
                            WHEN salario_mensal::DECIMAL(16,2) BETWEEN 0.01 AND 150000.00
                            THEN salario_mensal::DECIMAL(16,2)
                            ELSE 0.00
                        END::DECIMAL(16,2) AS salario_mensal,
                        GREATEST(COALESCE(horas_contratuais::DECIMAL(5,2), 0), 0)::DECIMAL(5,2) AS horas_contratuais,
                        1::BIGINT AS id_ingestao,
                        row_number() OVER ()::BIGINT AS numero_linha,
                        '2026-10-30 12:00:00+00'::TIMESTAMPTZ AS registrado_em
                    FROM read_csv({lit_csv}, all_varchar=true)
                    WHERE sigla_uf IN ('DF', 'GO', 'MT', 'MS')
                      AND ano::INTEGER BETWEEN 2023 AND 2026
                ) TO '{arq_mov_parquet}' (FORMAT PARQUET, COMPRESSION SNAPPY)
            """)

            refs_oficiais: dict[str, dict[str, str]] = {"cbo_2002": {}, "municipios": {}, "cnae_subclasses": {}}
            if CAMINHO_REFERENCIAS_JSON.exists():
                refs_oficiais = json.loads(CAMINHO_REFERENCIAS_JSON.read_text(encoding="utf-8"))

            mapa_mun_oficial = refs_oficiais.get("municipios", {})
            municipios = origem.execute(f"""
                SELECT
                    lpad(COALESCE(NULLIF(id_municipio, ''), '9999999'), 7, '0') AS id_mun,
                    COALESCE(MAX(NULLIF(sigla_uf, '')), 'NI') AS uf
                FROM read_csv({lit_csv}, all_varchar=true)
                GROUP BY 1
            """).fetchall()

            dados_mun = []
            vistas_mun = set()
            for id_mun, uf in sorted(municipios):
                vistas_mun.add(id_mun)
                if id_mun in CAPITAIS_CO:
                    nome_m, sigla, nome_u = CAPITAIS_CO[id_mun]
                    dados_mun.append((id_mun, nome_m, sigla, nome_u, "Centro-Oeste", True))
                elif id_mun == "9999999":
                    dados_mun.append(("9999999", "Município não identificado", "NI", "Não Identificado", "Centro-Oeste", False))
                else:
                    nome_real = mapa_mun_oficial.get(id_mun, f"Município {id_mun} ({uf})")
                    dados_mun.append((
                        id_mun,
                        nome_real,
                        uf,
                        NOMES_UF_CO.get(uf, uf),
                        "Centro-Oeste",
                        False,
                    ))
            if "9999999" not in vistas_mun:
                dados_mun.append(("9999999", "Município não identificado", "NI", "Não Identificado", "Centro-Oeste", False))
            origem.executemany("INSERT INTO municipio VALUES (?, ?, ?, ?, ?, ?)", dados_mun)

            origem.executemany(
                "INSERT INTO cnae_secao VALUES (?, ?)",
                sorted(SECOES_CNAE_OFICIAIS.items()),
            )

            mapa_cnae_oficial = refs_oficiais.get("cnae_subclasses", {})
            subclasses_rows = origem.execute(f"""
                SELECT
                    lpad(COALESCE(NULLIF(cnae_2_subclasse, ''), '9999999'), 7, '0') AS cod,
                    COALESCE(MAX(NULLIF(cnae_2_secao, '')), 'Z') AS sec
                FROM read_csv({lit_csv}, all_varchar=true)
                GROUP BY 1
            """).fetchall()
            mapa_sub = {cod: (sec if sec in SECOES_CNAE_OFICIAIS else "Z") for cod, sec in subclasses_rows}
            mapa_sub["9999999"] = "Z"

            origem.executemany(
                "INSERT INTO cnae_subclasse VALUES (?, ?, ?)",
                [
                    (
                        cod,
                        "Atividades econômicas não identificadas"
                        if cod == "9999999"
                        else mapa_cnae_oficial.get(
                            cod,
                            f"SUBCLASSE CNAE {cod} (REGISTRO ADMINISTRATIVO)",
                        ),
                        sec,
                    )
                    for cod, sec in sorted(mapa_sub.items())
                ],
            )

            mapa_cbo = dict(refs_oficiais.get("cbo_2002", {}))
            for cod_padrao, tit_padrao in dict(CATALOGO_CBO_PADRAO).items():
                mapa_cbo[cod_padrao] = tit_padrao
            cbos_vistos = {
                row[0]
                for row in origem.execute(f"SELECT DISTINCT cbo_2002 FROM '{arq_mov_parquet}'").fetchall()
            }
            for cod in sorted(cbos_vistos):
                if cod not in mapa_cbo:
                    mapa_cbo[cod] = f"OCUPACAO CBO {cod} (ATUALIZACAO MTE)"

            origem.executemany(
                "INSERT INTO cbo_2002 VALUES (?, ?)",
                sorted(mapa_cbo.items()),
            )

            for tabela in ("municipio", "cnae_secao", "cnae_subclasse", "cbo_2002"):
                pasta_t = pasta_lake / tabela
                pasta_t.mkdir(parents=True, exist_ok=True)
                arq_p = str(pasta_t / "dados.parquet").replace("'", "''")
                origem.execute(f"COPY {tabela} TO '{arq_p}' (FORMAT PARQUET, COMPRESSION SNAPPY)")

        env = {
            **os.environ,
            "METRA_LAKE_PARQUET": str(pasta_lake),
            "METRA_DUCKDB": str(caminho_banco),
            "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
        }
        res = subprocess.run(
            [
                sys.executable,
                "-c",
                "from dbt.cli.main import cli; cli()",
                "--no-use-colors",
                "--log-path",
                str(pasta_logs),
                "build",
                "--project-dir",
                str(DBT_PROJECT_DIR),
                "--profiles-dir",
                str(DBT_PROJECT_DIR),
                "--target-path",
                str(pasta_target),
            ],
            env=env,
            cwd=ROOT,
            text=True,
            capture_output=True,
            timeout=600,
        )
        if res.returncode != 0:
            raise RuntimeError(f"Falha ao construir camada Gold com dbt:\n{res.stdout}\n{res.stderr}")


def abrir_conexao_analitica(
    caminho: str | Path | None = None,
    garantir_construcao: bool = True,
) -> duckdb.DuckDBPyConnection:
    """Abre conexão DuckDB exclusivamente em modo `read_only=True` sobre o banco analítico Gold."""
    caminho_resolvido = obter_caminho_duckdb(caminho)
    if garantir_construcao and not banco_possui_camada_gold(caminho_resolvido):
        usar_completos = caminho_resolvido == CAMINHO_PADRAO_DUCKDB.resolve()
        construir_gold_de_amostra(caminho_resolvido, usar_arquivos_completos=usar_completos)
    return duckdb.connect(str(caminho_resolvido), read_only=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Constrói o banco analítico DuckDB (Silver + Gold) do METRA.")
    parser.add_argument(
        "--completo",
        action="store_true",
        help="Constrói usando os arquivos completos (caged_2023_2024.csv + caged_2025_2026.csv) se presentes.",
    )
    args = parser.parse_args()
    caminho = obter_caminho_duckdb()
    construir_gold_de_amostra(caminho, usar_arquivos_completos=args.completo)
    with duckdb.connect(str(caminho), read_only=True) as conn:
        tot = conn.execute("SELECT COUNT(*) FROM gold.fct_movimentacao").fetchone()[0]
        print(f"Banco analítico construído com sucesso em {caminho}: {tot:,} movimentações na camada Gold.")


if __name__ == "__main__":
    main()
