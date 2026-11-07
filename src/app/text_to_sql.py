"""Assistente Text-to-SQL governado pelo catálogo de métricas da camada Gold (ADR 0007).

Converte perguntas em linguagem natural em consultas SQL parametrizadas e auditáveis sobre
o schema `gold` do DuckDB, garantindo:
1. Alinhamento exato com as 5 consultas de referência (`p1_setores_df` a `p5_perfil_remuneracao`)
   e com o contrato de indicadores por ocupação CBO (`gold.fct_movimentacao` + `gold.dim_cbo`).
2. Recomposição estrita de médias salariais (`sum(soma_salarios_admissao) / nullif(sum(qtd_salarios_admissao), 0)`),
   nunca realizando média de médias.
3. Validação estrutural e de segurança (`validar_sql_seguro`): bloqueia DDL/DML, múltiplas instruções,
   leitura de arquivos externos (por funções ou caminhos entre aspas em `FROM`/`JOIN`), tabelas fora do
   schema `gold` e consultas de linhas individuais sem agregação na projeção de `gold.fct_movimentacao` (LGPD).
4. Recusa transparente para perguntas fora do escopo (estoque total de vínculos RAIS, taxa de desemprego
   PNAD, probabilidade individual de recolocação ou previsões futuras).
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import re
from typing import Any, Iterable

import duckdb

from src.app.busca_cbo import IndiceVetorialCBO, normalizar_texto

TABELAS_GOLD_PERMITIDAS = frozenset({
    "gold.dim_competencia",
    "gold.dim_municipio",
    "gold.dim_cnae",
    "gold.dim_cbo",
    "gold.dim_perfil_demografico",
    "gold.fct_movimentacao",
    "gold.fct_setor_mensal",
    "gold.fct_geografia_mensal",
    "gold.fct_perfil_mensal",
})

COMANDOS_PROIBIDOS_SQL = frozenset({
    "insert", "update", "delete", "drop", "alter", "create", "truncate",
    "replace", "attach", "detach", "copy", "export", "import", "pragma",
    "install", "load", "call", "set", "grant", "revoke", "vacuum", "merge",
    "describe", "show", "summarize",
})

FUNCOES_EXTERNAS_PROIBIDAS = frozenset({
    "read_csv", "read_csv_auto", "read_parquet", "read_json", "read_json_auto",
    "delta_scan", "postgres_scan", "sqlite_scan", "iceberg_scan", "glob",
    "read_text", "read_blob", "parquet_scan", "sniff_csv",
    "duckdb_tables", "duckdb_columns", "duckdb_views", "duckdb_settings",
})


class ViolacaoSegurancaSQL(ValueError):
    """Exceção levantada quando uma consulta viola as políticas de segurança e governança."""


@dataclass(frozen=True)
class RespostaTextToSQL:
    """Contrato completo de resposta do assistente Text-to-SQL (ADR 0007)."""

    pergunta_original: str
    suportada: bool
    intencao: str
    titulo_intencao: str
    filtros_aplicados: dict[str, Any]
    formula_metrica: str
    ressalva_metodologica: str
    sql_gerado: str
    colunas: list[str]
    linhas: list[tuple[Any, ...]]
    ocupacoes_resolvidas: list[dict[str, Any]]
    motivo_recusa: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _contem_termo(texto_norm: str, termos: Iterable[str]) -> bool:
    """Verifica se algum termo ou expressão ocorre como palavra(s) inteira(s) em `texto_norm`."""
    if not texto_norm:
        return False
    tokens = set(texto_norm.split())
    for termo in termos:
        t = termo.strip()
        if not t:
            continue
        if " " not in t:
            if t in tokens:
                return True
        else:
            if re.search(rf"\b{re.escape(t)}\b", texto_norm):
                return True
    return False


def validar_sql_seguro(sql: str) -> None:
    """Valida estruturalmente que a instrução SQL é apenas de leitura agregada sobre o schema `gold`."""
    texto = (sql or "").strip()
    if not texto:
        raise ViolacaoSegurancaSQL("Consulta SQL vazia.")

    # Remove comentários SQL antes de inspecionar
    sem_comentarios = re.sub(r"--[^\n]*", " ", texto)
    sem_comentarios = re.sub(r"/\*.*?\*/", " ", sem_comentarios, flags=re.DOTALL).strip()

    if not sem_comentarios:
        raise ViolacaoSegurancaSQL("Consulta SQL vazia após remoção de comentários.")

    # Bloqueia identificadores entre aspas duplas (evita camuflar caminhos de arquivos ou schemas internos)
    if '"' in sem_comentarios:
        raise ViolacaoSegurancaSQL(
            "Identificadores entre aspas duplas não são permitidos pela camada de governança."
        )

    # Inspeciona todos os literais entre aspas simples antes de substituí-los por placeholder estrutural
    literais_aspas = re.findall(r"'(?:''|[^'])*'", sem_comentarios)
    for lit in literais_aspas:
        conteudo_lit = lit[1:-1].lower().strip()
        if (
            "/" in conteudo_lit
            or "\\" in conteudo_lit
            or ".." in conteudo_lit
            or re.search(
                r"\.(?:csv|parquet|json|db|duckdb|sqlite|txt|sql|gz|zip)\b",
                conteudo_lit,
            )
            or re.match(r"^(?:s3|http|https|file|hf|az|gcs):", conteudo_lit)
        ):
            raise ViolacaoSegurancaSQL(
                f"Caminho de arquivo ou URI externa não permitido em literal SQL: {lit}."
            )

    # Substitui literais de texto por marcador neutro para que palavras dentro de strings (ex.: 'count(')
    # jamais enganem a validação sintática/estrutural.
    corpo_sem_literais = re.sub(r"'(?:''|[^'])*'", "__str_lit__", sem_comentarios)

    # Bloqueia múltiplas instruções separadas por ponto-e-vírgula
    partes = [p.strip() for p in corpo_sem_literais.split(";") if p.strip()]
    if len(partes) > 1:
        raise ViolacaoSegurancaSQL(
            "Múltiplas instruções SQL (';') são bloqueadas pela camada de governança."
        )

    corpo_estrutural = partes[0].lower()

    if not (corpo_estrutural.startswith("select") or corpo_estrutural.startswith("with")):
        raise ViolacaoSegurancaSQL(
            "Apenas consultas analíticas iniciadas por SELECT ou WITH são permitidas."
        )

    tokens = re.findall(r"\b[a-z_][a-z0-9_]*\b", corpo_estrutural)
    for tok in tokens:
        if tok in COMANDOS_PROIBIDOS_SQL:
            raise ViolacaoSegurancaSQL(
                f"Operação ou palavra-chave SQL proibida detectada: '{tok.upper()}'."
            )
        if tok in FUNCOES_EXTERNAS_PROIBIDAS:
            raise ViolacaoSegurancaSQL(
                f"Função de leitura externa proibida detectada: '{tok}'."
            )

    # Bloqueia literais em cláusulas FROM ou JOIN (ex.: SELECT ... FROM '/etc/passwd')
    if re.search(r"\b(?:from|join)\s+__str_lit__\b", corpo_estrutural):
        raise ViolacaoSegurancaSQL(
            "Leitura direta de arquivos ou literais na cláusula FROM/JOIN é bloqueada."
        )

    # Bloqueia junções implícitas por vírgula na cláusula FROM (ex.: FROM '/etc/passwd', gold.dim_cbo)
    if re.search(
        r"\bfrom\s+[a-z0-9_.]+\s*(?:(?:as\s+)?[a-z0-9_]+\s*)?,",
        corpo_estrutural,
    ):
        raise ViolacaoSegurancaSQL(
            "Múltiplas relações separadas por vírgula na cláusula FROM são bloqueadas; utilize JOIN explícito."
        )

    # Identifica CTEs declaradas na própria consulta (WITH nome AS (...))
    aliases_cte = set(re.findall(r"\b([a-z_][a-z0-9_]*)\s+as\s*\(", corpo_estrutural))

    # Valida estruturalmente todos os alvos de FROM e JOIN (exceto LATERAL / subqueries)
    tabelas_gold_usadas: set[str] = set()
    for match_rel in re.finditer(r"\b(from|join)\s+(?!lateral\b|\()([a-z0-9_.]+)", corpo_estrutural):
        clausula_kw = match_rel.group(1).upper()
        alvo = match_rel.group(2)
        if alvo in TABELAS_GOLD_PERMITIDAS:
            tabelas_gold_usadas.add(alvo)
        elif alvo not in aliases_cte:
            raise ViolacaoSegurancaSQL(
                f"Relação '{alvo}' na cláusula {clausula_kw} não pertence ao catálogo Gold homologado."
            )

    if not tabelas_gold_usadas:
        raise ViolacaoSegurancaSQL(
            "A consulta deve referenciar exclusivamente as tabelas homologadas do schema 'gold'."
        )

    # Verifica referências qualificadas schema.objeto ou alias.coluna
    referencias_qualificadas = re.findall(
        r"\b([a-z_][a-z0-9_]*)\.([a-z_][a-z0-9_]*)\b", corpo_estrutural
    )
    aliases_from = set(
        re.findall(
            r"\b(?:from|join)\s+(?:gold\.[a-z_][a-z0-9_]*|[a-z_][a-z0-9_]*)\s+(?:as\s+)?([a-z_][a-z0-9_]*)\b",
            corpo_estrutural,
        )
    )
    for alias_ou_schema, objeto in referencias_qualificadas:
        if alias_ou_schema in ("silver", "bronze", "oltp", "pg_catalog", "information_schema", "main", "temp", "system"):
            raise ViolacaoSegurancaSQL(
                f"Acesso ao schema '{alias_ou_schema}' negado. Apenas o schema 'gold' é permitido."
            )
        if alias_ou_schema == "gold":
            nome_completo = f"gold.{objeto}"
            if nome_completo not in TABELAS_GOLD_PERMITIDAS:
                raise ViolacaoSegurancaSQL(
                    f"Tabela '{nome_completo}' não pertence ao catálogo público da camada Gold."
                )
        elif alias_ou_schema not in aliases_cte and alias_ou_schema not in aliases_from and len(alias_ou_schema) > 4:
            if alias_ou_schema not in {
                "base", "setores", "secoes", "janela", "cobertura", "calendario",
                "grupos", "serie", "resumo", "comparacao", "totais", "pares",
                "correlacao", "eixos", "referencias",
            }:
                raise ViolacaoSegurancaSQL(
                    f"Referência qualificada não autorizada: '{alias_ou_schema}.{objeto}'."
                )

    # Proteção estrutural de privacidade (LGPD): proíbe exposição de linhas individuais de gold.fct_movimentacao
    if "gold.fct_movimentacao" in tabelas_gold_usadas:
        # 1. Proíbe colunas de linhagem individual em qualquer parte da consulta
        for col_proibida in ("id_ingestao", "numero_linha", "registrado_em"):
            if re.search(rf"\b{col_proibida}\b", corpo_estrutural):
                raise ViolacaoSegurancaSQL(
                    f"Coluna de linhagem individual '{col_proibida}' bloqueada pela política de privacidade (LGPD)."
                )

        # 2. id_movimentacao só pode aparecer dentro de COUNT(...)
        sem_count_id = re.sub(
            r"\bcount\s*\(\s*(?:distinct\s+)?(?:[a-z_][a-z0-9_]*\.)?id_movimentacao\s*\)",
            "count_id_ok",
            corpo_estrutural,
        )
        if re.search(r"\bid_movimentacao\b", sem_count_id):
            raise ViolacaoSegurancaSQL(
                "A coluna 'id_movimentacao' não pode ser projetada ou agrupada individualmente (LGPD)."
            )

        # 3. Inspeciona cada bloco SELECT ... FROM que referencia gold.fct_movimentacao
        blocos_fct = [
            m
            for m in re.finditer(
                r"\bselect\b(?P<projecao>(?:(?!\bselect\b|\bfrom\b).)+)\bfrom\b(?P<clausula_from>(?:(?!\bselect\b).)+)",
                corpo_estrutural,
                flags=re.DOTALL,
            )
            if "gold.fct_movimentacao" in m.group("clausula_from")
        ]
        if not blocos_fct:
            raise ViolacaoSegurancaSQL(
                "Estrutura de consulta sobre 'gold.fct_movimentacao' inválida."
            )

        for bloco in blocos_fct:
            projecao = bloco.group("projecao")
            clausula_from = bloco.group("clausula_from")
            # Proíbe SELECT * ou SELECT f.* fora de COUNT(*)
            projecao_sem_count_star = re.sub(r"\bcount\s*\(\s*\*\s*\)", "count_star", projecao)
            if "*" in projecao_sem_count_star:
                raise ViolacaoSegurancaSQL(
                    "Acesso negado pela política de governança/LGPD: 'SELECT *' sobre "
                    "'gold.fct_movimentacao' é proibido."
                )
            # Exige função de agregação (COUNT, SUM, AVG) diretamente na projeção SELECT do bloco
            if not re.search(r"\b(?:count|sum|avg)\s*\(", projecao):
                raise ViolacaoSegurancaSQL(
                    "Acesso negado pela política de governança/LGPD: 'gold.fct_movimentacao' só pode "
                    "ser consultada com funções de agregação (SUM, COUNT, AVG) na cláusula SELECT."
                )
            # Se houver colunas dimensionais na projeção além das agregações, exige GROUP BY no mesmo bloco
            if not re.search(r"\bgroup\s+by\b", clausula_from):
                # Permite apenas agregação global pura (ex.: SELECT COUNT(*), SUM(...) FROM gold.fct_movimentacao)
                expressoes = [e.strip() for e in projecao.split(",") if e.strip()]
                if not all(re.search(r"\b(?:count|sum|avg|min|max|coalesce)\s*\(", e) for e in expressoes):
                    raise ViolacaoSegurancaSQL(
                        "Consultas em 'gold.fct_movimentacao' com colunas dimensionais exigem cláusula GROUP BY."
                    )


def _extrair_filtros_pergunta(pergunta: str) -> dict[str, Any]:
    """Extrai filtros explícitos de UF, ano, localidade e eixo demográfico usando palavras inteiras."""
    norm = normalizar_texto(pergunta)
    filtros: dict[str, Any] = {}

    # UF
    if _contem_termo(norm, ("distrito federal", "brasilia", "df")):
        filtros["sigla_uf"] = "DF"
    elif _contem_termo(norm, ("goias", "goiania", "go")):
        filtros["sigla_uf"] = "GO"
    elif _contem_termo(norm, ("mato grosso do sul", "campo grande", "ms")):
        filtros["sigla_uf"] = "MS"
    elif _contem_termo(norm, ("mato grosso", "cuiaba", "mt")):
        filtros["sigla_uf"] = "MT"

    # Ano (2023 a 2026)
    anos = [int(a) for a in re.findall(r"\b(202[3-6])\b", norm)]
    if len(anos) == 1:
        filtros["ano"] = anos[0]

    # Eixo demográfico (P5) — usa palavras inteiras para evitar falsos positivos (ex.: 'cor' em 'coracao'/'recorte')
    if _contem_termo(norm, ("sexo", "genero", "homem", "mulher", "homens", "mulheres", "feminino", "masculino")):
        filtros["eixo"] = "sexo"
    elif _contem_termo(
        norm,
        ("raca", "racas", "raca cor", "por cor", "cor ou raca", "branca", "preta", "parda", "indigena", "amarela", "negros", "negras", "pardos", "pardas"),
    ):
        filtros["eixo"] = "raca_cor"
    elif _contem_termo(
        norm,
        (
            "escolaridade", "instrucao", "ensino", "superior", "fundamental",
            "ensino medio", "medio completo", "medio incompleto", "pos graduacao",
            "mestrado", "doutorado", "analfabeto", "estudo", "graduacao",
        ),
    ):
        filtros["eixo"] = "escolaridade"
    elif _contem_termo(norm, ("idade", "faixa etaria", "etaria", "jovens", "idosos", "anos de idade")):
        filtros["eixo"] = "faixa_etaria"

    # Nível para P3
    if _contem_termo(norm, ("mensal", "mes a mes")):
        filtros["nivel"] = "mensal"
    elif _contem_termo(norm, ("anual", "por ano")):
        filtros["nivel"] = "anual"
    elif _contem_termo(norm, ("total", "consolidado", "acumulado")):
        filtros["nivel"] = "total"

    return filtros


def _cte_base_setor_mensal(filtros: dict[str, Any], where_extra: str = "") -> str:
    """Gera a CTE `base` equivalente a `gold.fct_setor_mensal`, filtrando por CBO quando solicitado."""
    codigos_cbo = filtros.get("codigos_cbo")
    if not codigos_cbo:
        clausula = f"\n    {where_extra}" if where_extra else ""
        return f"select * from gold.fct_setor_mensal{clausula}"

    lista_cbo = ", ".join(f"'{str(c).zfill(6)}'" for c in codigos_cbo)
    condicoes = [
        "f.is_identificado",
        "f.is_centro_oeste",
        "f.ano between 2023 and 2026",
        f"f.codigo_cbo in ({lista_cbo})",
    ]
    if where_extra:
        limpo = re.sub(r"^\s*where\s+", "", where_extra.strip(), flags=re.IGNORECASE)
        if limpo:
            condicoes.append(limpo)
    where_sql = " and ".join(condicoes)
    return f"""select
        f.competencia, f.sigla_uf, f.codigo_secao,
        count(*) filter (where f.saldo_movimentacao = 1) as admissoes,
        count(*) filter (where f.saldo_movimentacao = -1) as desligamentos,
        coalesce(sum(f.saldo_movimentacao), 0) as saldo,
        coalesce(sum(case when f.saldo_movimentacao = 1 and f.salario_valido then f.salario_mensal else 0 end), 0) as soma_salarios_admissao,
        count(*) filter (where f.saldo_movimentacao = 1 and f.salario_valido) as qtd_salarios_admissao,
        sum(case when f.saldo_movimentacao = 1 and f.salario_valido then f.salario_mensal else 0 end)
            / nullif(count(*) filter (where f.saldo_movimentacao = 1 and f.salario_valido), 0) as salario_medio_admissao
    from gold.fct_movimentacao f
    where {where_sql}
    group by f.competencia, f.sigla_uf, f.codigo_secao"""


def _gerar_sql_p1(filtros: dict[str, Any]) -> str:
    uf = filtros.get("sigla_uf", "DF")
    if uf not in ("DF", "GO", "MT", "MS"):
        uf = "DF"
    filtros["sigla_uf"] = uf
    where_base = ""
    if "ano" in filtros and int(filtros["ano"]) in (2023, 2024, 2025, 2026):
        where_base = f"where year(competencia) = {int(filtros['ano'])}"
    corpo_base = _cte_base_setor_mensal(filtros, where_base)
    return f"""with base as (
    {corpo_base}
), janela as (
    select (max(competencia) - interval '11 months')::date as inicio,
           max(competencia) as fim
    from base
), cobertura as (
    select count(distinct competencia) as competencias_disponiveis
    from base cross join janela
    where competencia between inicio and fim
), setores as (
    select codigo_secao,
           sum(admissoes) as admissoes, sum(desligamentos) as desligamentos,
           sum(saldo) as saldo
    from base cross join janela
    where sigla_uf = '{uf}' and codigo_secao <> 'Z'
      and competencia between inicio and fim
    group by codigo_secao
), secoes as (
    select distinct codigo_secao, descricao_secao from gold.dim_cnae
)
select s.*, d.descricao_secao,
       dense_rank() over (order by admissoes desc) as ranking_admissoes,
       dense_rank() over (order by desligamentos desc) as ranking_desligamentos,
       j.inicio, j.fim, c.competencias_disponiveis
