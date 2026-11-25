"""Exporta somente as views públicas de consumo; nunca recorre à Gold detalhada."""

import argparse
from dataclasses import asdict
from datetime import date, datetime, timezone
from decimal import Decimal
import hashlib
import json
import math
import os
from pathlib import Path
import tempfile

import duckdb
from filelock import FileLock

from src.metricas.camada_semantica import (
    ANOS_VALIDOS, SECOES_CNAE_VALIDAS, UFS_VALIDAS, catalogo, catalogo_dimensoes, colunas_select,
)

RAIZ = Path(__file__).resolve().parents[2]
DESTINO_PADRAO = RAIZ / "docs/assets/dados/metra.json"
COLECOES = {
    "setores": ("setor_mensal", ("competencia", "sigla_uf", "codigo_secao")),
    "geografia": ("geografia_mensal", ("competencia", "sigla_uf", "is_capital")),
    # Perfis por ano (v2): a P5 só filtra por ano, UF e seção, e o grão mensal levava o
    # arquivo a ~43 MB na base completa, acima do limite do ADR-0008.
    "perfis": ("perfil_anual", (
        "ano", "sigla_uf", "is_capital", "codigo_secao", "eixo", "codigo_categoria",
    )),
}
EIXOS = {"sexo", "raca_cor", "escolaridade", "faixa_etaria"}
METRICAS = (
    "admissoes", "desligamentos", "saldo", "salario_medio_admissao",
    "qtd_salarios_admissao", "indice_fluxos_pareados_pct",
)
CONTAGENS = {"admissoes", "desligamentos", "saldo", "qtd_salarios_admissao"}
RESSALVA = (
    "Somente grupos publicados pelas views de consumo. Grupos com menos de 5 "
    "movimentações são omitidos; medidas salariais com menos de 5 salários válidos "
    "não são divulgadas. Totais recompostos podem ser parciais. Não somar os "
    "diferentes conjuntos nem os eixos demográficos entre si. Perfis demográficos são "
    "anuais; setores e geografia, mensais."
)


def _competencia(valor):
    if type(valor) is not date or valor.day != 1 or valor.year not in ANOS_VALIDOS:
        raise ValueError(f"Competência inválida: {valor!r}; esperado DATE, primeiro dia do mês.")
    return valor.isoformat()


def _validar_registro(registro, dimensoes):
    if "competencia" in registro:
        registro["competencia"] = _competencia(registro["competencia"])
    if "ano" in registro and (type(registro["ano"]) is not int or registro["ano"] not in ANOS_VALIDOS):
        raise ValueError(f"Ano inválido: {registro['ano']!r}; esperado inteiro do recorte.")
    if any(registro[d] is None for d in dimensoes):
        raise ValueError("Dimensão nula na view pública.")
    if registro["sigla_uf"] not in UFS_VALIDAS:
        raise ValueError("UF fora do Centro-Oeste.")
    if "is_capital" in registro and type(registro["is_capital"]) is not bool:
        raise ValueError("is_capital deve ser BOOLEAN.")
    if "codigo_secao" in registro and registro["codigo_secao"] not in SECOES_CNAE_VALIDAS:
        raise ValueError("Seção CNAE inválida.")
    if "eixo" in registro:
        if registro["eixo"] not in EIXOS or not isinstance(registro["categoria"], str):
            raise ValueError("Eixo ou categoria demográfica inválida.")
        if type(registro["codigo_categoria"]) is not int:
            raise ValueError("codigo_categoria deve ser inteiro.")
    for nome in CONTAGENS:
        valor = registro[nome]
        if valor is not None:
            if isinstance(valor, bool) or not isinstance(valor, (int, float, Decimal)):
                raise ValueError(f"{nome} deve ser inteiro.")
            if not math.isfinite(valor) or valor != int(valor):
                raise ValueError(f"{nome} deve ser inteiro finito.")
            registro[nome] = int(valor)
    adm, desl = registro["admissoes"], registro["desligamentos"]
    if adm is None or desl is None or adm < 0 or desl < 0 or adm + desl < 5:
        raise ValueError("A view contém grupo com menos de 5 movimentações ou contagem inválida.")
    if registro["saldo"] != adm - desl:
        raise ValueError("Saldo inconsistente na view pública.")
    soma = registro.pop("soma_salarios_admissao")
    qtd = registro["qtd_salarios_admissao"]
    media = registro["salario_medio_admissao"]
    if qtd is None:
        if soma is not None or media is not None:
            raise ValueError("Supressão salarial incompleta.")
    elif qtd < 5 or qtd > adm or soma is None or not math.isfinite(soma) or soma <= 0:
        raise ValueError("A view contém medidas salariais sem supressão ou inválidas.")
    for nome in ("salario_medio_admissao", "indice_fluxos_pareados_pct"):
        valor = registro[nome]
        if valor is not None:
            if not math.isfinite(valor):
                raise ValueError(f"Métrica não finita: {nome}.")
            registro[nome] = float(valor)


