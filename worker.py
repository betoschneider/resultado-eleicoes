# -*- coding: utf-8 -*-
"""
Worker de Coleta Contínua da Apuração das Eleições 2026 (TSE).
Consulta a API oficial do TSE periodicamente e appenda as novas fotografias
ao banco de dados SQLite.
Totalmente focado no pleito de 2026 no formato oficial (-u.json).
"""

import time
import argparse
import logging
import signal
import sys
import threading
from datetime import datetime
import random
from typing import Optional

from config import (
    CICLO_PADRAO,
    TURNO_PADRAO,
    COD_ELEICAO_1T,
    COD_ELEICAO_2T,
    POLL_INTERVAL_SECONDS,
    SIMULATE,
    DB_PATH,
    build_tse_url
)
from database import init_db, save_snapshot, normalize_tse_payload
from tse_client import TSEClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("worker")

running = True


def handle_sigint(sig, frame):
    global running
    logger.info("Recebido sinal de encerramento. Finalizando worker...")
    running = False


def register_signal_handlers():
    """Registra tratadores de sinais apenas se estiver rodando na thread principal."""
    try:
        if threading.current_thread() is threading.main_thread():
            signal.signal(signal.SIGINT, handle_sigint)
            signal.signal(signal.SIGTERM, handle_sigint)
    except (ValueError, AttributeError):
        pass


def generate_simulated_snapshot(
    ciclo: str = "ele2026",
    turno: int = 1,
    step_pct: float = 50.0,
    base_candidates=None
) -> dict:
    """
    Gera uma fotografia simulada da apuração de 2026 para permitir testes
    completos da interface e do pipeline antes do dia do pleito.
    """
    now = datetime.now()
    dt = now.strftime("%d/%m/%Y")
    ht = now.strftime("%H:%M:%S")

    total_secoes = 528951
    secoes_apuradas = int(total_secoes * (step_pct / 100.0))
    total_eleitores = 160000000
    eleitores_apurados = int(total_eleitores * (step_pct / 100.0))
    
    abstencao = int(eleitores_apurados * 0.205)
    comparecimento = eleitores_apurados - abstencao
    brancos = int(comparecimento * 0.018)
    nulos = int(comparecimento * 0.032)
    validos = comparecimento - brancos - nulos

    if not base_candidates:
        if turno == 1:
            base_candidates = [
                {"n": "13", "nm": "CANDIDATO A", "cc": "COLIGAÇÃO BRASIL DO FUTURO", "nv": "VICE A", "ratio": 0.46},
                {"n": "22", "nm": "CANDIDATO B", "cc": "ALIANÇA PELA PATRIA", "nv": "VICE B", "ratio": 0.43},
                {"n": "15", "nm": "CANDIDATO C", "cc": "UNIÃO CENTRO DEMOCRÁTICO", "nv": "VICE C", "ratio": 0.07},
                {"n": "12", "nm": "CANDIDATO D", "cc": "FRENTE PROGRESSISTA TRABALHISTA", "nv": "VICE D", "ratio": 0.04},
            ]
        else:
            base_candidates = [
                {"n": "13", "nm": "CANDIDATO A", "cc": "COLIGAÇÃO BRASIL DO FUTURO", "nv": "VICE A", "ratio": 0.509},
                {"n": "22", "nm": "CANDIDATO B", "cc": "ALIANÇA PELA PATRIA", "nv": "VICE B", "ratio": 0.491},
            ]

    cand_list = []
    for idx, c in enumerate(base_candidates):
        noise = (random.random() - 0.5) * 0.015 if step_pct < 98 else 0.0
        pct_cand = max(0.01, c["ratio"] + noise)
        votos_cand = int(validos * pct_cand)
        
        status = "Em apuração"
        eleito = "n"
        if step_pct >= 100.0:
            if turno == 1:
                status = "2º turno" if idx < 2 else "Não eleito"
            else:
                status = "Eleito" if idx == 0 else "Não eleito"
                eleito = "s" if idx == 0 else "n"

        cand_list.append({
            "seq": str(idx + 1),
            "sqcand": f"28000999{idx}",
            "n": c["n"],
            "nm": c["nm"],
            "cc": c["cc"],
            "nv": c["nv"],
            "e": eleito,
            "st": status,
            "dvt": "Válido",
            "vap": str(votos_cand),
            "pvap": f"{(pct_cand * 100):.2f}".replace(".", ",")
        })

    cand_list.sort(key=lambda x: int(x["vap"]), reverse=True)

    sim_data = {
        "ele": COD_ELEICAO_1T if turno == 1 else COD_ELEICAO_2T,
        "tpabr": "br",
        "cdabr": "br",
        "carper": "1",
        "t": str(turno),
        "dt": dt,
        "ht": ht,
        "s": str(total_secoes),
        "st": str(secoes_apuradas),
        "pst": f"{step_pct:.2f}".replace(".", ","),
        "snt": str(total_secoes - secoes_apuradas),
        "psnt": f"{100.0 - step_pct:.2f}".replace(".", ","),
        "c": str(comparecimento),
        "pc": f"{(comparecimento / (eleitores_apurados or 1) * 100):.2f}".replace(".", ","),
        "a": str(abstencao),
        "pa": f"{(abstencao / (eleitores_apurados or 1) * 100):.2f}".replace(".", ","),
        "vv": str(validos),
        "pvv": f"{(validos / (comparecimento or 1) * 100):.2f}".replace(".", ","),
        "vb": str(brancos),
        "pvb": f"{(brancos / (comparecimento or 1) * 100):.2f}".replace(".", ","),
        "tvn": str(nulos),
        "ptvn": f"{(nulos / (comparecimento or 1) * 100):.2f}".replace(".", ","),
        "tv": str(comparecimento),
        "cand": cand_list
    }
    return sim_data


