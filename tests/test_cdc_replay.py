import importlib.util
import sqlite3
import tempfile
import unittest
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parents[1] / "src/cdc/04_reprocessar.py"
spec = importlib.util.spec_from_file_location("replay_cdc", ARQUIVO)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)

LOG = """BEGIN 769
table oltp.cdc_probe: INSERT: id[bigint]:1 descricao[text]:'exemplo'
COMMIT 769
BEGIN 770
table oltp.cdc_probe: UPDATE: id[bigint]:1 descricao[text]:'exemplo-atualizado'
COMMIT 770
"""


class ReplayCDC(unittest.TestCase):
    def test_replay_mesmo_log_nao_duplicar(self):
        with tempfile.TemporaryDirectory() as pasta:
            diretorio = Path(pasta)
            log = diretorio / "eventos.log"
            banco = diretorio / "replay.sqlite3"
            log.write_text(LOG, encoding="utf-8")
            primeira = replay.processar(log, banco)
            segunda = replay.processar(log, banco)
            self.assertEqual(primeira["novos"], 2)
            self.assertEqual(primeira["total_destino"], 2)
            self.assertEqual(segunda["novos"], 0)
            self.assertEqual(segunda["duplicados"], 2)
            self.assertEqual(segunda["total_destino"], 2)
            # Mesmo conteúdo reanexado ao log: continua sem duplicação.
            with log.open("a", encoding="utf-8") as arquivo:
                arquivo.write(LOG)
            terceira = replay.processar(log, banco)
            self.assertEqual(terceira["total_destino"], 2)
            self.assertEqual(terceira["duplicados"], 4)

    def test_ignora_transacao_incompleta(self):
        with tempfile.TemporaryDirectory() as pasta:
            diretorio = Path(pasta)
            log = diretorio / "eventos.log"
            log.write_text(LOG + "BEGIN 771\ntable oltp.cdc_probe: INSERT: id[bigint]:2 descricao[text]:'incompleto'\n", encoding="utf-8")
            resultado = replay.processar(log, diretorio / "replay.sqlite3")
            self.assertEqual(resultado["total_destino"], 2)


if __name__ == "__main__":
    unittest.main()
