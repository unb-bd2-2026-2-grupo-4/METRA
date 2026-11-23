"""Camada semântica única de métricas (E4).

Executar na raiz: python -m unittest tests.test_camada_semantica -v
Não precisa do banco analítico: usa o YAML versionado e um DuckDB em memória.
A igualdade entre o macro dbt e o compilador Python é conferida em test_dbt_quality.py,
que já executa o dbt de verdade.
"""

import datetime
from pathlib import Path
import re
import unittest

import duckdb
import yaml

from src.metricas.camada_semantica import (
    MetricaDesconhecida,
    catalogo,
    colunas_select,
    definicao,
    expressao,
    montar_consulta,
    recorte_padrao,
)

ROOT = Path(__file__).resolve().parents[1]
MEDIDAS_DOS_MARTS = [
    "admissoes", "desligamentos", "saldo", "soma_salarios_admissao", "qtd_salarios_admissao",
]

# Fórmulas de métrica que só podem existir em metricas.yml. Ferramentas de medição e
# gabaritos independentes (src/qualidade, avaliar_busca_e_text2sql.py e os testes de
# conciliação) ficam de fora de propósito: conferir com o próprio compilador seria circular.
PADROES_PROIBIDOS = {
    "média salarial escrita à mão": re.compile(r"nullif\(\s*(sum\(\s*)?qtd_sal", re.I),
    "índice de fluxos escrito à mão": re.compile(r"least\(\s*admissoes", re.I),
    "contagem de admissão/desligamento à mão": re.compile(
        r"filter\s*\(\s*where\s+(f\.)?saldo_movimentacao", re.I),
    "soma salarial à mão": re.compile(
        r"case\s+when\s+(f\.)?saldo_movimentacao\s*=\s*1\s+and\s+(f\.)?salario_valido", re.I),
    "média recalculada em pandas": re.compile(r"\[\s*[\"']soma_sal\w*[\"']\s*\]\s*\)?\s*/", re.I),
}
ARQUIVOS_CONSUMIDORES = [
    *(p for p in (ROOT / "src" / "app").glob("*.py") if p.name != "avaliar_busca_e_text2sql.py"),
    *(ROOT / "dbt_metra" / "analyses").glob("*.sql"),
    *(ROOT / "dbt_metra" / "models").rglob("*.sql"),
    *(p for p in (ROOT / "dbt_metra" / "macros").glob("*.sql") if p.name != "metricas.sql"),
]


class DefinicaoTest(unittest.TestCase):
    def test_yaml_tem_todas_as_metricas_com_catalogo(self):
        cat = catalogo()
        for nome in [*MEDIDAS_DOS_MARTS, "salario_medio_admissao", "indice_fluxos_pareados_pct"]:
            with self.subTest(metrica=nome):
                self.assertIn(nome, cat)
                self.assertTrue(cat[nome].label)
                self.assertTrue(cat[nome].descricao)
                self.assertTrue(cat[nome].unidade)
                self.assertTrue(cat[nome].formato)

    def test_medidas_tem_o_nome_das_colunas_dos_marts(self):
        self.assertEqual(sorted(definicao()["medidas"]), sorted(MEDIDAS_DOS_MARTS))
        contratos = yaml.safe_load(
            (ROOT / "dbt_metra/models/marts/_gold__models.yml").read_text(encoding="utf-8"))
        colunas = {c["name"] for m in contratos["models"] if m["name"] == "fct_setor_mensal"
                   for c in m.get("columns", [])}
        if colunas:
            for medida in MEDIDAS_DOS_MARTS:
                self.assertIn(medida, colunas)

    def test_referencias_internas_existem(self):
        d = definicao()
        for nome, mt in d["metricas"].items():
            tp = mt["type_params"]
            with self.subTest(metrica=nome):
                if mt["type"] == "simple":
                    self.assertIn(tp["measure"], d["medidas"])
                elif mt["type"] == "ratio":
                    self.assertIn(tp["numerator"], d["metricas"])
                    self.assertIn(tp["denominator"], d["metricas"])
                else:
                    for filha in tp["metrics"]:
                        self.assertIn(filha["name"], d["metricas"])

    def test_recorte_padrao_igual_ao_dos_marts(self):
        recorte = recorte_padrao()
        for mart in ["fct_setor_mensal", "fct_geografia_mensal", "fct_perfil_mensal"]:
            sql = (ROOT / "dbt_metra/models/marts" / f"{mart}.sql").read_text(encoding="utf-8")
            with self.subTest(mart=mart):
                self.assertIn(f"where {recorte}", sql)


