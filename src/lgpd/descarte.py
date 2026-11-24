"""Inventário LGPD, auditoria de pequenos grupos/ataque por diferença e script de descarte (E4).

Nomeia formalmente os dados pessoais (quase-identificadores) e dados pessoais sensíveis
tratados no pipeline do METRA, registra a base legal (arts. 7º, IV, § 3º e 11, II, 'c' da
Lei nº 13.709/2018 — LGPD) e o prazo de retenção, audita a eficácia do limiar k >= 5
frente a ataques por diferença entre recortes e executa (ou simula) o descarte seguro
dos artefatos locais que contêm microdados em nível de movimentação individual.

Uso:
    # Simulação (dry-run) sobre o diretório data/ local:
    python -m src.lgpd.descarte --simular

    # Execução real do descarte sobre um diretório de dados:
    python -m src.lgpd.descarte --executar --diretorio-dados /caminho/para/data

    # Execução real demonstrativa (audita o banco analítico real, popula ambiente
    # de homologação com microdados + lake + CDC + base de consumo, executa o descarte
    # real dos microdados e grava a evidência JSON auditável):
    python -m src.lgpd.descarte --demonstrar-descarte --saida docs/adr/evidencias/0008-lgpd-descarte.json
"""

from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
from typing import Any

import duckdb

from src.app.banco_analitico import obter_caminho_duckdb

RAIZ = Path(__file__).resolve().parents[2]
DIRETORIO_DADOS_PADRAO = RAIZ / "data"
LIMIAR_K_ANONIMATO = 5

ENQUADRAMENTO_LGPD: dict[str, Any] = {
    "controlador_academico": (
        "Projeto Integrado de Banco de Dados 2 — Faculdade de Ciências e Tecnologias em "
        "Engenharia (FCTE / Universidade de Brasília — UnB), Oferta 2026/2, Squad G4"
    ),
    "fonte_primaria": (
        "Microdados públicos do Novo CAGED divulgados pelo Ministério do Trabalho e Emprego "
        "(MTE / PDET), recortados para a Região Centro-Oeste (DF, GO, MT, MS) entre 2023 e 2026"
    ),
    "dados_nomeados": {
        "identificadores_diretos": [],
        "nota_identificadores_diretos": (
            "A fonte pública do Novo CAGED não fornece nome civil, CPF, RG, PIS/PASEP, NIT, "
            "CTPS ou CNPJ do empregador."
        ),
        "quase_identificadores": [
            "id_municipio",
            "competencia",
            "ano",
            "mes",
            "codigo_cbo",
            "codigo_cnae_subclasse",
            "idade",
            "codigo_sexo",
            "codigo_grau_instrucao",
            "salario_mensal",
            "horas_contratuais",
            "tipo_movimentacao",
            "saldo_movimentacao",
            "id_ingestao",
            "numero_linha",
        ],
        "dados_pessoais_sensiveis": [
            "codigo_raca_cor",
            "raca_cor",
        ],
        "justificativa_classificacao": (
            "Embora desprovido de identificadores diretos, cada registro de movimentação combina "
            "município (IBGE 7 dígitos), mês/ano da contratação ou demissão, ocupação (CBO 6 dígitos), "
            "subclasse econômica (CNAE 7 dígitos), idade exata, sexo, escolaridade e salário nominal "
            "(art. 5º, I da LGPD — dado relacionado a pessoa natural identificável por combinação rara). "
            "O atributo raça/cor, quando vinculado a registro individual potencialmente reidentificável, "
            "constitui dado pessoal sensível sobre origem racial ou étnica (art. 5º, II da LGPD)."
        ),
    },
    "base_legal": {
        "finalidade": (
            "Pesquisa e ensino acadêmico em Engenharia de Dados, voltados exclusivamente à "
            "produção e validação de indicadores estatísticos agregados sobre o mercado de "
            "trabalho formal no Centro-Oeste (perguntas de gestão P1 a P5)."
        ),
        "hipotese_dados_pessoais": (
            "Art. 7º, inciso IV da Lei nº 13.709/2018 (LGPD) — realização de estudos por órgão "
            "de pesquisa, garantida, sempre que possível, a anonimização dos dados pessoais; "
            "combinado com o Art. 7º, § 3º (tratamento de dados de acesso público observados a "
            "finalidade, a boa-fé e o interesse público que justificaram sua disponibilização pelo MTE)."
        ),
        "hipotese_dados_sensiveis": (
            "Art. 11, inciso II, alínea 'c' da Lei nº 13.709/2018 (LGPD) — realização de estudos "
            "por órgão de pesquisa sem fornecimento de consentimento do titular, garantida, sempre "
            "que possível, a anonimização dos dados pessoais sensíveis (UnB enquadrada como órgão "
            "de pesquisa da administração indireta federal nos termos do art. 5º, XVIII da LGPD)."
        ),
        "ressalva_institucional": (
            "Este enquadramento documenta a conformidade técnico-acadêmica da disciplina Banco de "
            "Dados 2 (FCTE/UnB) e não substitui parecer jurídico formal do Encarregado (DPO) da UnB "
            "para usos administrativos ou externos ao escopo didático."
        ),
    },
    "retencao": {
        "prazo_dias_apos_encerramento": 30,
        "data_limite_maxima": "2026-12-31",
        "regra_retencao": (
            "Os artefatos locais com granularidade individual (PostgreSQL bronze/oltp, Parquet, "
            "Delta Lake, logs de CDC e bancos DuckDB analíticos) são retidos apenas durante o "
            "semestre letivo 2026/2 e por até 30 (trinta) dias corridos após a publicação final "
            "das menções e encerramento do prazo recursal da disciplina (art. 15, I e art. 16 da LGPD)."
        ),
        "regra_pos_descarte": (
            "Após o descarte dos microdados individuais, apenas artefatos puramente agregados e "
            "submetidos à supressão de pequenos grupos (k >= 5, como data/metra_consumo.duckdb e "
            "docs/assets/dados/metra.json) podem permanecer publicados para consulta estatística."
        ),
    },
}