from setores s
left join secoes d using (codigo_secao)
cross join janela j
cross join cobertura c
order by ranking_admissoes, codigo_secao"""


def _gerar_sql_p2(filtros: dict[str, Any]) -> str:
    clausulas_base: list[str] = []
    if "sigla_uf" in filtros and filtros["sigla_uf"] in ("DF", "GO", "MT", "MS"):
        clausulas_base.append(f"sigla_uf = '{filtros['sigla_uf']}'")
    if "ano" in filtros and int(filtros["ano"]) in (2023, 2024, 2025, 2026):
        clausulas_base.append(f"year(competencia) = {int(filtros['ano'])}")
    where_base = f"where {' and '.join(clausulas_base)}" if clausulas_base else ""
    corpo_base = _cte_base_setor_mensal(filtros, where_base)

    return f"""with base as (
    {corpo_base}
), competencias as (
    select distinct competencia from base
), calendario as (
    select c.competencia, c.ano, c.mes, p.competencia is not null as tem_dados
    from gold.dim_competencia c
    left join competencias p using (competencia)
    where c.competencia between (select min(competencia) from base)
                            and (select max(competencia) from base)
), anos_completos as (
    select ano from calendario
    group by ano having count(*) filter (where tem_dados) = 12
), grupos as (
    select distinct sigla_uf, codigo_secao from base
), serie as (
    select c.*, g.sigla_uf, g.codigo_secao,
           a.ano is not null as ano_completo_na_base,
           case when c.tem_dados then coalesce(b.admissoes, 0) end as admissoes,
           case when c.tem_dados then coalesce(b.desligamentos, 0) end as desligamentos,
           case when c.tem_dados then coalesce(b.saldo, 0) end as saldo
    from calendario c cross join grupos g
    left join base b using (competencia, sigla_uf, codigo_secao)
    left join anos_completos a on c.ano = a.ano
), resumo as (
    select sigla_uf, codigo_secao, mes,
           count(*) as anos_considerados,
           avg(admissoes) as media_admissoes_mes,
           avg(desligamentos) as media_desligamentos_mes,
           avg(saldo) as media_saldo_mes
    from serie where ano_completo_na_base
    group by sigla_uf, codigo_secao, mes
)
select s.*, coalesce(r.anos_considerados, 0) as anos_considerados,
       r.media_admissoes_mes, r.media_desligamentos_mes, r.media_saldo_mes