def _ler_publicacao(conn):
    definicoes = catalogo()
    publicacao = {
        "versao_schema": 2,
        "recorte": {"anos": sorted(ANOS_VALIDOS), "ufs": sorted(UFS_VALIDAS), "ressalva": RESSALVA},
        "metricas": {nome: asdict(definicoes[nome]) for nome in METRICAS},
        # Vocabulário da camada semântica: o agente do Pages identifica métrica e
        # dimensão de uma pergunta por esses sinônimos, sem lista própria.
        "dimensoes": {nome: asdict(d) for nome, d in catalogo_dimensoes().items()},
    }
    for colecao, (view, dimensoes) in COLECOES.items():
        colunas = list(dimensoes) + (["categoria"] if colecao == "perfis" else [])
        grupo = ", ".join(colunas)
        cursor = conn.execute(f"""
            select {grupo}, {colunas_select((*METRICAS, 'soma_salarios_admissao'))},
                   count(*) as linhas
            from consumo.{view}
            group by {grupo} order by {grupo}
        """)
        nomes = [c[0] for c in cursor.description]
        registros, chaves = [], set()
        for linha in cursor.fetchall():
            registro = dict(zip(nomes, linha))
            if registro.pop("linhas") != 1:
                raise ValueError(f"Chave duplicada em consumo.{view}.")
            _validar_registro(registro, dimensoes)
            chave = tuple(registro[d] for d in dimensoes)
            if chave in chaves:
                raise ValueError(f"Chave duplicada em consumo.{view}.")
            chaves.add(chave)
            registros.append(registro)
        publicacao[colecao] = registros

    calendario, competencias = [], set()
    for competencia, tem_dados in conn.execute(
        "select competencia, tem_dados from consumo.calendario order by competencia"
    ).fetchall():
        competencia = _competencia(competencia)
        if competencia in competencias or type(tem_dados) is not bool:
            raise ValueError("Calendário com competência duplicada ou tem_dados não booleano.")
        competencias.add(competencia)
        calendario.append({"competencia": competencia, "tem_dados": tem_dados})
    if not calendario or not any(c["tem_dados"] for c in calendario):
        raise ValueError("Calendário público vazio ou sem competências com dados.")
    inicio = date.fromisoformat(calendario[0]["competencia"])
    fim = date.fromisoformat(calendario[-1]["competencia"])
    if len(calendario) != (fim.year - inicio.year) * 12 + fim.month - inicio.month + 1:
        raise ValueError("Calendário público com lacunas entre competências.")
    observadas = {c["competencia"] for c in calendario if c["tem_dados"]}
    anos_observados = {int(c[:4]) for c in observadas}
    for colecao in COLECOES:
        if any(r["competencia"] not in observadas if "competencia" in r else r["ano"] not in anos_observados
               for r in publicacao[colecao]):
            raise ValueError(f"{colecao}: competência ou ano sem dados no calendário.")
    publicacao["calendario"] = calendario
    return publicacao


def exportar(banco, destino):
    """Valida o snapshot público e troca o JSON atomicamente; retorna metadados Dagster."""
    banco, destino = Path(banco).resolve(), Path(destino).resolve()
    if banco == destino:
        raise ValueError("O destino não pode sobrescrever o banco analítico.")
    destino.parent.mkdir(parents=True, exist_ok=True)
    # O container (root) e o operador local compartilham o mesmo lock, sem dados nele.
    with FileLock(destino.with_name(f".{destino.name}.lock"), mode=0o666):
        with duckdb.connect(str(banco), read_only=True) as conn:
            conn.execute("SET enable_external_access = false; SET lock_configuration = true;")
            conn.execute("BEGIN TRANSACTION")
            dados = _ler_publicacao(conn)
            conn.execute("COMMIT")
        conteudo = (json.dumps(dados, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")
        temporario = None
        try:
            with tempfile.NamedTemporaryFile(dir=destino.parent, prefix=".metra-", delete=False) as arquivo:
                temporario = Path(arquivo.name)
                arquivo.write(conteudo)
                os.fchmod(arquivo.fileno(), 0o644)
                arquivo.flush()
                os.fsync(arquivo.fileno())
            temporario.replace(destino)
        finally:
            if temporario is not None:
                temporario.unlink(missing_ok=True)
    observadas = [c["competencia"] for c in dados["calendario"] if c["tem_dados"]]
    return {
        "destino": str(destino),
        "registros": {nome: len(dados[nome]) for nome in (*COLECOES, "calendario")},
        "competencia_inicial": min(observadas), "competencia_final": max(observadas),
        "bytes": len(conteudo), "sha256": hashlib.sha256(conteudo).hexdigest(),
        "executado_em": datetime.now(timezone.utc).isoformat(),
    }


def main():
    from dagster_metra.assets import caminho_banco_analitico

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--banco", type=Path, default=caminho_banco_analitico())
    parser.add_argument("--destino", type=Path,
                        default=Path(os.environ.get("METRA_JSON_DESTINO", DESTINO_PADRAO)))
    args = parser.parse_args()
    print(json.dumps(exportar(args.banco, args.destino), ensure_ascii=False))


if __name__ == "__main__":
    main()
