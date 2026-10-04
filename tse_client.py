# -*- coding: utf-8 -*-
"""
Cliente HTTP especializado para consumo dos dados oficiais do TSE.
Inclui cabeçalhos adequados, tratamento de erros de rede (404, 429, timeouts).
"""

import base64
import json
import requests
import logging
from typing import Dict, Any, Optional
from config import HTTP_HEADERS, build_tse_url

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger(__name__)


class TSEClient:
    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update(HTTP_HEADERS)

    def _decode_response(self, response) -> Optional[Dict[str, Any]]:
        """
        Decodifica a resposta do TSE. Suporta dois formatos:
        - JSON puro (simulado, .json)
        - JWS compacto 'header.payload.signature' (oficial, .jws), cujo payload contém o JSON.
        """
        texto = (response.text or "").strip()
        if not texto:
            return None

        # JWS compacto: três segmentos separados por '.' e não começa com '{'
        if not texto.startswith("{") and texto.count(".") >= 2:
            try:
                payload_b64 = texto.split(".")[1]
                payload_b64 += "=" * (-len(payload_b64) % 4)
                return json.loads(base64.urlsafe_b64decode(payload_b64).decode("utf-8"))
            except (IndexError, ValueError, json.JSONDecodeError) as exc:
                logger.error(f"Falha ao decodificar o payload JWS do TSE: {exc}")
                return None

        try:
            return response.json()
        except ValueError:
            logger.warning("Resposta do TSE não é JSON nem JWS válido.")
            return None

    def fetch_url(self, url: str) -> Optional[Dict[str, Any]]:
        """
        Executa requisição GET ao endpoint do TSE com tratamento de exceções.
        """
        try:
            response = self.session.get(url, timeout=self.timeout)
            
            if response.status_code == 200:
                return self._decode_response(response)
            elif response.status_code == 404:
                logger.info(f"Dados ainda não disponibilizados pelo TSE no ambiente oficial (404): {url}")
                return None
            elif response.status_code == 429:
                logger.error(f"Taxa limite excedida (429) no TSE. Aguarde antes da próxima requisição.")
                return None
            else:
                logger.warning(f"Resposta do TSE com status {response.status_code} para {url}")
                return None
                
        except requests.exceptions.Timeout:
            logger.warning(f"Timeout ao consultar o TSE após {self.timeout}s.")
            return None
        except requests.exceptions.RequestException as e:
            logger.warning(f"Falha de conexão ao consultar TSE: {e}")
            return None
        except Exception as e:
            logger.error(f"Erro inesperado ao processar dados do TSE: {e}")
            return None

    def fetch_apuracao(self, ciclo: str = "ele2026", cod_eleicao: str = None, turno: int = 1) -> Optional[Dict[str, Any]]:
        """
        Monta a URL e busca os dados de apuração para o ciclo, código e turno informados.
        """
        url = build_tse_url(ciclo=ciclo, cod_eleicao=cod_eleicao, turno=turno)
        logger.info(f"Consultando API do TSE: {url}")
        return self.fetch_url(url)