from serie s
left join resumo r using (sigla_uf, codigo_secao, mes)
order by sigla_uf, codigo_secao, competencia"""


def _gerar_sql_p3(filtros: dict[str, Any]) -> str:
    clausulas_base: list[str] = []
    if "sigla_uf" in filtros and filtros["sigla_uf"] in ("DF", "GO", "MT", "MS"):
        clausulas_base.append(f"sigla_uf = '{filtros['sigla_uf']}'")
    if "ano" in filtros and int(filtros["ano"]) in (2023, 2024, 2025, 2026):
        clausulas_base.append(f"year(competencia) = {int(filtros['ano'])}")
    where_base = f"where {' and '.join(clausulas_base)}" if clausulas_base else ""

    where_final = ""
    if "nivel" in filtros and filtros["nivel"] in ("mensal", "anual", "total"):
        where_final = f"where nivel = '{filtros['nivel']}'"

    codigos_cbo = filtros.get("codigos_cbo")
    if not codigos_cbo:
        corpo_base = f"""select *, year(competencia)::integer as ano
    from gold.fct_geografia_mensal
    {where_base}"""
    else:
        lista_cbo = ", ".join(f"'{str(c).zfill(6)}'" for c in codigos_cbo)
        conds = [
            "f.is_identificado",
            "f.is_centro_oeste",
            "f.ano between 2023 and 2026",
            f"f.codigo_cbo in ({lista_cbo})",
        ]
        if clausulas_base:
            conds.extend(clausulas_base)
        corpo_base = f"""select
        f.competencia, f.sigla_uf, f.is_capital,
        count(*) filter (where f.saldo_movimentacao = 1) as admissoes,
        count(*) filter (where f.saldo_movimentacao = -1) as desligamentos,
        coalesce(sum(f.saldo_movimentacao), 0) as saldo,
        coalesce(sum(case when f.saldo_movimentacao = 1 and f.salario_valido then f.salario_mensal else 0 end), 0) as soma_salarios_admissao,
        count(*) filter (where f.saldo_movimentacao = 1 and f.salario_valido) as qtd_salarios_admissao,
        year(f.competencia)::integer as ano
    from gold.fct_movimentacao f
    where {' and '.join(conds)}
    group by f.competencia, f.sigla_uf, f.is_capital"""

    return f"""with base as (
    {corpo_base}
), grupos as (
    select competencia, ano,
           case when grouping(sigla_uf) = 1 then 'Centro-Oeste' else sigla_uf end as recorte,
           case when grouping(competencia) = 0 then 'mensal'
                when grouping(ano) = 0 then 'anual' else 'total' end as nivel,
           is_capital,
           sum(admissoes) as admissoes, sum(desligamentos) as desligamentos,
           sum(saldo) as saldo,
           sum(soma_salarios_admissao) / nullif(sum(qtd_salarios_admissao), 0) as salario,
           sum(qtd_salarios_admissao) as n_salarios
    from base
    group by grouping sets (
        (competencia, sigla_uf, is_capital), (competencia, is_capital),
        (ano, sigla_uf, is_capital), (ano, is_capital),
        (sigla_uf, is_capital), (is_capital)
    )
), comparacao as (
    select nivel, competencia, ano, recorte,
           max(admissoes) filter (where is_capital) as admissoes_capital,
           max(admissoes) filter (where not is_capital) as admissoes_interior,
           max(desligamentos) filter (where is_capital) as desligamentos_capital,
           max(desligamentos) filter (where not is_capital) as desligamentos_interior,
           max(saldo) filter (where is_capital) as saldo_capital,
           max(saldo) filter (where not is_capital) as saldo_interior,
           max(salario) filter (where is_capital) as salario_capital,
           max(salario) filter (where not is_capital) as salario_interior,
           coalesce(max(n_salarios) filter (where is_capital), 0) as n_capital,
           coalesce(max(n_salarios) filter (where not is_capital), 0) as n_interior
    from grupos group by nivel, competencia, ano, recorte
)
select *,
       saldo_capital - saldo_interior as diferenca_saldo,
       salario_capital - salario_interior as diferenca_salario
