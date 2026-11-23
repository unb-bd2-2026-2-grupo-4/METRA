"""Conciliação dos agregados, OLTP e respostas P1-P5 na Gold real.

Executar após scripts/metra-do-zero.sh, na imagem do Dagster:
    python -m unittest discover -s tests -p 'test_gold_integracao.py' -v

Sem data/metra_analitico.duckdb, os testes são pulados. METRA_DUCKDB permite
usar o mesmo caminho configurado para o pipeline, inclusive no container.
O teste contra o OLTP exige o Postgres correspondente, configurado pelas
variáveis PG*. Com o DuckDB presente, falhas de conexão não são puladas.
"""

import os
from pathlib import Path
import unittest

import duckdb
import psycopg


ROOT = Path(__file__).resolve().parents[1]
AGREGADOS = {
    "fct_setor_mensal": ("competencia", "sigla_uf", "codigo_secao"),
    "fct_geografia_mensal": ("competencia", "sigla_uf", "is_capital"),
    "fct_perfil_mensal": (
        "competencia", "sigla_uf", "is_capital", "codigo_secao", "id_perfil_demografico"
    ),
}


class GoldIntegracaoTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        banco = Path(os.environ.get(
            "METRA_DUCKDB", str(ROOT / "data" / "metra_analitico.duckdb")
        ))
        if not banco.is_file():
            raise unittest.SkipTest(
                f"Banco analítico ausente: {banco}. Execute scripts/metra-do-zero.sh."
            )
        cls.conn = duckdb.connect(str(banco), read_only=True)
        cls.addClassCleanup(cls.conn.close)

    def conferir_agregado(self, tabela, dimensoes, identificado="is_identificado"):
        # Mesmo recorte de negócio dos marts; a referência é calculada a partir
        # dos eventos, sem reutilizar a macro dbt que produz os agregados.
        chaves = ", ".join(dimensoes)
        medidas = (
            "admissoes, desligamentos, saldo, "
            "soma_salarios_admissao, qtd_salarios_admissao"
        )
        sql = f"""
            with esperado as (
                select {chaves},
                    count(*) filter (where saldo_movimentacao = 1) as admissoes,
                    count(*) filter (where saldo_movimentacao = -1) as desligamentos,
                    sum(saldo_movimentacao) as saldo,
                    sum(case when saldo_movimentacao = 1 and salario_valido
                        then salario_mensal else 0 end) as soma_salarios_admissao,
                    count(*) filter (
                        where saldo_movimentacao = 1 and salario_valido
                    ) as qtd_salarios_admissao
                from gold.fct_movimentacao
                where {identificado} and is_centro_oeste
                    and ano between 2023 and 2026
                group by {chaves}
            ), atual as (
                select {chaves}, {medidas} from gold.{tabela}
            ), faltantes as (
                select * from esperado except all select * from atual
            ), excedentes as (
                select * from atual except all select * from esperado
            )
            select 'faltante ou divergente' as problema, * from faltantes
            union all
            select 'excedente ou divergente' as problema, * from excedentes
            limit 10
        """
        self.assertGreater(
            self.conn.execute(f"select count(*) from gold.{tabela}").fetchone()[0],
            0, f"gold.{tabela} está vazio; a conciliação exige dados reais.",
        )
        self.assertEqual(
            self.conn.execute(sql).fetchall(), [],
            f"gold.{tabela} diverge da soma de gold.fct_movimentacao "
            f"por {chaves} (amostra de até 10 divergências).",
        )

    def test_setor_mensal_bate_com_movimentacao(self):
        self.conferir_agregado(
            "fct_setor_mensal", ("competencia", "sigla_uf", "codigo_secao")
        )

    def test_geografia_mensal_bate_com_movimentacao(self):
        self.conferir_agregado(
            "fct_geografia_mensal", ("competencia", "sigla_uf", "is_capital")
        )

    def test_perfil_mensal_bate_com_movimentacao(self):
        self.conferir_agregado(
            "fct_perfil_mensal",
            ("competencia", "sigla_uf", "is_capital", "codigo_secao",
             "id_perfil_demografico"),
        )

    def test_camada_semantica_mesmo_valor_em_eventos_e_marts(self):
        # Uma métrica, um valor: recompor a partir dos eventos ou de cada mart dá o mesmo número.
        from src.metricas.camada_semantica import montar_consulta

        metricas = ["admissoes", "desligamentos", "saldo", "qtd_salarios_admissao",
                    "salario_medio_admissao", "indice_fluxos_pareados_pct"]
        casos = [
            ("gold.fct_setor_mensal", ["ano", "sigla_uf", "codigo_secao"]),
            ("gold.fct_geografia_mensal", ["ano", "sigla_uf", "is_capital"]),
            ("gold.fct_perfil_mensal", ["sigla_uf", "is_capital"]),
            ("gold.fct_setor_mensal", []),
        ]
        for tabela, dimensoes in casos:
            eventos = self.conn.execute(
                montar_consulta(metricas, dimensoes, tabela="gold.fct_movimentacao")).fetchall()
            agregado = self.conn.execute(montar_consulta(metricas, dimensoes, tabela=tabela)).fetchall()
            with self.subTest(tabela=tabela, dimensoes=dimensoes):
                self.assertTrue(eventos, "A Gold real não retornou dados.")
                self.assertEqual(len(eventos), len(agregado))
                for linha_e, linha_a in zip(eventos, agregado):
                    for valor_e, valor_a in zip(linha_e, linha_a):
                        if isinstance(valor_e, float) or isinstance(valor_a, float):
                            self.assertAlmostEqual(float(valor_e), float(valor_a), places=7)
                        else:
                            self.assertEqual(valor_e, valor_a)

    def test_kpis_do_painel_vem_da_camada_semantica(self):
        from src.app import dashboard
        from src.metricas.camada_semantica import montar_consulta

        consultar_kpis = getattr(dashboard.consultar_kpis_recorte_cached, "__wrapped__",
                                 dashboard.consultar_kpis_recorte_cached)
        banco = os.environ.get("METRA_DUCKDB", str(ROOT / "data" / "metra_analitico.duckdb"))
        for uf, ano in [(None, None), ("GO", 2025), ("DF", None)]:
            filtros = {k: v for k, v in {"sigla_uf": uf, "ano": ano}.items() if v is not None}
            esperado = self.conn.execute(montar_consulta(
                ["admissoes", "desligamentos", "saldo", "salario_medio_admissao",
                 "qtd_salarios_admissao"], filtros=filtros)).fetchone()
            kpis = consultar_kpis(banco, uf, ano, None, None)
            with self.subTest(uf=uf, ano=ano):
                self.assertEqual(kpis["admissoes"], int(esperado[0] or 0))
                self.assertEqual(kpis["desligamentos"], int(esperado[1] or 0))
                self.assertEqual(kpis["saldo"], int(esperado[2] or 0))
                self.assertEqual(kpis["qtd_salarios"], int(esperado[4] or 0))
                if esperado[3] is None:
                    self.assertIsNone(kpis["salario_medio"])
                else:
                    self.assertAlmostEqual(kpis["salario_medio"], float(esperado[3]), places=7)

    def test_agregados_excluem_municipio_sentinela(self):
        self.assertEqual(self.conn.execute("""
            select id_municipio from gold.dim_municipio
            where id_municipio = '9999999' and is_identificado is distinct from false
        """).fetchall(), [], "O município sentinela não pode ser identificado.")
        # Os agregados não guardam id_municipio. Reconstituir seus valores
        # excluindo o código diretamente detecta contribuição indevida mesmo
        # quando ela fica misturada a municípios válidos no mesmo grupo.
        for tabela, dimensoes in AGREGADOS.items():
            with self.subTest(tabela=tabela):
                self.conferir_agregado(
                    tabela, dimensoes,
                    "is_identificado and id_municipio <> '9999999'",
                )

    def test_salario_medio_igual_soma_dividida_por_quantidade(self):
        for tabela in AGREGADOS:
            with self.subTest(tabela=tabela):
                divergencias = self.conn.execute(f"""
                    select * from gold.{tabela}
                    where qtd_salarios_admissao is null
                       or qtd_salarios_admissao < 0
                       or soma_salarios_admissao is null
                       or (qtd_salarios_admissao = 0 and (
                           salario_medio_admissao is not null
                           or soma_salarios_admissao <> 0
                       ))
                       or (qtd_salarios_admissao > 0 and (
                           salario_medio_admissao is null
                           or not isfinite(salario_medio_admissao)
                           or abs(salario_medio_admissao -
                               soma_salarios_admissao / qtd_salarios_admissao) > 0.0000001
                       ))
                    limit 10
                """).fetchall()
                self.assertEqual(divergencias, [],
                                 f"gold.{tabela}: salário médio inconsistente (até 10 linhas).")

    def test_competencias_sem_meses_faltando(self):
        # Exige continuidade somente entre os extremos carregados; não exige
        # anos completos nem eventos em cada combinação de UF/setor/perfil.
        for tabela in ("dim_competencia", "fct_movimentacao", *AGREGADOS):
            with self.subTest(tabela=tabela):
                filtro = (
                    "where is_identificado and is_centro_oeste and ano between 2023 and 2026"
                    if tabela in AGREGADOS else ""
                )
                faltantes = self.conn.execute(f"""
                    with limites as (
                        select min(competencia) as inicio, max(competencia) as fim
                        from gold.fct_movimentacao
                        {filtro}
                    ), esperadas as (
                        select unnest(generate_series(inicio, fim, interval '1 month'))::date
                            as competencia from limites
                    )
                    select competencia from esperadas
                    except select competencia from gold.{tabela}
                    order by competencia
                """).fetchall()
                self.assertGreater(
                    self.conn.execute(f"select count(*) from gold.{tabela}").fetchone()[0],
                    0, f"gold.{tabela} está vazio.",
                )
                self.assertEqual(faltantes, [], f"gold.{tabela}: meses faltantes.")

    def test_movimentacao_bate_com_postgres_por_competencia_e_uf(self):
        # Concilia toda a fato, incluindo municípios não identificados: o
        # recorte dos agregados não deve esconder perdas entre OLTP e Gold.
        with psycopg.connect(connect_timeout=10) as pg:
            pg.read_only = True
            esperado = pg.execute("""
                select make_date(m.ano, m.mes, 1) as competencia, mu.sigla_uf,
                    count(*) as movimentacoes,
                    count(*) filter (where m.saldo_movimentacao = 1) as admissoes,
                    count(*) filter (where m.saldo_movimentacao = -1) as desligamentos,
                    sum(m.saldo_movimentacao) as saldo,
                    sum(case when m.saldo_movimentacao = 1 and m.salario_mensal > 0
                        then m.salario_mensal else 0 end) as soma_salarios_admissao,
                    count(*) filter (
                        where m.saldo_movimentacao = 1 and m.salario_mensal > 0
                    ) as qtd_salarios_admissao
                from oltp.movimentacao m
                left join oltp.municipio mu using (id_municipio)
                group by make_date(m.ano, m.mes, 1), mu.sigla_uf
            """).fetchall()
        atual = self.conn.execute("""
            select competencia, sigla_uf,
                count(*) as movimentacoes,
                count(*) filter (where saldo_movimentacao = 1) as admissoes,
                count(*) filter (where saldo_movimentacao = -1) as desligamentos,
                sum(saldo_movimentacao) as saldo,
                sum(case when saldo_movimentacao = 1 and salario_valido
                    then salario_mensal else 0 end) as soma_salarios_admissao,
                count(*) filter (
                    where saldo_movimentacao = 1 and salario_valido
                ) as qtd_salarios_admissao
            from gold.fct_movimentacao
            group by competencia, sigla_uf
        """).fetchall()
        self.assertTrue(esperado, "oltp.movimentacao está vazio; execute o fluxo completo.")
        por_grupo_esperado = {linha[:2]: linha[2:] for linha in esperado}
        por_grupo_atual = {linha[:2]: linha[2:] for linha in atual}
        # Inclui grupos ausentes e extras e limita o diagnóstico em bases grandes.
        divergencias = [
            (chave, por_grupo_esperado.get(chave), por_grupo_atual.get(chave))
            for chave in por_grupo_esperado.keys() | por_grupo_atual.keys()
            if por_grupo_esperado.get(chave) != por_grupo_atual.get(chave)
        ]
        self.assertFalse(
            divergencias,
            "Gold diverge do OLTP por (competencia, UF). "
            "Métricas: movimentações, admissões, desligamentos, saldo, "
            "soma e quantidade de salários de admissão. "
            f"Amostra (chave, OLTP, Gold): {divergencias[:10]}",
        )

    def conferir_resposta_painel(self, analise, pergunta):
        from src.app.avaliar_busca_e_text2sql import _carregar_sql_analise_dbt
        from src.app.text_to_sql import AssistenteTextToSQL

        # Lê o SQL canônico versionado em analyses/, resolvendo apenas ref().
        # Não depende de arquivos compilados antigos em target/ nem gera dados.
        referencia = self.conn.sql(_carregar_sql_analise_dbt(analise))
        colunas = list(referencia.columns)
        esperado = referencia.fetchall()
        self.assertTrue(esperado, f"A análise {analise} não retornou dados na Gold real.")

        resposta = AssistenteTextToSQL().responder(self.conn, pergunta)
        self.assertTrue(resposta.suportada, resposta.motivo_recusa)
        self.assertEqual(resposta.intencao, analise)
        self.assertEqual(resposta.colunas, colunas)
        self.assertEqual(len(resposta.linhas), len(esperado))
        # A ordenação faz parte dos contratos SQL. Nulos e valores exatos são
        # preservados; tolerância só para cálculos de ponto flutuante.
        for numero, (atual, referencia) in enumerate(zip(resposta.linhas, esperado)):
            for coluna, valor, valor_esperado in zip(colunas, atual, referencia):
                with self.subTest(analise=analise, linha=numero, coluna=coluna):
                    if isinstance(valor, float) and isinstance(valor_esperado, float):
                        self.assertAlmostEqual(valor, valor_esperado, places=7)
                    else:
                        self.assertEqual(valor, valor_esperado)

    def test_p1_painel_bate_com_analise_dbt(self):
        self.conferir_resposta_painel(
            "p1_setores_df",
            "Qual setor econômico mais contratou e demitiu no Distrito Federal "
            "nos últimos 12 meses?",
        )

    def test_p2_painel_bate_com_analise_dbt(self):
        self.conferir_resposta_painel(
            "p2_sazonalidade",
            "Existe sazonalidade evidente nas contratações e demissões?",
        )

    def test_p3_painel_bate_com_analise_dbt(self):
        self.conferir_resposta_painel(
            "p3_capitais_interior",
            "Qual é a diferença no saldo líquido e no salário médio entre "
            "as capitais e os municípios do interior?",
        )

    def test_p4_painel_bate_com_analise_dbt(self):
        self.conferir_resposta_painel(
            "p4_fluxos_salarios",
            "Os setores com maior taxa de rotatividade praticam salários médios mais baixos?",
        )

    def test_p5_painel_bate_com_analise_dbt(self):
        self.conferir_resposta_painel(
            "p5_perfil_remuneracao",
            "Como o perfil sociodemográfico impacta o nível salarial e as movimentações?",
        )


if __name__ == "__main__":
    unittest.main()