def _sha256_arquivo(caminho: Path) -> str:
    digest = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(65536), b""):
            digest.update(bloco)
    return digest.hexdigest()


def _tamanho_caminho(caminho: Path) -> tuple[int, int]:
    """Devolve (total_bytes, quantidade_arquivos) de um arquivo ou diretório."""
    if caminho.is_file():
        return caminho.stat().st_size, 1
    if caminho.is_dir():
        arquivos = [p for p in caminho.rglob("*") if p.is_file()]
        return sum(p.stat().st_size for p in arquivos), len(arquivos)
    return 0, 0


def inventariar_artefatos(diretorio_dados: Path) -> list[dict[str, Any]]:
    """Lista e classifica todos os artefatos de dados presentes em `diretorio_dados`."""
    diretorio_dados = Path(diretorio_dados).resolve()
    alvos_padrao = [
        (
            "banco_analitico_duckdb",
            diretorio_dados / "metra_analitico.duckdb",
            "microdados_individuais",
            "Schemas silver e gold.fct_movimentacao (1 linha por evento, com quase-identificadores e raça/cor)",
        ),
        (
            "banco_analitico_duckdb_wal",
            diretorio_dados / "metra_analitico.duckdb.wal",
            "microdados_individuais",
            "Write-Ahead Log do banco analítico DuckDB",
        ),
        (
            "banco_analise_e2_duckdb",
            diretorio_dados / "metra.duckdb",
            "microdados_individuais",
            "Tabela movimentacao local gerada pelo script standalone src/analise.py (E2)",
        ),
        (
            "banco_analise_e2_duckdb_wal",
            diretorio_dados / "metra.duckdb.wal",
            "microdados_individuais",
            "Write-Ahead Log do banco local da E2",
        ),
        (
            "lake_parquet",
            diretorio_dados / "lake" / "parquet",
            "microdados_individuais",
            "Arquivos Apache Parquet particionados por ano com cópia 1:1 de oltp.movimentacao",
        ),
        (
            "lake_delta",
            diretorio_dados / "lake" / "delta",
            "microdados_individuais",
            "Tabela Delta Lake com histórico de transações e microdados de movimentação",
        ),
        (
            "cdc_logs_e_estado",
            diretorio_dados / "cdc",
            "microdados_individuais",
            "Log de decodificação lógica (eventos.log) e banco de deduplicação (replay.sqlite3)",
        ),
        (
            "base_consumo_isolada",
            diretorio_dados / "metra_consumo.duckdb",
            "agregado_anonimizado_k5",
            "Base isolada contendo exclusivamente as tabelas agregadas consumo.* com supressão k >= 5",
        ),
        (
            "amostra_versionada_git",
            diretorio_dados / "caged_centro_oeste_amostra.csv",
            "versionado_git_amostra",
            "Amostra pública versionada no Git (49.178 linhas); requer git rm + reescrita de histórico para expurgo do repositório",
        ),
    ]

    inventario: list[dict[str, Any]] = []
    nomes_mapeados = {caminho.name for _, caminho, _, _ in alvos_padrao}

    for id_alvo, caminho, categoria, descricao in alvos_padrao:
        existe = caminho.exists()
        total_bytes, qtd_arquivos = _tamanho_caminho(caminho) if existe else (0, 0)
        sha256 = _sha256_arquivo(caminho) if (existe and caminho.is_file()) else None
        inventario.append({
            "id_artefato": id_alvo,
            "caminho": str(caminho.relative_to(RAIZ)) if caminho.is_relative_to(RAIZ) else str(caminho),
            "categoria_lgpd": categoria,
            "contem_microdado_individual": categoria in ("microdados_individuais", "versionado_git_amostra"),
            "existe": existe,
            "tipo": "diretorio" if caminho.is_dir() else ("arquivo" if caminho.is_file() else "ausente"),
            "arquivos_contidos": qtd_arquivos,
            "tamanho_bytes": total_bytes,
            "sha256": sha256,
            "descricao": descricao,
        })

    # Detecta quaisquer CSVs brutos adicionais em data/ (ex.: base completa de 14,7M linhas)
    if diretorio_dados.is_dir():
        for csv_extra in sorted(diretorio_dados.glob("*.csv")):
            if csv_extra.name in nomes_mapeados:
                continue
            total_bytes, _ = _tamanho_caminho(csv_extra)
            inventario.append({
                "id_artefato": f"csv_bruto_{csv_extra.stem}",
                "caminho": str(csv_extra.relative_to(RAIZ)) if csv_extra.is_relative_to(RAIZ) else str(csv_extra),
                "categoria_lgpd": "microdados_individuais",
                "contem_microdado_individual": True,
                "existe": True,
                "tipo": "arquivo",
                "arquivos_contidos": 1,
                "tamanho_bytes": total_bytes,
                "sha256": _sha256_arquivo(csv_extra),
                "descricao": "Arquivo CSV bruto de microdados do Novo CAGED não versionado",
            })

    return inventario