from comparacao
{where_final}
order by nivel, competencia nulls last, ano nulls last, recorte"""


def _gerar_sql_p4(filtros: dict[str, Any]) -> str:
    clausulas_extra: list[str] = []
    if "sigla_uf" in filtros and filtros["sigla_uf"] in ("DF", "GO", "MT", "MS"):
        clausulas_extra.append(f"and sigla_uf = '{filtros['sigla_uf']}'")
    if "ano" in filtros and int(filtros["ano"]) in (2023, 2024, 2025, 2026):
        clausulas_extra.append(f"and year(competencia) = {int(filtros['ano'])}")
    where_extra = f"where codigo_secao <> 'Z' {' '.join(clausulas_extra)}".strip()
    corpo_base = _cte_base_setor_mensal(filtros, where_extra)

    return f"""with base as (
    {corpo_base}
), totais as (
    select codigo_secao,
           sum(admissoes) as admissoes, sum(desligamentos) as desligamentos,
           sum(saldo) as saldo,
           sum(soma_salarios_admissao) as soma_salarios_admissao,
           sum(qtd_salarios_admissao) as qtd_salarios_admissao
    from base group by codigo_secao
), setores as (
    select *, soma_salarios_admissao / nullif(qtd_salarios_admissao, 0) as salario_medio_admissao,
           200.0 * least(admissoes, desligamentos)
               / nullif(admissoes + desligamentos, 0) as indice_fluxos_pareados_pct
    from totais
), pares as (
    select * from setores
    where indice_fluxos_pareados_pct is not null and salario_medio_admissao is not null
), correlacao as (
    select count(*) as pares_validos,
           case when count(*) >= 3
                  and stddev_pop(indice_fluxos_pareados_pct) > 0
                  and stddev_pop(salario_medio_admissao) > 0
                then corr(indice_fluxos_pareados_pct, salario_medio_admissao)
           end as correlacao_pearson
    from pares
)
select s.*, c.pares_validos, c.correlacao_pearson
from setores s cross join correlacao c
order by codigo_secao"""


def _gerar_sql_p5(filtros: dict[str, Any]) -> str:
    clausulas_base: list[str] = []
    if "sigla_uf" in filtros and filtros["sigla_uf"] in ("DF", "GO", "MT", "MS"):
        clausulas_base.append(f"f.sigla_uf = '{filtros['sigla_uf']}'")
    if "ano" in filtros and int(filtros["ano"]) in (2023, 2024, 2025, 2026):
        clausulas_base.append(f"year(f.competencia) = {int(filtros['ano'])}")
    where_base = f"where {' and '.join(clausulas_base)}" if clausulas_base else ""

    where_eixo = ""
    if "eixo" in filtros and filtros["eixo"] in ("sexo", "raca_cor", "escolaridade", "faixa_etaria"):
        where_eixo = f"where eixo = '{filtros['eixo']}'"

    codigos_cbo = filtros.get("codigos_cbo")
    if not codigos_cbo:
        corpo_base = f"""select f.*, p.* exclude (id_perfil_demografico)
    from gold.fct_perfil_mensal f
    left join gold.dim_perfil_demografico p using (id_perfil_demografico)
    {where_base}"""
    else:
        lista_cbo = ", ".join(f"'{str(c).zfill(6)}'" for c in codigos_cbo)
        conds = [
            "f.is_identificado",
            "f.is_centro_oeste",
            "f.ano between 2023 and 2026",
            f"f.codigo_cbo in ({lista_cbo})",
        ]
        if clausulas_base:
            conds.extend(clausulas_base)
        corpo_base = f"""select
        f.sigla_uf, f.is_capital, f.codigo_secao,
        p.codigo_sexo, p.sexo,
        p.codigo_raca_cor, p.raca_cor,
        p.codigo_grau_instrucao, p.escolaridade,
        p.codigo_faixa_etaria, p.faixa_etaria,
        count(*) filter (where f.saldo_movimentacao = 1) as admissoes,
        count(*) filter (where f.saldo_movimentacao = -1) as desligamentos,
        coalesce(sum(f.saldo_movimentacao), 0) as saldo,
        coalesce(sum(case when f.saldo_movimentacao = 1 and f.salario_valido then f.salario_mensal else 0 end), 0) as soma_salarios_admissao,
        count(*) filter (where f.saldo_movimentacao = 1 and f.salario_valido) as qtd_salarios_admissao
    from gold.fct_movimentacao f
    left join gold.dim_perfil_demografico p using (id_perfil_demografico)
    where {' and '.join(conds)}
    group by
        f.sigla_uf, f.is_capital, f.codigo_secao,
        p.codigo_sexo, p.sexo,
        p.codigo_raca_cor, p.raca_cor,
        p.codigo_grau_instrucao, p.escolaridade,
        p.codigo_faixa_etaria, p.faixa_etaria"""

    return f"""with base as (
    {corpo_base}
), eixos as (
    select b.sigla_uf, b.is_capital, b.codigo_secao,
           e.eixo, e.codigo_categoria, e.categoria,
           b.admissoes, b.desligamentos, b.saldo,
           b.soma_salarios_admissao, b.qtd_salarios_admissao
    from base b
    cross join lateral (values
        ('sexo', b.codigo_sexo, b.sexo),
        ('raca_cor', b.codigo_raca_cor, b.raca_cor),
        ('escolaridade', b.codigo_grau_instrucao, b.escolaridade),
        ('faixa_etaria', b.codigo_faixa_etaria, b.faixa_etaria)
    ) e(eixo, codigo_categoria, categoria)
), grupos as (
    select sigla_uf, is_capital, codigo_secao, eixo, codigo_categoria, categoria,
           sum(admissoes) as admissoes, sum(desligamentos) as desligamentos,
           sum(saldo) as saldo,
           sum(soma_salarios_admissao) as soma_salarios_admissao,
           sum(qtd_salarios_admissao) as qtd_salarios_admissao
    from eixos group by sigla_uf, is_capital, codigo_secao, eixo, codigo_categoria, categoria
), referencias as (
    select *, soma_salarios_admissao / nullif(qtd_salarios_admissao, 0) as salario_medio_admissao,
           sum(admissoes) over recorte as admissoes_recorte,
           sum(soma_salarios_admissao) over recorte
               / nullif(sum(qtd_salarios_admissao) over recorte, 0) as salario_medio_recorte
    from grupos
    window recorte as (partition by sigla_uf, is_capital, codigo_secao, eixo)
)
select *,
       100.0 * admissoes / nullif(admissoes_recorte, 0) as participacao_admissoes_pct,
       salario_medio_admissao - salario_medio_recorte as diferenca_salarial,
       100.0 * (salario_medio_admissao - salario_medio_recorte)
           / nullif(salario_medio_recorte, 0) as diferenca_salarial_pct