def run_worker(
    ciclo: str = "ele2026",
    cod_eleicao: Optional[str] = None,
    turno: Optional[int] = None,
    interval: int = POLL_INTERVAL_SECONDS,
    custom_url: Optional[str] = None,
    simulate: bool = SIMULATE,
    run_once: bool = False
):
    global running
    register_signal_handlers()
    init_db(DB_PATH)
    client = TSEClient()

    ciclo_alvo = ciclo or CICLO_PADRAO
    turno_alvo = turno if turno is not None else TURNO_PADRAO

    if not custom_url:
        target_url = build_tse_url(ciclo=ciclo_alvo, cod_eleicao=cod_eleicao, turno=turno_alvo)
    else:
        target_url = custom_url

    logger.info("=" * 70)
    logger.info("WORKER DE APURAÇÃO ELEIÇÕES 2026 INICIADO")
    logger.info(f"Ciclo: {ciclo_alvo} | Turno: {turno_alvo} | Código Eleição: {cod_eleicao or COD_ELEICAO_1T}")
    logger.info(f"Ambiente: Oficial (Produção TSE)")
    logger.info(f"URL Alvo: {target_url}")
    logger.info(f"Intervalo de Coleta: {interval}s | Banco SQLite: {DB_PATH}")
    if simulate:
        logger.info(f"MODO DE SIMULAÇÃO ATIVADO: Gerando evolução progressiva para {ciclo_alvo}.")
    logger.info("=" * 70)

    sim_step = 5.0

    while running:
        logger.info(f"Iniciando consulta da apuração ({datetime.now().strftime('%H:%M:%S')})...")
        
        dados = None
        if simulate:
            dados = generate_simulated_snapshot(ciclo=ciclo_alvo, turno=turno_alvo, step_pct=sim_step)
            sim_step = min(100.0, sim_step + random.uniform(5.0, 15.0))
        else:
            dados = client.fetch_url(target_url)

        if dados and ("cand" in dados or "carg" in dados):
            norm_dados = normalize_tse_payload(dados)
            eleicao_str = str(norm_dados.get("ele", cod_eleicao or COD_ELEICAO_1T))
            pst = norm_dados.get("pst", "0,00")
            dt = norm_dados.get("dt", "")
            ht = norm_dados.get("ht", "")
            
            is_new = save_snapshot(
                dados_tse=norm_dados,
                ciclo=ciclo_alvo,
                eleicao=eleicao_str,
                turno=turno_alvo,
                db_path=DB_PATH
            )
            
            if is_new:
                logger.info(f"[NOVO SNAPSHOT APURADO] Seções Totalizadas: {pst}% | Horário TSE: {dt} {ht}")
                
                candidatos = norm_dados.get("cand", [])
                for idx, c in enumerate(candidatos[:3]):
                    logger.info(f"  #{idx+1} {c.get('nm')} ({c.get('n')}): {c.get('pvap')}% ({c.get('vap')} votos) [{c.get('st')}]")
            else:
                logger.info(f"[SNAPSHOT INALTERADO] Seções: {pst}% (Sem alterações desde a última consulta)")
        else:
            if not simulate:
                logger.info(
                    f"Dados da apuração ainda não disponibilizados pelo TSE no ambiente oficial ({target_url}). "
                    f"Aguardando próxima checagem em {interval}s..."
                )

        if run_once:
            logger.info("Execução única concluída (--once).")
            break

        for _ in range(interval):
            if not running:
                break
            time.sleep(1)

    logger.info("Worker finalizado com sucesso.")


def parse_arguments():
    parser = argparse.ArgumentParser(description="Worker de coleta da apuração das Eleições 2026 (TSE).")
    parser.add_argument("--ciclo", type=str, default="ele2026", help="Ciclo eleitoral (ele2026).")
    parser.add_argument("--eleicao", type=str, default=None, help="Código oficial da eleição no TSE.")
    parser.add_argument("--turno", type=int, default=TURNO_PADRAO, choices=[1, 2], help="Turno da eleição (1 ou 2).")
    parser.add_argument("--interval", type=int, default=POLL_INTERVAL_SECONDS, help="Intervalo de consulta em segundos.")
    parser.add_argument("--url", type=str, default=None, help="URL customizada direta do endpoint JSON.")
    parser.add_argument("--simulate", action="store_true", default=SIMULATE, help="Ativa simulação progressiva da contagem de votos (padrão: definido no .env).")
    parser.add_argument("--no-simulate", action="store_false", dest="simulate", help="Desativa o modo de simulação.")
    parser.add_argument("--once", action="store_true", help="Executa apenas uma consulta e encerra.")
    return parser.parse_args()


if __name__ == "__main__":
    args = parse_arguments()
    run_worker(
        ciclo=args.ciclo,
        cod_eleicao=args.eleicao,
        turno=args.turno,
        interval=args.interval,
        custom_url=args.url,
        simulate=args.simulate,
        run_once=args.once
    )