class CompiladorTest(unittest.TestCase):
    def test_razao_recomposta_das_medidas_aditivas(self):
        self.assertEqual(
            expressao("salario_medio_admissao", "agregado"),
            "sum(soma_salarios_admissao) / nullif(sum(qtd_salarios_admissao), 0)",
        )
        self.assertEqual(
            expressao("salario_medio_admissao", "agregado", janela="recorte"),
            "sum(soma_salarios_admissao) over recorte / nullif(sum(qtd_salarios_admissao) over recorte, 0)",
        )

    def test_derivada_substitui_cada_filha_uma_vez(self):
        sql = expressao("indice_fluxos_pareados_pct", "agregado")
        self.assertEqual(
            sql,
            "200.0 * least((sum(admissoes)), (sum(desligamentos))) "
            "/ nullif((sum(admissoes)) + (sum(desligamentos)), 0)",
        )
        self.assertNotIn("@@", expressao("indice_fluxos_pareados_pct", "evento"))

    def test_entradas_invalidas(self):
        with self.assertRaises(MetricaDesconhecida):
            expressao("taxa_de_desemprego")
        with self.assertRaises(ValueError):
            expressao("saldo", "outra")
        with self.assertRaises(ValueError):
            expressao("saldo", "evento", janela="recorte")
        with self.assertRaises(ValueError):
            expressao("saldo", "agregado", janela="recorte; drop table x")
        with self.assertRaises(ValueError):
            montar_consulta(["saldo"], filtros={"sigla_uf": "SP"})
        with self.assertRaises(ValueError):
            montar_consulta(["saldo"], tabela="silver.stg_movimentacao")
        with self.assertRaises(ValueError):
            montar_consulta(["saldo"], dimensoes=["salario_mensal"])


