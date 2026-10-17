#!/usr/bin/env python3
"""Consome log test_decoding e aplica eventos idempotentemente em SQLite.

Uso: python3 src/cdc/04_reprocessar.py [--log data/cdc/eventos.log] [--db data/cdc/replay.sqlite3]
Somente transações COMMIT são aplicadas; fragmentos incompletos são ignorados.
"""
import argparse
import hashlib
import json
import re
import sqlite3
from pathlib import Path

BEGIN = re.compile(r"^BEGIN\s+(\d+)\s*$")
COMMIT = re.compile(r"^COMMIT\s+(\d+)\s*$")
CHANGE = re.compile(r"^table\s+([^:]+):\s+(INSERT|UPDATE|DELETE):\s*(.*)$")


def transacoes(caminho: Path):
    xid, eventos, indice = None, [], 0
    with caminho.open(encoding="utf-8") as arquivo:
        for numero_linha, linha in enumerate(arquivo, 1):
            linha = linha.rstrip("\r\n")
            inicio = BEGIN.fullmatch(linha)
            if inicio:
                xid, eventos, indice = inicio.group(1), [], 0
                continue
            fim = COMMIT.fullmatch(linha)
            if fim:
                if xid is not None and fim.group(1) == xid:
                    yield eventos
                xid, eventos, indice = None, [], 0
                continue
            if xid is None:
                continue
            mudanca = CHANGE.fullmatch(linha)
            if mudanca:
                indice += 1
                tabela, operacao, detalhes = mudanca.groups()
                # Identidade estável para reenvio do mesmo conteúdo do log.
                # xid isolado não é suficiente; combina posição dentro da transação
                # e conteúdo. Adequado para a demonstração local (não é ID global).
                identidade = hashlib.sha256(
                    json.dumps([xid, indice, tabela, operacao, detalhes], ensure_ascii=False).encode("utf-8")
                ).hexdigest()
                eventos.append((identidade, xid, indice, tabela, operacao, detalhes))
            elif linha.strip():
                # Ignorar transações que tenham conteúdos desconhecidos seria mais seguro
                # do que aplicá-las parcialmente.
                xid, eventos, indice = None, [], 0


def inicializar(conexao):
    conexao.execute("""CREATE TABLE IF NOT EXISTS eventos_aplicados (
        evento_id TEXT PRIMARY KEY,
        xid TEXT NOT NULL,
        indice INTEGER NOT NULL,
        tabela TEXT NOT NULL,
        operacao TEXT NOT NULL,
        detalhes TEXT NOT NULL
    )""")


def processar(log: Path, banco: Path):
    banco.parent.mkdir(parents=True, exist_ok=True)
    novos = duplicados = transacoes_confirmadas = 0
    with sqlite3.connect(banco) as conexao:
        inicializar(conexao)
        for eventos in transacoes(log):
            # SQLite confirma todos os eventos da transação juntos.
            with conexao:
                for evento in eventos:
                    cursor = conexao.execute(
                        "INSERT OR IGNORE INTO eventos_aplicados "
                        "(evento_id, xid, indice, tabela, operacao, detalhes) "
                        "VALUES (?, ?, ?, ?, ?, ?)", evento,
                    )
                    if cursor.rowcount == 1:
                        novos += 1
                    else:
                        duplicados += 1
            transacoes_confirmadas += 1
        total = conexao.execute("SELECT COUNT(*) FROM eventos_aplicados").fetchone()[0]
    return {"transacoes_confirmadas": transacoes_confirmadas, "novos": novos,
            "duplicados": duplicados, "total_destino": total}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log", type=Path, default=Path("data/cdc/eventos.log"))
    parser.add_argument("--db", type=Path, default=Path("data/cdc/replay.sqlite3"))
    args = parser.parse_args()
    if not args.log.is_file():
        parser.error(f"log nao encontrado: {args.log}")
    print(json.dumps(processar(args.log, args.db), ensure_ascii=False))


if __name__ == "__main__":
    main()