def auditar_pequenos_grupos_e_diferenca(
    caminho_banco: Path | None = None,
    limiar_k: int = LIMIAR_K_ANONIMATO,
) -> dict[str, Any]:
    """Avalia a supressão de pequenos grupos (k >= 5) e quantifica ataques por diferença na Gold."""
    banco = Path(caminho_banco or obter_caminho_duckdb()).resolve()
    if not banco.is_file():
        raise FileNotFoundError(f"Banco analítico não encontrado em {banco}")

    with duckdb.connect(str(banco), read_only=True) as conn:
        # 1. Unicidade de combinações de quase-identificadores + raça/cor em gold.fct_movimentacao
        (
            total_eventos,
            combinacoes_distintas,
            combinacoes_unicas_k1,
            combinacoes_abaixo_k5,
        ) = conn.execute(f"""
            WITH grupos_qi AS (
                SELECT
                    id_municipio,
                    competencia,
                    codigo_cbo,
                    codigo_cnae_subclasse,
                    idade,
                    id_perfil_demografico,
                    COUNT(*) AS k
                FROM gold.fct_movimentacao
                WHERE is_identificado AND is_centro_oeste AND ano BETWEEN 2023 AND 2026
                GROUP BY 1, 2, 3, 4, 5, 6
            )
            SELECT
                COALESCE(SUM(k), 0) AS total_eventos,
                COUNT(*) AS combinacoes_distintas,
                COUNT(*) FILTER (WHERE k = 1) AS combinacoes_unicas_k1,
                COUNT(*) FILTER (WHERE k < {int(limiar_k)}) AS combinacoes_abaixo_k5
            FROM grupos_qi
        """).fetchone()

        # 2. Supressão em setor_mensal e geografia_mensal
        (
            setores_total,
            setores_publicados,
            setores_omitidos_fluxo,
            setores_salario_suprimido,
        ) = conn.execute(f"""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE admissoes + desligamentos >= {int(limiar_k)}) AS publicados,
                COUNT(*) FILTER (WHERE admissoes + desligamentos < {int(limiar_k)}) AS omitidos_fluxo,
                COUNT(*) FILTER (
                    WHERE admissoes + desligamentos >= {int(limiar_k)}
                      AND qtd_salarios_admissao < {int(limiar_k)}
                ) AS salario_suprimido
            FROM gold.fct_setor_mensal
        """).fetchone()

        (
            geo_total,
            geo_publicados,
            geo_omitidos_fluxo,
            geo_salario_suprimido,
        ) = conn.execute(f"""
            SELECT
                COUNT(*) AS total,
                COUNT(*) FILTER (WHERE admissoes + desligamentos >= {int(limiar_k)}) AS publicados,
                COUNT(*) FILTER (WHERE admissoes + desligamentos < {int(limiar_k)}) AS omitidos_fluxo,
                COUNT(*) FILTER (
                    WHERE admissoes + desligamentos >= {int(limiar_k)}
                      AND qtd_salarios_admissao < {int(limiar_k)}
                ) AS salario_suprimido
            FROM gold.fct_geografia_mensal
        """).fetchone()

        # 3. Ataque por diferença entre geografia_mensal (total da UF/mês) e setor_mensal (soma dos setores da UF/mês):
        # Ocorre quando uma (competencia, sigla_uf) tem exatamente 1 seção CNAE omitida (ou resíduo total < k).
        (
            uf_mes_total,
            uf_mes_com_1_setor_omitido,
            uf_mes_com_residuo_menor_k,
        ) = conn.execute(f"""
            WITH por_uf_mes AS (
                SELECT
                    competencia,
                    sigla_uf,
                    COUNT(*) FILTER (WHERE admissoes + desligamentos < {int(limiar_k)}) AS setores_omitidos,
                    COALESCE(SUM(admissoes + desligamentos) FILTER (
                        WHERE admissoes + desligamentos < {int(limiar_k)}
                    ), 0) AS volume_omitido
                FROM gold.fct_setor_mensal
                GROUP BY competencia, sigla_uf
            )
            SELECT
                COUNT(*) AS uf_mes_total,
                COUNT(*) FILTER (WHERE setores_omitidos = 1) AS com_1_setor_omitido,
                COUNT(*) FILTER (WHERE volume_omitido BETWEEN 1 AND {int(limiar_k) - 1}) AS com_residuo_menor_k
            FROM por_uf_mes
        """).fetchone()

        # 4. Ataque por diferença dentro de perfil_mensal (subtraindo do total de setor_mensal
        # a soma das categorias demográficas publicadas para um mesmo eixo):
        (
            perfis_grupos_total,
            perfis_grupos_publicados,
            perfis_grupos_omitidos,
            particoes_eixo_com_1_cat_omitida,
        ) = conn.execute(f"""
            WITH base AS (
                SELECT f.*, p.* EXCLUDE (id_perfil_demografico)
                FROM gold.fct_perfil_mensal f
                LEFT JOIN gold.dim_perfil_demografico p USING (id_perfil_demografico)
            ),
            eixos AS (
                SELECT
                    b.competencia, b.sigla_uf, b.is_capital, b.codigo_secao,
                    e.eixo, e.codigo_categoria,
                    SUM(b.admissoes) AS admissoes,
                    SUM(b.desligamentos) AS desligamentos
                FROM base b
                CROSS JOIN LATERAL (VALUES
                    ('sexo', b.codigo_sexo),
                    ('raca_cor', b.codigo_raca_cor),
                    ('escolaridade', b.codigo_grau_instrucao),
                    ('faixa_etaria', b.codigo_faixa_etaria)
                ) e(eixo, codigo_categoria)
                GROUP BY 1, 2, 3, 4, 5, 6
            ),
            por_particao AS (
                SELECT
                    competencia, sigla_uf, is_capital, codigo_secao, eixo,
                    COUNT(*) AS total_cats,
                    COUNT(*) FILTER (WHERE admissoes + desligamentos >= {int(limiar_k)}) AS cats_publicadas,
                    COUNT(*) FILTER (WHERE admissoes + desligamentos < {int(limiar_k)}) AS cats_omitidas
                FROM eixos
                GROUP BY 1, 2, 3, 4, 5
            )
            SELECT
                (SELECT COUNT(*) FROM eixos) AS grupos_total,
                (SELECT COUNT(*) FROM eixos WHERE admissoes + desligamentos >= {int(limiar_k)}) AS grupos_publicados,
                (SELECT COUNT(*) FROM eixos WHERE admissoes + desligamentos < {int(limiar_k)}) AS grupos_omitidos,
                COUNT(*) FILTER (WHERE cats_omitidas = 1 AND cats_publicadas >= 1) AS particoes_com_1_cat_omitida
            FROM por_particao
        """).fetchone()

    return {
        "limiar_k_anonimato": int(limiar_k),
        "risco_reidentificacao_microdado_gold": {
            "total_movimentacoes_recorte": int(total_eventos),
            "combinacoes_distintas_quase_identificadores": int(combinacoes_distintas),
            "combinacoes_unicas_k1": int(combinacoes_unicas_k1),
            "combinacoes_abaixo_k5": int(combinacoes_abaixo_k5),
            "proporcao_combinacoes_abaixo_k5_pct": round(
                100.0 * int(combinacoes_abaixo_k5) / max(int(combinacoes_distintas), 1), 2
            ),
        },
        "efeito_supressao_views_consumo": {
            "setor_mensal": {
                "grupos_totais": int(setores_total),
                "grupos_publicados": int(setores_publicados),
                "grupos_omitidos_fluxo_menor_k": int(setores_omitidos_fluxo),
                "grupos_com_salario_suprimido": int(setores_salario_suprimido),
            },
            "geografia_mensal": {
                "grupos_totais": int(geo_total),
                "grupos_publicados": int(geo_publicados),
                "grupos_omitidos_fluxo_menor_k": int(geo_omitidos_fluxo),
                "grupos_com_salario_suprimido": int(geo_salario_suprimido),
            },
            "perfil_mensal": {
                "grupos_totais": int(perfis_grupos_total),
                "grupos_publicados": int(perfis_grupos_publicados),
                "grupos_omitidos_fluxo_menor_k": int(perfis_grupos_omitidos),
            },
        },
        "auditoria_ataque_por_diferenca": {
            "uf_competencia_total": int(uf_mes_total),
            "uf_competencia_com_exatamente_1_setor_omitido": int(uf_mes_com_1_setor_omitido),
            "uf_competencia_com_residuo_entre_1_e_k_menos_1": int(uf_mes_com_residuo_menor_k),
            "particoes_perfil_com_exatamente_1_categoria_omitida": int(particoes_eixo_com_1_cat_omitida),
            "mitigacao_adotada": (
                "As views consumo.* impedem cruzamento entre múltiplos eixos demográficos e não expõem "
                "município nem CBO. Ainda assim, como a supressão primária (k >= 5) ocorre por view sem "
                "supressão complementar secundária, um consumidor que subtraia a soma de setores ou "
                "categorias publicadas do total da partição pode estimar resíduos quando apenas 1 célula "
                "foi omitida; por isso a regra de governança proíbe inferência por diferença entre coleções."
            ),
        },
    }


