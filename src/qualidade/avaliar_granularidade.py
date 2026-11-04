"""Experimento da ADR-0005 sobre a amostra, sem substituir os modelos Gold.

python -m src.qualidade.avaliar_granularidade --saida /tmp/metra-granularidade.json
Não usa cadastros oficiais nem mede SCD, extração PostgreSQL ou execução do dbt.
"""

import argparse
import hashlib
import json
from pathlib import Path
import platform
import statistics
import tempfile
import time

import duckdb

from src.extracao.comparar_compressao import AMOSTRA_SQL


ROOT = Path(__file__).resolve().parents[2]

AGREGACAO = """
select ano, mes, id_municipio, cnae_2_subclasse,
       count(*) as movimentacoes,
       count(*) filter (where saldo_movimentacao = 1) as admissoes,
       count(*) filter (where saldo_movimentacao = -1) as desligamentos,
       sum(saldo_movimentacao) as saldo,
       coalesce(sum(salario_mensal) filter
           (where saldo_movimentacao = 1 and salario_mensal > 0), 0) as soma_salarios_admissao,
       count(*) filter (where saldo_movimentacao = 1 and salario_mensal > 0) as n_salarios_admissao
from detalhe group by ano, mes, id_municipio, cnae_2_subclasse
"""
CONSULTA_DETALHE = """
select ano, mes, cnae_2_subclasse, sum(saldo_movimentacao) as saldo,
       coalesce(sum(salario_mensal) filter
           (where saldo_movimentacao = 1 and salario_mensal > 0), 0) as soma_salarios,
       count(*) filter (where saldo_movimentacao = 1 and salario_mensal > 0) as n_salarios
from detalhe group by ano, mes, cnae_2_subclasse
"""
CONSULTA_MENSAL = """
select ano, mes, cnae_2_subclasse, sum(saldo) as saldo,
       sum(soma_salarios_admissao) as soma_salarios, sum(n_salarios_admissao) as n_salarios
from mensal group by ano, mes, cnae_2_subclasse
"""


def avaliar(amostra: Path, repeticoes: int = 5) -> dict:
    if repeticoes < 3:
        raise ValueError('Use pelo menos três repetições.')
    with tempfile.TemporaryDirectory(prefix='metra-grao-') as tmp, duckdb.connect() as conn:
        conn.execute('set threads=1')
        # Reaproveita a normalização declarada na ADR-0003; a linhagem é sintética.
        conn.execute('create table detalhe as ' + AMOSTRA_SQL, [str(amostra.resolve())])
        conn.execute('create table mensal as ' + AGREGACAO)
        total = conn.execute('select count(*) from detalhe').fetchone()[0]
        if not total:
            raise ValueError('A amostra não pode ser vazia.')
        iguais = conn.execute(f"""
            with a as ({CONSULTA_DETALHE}), b as ({CONSULTA_MENSAL})
            select (select count(*) from (select * from a except all select * from b))
                 + (select count(*) from (select * from b except all select * from a))
        """).fetchone()[0] == 0
        if not iguais:
            raise AssertionError('As métricas aditivas não reconciliaram.')
        resultados = {}
        for tabela, consulta in [('detalhe', CONSULTA_DETALHE), ('mensal', CONSULTA_MENSAL)]:
            arquivo = Path(tmp) / (tabela + '.parquet')
            conn.execute(f"copy {tabela} to ? (format parquet, compression snappy)", [str(arquivo)])
            conn.execute(consulta).fetchall()  # aquecimento fora das medições
            tempos = []
            for _ in range(repeticoes):
                inicio = time.perf_counter()
                conn.execute(consulta).fetchall()
                tempos.append((time.perf_counter() - inicio) * 1000)
            resultados[tabela] = {
                'linhas': conn.execute(f'select count(*) from {tabela}').fetchone()[0],
                'parquet_bytes': arquivo.stat().st_size,
                'consulta_ms': tempos,
                'mediana_ms': statistics.median(tempos),
                'explain_analyze': conn.execute('explain analyze ' + consulta).fetchone()[1],
            }
        return {
            'fonte': str(amostra.name), 'sha256': hashlib.sha256(amostra.read_bytes()).hexdigest(),
            'python': platform.python_version(), 'duckdb': duckdb.__version__,
            'plataforma': platform.platform(), 'threads': 1, 'repeticoes': repeticoes,
            'limites': 'Amostra normalizada; linhagem sintética; sem cadastros, SCD ou PostgreSQL. '
                       'Tabelas em memória; cache aquecido; sem alternância da ordem; host compartilhado. '
                       'Parquet de cada candidato em arquivo único. Não é benchmark da Gold final.',
            'metricas_aditivas_iguais': iguais, 'resultados': resultados,
            'perdas_mensal': ['codigo_cbo', 'sexo', 'raca_cor', 'grau_instrucao', 'idade',
                              'id_movimentacao', 'id_ingestao', 'numero_linha'],
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--amostra', type=Path, default=ROOT / 'data/caged_centro_oeste_amostra.csv')
    parser.add_argument('--saida', type=Path, required=True)
    parser.add_argument('--repeticoes', type=int, default=5)
    args = parser.parse_args()
    report = avaliar(args.amostra, args.repeticoes)
    args.saida.parent.mkdir(parents=True, exist_ok=True)
    args.saida.write_text(json.dumps(report, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    print(json.dumps({k: {f: v[f] for f in ('linhas', 'parquet_bytes', 'mediana_ms')}
                      for k, v in report['resultados'].items()}, indent=2))


if __name__ == '__main__':
    main()