class ResultadoNumericoTest(unittest.TestCase):
    """Executa o SQL compilado num DuckDB em memória e compara com contas feitas à mão."""

    @classmethod
    def setUpClass(cls):
        cls.conn = duckdb.connect()
        cls.addClassCleanup(cls.conn.close)
        cls.conn.execute("create schema gold")
        # 8 eventos: GO capital e interior em 2025; um salário inválido e um fora do recorte.
        cls.conn.execute("""
            create table gold.fct_movimentacao as select * from (values
              (1, date '2025-01-01', 2025, 'GO', true,  'G',  1, true,  2000.00::decimal(16,2), true, true),
              (2, date '2025-01-01', 2025, 'GO', true,  'G',  1, true,  4000.00::decimal(16,2), true, true),
              (3, date '2025-01-01', 2025, 'GO', true,  'G', -1, false, 0.00::decimal(16,2),    true, true),
              (4, date '2025-02-01', 2025, 'GO', false, 'C',  1, true,  1500.00::decimal(16,2), true, true),
              (5, date '2025-02-01', 2025, 'GO', false, 'C',  1, false, 0.00::decimal(16,2),    true, true),
              (6, date '2025-02-01', 2025, 'GO', false, 'C', -1, false, 0.00::decimal(16,2),    true, true),
              (7, date '2025-02-01', 2025, 'GO', false, 'C', -1, false, 0.00::decimal(16,2),    true, true),
              (8, date '2025-02-01', 2025, 'NI', false, 'Z',  1, true,  9999.00::decimal(16,2), false, true)
            ) t(id_movimentacao, competencia, ano, sigla_uf, is_capital, codigo_secao,
                saldo_movimentacao, salario_valido, salario_mensal, is_identificado, is_centro_oeste)
        """)
        # Agregado mensal com as mesmas medidas, gerado pelo próprio compilador (como os marts).
        cls.conn.execute(f"""
            create table gold.fct_setor_mensal as
            select competencia, sigla_uf, codigo_secao,
                {colunas_select(MEDIDAS_DOS_MARTS, "evento")}
            from gold.fct_movimentacao
            where {recorte_padrao()}
            group by competencia, sigla_uf, codigo_secao
        """)

    def test_valores_conferidos_a_mao(self):
        sql = montar_consulta(
            ["admissoes", "desligamentos", "saldo", "qtd_salarios_admissao",
             "salario_medio_admissao", "indice_fluxos_pareados_pct"],
            tabela="gold.fct_movimentacao",
        )
        adm, desl, saldo, qtd, salario, indice = self.conn.execute(sql).fetchone()
        # Evento 8 está fora do recorte (município não identificado).
        self.assertEqual((adm, desl, saldo, qtd), (4, 3, 1, 3))
        self.assertAlmostEqual(float(salario), (2000 + 4000 + 1500) / 3)
        self.assertAlmostEqual(float(indice), 200.0 * 3 / 7)

    def test_agregado_recompoe_o_mesmo_valor_dos_eventos(self):
        metricas = ["admissoes", "saldo", "salario_medio_admissao", "indice_fluxos_pareados_pct"]
        for dims in ([], ["codigo_secao"], ["competencia", "codigo_secao"]):
            with self.subTest(dimensoes=dims):
                eventos = self.conn.execute(
                    montar_consulta(metricas, dims, tabela="gold.fct_movimentacao")).fetchall()
                agregado = self.conn.execute(
                    montar_consulta(metricas, dims, tabela="gold.fct_setor_mensal")).fetchall()
                self.assertEqual(len(eventos), len(agregado))
                for linha_e, linha_a in zip(eventos, agregado):
                    for ve, va in zip(linha_e, linha_a):
                        if ve is None or isinstance(ve, (int, str, datetime.date)):
                            self.assertEqual(ve, va)
                        else:
                            self.assertAlmostEqual(float(ve), float(va))

    def test_media_ponderada_nao_e_media_de_medias(self):
        sql = montar_consulta(["salario_medio_admissao"], tabela="gold.fct_setor_mensal")
        (salario,) = self.conn.execute(sql).fetchone()
        media_de_medias = (3000.0 + 1500.0) / 2
        self.assertAlmostEqual(float(salario), 2500.0)
        self.assertNotAlmostEqual(float(salario), media_de_medias)

    def test_filtros_em_lista_branca(self):
        # UF é normalizada para maiúsculas antes de entrar no SQL.
        sql = montar_consulta(["saldo"], ["codigo_secao"], {"sigla_uf": "go", "ano": 2025})
        self.assertIn("sigla_uf = 'GO'", sql)
        self.assertEqual(self.conn.execute(sql).fetchall(), [("C", 0), ("G", 1)])
        # A consulta de eventos aceita is_capital e devolve só o interior de GO.
        sql_eventos = montar_consulta(["saldo"], ["codigo_secao"],
                                      {"sigla_uf": "GO", "ano": 2025, "is_capital": False},
                                      tabela="gold.fct_movimentacao")
        self.assertEqual(self.conn.execute(sql_eventos).fetchall(), [("C", 0)])


class SemFormulaDuplicadaTest(unittest.TestCase):
    def test_consumidores_nao_reescrevem_formulas(self):
        achados = []
        for arquivo in ARQUIVOS_CONSUMIDORES:
            texto = arquivo.read_text(encoding="utf-8")
            for descricao, padrao in PADROES_PROIBIDOS.items():
                for m in padrao.finditer(texto):
                    linha = texto.count("\n", 0, m.start()) + 1
                    achados.append(f"{arquivo.relative_to(ROOT)}:{linha} {descricao}")
        self.assertEqual(achados, [], "Use src.metricas.camada_semantica / metrica() em vez de:\n"
                         + "\n".join(achados))


if __name__ == "__main__":
    unittest.main()