def executar_descarte(
    diretorio_dados: Path | None = None,
    modo: str = "simular",
    incluir_agregados: bool = False,
    incluir_amostra_versionada: bool = False,
) -> dict[str, Any]:
    """Executa ou simula o descarte dos artefatos locais com microdados individuais."""
    if modo not in ("simular", "executar"):
        raise ValueError("O modo deve ser 'simular' ou 'executar'.")

    alvo_dir = Path(diretorio_dados or DIRETORIO_DADOS_PADRAO).resolve()
    inventario_antes = inventariar_artefatos(alvo_dir)

    categorias_remover = {"microdados_individuais"}
    if incluir_agregados:
        categorias_remover.add("agregado_anonimizado_k5")
    if incluir_amostra_versionada:
        categorias_remover.add("versionado_git_amostra")

    removidos: list[dict[str, Any]] = []
    preservados: list[dict[str, Any]] = []
    bytes_liberados = 0
    arquivos_removidos = 0

    for item in inventario_antes:
        caminho_abs = (
            (RAIZ / item["caminho"]).resolve()
            if not Path(item["caminho"]).is_absolute()
            else Path(item["caminho"]).resolve()
        )
        if not item["existe"]:
            continue

        if item["categoria_lgpd"] in categorias_remover:
            registro_remocao = {
                "id_artefato": item["id_artefato"],
                "caminho": item["caminho"],
                "categoria_lgpd": item["categoria_lgpd"],
                "tamanho_bytes": item["tamanho_bytes"],
                "arquivos_contidos": item["arquivos_contidos"],
                "sha256_antes_do_descarte": item["sha256"],
                "acao": "removido" if modo == "executar" else "simulado_para_remocao",
            }
            if modo == "executar":
                if caminho_abs.is_dir():
                    shutil.rmtree(caminho_abs)
                else:
                    caminho_abs.unlink(missing_ok=True)
            removidos.append(registro_remocao)
            bytes_liberados += int(item["tamanho_bytes"])
            arquivos_removidos += int(item["arquivos_contidos"])
        else:
            preservados.append({
                "id_artefato": item["id_artefato"],
                "caminho": item["caminho"],
                "categoria_lgpd": item["categoria_lgpd"],
                "tamanho_bytes": item["tamanho_bytes"],
                "motivo_preservacao": (
                    "Base agregada com supressão de pequenos grupos (k >= 5), sem eventos individuais"
                    if item["categoria_lgpd"] == "agregado_anonimizado_k5"
                    else "Amostra pública rastreada pelo Git; remoção definitiva requer git rm e reescrita de histórico"
                ),
            })

    # Remove diretório lake/ vazio se parquet/ e delta/ tiverem sido descartados
    if modo == "executar":
        pasta_lake = alvo_dir / "lake"
        if pasta_lake.is_dir() and not any(pasta_lake.iterdir()):
            pasta_lake.rmdir()

    inventario_depois = inventariar_artefatos(alvo_dir)
    residuais_microdados = [
        item["caminho"]
        for item in inventario_depois
        if item["existe"] and item["categoria_lgpd"] == "microdados_individuais"
    ]

    return {
        "executado_em_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "modo": modo,
        "diretorio_dados": str(alvo_dir.relative_to(RAIZ)) if alvo_dir.is_relative_to(RAIZ) else str(alvo_dir),
        "enquadramento_lgpd": ENQUADRAMENTO_LGPD,
        "resumo_descarte": {
            "artefatos_descartados": len(removidos),
            "arquivos_fisicos_removidos": arquivos_removidos,
            "bytes_liberados": bytes_liberados,
            "artefatos_preservados": len(preservados),
            "microdados_individuais_residuais": len(residuais_microdados),
            "verificacao_pos_descarte_ok": (len(residuais_microdados) == 0) if modo == "executar" else None,
        },
        "artefatos_descartados": removidos,
        "artefatos_preservados": preservados,
        "residuais_microdados": residuais_microdados,
    }