from referencias
{where_eixo}
order by sigla_uf, is_capital, codigo_secao, eixo, codigo_categoria"""


def _gerar_sql_cbo(codigos_cbo: list[str], filtros: dict[str, Any]) -> str:
    lista_sql = ", ".join(f"'{c.zfill(6)}'" for c in codigos_cbo)
    clausulas_f = [
        "f.is_identificado",
        "f.is_centro_oeste",
        "f.ano between 2023 and 2026",
    ]
    if "sigla_uf" in filtros and filtros["sigla_uf"] in ("DF", "GO", "MT", "MS"):
        clausulas_f.append(f"f.sigla_uf = '{filtros['sigla_uf']}'")
    if "ano" in filtros and int(filtros["ano"]) in (2023, 2024, 2025, 2026):
        clausulas_f.append(f"f.ano = {int(filtros['ano'])}")
    cond_f = " and ".join(clausulas_f)

    return f"""select
    c.codigo_cbo,
    c.titulo_ocupacao,
    c.is_cadastro_oficial,
    coalesce(count(f.id_movimentacao) filter (where f.saldo_movimentacao = 1), 0) as admissoes,
    coalesce(count(f.id_movimentacao) filter (where f.saldo_movimentacao = -1), 0) as desligamentos,
    coalesce(sum(f.saldo_movimentacao), 0) as saldo,
    coalesce(count(f.id_movimentacao) filter (where f.saldo_movimentacao = 1 and f.salario_valido), 0) as qtd_salarios_admissao,
    sum(case when f.saldo_movimentacao = 1 and f.salario_valido then f.salario_mensal else 0 end)
        / nullif(count(f.id_movimentacao) filter (where f.saldo_movimentacao = 1 and f.salario_valido), 0) as salario_medio_admissao
from gold.dim_cbo c
left join gold.fct_movimentacao f
    on c.codigo_cbo = f.codigo_cbo
   and {cond_f}
