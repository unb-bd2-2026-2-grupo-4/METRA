"""Compilador Python da camada semântica do METRA (E4).

Lê a definição única das métricas em ``dbt_metra/models/semantic/metricas.yml`` (a
mesma que o dbt valida e que o macro ``metrica()`` usa para materializar os marts) e
gera o SQL de cada métrica para os consumidores: painel Streamlit, assistente
Text-to-SQL, exportação JSON e ETL reverso. Nenhum consumidor escreve fórmula própria.

Duas origens de dados:

* ``"evento"``: ``gold.fct_movimentacao``, um registro por movimentação. Cada medida
  aplica o seu ``agg`` à sua ``expr``.
* ``"agregado"``: marts ou CTEs que já trazem as medidas aditivas como colunas
  (``admissoes``, ``soma_salarios_admissao``...). A recomposição é ``sum(<medida>)``,
  o que garante média ponderada e nunca média simples de médias.

O SQL gerado é idêntico ao do macro dbt ``metrica()`` em ``dbt_metra/macros/metricas.sql``.
"""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
import os
from pathlib import Path
import re
from typing import Any, Iterable, Mapping, Sequence

import yaml

RAIZ = Path(__file__).resolve().parents[2]
ARQUIVO_METRICAS_PADRAO = RAIZ / "dbt_metra" / "models" / "semantic" / "metricas.yml"
ORIGENS = ("evento", "agregado")

# Listas brancas para consultas montadas a partir de entrada externa.
UFS_VALIDAS = frozenset({"DF", "GO", "MT", "MS"})
ANOS_VALIDOS = frozenset({2023, 2024, 2025, 2026})
SECOES_CNAE_VALIDAS = frozenset("ABCDEFGHIJKLMNOPQRSTUZ")
TABELAS_AGREGADAS = frozenset({
    "gold.fct_setor_mensal", "gold.fct_geografia_mensal", "gold.fct_perfil_mensal",
})
TABELA_EVENTOS = "gold.fct_movimentacao"
DIMENSOES_VALIDAS = {
    "competencia": "competencia",
    "ano": "year(competencia)",
    "sigla_uf": "sigla_uf",
    "is_capital": "is_capital",
    "codigo_secao": "codigo_secao",
    "id_perfil_demografico": "id_perfil_demografico",
}


class MetricaDesconhecida(KeyError):
    """A métrica pedida não está definida em metricas.yml."""


@dataclass(frozen=True)
class Metrica:
    """Metadados de catálogo de uma métrica (para painel, JSON e documentação)."""

    nome: str
    label: str
    descricao: str
    tipo: str
    unidade: str
    formato: str
    ressalva: str
    sinonimos: tuple[str, ...] = ()


@dataclass(frozen=True)
class DimensaoConsulta:
    """Dimensão pela qual o canal público agrupa métricas, com o vocabulário da pergunta."""

    nome: str
    label: str
    colecoes: tuple[str, ...]
    sinonimos: tuple[str, ...]
    eixo: str | None = None


def _arquivo_metricas() -> Path:
    return Path(os.environ.get("METRA_METRICAS_YML", str(ARQUIVO_METRICAS_PADRAO)))


@lru_cache(maxsize=4)
def _carregar(caminho: str) -> dict[str, Any]:
    with open(caminho, encoding="utf-8") as arquivo:
        dados = yaml.safe_load(arquivo)
    medidas: dict[str, dict[str, Any]] = {}
    recorte = None
    dimensoes: list[dict[str, Any]] = []
    for sm in dados.get("semantic_models", []):
        for medida in sm.get("measures", []):
            medidas[medida["name"]] = medida
        meta = (sm.get("config") or {}).get("meta") or {}
        recorte = recorte or meta.get("recorte_padrao")
        dimensoes.extend(meta.get("dimensoes_consulta") or [])
    metricas = {mt["name"]: mt for mt in dados.get("metrics", [])}
    return {"medidas": medidas, "metricas": metricas, "recorte_padrao": recorte,
            "dimensoes_consulta": dimensoes}


def definicao() -> dict[str, Any]:
    """Definição carregada (medidas, métricas, recorte padrão e dimensões de consulta)."""
    return _carregar(str(_arquivo_metricas()))


def _nome_ref(ref: Any) -> str:
    return ref["name"] if isinstance(ref, Mapping) else str(ref)


def _sql_medida(nome: str, origem: str, janela: str | None = None) -> str:
    medida = definicao()["medidas"][nome]
    if origem == "agregado":
        return f"sum({nome})" + (f" over {janela}" if janela else "")
    return f"{medida['agg']}({medida.get('expr') or nome})"


def expressao(nome: str, origem: str = "agregado", janela: str | None = None) -> str:
    """SQL da métrica ``nome`` para a ``origem`` indicada ("evento" ou "agregado").

    ``janela`` (só com origem "agregado") recompõe a métrica sobre uma janela nomeada
    da consulta, por exemplo ``janela="recorte"`` gera ``sum(x) over recorte``.
    """
    if origem not in ORIGENS:
        raise ValueError(f"origem inválida: {origem!r}; use {ORIGENS}")
    if janela is not None and (origem != "agregado" or not re.fullmatch(r"[a-z_][a-z0-9_]*", janela)):
        raise ValueError(f"janela inválida: {janela!r}")
    metricas = definicao()["metricas"]
    if nome not in metricas:
        raise MetricaDesconhecida(nome)
    mt = metricas[nome]
    tp = mt.get("type_params") or {}
    tipo = mt["type"]
    if tipo == "simple":
        return _sql_medida(_nome_ref(tp["measure"]), origem, janela)
    if tipo == "ratio":
        num = expressao(_nome_ref(tp["numerator"]), origem, janela)
        den = expressao(_nome_ref(tp["denominator"]), origem, janela)
        return f"{num} / nullif({den}, 0)"
    if tipo == "derived":
        # Duas passadas com marcadores, como no macro dbt: nada é substituído duas vezes.
        filhas = [_nome_ref(f) for f in tp.get("metrics", [])]
        sql = tp["expr"]
        for i, filha in enumerate(filhas):
            sql = re.sub(rf"\b{re.escape(filha)}\b", f"@@{i}@@", sql)
        for i, filha in enumerate(filhas):
            sql = sql.replace(f"@@{i}@@", f"({expressao(filha, origem, janela)})")
        return sql
    raise ValueError(f"tipo de métrica não suportado: {tipo}")