def demonstrar_descarte_auditavel(caminho_banco_origem: Path | None = None) -> dict[str, Any]:
    """Executa a auditoria na Gold real e demonstra o descarte real em ambiente de staging isolado.

    Cria em diretório temporário todos os artefatos operacionais com microdados individuais
    (`metra_analitico.duckdb`, `metra.duckdb`, `lake/parquet/movimentacao/ano=2025/part.parquet`,
    `lake/delta/movimentacao/_delta_log/00000.json`, `cdc/eventos.log` e `cdc/replay.sqlite3`)
    mais a base de consumo agregada (`metra_consumo.duckdb`), executa `executar_descarte(..., modo="executar")`
    e comprova que 100% dos microdados individuais foram eliminados enquanto a base agregada
    preservada contém apenas `consumo.*` com grupos k >= 5.
    """
    banco_real = Path(caminho_banco_origem or obter_caminho_duckdb()).resolve()
    auditoria_gold = auditar_pequenos_grupos_e_diferenca(banco_real)

    with tempfile.TemporaryDirectory(prefix="metra_lgpd_descarte_") as tmp:
        dir_staging = Path(tmp) / "data"
        (dir_staging / "lake" / "parquet" / "movimentacao" / "ano=2025").mkdir(parents=True)
        (dir_staging / "lake" / "delta" / "movimentacao" / "_delta_log").mkdir(parents=True)
        (dir_staging / "cdc").mkdir(parents=True)

        # 1. Cria banco analítico de staging com microdados individuais reais extraídos da amostra
        analitico_stg = dir_staging / "metra_analitico.duckdb"
        with duckdb.connect(str(analitico_stg)) as conn:
            conn.execute(f"ATTACH '{banco_real}' AS origem (READ_ONLY)")
            conn.execute("CREATE SCHEMA silver; CREATE SCHEMA gold")
            conn.execute(
                "CREATE TABLE silver.stg_movimentacao AS "
                "SELECT * FROM origem.silver.stg_movimentacao LIMIT 500"
            )
            conn.execute(
                "CREATE TABLE gold.fct_movimentacao AS "
                "SELECT * FROM origem.gold.fct_movimentacao LIMIT 500"
            )
            conn.execute(
                "COPY (SELECT * FROM gold.fct_movimentacao) "
                f"TO '{dir_staging / 'lake/parquet/movimentacao/ano=2025/dados.parquet'}' (FORMAT PARQUET)"
            )
            conn.execute("DETACH origem")

        # 2. Cria artefatos de Delta, E2, CDC e amostra no ambiente de staging
        (dir_staging / "lake" / "delta" / "movimentacao" / "part-00000.parquet").write_bytes(
            (dir_staging / "lake" / "parquet" / "movimentacao" / "ano=2025" / "dados.parquet").read_bytes()
        )
        (dir_staging / "lake" / "delta" / "movimentacao" / "_delta_log" / "00000000000000000000.json").write_text(
            '{"commitInfo":{"operation":"WRITE"}}', encoding="utf-8"
        )
        shutil.copy2(analitico_stg, dir_staging / "metra.duckdb")
        (dir_staging / "cdc" / "eventos.log").write_text(
            "BEGIN 769\ntable oltp.movimentacao: INSERT: id_movimentacao[bigint]:1\nCOMMIT 769\n",
            encoding="utf-8",
        )
        (dir_staging / "cdc" / "replay.sqlite3").write_bytes(b"SQLite format 3\x00")

        # 3. Cria base de consumo isolada (somente agregados k >= 5, sem linhas individuais)
        consumo_stg = dir_staging / "metra_consumo.duckdb"
        with duckdb.connect(str(consumo_stg)) as conn:
            conn.execute(f"ATTACH '{banco_real}' AS origem (READ_ONLY)")
            conn.execute("CREATE SCHEMA consumo")
            conn.execute(
                "CREATE TABLE consumo.setor_mensal AS "
                "SELECT competencia, sigla_uf, codigo_secao, admissoes, desligamentos, saldo "
                "FROM origem.gold.fct_setor_mensal WHERE admissoes + desligamentos >= 5"
            )
            conn.execute("DETACH origem")

        # 4. Executa o descarte real sobre o diretório de staging
        resultado_descarte = executar_descarte(dir_staging, modo="executar", incluir_agregados=False)
        resultado_descarte["diretorio_dados"] = "data/ (ambiente de homologação isolado)"
        for colecao in ("artefatos_descartados", "artefatos_preservados"):
            for item in resultado_descarte.get(colecao, []):
                p_item = Path(item["caminho"])
                if p_item.is_relative_to(dir_staging):
                    item["caminho"] = "data/" + p_item.relative_to(dir_staging).as_posix()

        # 5. Verifica que a base de consumo preservada não possui schema gold/silver nem linhas individuais
        with duckdb.connect(str(consumo_stg), read_only=True) as conn:
            tabelas_restantes = conn.execute(
                "SELECT table_schema || '.' || table_name FROM information_schema.tables ORDER BY 1"
            ).fetchall()
            (min_volume_consumo,) = conn.execute(
                "SELECT MIN(admissoes + desligamentos) FROM consumo.setor_mensal"
            ).fetchone()

    return {
        "protocolo": "ADR-0007 / E4 — Governança LGPD, Retenção, Pequenos Grupos e Execução de Descarte",
        "auditoria_base_analitica_real": auditoria_gold,
        "execucao_real_descarte": resultado_descarte,
        "verificacao_base_consumo_preservada": {
            "tabelas_presentes": [t[0] for t in tabelas_restantes],
            "contem_schema_gold_ou_silver": any(
                t[0].startswith(("gold.", "silver.", "bronze.", "oltp.")) for t in tabelas_restantes
            ),
            "menor_volume_grupo_publicado": int(min_volume_consumo or 0),
            "respeita_limiar_k5": int(min_volume_consumo or 0) >= LIMIAR_K_ANONIMATO,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inventário LGPD, auditoria de pequenos grupos e descarte de microdados do METRA."
    )
    grupo = parser.add_mutually_exclusive_group()
    grupo.add_argument(
        "--simular",
        action="store_true",
        help="Simula o descarte (dry-run) listando os artefatos que seriam removidos.",
    )
    grupo.add_argument(
        "--executar",
        action="store_true",
        help="Executa a remoção física dos artefatos de microdados individuais em --diretorio-dados.",
    )
    grupo.add_argument(
        "--demonstrar-descarte",
        action="store_true",
        help="Audita a Gold real, executa o descarte real em ambiente isolado de homologação e gera evidência.",
    )
    parser.add_argument(
        "--diretorio-dados",
        type=Path,
        default=DIRETORIO_DADOS_PADRAO,
        help="Diretório de dados alvo para --simular ou --executar (padrão: data/).",
    )
    parser.add_argument(
        "--incluir-agregados",
        action="store_true",
        help="Remove também a base agregada data/metra_consumo.duckdb.",
    )
    parser.add_argument(
        "--saida",
        type=Path,
        default=None,
        help="Caminho opcional para salvar o relatório JSON da execução.",
    )
    args = parser.parse_args()

    if args.demonstrar_descarte:
        relatorio = demonstrar_descarte_auditavel()
    elif args.executar:
        relatorio = executar_descarte(
            args.diretorio_dados,
            modo="executar",
            incluir_agregados=args.incluir_agregados,
        )
    else:
        relatorio = executar_descarte(
            args.diretorio_dados,
            modo="simular",
            incluir_agregados=args.incluir_agregados,
        )

    texto_json = json.dumps(relatorio, ensure_ascii=False, indent=2)
    if args.saida:
        args.saida.parent.mkdir(parents=True, exist_ok=True)
        args.saida.write_text(texto_json + "\n", encoding="utf-8")
        print(f"Relatório LGPD gravado em: {args.saida}")
    else:
        print(texto_json)


if __name__ == "__main__":
    main()
