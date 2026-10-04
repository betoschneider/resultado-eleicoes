# -*- coding: utf-8 -*-
"""
Configurações centralizadas para o acompanhamento da apuração das Eleições 2026 (TSE).
Em total conformidade com a documentação técnica oficial das Eleições 2026 do TSE.
"""

import os
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

if ENV_FILE.exists():
    load_dotenv(ENV_FILE)
else:
    load_dotenv()

DATA_DIR = Path(os.getenv("ELEICOES_DATA_DIR", str(BASE_DIR / "data")))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Banco de dados e arquivos de saída
DB_PATH = os.getenv("ELEICOES_DB_PATH", str(DATA_DIR / "eleicoes.db"))
CSV_OUTPUT_PATH = os.getenv("ELEICOES_CSV_PATH", str(BASE_DIR / "resultado.csv"))

# Configuração da API do TSE para 2026 (ambiente oficial de produção)
TSE_BASE_URL = os.getenv("TSE_BASE_URL", "https://resultados.tse.jus.br/oficial")
TSE_AMBIENTE = os.getenv("TSE_AMBIENTE", "")
CICLO_PADRAO = "ele2026"
TURNO_PADRAO = int(os.getenv("TURNO", "1"))

# Códigos oficiais das eleições de 2026 (fonte: /oficial/comum/config/ele-c.jws -> pleito 3220):
# 6257 = Eleição Ordinária Federal (Presidente) - 1º Turno  (2º turno: 6258)
# 6259 = Eleição Ordinária Estadual - 1º Turno             (2º turno: 6260)
# 6261 = Eleição Ordinária Municipal - 2026
COD_ELEICAO_1T = os.getenv("TSE_COD_ELEICAO_1T", "6257")
COD_ELEICAO_2T = os.getenv("TSE_COD_ELEICAO_2T", "6258")

# Código do cargo no TSE (c0001 = Presidente da República, c0005 = Senador)
COD_CARGO = os.getenv("TSE_COD_CARGO", "c0001")

# Extensão dos arquivos de dados: "jws" (oficial, JWS compacto) ou "json" (simulado)
TSE_EXTENSAO = os.getenv("TSE_EXTENSAO", "jws").strip().lower().lstrip(".") or "jws"

# Unidade federativa padrão (br = consolidado nacional; zz = votação no exterior)
TSE_UF_PADRAO = os.getenv("TSE_UF", "br").strip().lower()

# Modo simulação local/mock (definido no .env para gerar dados aleatórios progressivos sem rede)
SIMULATE = os.getenv("TSE_SIMULATE", "false").strip().lower() in ("true", "1", "t", "yes", "sim")

# Intervalo padrão de consulta do worker (segundos)
POLL_INTERVAL_SECONDS = int(os.getenv("POLL_INTERVAL_SECONDS", "60"))

# Porta padrão do Streamlit
STREAMLIT_PORT = int(os.getenv("STREAMLIT_SERVER_PORT", "8540"))

# Headers para requisições HTTP (boas práticas para evitar bloqueios no WAF/CDN do TSE)
HTTP_HEADERS = {
    "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 ApuracaoPresidencialBot/1.0",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "pt-BR,pt;q=0.9,en-US;q=0.8,en;q=0.7",
    "Referer": "https://resultados.tse.jus.br/",
    "Origin": "https://resultados.tse.jus.br",
}


def build_tse_url(
    ciclo: str = CICLO_PADRAO,
    cod_eleicao: str = None,
    turno: int = 1,
    cargo: str = None,
    uf: str = None,
    ambiente: str = None,
    base_url: str = None,
    extensao: str = None,
    nocache: bool = False
) -> str:
    """
    Constrói a URL oficial dos dados da apuração no TSE para as Eleições 2026.
    Padrão oficial 2026: {base}/{ambiente}/{ciclo}/{cod_eleicao}/dados/{uf}/{uf}-{cargo}-e{cod_eleicao_6d}-u.{ext}
    Exemplos (oficial, JWS):
    - Presidente (Brasil): .../oficial/ele2026/6257/dados/br/br-c0001-e006257-u.jws
    - Exterior (ZZ):        .../oficial/ele2026/6257/dados/zz/zz-c0001-e006257-u.jws
    """
    ciclo_alvo = ciclo or CICLO_PADRAO
    cargo_alvo = cargo or COD_CARGO
    uf_alvo = (uf or TSE_UF_PADRAO).strip().lower()
    base = (base_url or TSE_BASE_URL).rstrip("/")
    amb = TSE_AMBIENTE if ambiente is None else ambiente
    ext = (extensao or TSE_EXTENSAO).strip().lower().lstrip(".") or "jws"

    if cod_eleicao is None or cod_eleicao == "":
        cod_eleicao = COD_ELEICAO_1T if turno == 1 else COD_ELEICAO_2T

    cod_6d = str(cod_eleicao).zfill(6)
    arquivo = f"{uf_alvo}-{cargo_alvo}-e{cod_6d}-u.{ext}"

    if amb:
        url = f"{base}/{amb}/{ciclo_alvo}/{cod_eleicao}/dados/{uf_alvo}/{arquivo}"
    else:
        url = f"{base}/{ciclo_alvo}/{cod_eleicao}/dados/{uf_alvo}/{arquivo}"

    if nocache:
        url += f"?nocache={int(time.time() * 1000)}"

    return url


def load_lista_eleicoes(file_path: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """Carrega o arquivo lista-eleicoes.json (configuração oficial ele-c.json do TSE)."""
    path = Path(file_path) if file_path else (BASE_DIR / "lista-eleicoes.json")
    if path.exists():
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None
    return None