def colunas_select(nomes: Iterable[str], origem: str = "agregado", prefixo: str = "") -> str:
    """Trecho de SELECT ``<sql> as <prefixo><nome>`` para as métricas pedidas."""
    return ",\n    ".join(f"{expressao(n, origem)} as {prefixo}{n}" for n in nomes)


def recorte_padrao() -> str:
    """Recorte de negócio comum aos marts (identificado, Centro-Oeste, 2023-2026)."""
    return definicao()["recorte_padrao"]


def catalogo() -> dict[str, Metrica]:
    """Catálogo de métricas com label, descrição, unidade, formato e ressalva."""
    saida: dict[str, Metrica] = {}
    for nome, mt in definicao()["metricas"].items():
        meta = (mt.get("config") or {}).get("meta") or {}
        saida[nome] = Metrica(
            nome=nome,
            label=mt.get("label", nome),
            descricao=" ".join(str(mt.get("description", "")).split()),
            tipo=mt["type"],
            unidade=meta.get("unidade", ""),
            formato=meta.get("formato", ""),
            ressalva=meta.get("ressalva", ""),
            sinonimos=tuple(meta.get("sinonimos") or ()),
        )
    return saida


def catalogo_dimensoes() -> dict[str, DimensaoConsulta]:
    """Dimensões consultáveis no canal público, com coleções e sinônimos."""
    return {
        d["nome"]: DimensaoConsulta(
            nome=d["nome"],
            label=d["label"],
            colecoes=tuple(d["colecoes"]),
            sinonimos=tuple(d["sinonimos"]),
            eixo=d.get("eixo"),
        )
        for d in definicao()["dimensoes_consulta"]
    }


def _filtros_sql(filtros: Mapping[str, Any] | None) -> list[str]:
    """Converte filtros validados por lista branca em cláusulas SQL."""
    clausulas: list[str] = []
    for chave, valor in (filtros or {}).items():
        if valor is None:
            continue
        if chave == "sigla_uf":
            if str(valor).upper() not in UFS_VALIDAS:
                raise ValueError(f"UF fora do recorte: {valor!r}")
            clausulas.append(f"sigla_uf = '{str(valor).upper()}'")
        elif chave == "ano":
            if int(valor) not in ANOS_VALIDOS:
                raise ValueError(f"ano fora do recorte: {valor!r}")
            clausulas.append(f"year(competencia) = {int(valor)}")
        elif chave == "codigo_secao":
            if str(valor).upper() not in SECOES_CNAE_VALIDAS:
                raise ValueError(f"seção CNAE inválida: {valor!r}")
            clausulas.append(f"codigo_secao = '{str(valor).upper()}'")
        elif chave == "is_capital":
            clausulas.append("is_capital" if bool(valor) else "not is_capital")
        else:
            raise ValueError(f"filtro não suportado: {chave!r}")
    return clausulas


def montar_consulta(
    metricas: Sequence[str],
    dimensoes: Sequence[str] = (),
    filtros: Mapping[str, Any] | None = None,
    tabela: str = "gold.fct_setor_mensal",
) -> str:
    """SQL de agregação das ``metricas`` por ``dimensoes``, com filtros em lista branca.

    Tabelas agregadas usam origem "agregado"; ``gold.fct_movimentacao`` usa origem
    "evento" e aplica o recorte padrão dos marts.
    """
    if tabela == TABELA_EVENTOS:
        origem = "evento"
        where = [recorte_padrao()]
    elif tabela in TABELAS_AGREGADAS:
        origem = "agregado"
        where = []
    else:
        raise ValueError(f"tabela não permitida: {tabela!r}")
    for dim in dimensoes:
        if dim not in DIMENSOES_VALIDAS:
            raise ValueError(f"dimensão não suportada: {dim!r}")
    where += _filtros_sql(filtros)
    cols_dim = [f"{DIMENSOES_VALIDAS[d]} as {d}" for d in dimensoes]
    select = ",\n    ".join([*cols_dim, colunas_select(metricas, origem)])
    sql = f"select\n    {select}\nfrom {tabela}"
    if where:
        sql += "\nwhere " + " and ".join(f"({c})" for c in where)
    if dimensoes:
        grupo = ", ".join(DIMENSOES_VALIDAS[d] for d in dimensoes)
        sql += f"\ngroup by {grupo}\norder by {grupo}"
    return sql


def consultar(conn, metricas: Sequence[str], dimensoes: Sequence[str] = (),
              filtros: Mapping[str, Any] | None = None,
              tabela: str = "gold.fct_setor_mensal"):
    """Executa :func:`montar_consulta` numa conexão DuckDB e devolve um DataFrame."""
    return conn.execute(montar_consulta(metricas, dimensoes, filtros, tabela)).df()