where c.codigo_cbo in ({lista_sql})
group by c.codigo_cbo, c.titulo_ocupacao, c.is_cadastro_oficial
order by admissoes desc, c.codigo_cbo asc"""


def _detectar_violacao_ou_fora_escopo(pergunta: str) -> tuple[str | None, str | None]:
    """Verifica se a pergunta tenta violar segurança/LGPD ou pede conceitos fora do catálogo."""
    bruto = (pergunta or "").strip()
    bruto_lower = bruto.lower()
    norm = normalizar_texto(bruto)

    # 1. Tentativas explícitas de SQL injection, DDL/DML, SELECT * bruto ou leitura de arquivos externos
    padroes_ataque = (
        r"\b(drop|delete|insert|update|alter|truncate|attach|copy|pragma|install|load)\b",
        r"\b(read_csv|read_parquet|read_json|delta_scan|postgres_scan|read_text|read_blob)\b",
        r";\s*(select|drop|delete|insert|update)",
        r"\bselect\s+(?:distinct\s+)?(?:[a-z_][a-z0-9_]*\.)?\*\s+from\b",
        r"\b(?:from|join)\s+'[^']*'",
    )
    for pad in padroes_ataque:
        if re.search(pad, bruto_lower):
            return (
                "bloqueada_seguranca",
                "Operação bloqueada pelos guardrails de segurança (ADR 0007): comandos de escrita, "
                "alteração de esquema, múltiplas instruções, 'SELECT *' ou leitura de arquivos externos não são permitidos.",
            )

    # Se o usuário enviou diretamente uma instrução SQL iniciada por SELECT ou WITH, valida sua estrutura
    if re.match(r"^(?:select|with)\b", bruto_lower):
        try:
            validar_sql_seguro(bruto)
        except ViolacaoSegurancaSQL as exc:
            return ("bloqueada_seguranca", str(exc))

    # 2. Tentativa de acesso a dados individuais / desagregados (violação LGPD / k-anonimato)
    if _contem_termo(
        norm,
        (
            "cpf", "rg", "pis", "pasep", "ctps",
            "nome do trabalhador", "dados individuais", "registro individual", "registros individuais",
            "listar trabalhadores", "lista de pessoas", "microdado bruto", "microdados brutos",
            "sem agrupar", "linha por linha", "cada trabalhador",
        ),
    ):
        return (
            "bloqueada_seguranca",
            "Consulta recusada por governança e privacidade (LGPD): o catálogo expõe exclusivamente "
            "indicadores estatísticos agregados da camada Gold, vedando a listagem de eventos individuais.",
        )

    # 3. Conceitos fora do escopo metodológico do CAGED / camada Gold (comparados por palavra inteira)
    if _contem_termo(
        norm,
        (
            "taxa de desemprego", "pnad", "pnadc",
            "estoque total de empregados", "estoque de vinculos", "estoque total de vinculos",
            "rais", "previsao para 2027", "previsao para 2028", "prever salario",
            "probabilidade de eu ser contratado", "chance individual de recolocacao",
            "efeito causal", "inflacao ipca",
        ),
    ):
        return (
            "nao_suportada",
            "Pergunta fora do escopo metodológico do catálogo Gold: o Novo CAGED registra fluxos mensais "
            "(admissões e desligamentos), não fornecendo estoque total de vínculos (RAIS), taxa de desemprego "
            "(PNAD/IBGE), previsões futuras ou probabilidade individual de recolocação.",
        )

    return None, None


def _extrair_termo_ocupacao(pergunta: str) -> str | None:
    """Extrai o termo de cargo/ocupação quando a pergunta solicita indicadores ou filtro de profissão."""
    norm = normalizar_texto(pergunta)

    # Se menciona código CBO explícito
    m_cbo = re.search(r"\bcbo\s*(\d{4}-?\d{2})\b", norm)
    if m_cbo:
        return m_cbo.group(1)

    gatilhos_ocupacao = (
        "ocupacao", "ocupacoes", "cargo", "cargos", "profissao", "profissoes",
        "cbo", "programador", "desenvolvedor", "engenheiro", "arquiteto", "medico", "medica",
        "enfermeiro", "enfermeira", "tecnico de enfermagem", "dentista", "farmaceutico",
        "psicologo", "nutricionista", "fisioterapeuta", "veterinario", "biomedico",
        "motorista", "caminhoneiro", "carreteiro", "pedreiro", "servente", "carpinteiro",
        "pintor", "vendedor", "vendedora", "balconista", "operador de caixa",
        "caixa de supermercado", "telemarketing", "call center", "professor", "professora",
        "professores", "docente", "advogado", "contador", "administrador", "gerente",
        "diretor", "faxineiro", "auxiliar de limpeza", "vigilante", "porteiro", "cozinheiro",
        "garcom", "trabalhador rural", "trabalhadores rurais", "rurais", "tratorista",
        "boia fria", "agronomo", "eletricista",
        "mecanico", "soldador", "almoxarife", "estoquista", "repositor", "auxiliar administrativo",
        "assistente administrativo", "auxiliar de escritorio", "recepcionista", "secretaria",
        "acougueiro", "padeiro", "motoboy", "cabeleireiro", "cuidador", "jornalista",
        "designer", "cientista de dados", "analista de dados", "analista de sistemas",
    )
    if not _contem_termo(norm, gatilhos_ocupacao):
        return None

    # Remove palavras de comando, eixos demográficos e recortes geográficos para isolar a profissão
    remover = {
        "qual", "quais", "quanto", "quantos", "quantas", "como", "esta", "estao",
        "o", "a", "os", "as", "de", "do", "da", "dos", "das", "em", "no", "na",
        "nos", "nas", "para", "por", "com", "e", "ou", "um", "uma", "uns", "umas",
        "salario", "salarios", "medio", "medios",
        "remuneracao", "media", "saldo", "liquido", "admissoes", "contratacoes",
        "demissoes", "desligamentos", "movimentacoes", "empregos", "vagas", "indicadores",
        "centro", "oeste", "distrito", "federal", "goias", "mato", "grosso", "sul",
        "df", "go", "mt", "ms", "2023", "2024", "2025", "2026", "ocupacao", "ocupacoes",
        "cargo", "cargos", "profissao", "profissoes", "cbo", "ganha", "recebe", "tem",
        "teve", "houve", "diferenca", "diferencas", "salarial", "salariais", "entre",
        "homem", "mulher", "homens", "mulheres", "sexo", "genero", "masculino", "feminino",
        "raca", "cor", "branca", "preta", "parda", "indigena", "amarela", "negros",
        "negras", "pardos", "pardas", "escolaridade", "instrucao", "grau", "impacta",
        "impacto", "idade", "faixa", "etaria", "capital", "capitais", "interior",
        "sazonalidade", "sazonal", "meses", "ano", "anos", "mensal", "anual", "ao",
        "longo", "rotatividade", "turnover", "setor", "setores", "economico", "economicos",
        "cnae", "secao", "ultimos", "12", "mais", "contratou", "demitiu", "existe",
        "praticam", "baixos", "perfil", "sociodemografico", "demografico", "nivel", "abaixo",
    }
    tokens_restantes = [t for t in norm.split() if t not in remover]
    if not tokens_restantes:
        return None
    return " ".join(tokens_restantes)


class AssistenteTextToSQL:
    """Tradutor e executor Text-to-SQL controlado pelo catálogo de métricas Gold (ADR 0007)."""

    def __init__(self, indice_cbo: IndiceVetorialCBO | None = None):
        self.indice_cbo = indice_cbo

    def _obter_indice(self, conn: duckdb.DuckDBPyConnection) -> IndiceVetorialCBO:
        if self.indice_cbo is None:
            self.indice_cbo = IndiceVetorialCBO.de_conexao_duckdb(conn)
        return self.indice_cbo

    def classificar_intencao(self, pergunta: str) -> str:
        """Identifica qual contrato analítico da camada Gold responde à pergunta."""
        norm = normalizar_texto(pergunta)
        if not norm:
            return "nao_suportada"

        motivo_bloqueio, _ = _detectar_violacao_ou_fora_escopo(pergunta)
        if motivo_bloqueio:
            return motivo_bloqueio

        # P3: Capital vs. Interior (Pergunta Central)
        if _contem_termo(norm, ("capital", "capitais", "interior")):
            return "p3_capitais_interior"

        # P2: Sazonalidade / Série Mensal
        if _contem_termo(
            norm,
            (
                "sazonalidade", "sazonal", "fim de ano", "meses do ano",
                "variacao mensal", "serie mensal", "ciclo mensal", "quarto trimestre",
            ),
        ):
            return "p2_sazonalidade"

        # P4: Rotatividade / Turnover / Equilíbrio de Fluxos Pareados e Correlação com Salário
        if _contem_termo(
            norm,
            (
                "rotatividade", "turnover", "fluxos pareados", "equilibrio dos fluxos",
                "correlacao", "pearson", "praticam salarios", "salarios mais baixos",
            ),
        ):
            return "p4_fluxos_salarios"

        # P5: Perfil Sociodemográfico (Sexo, Raça/Cor, Escolaridade, Idade/Faixa Etária)
        if _contem_termo(
            norm,
            (
                "idade", "sociodemografico", "demografico", "perfil", "genero", "sexo",
                "raca", "racas", "raca cor", "por cor", "cor ou raca",
                "escolaridade", "grau de instrucao", "faixa etaria",
                "mulheres", "homens", "homem", "mulher", "masculino", "feminino",
                "negras", "negros", "pardas", "pardos", "branca", "preta", "indigenas",
                "mestrado", "doutorado", "ensino medio", "superior completo",
            ),
        ):
            return "p5_perfil_remuneracao"

        # P1: Ranking de setores econômicos (CNAE) no DF / últimos 12 meses
        if _contem_termo(
            norm,
            (
                "setor", "setores", "cnae", "secao", "ultimos 12 meses",
                "mais contratou", "mais demitiu", "ranking de admissoes",
            ),
        ):
            return "p1_setores_df"

        # Consulta por Ocupação / Cargo (CBO 2002 via Busca Semântica)
        if _extrair_termo_ocupacao(pergunta) is not None:
            return "cbo_ocupacao"

        return "nao_suportada"

    def responder(
        self,
        conn: duckdb.DuckDBPyConnection,
        pergunta: str,
        top_k_cbo: int = 3,
        filtro_cargo: str | None = None,
        codigos_cbo_override: list[str] | None = None,
        sigla_uf_override: str | None = None,
        ano_override: int | None = None,
        eixo_override: str | None = None,
    ) -> RespostaTextToSQL:
        """Traduz a pergunta para o contrato SQL Gold, valida guardrails e executa em modo leitura."""
        texto = (pergunta or "").strip()
        if not texto:
            return RespostaTextToSQL(
                pergunta_original=texto,
                suportada=False,
                intencao="nao_suportada",
                titulo_intencao="Pergunta vazia",
                filtros_aplicados={},
                formula_metrica="N/A",
                ressalva_metodologica="Informe uma pergunta sobre as métricas do catálogo Gold.",
                sql_gerado="",
                colunas=[],
                linhas=[],
                ocupacoes_resolvidas=[],
                motivo_recusa="A pergunta fornecida está vazia.",
            )

        tipo_bloqueio, msg_bloqueio = _detectar_violacao_ou_fora_escopo(texto)
        if tipo_bloqueio:
            return RespostaTextToSQL(
                pergunta_original=texto,
                suportada=False,
                intencao=tipo_bloqueio,
                titulo_intencao=(
                    "Bloqueio de Segurança / Governança"
                    if tipo_bloqueio == "bloqueada_seguranca"
                    else "Consulta Fora do Escopo do Catálogo"
                ),
                filtros_aplicados={},
                formula_metrica="N/A",
                ressalva_metodologica=msg_bloqueio or "",
                sql_gerado="",
                colunas=[],
                linhas=[],
                ocupacoes_resolvidas=[],
                motivo_recusa=msg_bloqueio,
            )

        intencao = self.classificar_intencao(texto)
        filtros = _extrair_filtros_pergunta(texto)
        if sigla_uf_override and sigla_uf_override in ("DF", "GO", "MT", "MS"):
            filtros["sigla_uf"] = sigla_uf_override
        if ano_override and int(ano_override) in (2023, 2024, 2025, 2026):
            filtros["ano"] = int(ano_override)
        if eixo_override and eixo_override in ("sexo", "raca_cor", "escolaridade", "faixa_etaria"):
            filtros["eixo"] = eixo_override

        ocupacoes_resolvidas: list[dict[str, Any]] = []

        # Se a consulta for analítica (P1 a P5) e contiver um cargo/profissão (na pergunta ou no filtro UI),
        # resolve os códigos CBO via busca semântica para aplicar o drill-down por cargo!
        if intencao in (
            "p1_setores_df",
            "p2_sazonalidade",
            "p3_capitais_interior",
            "p4_fluxos_salarios",
            "p5_perfil_remuneracao",
        ):
            termo_cbo_composto = (filtro_cargo or "").strip() or _extrair_termo_ocupacao(texto)
            if codigos_cbo_override:
                indice = self._obter_indice(conn)
                mapa_reg = {r.codigo_cbo: r for r in indice.registros}
                cods_limpos = [str(c).zfill(6) for c in codigos_cbo_override]
                filtros["codigos_cbo"] = cods_limpos
                if termo_cbo_composto:
                    filtros["termo_ocupacao"] = termo_cbo_composto
                    filtros["termo_busca_cbo"] = termo_cbo_composto
                ocupacoes_resolvidas = [
                    {
                        "codigo_cbo": c,
                        "titulo_ocupacao": mapa_reg[c].titulo_ocupacao if c in mapa_reg else c,
                        "codigo_grande_grupo": mapa_reg[c].codigo_grande_grupo if c in mapa_reg else c[0],
                        "score": 1.0,
                        "is_cadastro_oficial": mapa_reg[c].is_cadastro_oficial if c in mapa_reg else True,
                        "versao_indice": indice.versao_indice,
                        "metodo": "selecao_usuario",
                    }
                    for c in cods_limpos
                ]
            elif termo_cbo_composto:
                indice = self._obter_indice(conn)
                res_cbo = indice.buscar_semantico(termo_cbo_composto, top_k=top_k_cbo, apenas_oficiais=True)
                if not res_cbo:
                    res_cbo = indice.buscar_semantico(termo_cbo_composto, top_k=top_k_cbo, apenas_oficiais=False)
                if res_cbo:
                    ocupacoes_resolvidas = [r.to_dict() for r in res_cbo]
                    filtros["codigos_cbo"] = [r.codigo_cbo for r in res_cbo]
                    filtros["termo_ocupacao"] = termo_cbo_composto
                    filtros["termo_busca_cbo"] = termo_cbo_composto

        sufixo_cargo = (
            f" — Cargo: {filtros['termo_ocupacao']}"
            if filtros.get("termo_ocupacao")
            else (
                f" — CBOs: {', '.join(filtros['codigos_cbo'])}"
                if filtros.get("codigos_cbo") and intencao != "cbo_ocupacao"
                else ""
            )
        )

        if intencao == "p1_setores_df":
            sql = _gerar_sql_p1(filtros)
            recorte_janela = f"Ano {filtros['ano']}" if filtros.get("ano") else "Janela de 12 Meses"
            titulo = f"P1 — Ranking de Setores Econômicos (CNAE) em {filtros.get('sigla_uf', 'DF')} ({recorte_janela}){sufixo_cargo}"
            formula = (
                "admissoes = SUM(admissoes); desligamentos = SUM(desligamentos); "
                "saldo = SUM(saldo); DENSE_RANK() independente para admissões e desligamentos."
            )
            ressalva = (
                "Setor econômico corresponde à seção CNAE (excluindo 'Z' dos rankings). "
                "A janela abrange até 12 meses de calendário até a última competência do recorte."
            )
        elif intencao == "p2_sazonalidade":
            sql = _gerar_sql_p2(filtros)
            titulo = f"P2 — Sazonalidade Mensal de Contratações, Desligamentos e Saldo{sufixo_cargo}"
            formula = (
                "media_admissoes_mes = AVG(admissoes) nos anos com 12 competências presentes; "
                "distinção estrita entre mês sem dados (NULL) e zero observado (0)."
            )
            ressalva = (
                "Apenas anos completos (12 competências com dados no recorte) compõem a média histórica mensal "
                "(2026 parcial permanece na série temporal, mas não distorce a média sazonal)."
            )
        elif intencao == "p3_capitais_interior":
            sql = _gerar_sql_p3(filtros)
            titulo = f"P3 — Comparação de Saldo Líquido e Salário Médio de Admissão: Capitais vs. Interior{sufixo_cargo}"
            formula = (
                "diferenca_saldo = saldo_capital - saldo_interior; "
                "salario = SUM(soma_salarios_admissao) / NULLIF(SUM(qtd_salarios_admissao), 0); "
                "diferenca_salario = salario_capital - salario_interior."
            )
            ressalva = (
                "Considera municípios identificados do Centro-Oeste (2023–2026). "
                "O Distrito Federal não possui municípios de interior (campos de interior permanecem NULL e n_interior = 0)."
            )
        elif intencao == "p4_fluxos_salarios":
            sql = _gerar_sql_p4(filtros)
            titulo = f"P4 — Equilíbrio de Fluxos Pareados (Proxy) e Salário Médio por Seção CNAE{sufixo_cargo}"
            formula = (
                "indice_fluxos_pareados_pct = 200.0 * LEAST(admissoes, desligamentos) / NULLIF(admissoes + desligamentos, 0); "
                "correlacao_pearson = CORR(indice_fluxos_pareados_pct, salario_medio_admissao)."
            )
            ressalva = (
                "O índice mede o equilíbrio entre entradas e saídas (0 a 100%), e NÃO a taxa convencional de "
                "turnover sobre o estoque de vínculos (indisponível no CAGED)."
            )
        elif intencao == "p5_perfil_remuneracao":
            sql = _gerar_sql_p5(filtros)
            titulo = f"P5 — Remuneração Média de Admissão e Participação por Perfil Sociodemográfico{sufixo_cargo}"
            formula = (
                "participacao_admissoes_pct = 100.0 * admissoes / NULLIF(admissoes_recorte, 0); "
                "diferenca_salarial = salario_medio_admissao - salario_medio_recorte."
            )
            ressalva = (
                "Análise descritiva sobre eventos formais registrados; não mede identidade de gênero autodeclarada "
                "além do cadastro CAGED nem estima probabilidade individual de recolocação."
            )
        elif intencao == "cbo_ocupacao":
            termo_cbo = (filtro_cargo or "").strip() or _extrair_termo_ocupacao(texto) or texto
            indice = self._obter_indice(conn)
            if codigos_cbo_override:
                mapa_reg = {r.codigo_cbo: r for r in indice.registros}
                cods_limpos = [str(c).zfill(6) for c in codigos_cbo_override]
                filtros["codigos_cbo"] = cods_limpos
                filtros["termo_ocupacao"] = termo_cbo
                filtros["termo_busca_cbo"] = termo_cbo
                ocupacoes_resolvidas = [
                    {
                        "codigo_cbo": c,
                        "titulo_ocupacao": mapa_reg[c].titulo_ocupacao if c in mapa_reg else c,
                        "codigo_grande_grupo": mapa_reg[c].codigo_grande_grupo if c in mapa_reg else c[0],
                        "score": 1.0,
                        "is_cadastro_oficial": mapa_reg[c].is_cadastro_oficial if c in mapa_reg else True,
                        "versao_indice": indice.versao_indice,
                        "metodo": "selecao_usuario",
                    }
                    for c in cods_limpos
                ]
            else:
                resultados_cbo = indice.buscar_semantico(termo_cbo, top_k=top_k_cbo, apenas_oficiais=True)
                if not resultados_cbo:
                    resultados_cbo = indice.buscar_semantico(termo_cbo, top_k=top_k_cbo, apenas_oficiais=False)
                if not resultados_cbo:
                    return RespostaTextToSQL(
                        pergunta_original=texto,
                        suportada=False,
                        intencao="nao_suportada",
                        titulo_intencao="Ocupação CBO não localizada no catálogo",
                        filtros_aplicados=filtros,
                        formula_metrica="N/A",
                        ressalva_metodologica="Nenhuma ocupação CBO atingiu similaridade mínima para a consulta.",
                        sql_gerado="",
                        colunas=[],
                        linhas=[],
                        ocupacoes_resolvidas=[],
                        motivo_recusa="Não foram encontradas ocupações CBO compatíveis com o termo informado.",
                    )
                ocupacoes_resolvidas = [r.to_dict() for r in resultados_cbo]
                filtros["codigos_cbo"] = [r.codigo_cbo for r in resultados_cbo]
                filtros["termo_ocupacao"] = termo_cbo
                filtros["termo_busca_cbo"] = termo_cbo

            sql = _gerar_sql_cbo(filtros["codigos_cbo"], filtros)
            titulo = f"Indicadores por Ocupação CBO 2002 (Busca Semântica: '{termo_cbo}')"
            formula = (
                "admissoes = COUNT(*) FILTER (saldo = 1); desligamentos = COUNT(*) FILTER (saldo = -1); "
                "saldo = SUM(saldo_movimentacao); salario_medio_admissao = SUM(salario_valido) / NULLIF(COUNT(salario_valido), 0)."
            )
            ressalva = (
                "Ocupações resolvidas via índice vetorial CBO 2002 (384 dimensões). "
                "Títulos não oficiais '(ATUALIZACAO MTE)' aparecem identificados por is_cadastro_oficial = FALSE."
            )
        else:
            return RespostaTextToSQL(
                pergunta_original=texto,
                suportada=False,
                intencao="nao_suportada",
                titulo_intencao="Pergunta Ambígua ou Não Mapeada no Catálogo Gold",
                filtros_aplicados=filtros,
                formula_metrica="N/A",
                ressalva_metodologica=(
                    "O assistente responde exclusivamente às métricas auditadas do catálogo Gold: "
                    "(P1) Setores no DF, (P2) Sazonalidade mensal, (P3) Capitais vs. Interior, "
                    "(P4) Fluxos pareados vs. Salários, (P5) Perfil sociodemográfico e consultas por Ocupação CBO."
                ),
                sql_gerado="",
                colunas=[],
                linhas=[],
                ocupacoes_resolvidas=[],
                motivo_recusa=(
                    "A pergunta não pôde ser associada com segurança a uma métrica homologada do catálogo Gold. "
                    "Reformule especificando o indicador desejado (ex.: saldo, salário médio de admissão, "
                    "sazonalidade, capital vs. interior, perfil demográfico ou ocupação CBO)."
                ),
            )

        validar_sql_seguro(sql)
        try:
            conn.execute("SET enable_external_access = false; SET lock_configuration = true;")
        except duckdb.Error:
            pass
        relacao = conn.sql(sql)
        colunas = list(relacao.columns)
        linhas = relacao.fetchall()

        return RespostaTextToSQL(
            pergunta_original=texto,
            suportada=True,
            intencao=intencao,
            titulo_intencao=titulo,
            filtros_aplicados=filtros,
            formula_metrica=formula,
            ressalva_metodologica=ressalva,
            sql_gerado=sql,
            colunas=colunas,
            linhas=linhas,
            ocupacoes_resolvidas=ocupacoes_resolvidas,
            motivo_recusa=None,
        )
