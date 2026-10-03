# -*- coding: utf-8 -*-
"""
Testes automatizados do sistema de apuração das eleições 2026.
Valida o padrão técnico oficial de 2026 (-u.json), normalização de payloads
e persistência no SQLite.
"""

import unittest
import os
import tempfile
import pandas as pd

from config import build_tse_url
from database import (
    init_db,
    save_snapshot,
    normalize_tse_payload,
    get_latest_snapshot,
    get_candidates_evolution,
    get_all_snapshots
)
from worker import generate_simulated_snapshot


class TestApuracaoSistema2026(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = os.path.join(self.temp_dir.name, "test_eleicoes.db")
        init_db(self.db_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_url_builder_2026_presidente(self):
        # Simulado Oficial
        url_sim = build_tse_url("ele2026", cod_eleicao="21270", turno=1, ambiente="simulado2026", base_url="https://resultados-sim.tse.jus.br/simulado")
        self.assertEqual(url_sim, "https://resultados-sim.tse.jus.br/simulado/simulado2026/ele2026/21270/dados/br/br-c0001-e021270-u.json")

        # Produção Oficial
        url_prod = build_tse_url("ele2026", cod_eleicao="21270", turno=1, ambiente="", base_url="https://resultados.tse.jus.br/oficial")
        self.assertEqual(url_prod, "https://resultados.tse.jus.br/oficial/ele2026/21270/dados/br/br-c0001-e021270-u.json")

    def test_url_builder_2026_senador(self):
        # Endpoint de Senador (SP)
        url_senador = build_tse_url("ele2026", cod_eleicao="21272", cargo="c0005", uf="sp", ambiente="simulado2026", base_url="https://resultados-sim.tse.jus.br/simulado")
        self.assertEqual(url_senador, "https://resultados-sim.tse.jus.br/simulado/simulado2026/ele2026/21272/dados/sp/sp-c0005-e021272-u.json")

    def test_normalize_payload_2026(self):
        raw_2026 = {
            "ele": "21270",
            "t": "1",
            "dt": "24/09/2026",
            "ht": "16:00:00",
            "s": {"ts": "500000", "st": "250000", "pst": "50,00", "snt": "250000", "psnt": "50,00"},
            "v": {"tv": "70000000", "vv": "60000000", "pvv": "85,71", "vb": "4000000", "pvb": "5,71", "tvn": "6000000", "ptvn": "8,57"},
            "e": {"c": "70000000", "pc": "80,00", "a": "17500000", "pa": "20,00"},
            "carg": [{
                "cd": "1",
                "agr": [{
                    "nm": "COLIGAÇÃO ALFA",
                    "par": [{
                        "sg": "PARTIDO X",
                        "cand": [{
                            "n": "10",
                            "nm": "CANDIDATO 10",
                            "sqcand": "12345",
                            "seq": "1",
                            "e": "s",
                            "st": "2º turno",
                            "vap": "35000000",
                            "pvap": "58,33",
                            "vs": [{"nm": "VICE 10"}]
                        }]
                    }]
                }]
            }]
        }
        normalized = normalize_tse_payload(raw_2026)
        self.assertIn("cand", normalized)
        self.assertEqual(len(normalized["cand"]), 1)
        c0 = normalized["cand"][0]
        self.assertEqual(c0["n"], "10")
        self.assertEqual(c0["nm"], "CANDIDATO 10")
        self.assertEqual(c0["nv"], "VICE 10")
        self.assertEqual(c0["vap"], "35000000")
        self.assertEqual(normalized["pst"], "50,00")

    def test_snapshot_persistence_and_duplicate_prevention(self):
        snap1 = generate_simulated_snapshot("ele2026", 1, 20.0)
        saved_first = save_snapshot(snap1, "ele2026", "21270", 1, db_path=self.db_path)
        self.assertTrue(saved_first)

        # Inserção idêntica deve ser ignorada (retornar False)
        saved_duplicate = save_snapshot(snap1, "ele2026", "21270", 1, db_path=self.db_path)
        self.assertFalse(saved_duplicate)

        # Inserção com progresso novo deve retornar True
        snap2 = generate_simulated_snapshot("ele2026", 1, 50.0)
        snap2["ht"] = "17:30:00"
        saved_second = save_snapshot(snap2, "ele2026", "21270", 1, db_path=self.db_path)
        self.assertTrue(saved_second)

    def test_database_queries(self):
        snap = generate_simulated_snapshot("ele2026", 1, 75.0)
        save_snapshot(snap, "ele2026", "21270", 1, db_path=self.db_path)

        resumo, df_cand = get_latest_snapshot("ele2026", 1, db_path=self.db_path)
        self.assertIsNotNone(resumo)
        self.assertEqual(resumo["pct_secoes_totalizadas"], 75.0)
        self.assertGreater(len(df_cand), 0)

        df_evolucao = get_candidates_evolution("ele2026", 1, db_path=self.db_path)
        self.assertFalse(df_evolucao.empty)

        df_all = get_all_snapshots("ele2026", 1, db_path=self.db_path)
        self.assertEqual(len(df_all), 1)


if __name__ == "__main__":
    unittest.main()
