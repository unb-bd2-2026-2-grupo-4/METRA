"""Contrato público, publicação atômica e retry com DuckDB temporário, sem dados reais."""

import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import duckdb
from dagster import AssetKey, AssetSpec, RetryPolicy, materialize

from dagster_metra.assets import POLITICA_RETRY, exportar_json_consumo_asset
from src.consumo.exportar_json import COLECOES, METRICAS, exportar
from src.metricas.camada_semantica import expressao


def criar_views(banco):
    """As views de produção são responsabilidade de Lucas; estas são só fixtures."""
    with duckdb.connect(str(banco)) as conn:
        conn.execute("""
            create schema consumo;
            create table base as select date '2025-01-01' as competencia, 'GO' as sigla_uf,
                codigo_secao, admissoes, desligamentos, admissoes-desligamentos as saldo,
                soma::decimal(38,2) as soma_salarios_admissao, qtd as qtd_salarios_admissao,
                999 as id_movimentacao
            from (values
                ('A', 5, 0, 10000, 5), ('B', 10, 2, 40000, 10),
                ('C', 4, 1, 8000, 4), ('D', 2, 2, 4000, 2), ('E', 0, 5, 0, 0)
            ) t(codigo_secao, admissoes, desligamentos, soma, qtd);
            create view consumo.setor_mensal as select * replace (
                case when qtd_salarios_admissao >= 5 then soma_salarios_admissao end
                    as soma_salarios_admissao,
                case when qtd_salarios_admissao >= 5 then qtd_salarios_admissao end
                    as qtd_salarios_admissao
            ) from base where admissoes + desligamentos >= 5;
            create view consumo.geografia_mensal as
                select *, true as is_capital from consumo.setor_mensal where codigo_secao = 'A';
            create view consumo.perfil_anual as
                select * exclude (competencia), year(competencia)::integer as ano, true as is_capital, eixo,
                    ascii(codigo_secao)::integer as codigo_categoria,
                    'Categoria ' || codigo_secao as categoria
                from consumo.setor_mensal cross join (values
                    ('sexo'), ('raca_cor'), ('escolaridade'), ('faixa_etaria')
                ) e(eixo);
            create table meses(competencia date, tem_dados boolean);
            insert into meses values ('2025-01-01', true), ('2025-02-01', false), ('2025-03-01', true);
            create view consumo.calendario as select * from meses;
        """)


class ExportarJsonTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory(prefix="metra-json-")
        self.addCleanup(tmp.cleanup)
        self.pasta = Path(tmp.name)
        self.banco = self.pasta / "analitico.duckdb"
        self.destino = self.pasta / "publico/metra.json"
        criar_views(self.banco)

    def alterar(self, sql):
        with duckdb.connect(str(self.banco)) as conn:
            conn.execute(sql)

    def ler(self):
        return json.loads(self.destino.read_text(encoding="utf-8"))

    def test_metricas_batem_com_views_e_media_ponderada(self):
        metadados = exportar(self.banco, self.destino)
        dados = self.ler()
        with duckdb.connect(str(self.banco), read_only=True) as conn:
            for colecao, (view, dimensoes) in COLECOES.items():
                grupo = ", ".join((*dimensoes, *(("categoria",) if colecao == "perfis" else ())))
                for nome in METRICAS:
                    esperado = conn.execute(
                        f"select {expressao(nome)} from consumo.{view} group by {grupo} order by {grupo}"
                    ).fetchall()
                    self.assertEqual([r[nome] for r in dados[colecao]], [r[0] for r in esperado])
        setores = {r["codigo_secao"]: r for r in dados["setores"]}
        self.assertEqual(setores["A"]["salario_medio_admissao"], 2000)
        self.assertEqual(setores["B"]["salario_medio_admissao"], 4000)
        with duckdb.connect(str(self.banco), read_only=True) as conn:
            (media,) = conn.execute(
                f"select {expressao('salario_medio_admissao')} from consumo.setor_mensal "
                "where codigo_secao in ('A', 'B')"
            ).fetchone()
        self.assertAlmostEqual(media, (10000 + 40000) / (5 + 10))
        self.assertNotEqual(media, (2000 + 4000) / 2)
        for registros in (dados[c] for c in COLECOES):
            self.assertTrue(all(set(r) <= set(METRICAS) | {
                "competencia", "ano", "sigla_uf", "codigo_secao", "is_capital", "eixo",
                "codigo_categoria", "categoria",
            } for r in registros))
        # v2: perfis anuais, sem competência; setores e geografia seguem mensais.
        self.assertTrue(all(r["ano"] == 2025 and "competencia" not in r for r in dados["perfis"]))
        self.assertTrue(all("competencia" in r for r in dados["setores"]))
        self.assertEqual(metadados["registros"]["setores"], 4)
        self.assertEqual(dados["versao_schema"], 2)
        self.assertEqual(set(dados["metricas"]), set(METRICAS))
        self.assertEqual(os.stat(self.destino).st_mode & 0o777, 0o644)
        self.assertEqual(os.stat(self.destino.with_name(".metra.json.lock")).st_mode & 0o777, 0o666)

    def test_limites_de_supressao_e_calendario(self):
        exportar(self.banco, self.destino)
        dados = self.ler()
        setores = {r["codigo_secao"]: r for r in dados["setores"]}
        self.assertNotIn("D", setores)  # 4 movimentações: omitido.
        self.assertEqual(setores["A"]["qtd_salarios_admissao"], 5)
        self.assertEqual(setores["C"]["admissoes"], 4)  # 5 movimentações: fluxos publicados.
        self.assertIsNone(setores["C"]["qtd_salarios_admissao"])
        self.assertIsNone(setores["C"]["salario_medio_admissao"])
        self.assertEqual(setores["E"]["admissoes"], 0)  # Zero observado preservado.
        self.assertEqual(dados["calendario"][1], {"competencia": "2025-02-01", "tem_dados": False})
        self.assertEqual(dados["calendario"][2], {"competencia": "2025-03-01", "tem_dados": True})
        self.assertEqual({r["eixo"] for r in dados["perfis"]},
                         {"sexo", "raca_cor", "escolaridade", "faixa_etaria"})

    def test_reexecucao_identica_e_correcao_historica_sem_duplicar(self):
        primeiro = exportar(self.banco, self.destino)
        conteudo = self.destino.read_bytes()
        segundo = exportar(self.banco, self.destino)
        self.assertEqual(conteudo, self.destino.read_bytes())
        self.assertEqual(primeiro["sha256"], segundo["sha256"])
        self.alterar("update base set soma_salarios_admissao=15000 where codigo_secao='A'")
        terceiro = exportar(self.banco, self.destino)
        self.assertNotEqual(primeiro["sha256"], terceiro["sha256"])
        self.assertEqual(primeiro["registros"], terceiro["registros"])
        self.assertEqual(self.ler()["setores"][0]["salario_medio_admissao"], 3000)

    def test_falha_na_troca_preserva_anterior_e_remove_temporario(self):
        exportar(self.banco, self.destino)
        anterior = self.destino.read_bytes()
        with patch("src.consumo.exportar_json.Path.replace", side_effect=OSError("destino indisponível")):
            with self.assertRaises(OSError):
                exportar(self.banco, self.destino)
        self.assertEqual(self.destino.read_bytes(), anterior)
        self.assertEqual(list(self.destino.parent.glob(".metra-*")), [])

    def test_views_ausentes_nao_usam_gold_nem_criam_banco(self):
        self.alterar("drop view consumo.perfil_anual")
        with self.assertRaises(duckdb.Error):
            exportar(self.banco, self.destino)
        self.assertFalse(self.destino.exists())
        ausente = self.pasta / "ausente.duckdb"
        with self.assertRaises(duckdb.Error):
            exportar(ausente, self.destino)
        self.assertFalse(ausente.exists())
        with self.assertRaises(ValueError):
            exportar(self.banco, self.banco)

    def test_contratos_invalidos_preservam_publicacao(self):
        exportar(self.banco, self.destino)
        anterior = self.destino.read_bytes()
        casos = [
            # Primeiro, com setores e geografia ainda válidos: o ano fora do recorte nos perfis.
            "create or replace view consumo.perfil_anual as select * exclude (competencia), 2022 as ano, true as is_capital, "
            "'sexo' as eixo, 1 as codigo_categoria, 'Homem' as categoria from base where codigo_secao='A'",
            "create or replace view consumo.setor_mensal as select * from base",  # Sem supressão.
            "create or replace view consumo.setor_mensal as select * from base where codigo_secao='C'",
            "create or replace view consumo.setor_mensal as select * exclude (saldo) from base",
            "create or replace view consumo.setor_mensal as select * from base where codigo_secao='A' union all select * from base where codigo_secao='A'",
            "create or replace view consumo.setor_mensal as select * replace ('SP' as sigla_uf) from base where codigo_secao='A'",
            "create or replace view consumo.setor_mensal as select * replace (date '2025-01-02' as competencia) from base where codigo_secao='A'",
            "create or replace view consumo.setor_mensal as select * replace (null::bigint as qtd_salarios_admissao) from base where codigo_secao='A'",
            "create or replace view consumo.setor_mensal as select * replace ('Infinity'::double as soma_salarios_admissao) from base where codigo_secao='A'",
            "create or replace view consumo.setor_mensal as select * replace ('NaN'::double as soma_salarios_admissao) from base where codigo_secao='A'",
        ]
        for sql in casos:
            with self.subTest(sql=sql):
                self.alterar(sql)
                with self.assertRaises((ValueError, duckdb.Error)):
                    exportar(self.banco, self.destino)
                self.assertEqual(self.destino.read_bytes(), anterior)

    def test_calendario_inconsistente_e_rejeitado(self):
        for sql in (
            "update meses set tem_dados=false",
            "insert into meses values ('2025-01-01', true)",
            "insert into meses values ('2025-03-01', false)",
        ):
            with self.subTest(sql=sql):
                self.alterar("delete from meses; insert into meses values ('2025-01-01', true)")
                self.alterar(sql)
                with self.assertRaises(ValueError):
                    exportar(self.banco, self.destino)

    def test_retry_real_do_asset_recupera_falha_de_destino(self):
        from dagster_metra import assets
        exportar(self.banco, self.destino)
        anterior = self.destino.read_bytes()
        self.alterar("update base set soma_salarios_admissao=15000 where codigo_secao='A'")
        chamadas = []
        substituir = Path.replace

        def falhar_uma_vez(temporario, destino):
            if destino != self.destino:
                return substituir(temporario, destino)
            chamadas.append(destino)
            if len(chamadas) == 1:
                self.assertEqual(self.destino.read_bytes(), anterior)
                raise OSError("destino temporariamente indisponível")
            return substituir(temporario, destino)

        # Mesma política, apenas sem esperar os 10 s na suíte.
        with (
            patch.dict(os.environ, {"METRA_JSON_DESTINO": str(self.destino)}),
            patch.object(assets, "caminho_banco_analitico", return_value=self.banco),
            patch.object(Path, "replace", falhar_uma_vez),
            patch.object(RetryPolicy, "calculate_delay", return_value=0),
        ):
            fontes = [AssetSpec(AssetKey(["consumo", view])) for view in
                      ("setor_mensal", "geografia_mensal", "perfil_anual", "calendario")]
            resultado = materialize([*fontes, exportar_json_consumo_asset])
        self.assertTrue(resultado.success)
        self.assertEqual(len(chamadas), 2)
        self.assertTrue(self.destino.is_file())
        self.assertNotEqual(self.destino.read_bytes(), anterior)
        eventos = [e.event_type_value for e in resultado.all_events]
        self.assertIn("STEP_UP_FOR_RETRY", eventos)
        self.assertIn("STEP_RESTARTED", eventos)
        self.assertEqual(exportar_json_consumo_asset.op.retry_policy, POLITICA_RETRY)


if __name__ == "__main__":
    unittest.main()
