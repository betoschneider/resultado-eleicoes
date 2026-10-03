# -*- coding: utf-8 -*-
"""
Camada de Persistência em Banco de Dados SQLite (Thread-safe com WAL mode)
para o acompanhamento da apuração das Eleições 2026 do TSE.
Totalmente em conformidade com o formato oficial (-u.json) do TSE.
"""

import sqlite3
import os
import json
import logging
from datetime import datetime
from typing import Dict, Any, List, Optional, Tuple
import pandas as pd

from config import DB_PATH

logger = logging.getLogger("database")


def get_connection(db_path: str = DB_PATH) -> sqlite3.Connection:
    """Cria e retorna uma conexão com o SQLite otimizada com WAL mode."""
    conn = sqlite3.connect(db_path, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    return conn


def init_db(db_path: str = DB_PATH):
    """Inicializa as tabelas do banco de dados relacional se não existirem."""
    os.makedirs(os.path.dirname(os.path.abspath(db_path)), exist_ok=True)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()

        # Tabela com as fotografias (snapshots) da apuração geral
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS apuracao_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                ciclo TEXT NOT NULL,
                eleicao TEXT NOT NULL,
                turno INTEGER NOT NULL,
                dt_hr_tse TEXT NOT NULL,
                dt_tse TEXT,
                ht_tse TEXT,
                timestamp_coleta TEXT NOT NULL,
                secoes_total INTEGER,
                secoes_totalizadas INTEGER,
                pct_secoes_totalizadas REAL,
                secoes_nao_totalizadas INTEGER,
                pct_secoes_nao_totalizadas REAL,
                comparecimento INTEGER,
                pct_comparecimento REAL,
                abstencao INTEGER,
                pct_abstencao REAL,
                votos_validos INTEGER,
                pct_votos_validos REAL,
                votos_brancos INTEGER,
                pct_votos_brancos REAL,
                votos_nulos INTEGER,
                pct_votos_nulos REAL,
                total_votos INTEGER,
                CONSTRAINT uq_snapshot UNIQUE (ciclo, eleicao, turno, dt_hr_tse, pct_secoes_totalizadas)
            );
        """)

        # Tabela com o histórico detalhado por candidato a cada snapshot
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS apuracao_candidatos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_id INTEGER NOT NULL,
                ciclo TEXT NOT NULL,
                turno INTEGER NOT NULL,
                dt_hr_tse TEXT NOT NULL,
                timestamp_coleta TEXT NOT NULL,
                pct_secoes_totalizadas REAL,
                seq INTEGER,
                sqcand TEXT,
                numero TEXT NOT NULL,
                nome TEXT NOT NULL,
                partido_coligacao TEXT,
                vice TEXT,
                eleito TEXT,
                situacao TEXT,
                votos_apurados INTEGER,
                pct_votos_apurados REAL,
                FOREIGN KEY (snapshot_id) REFERENCES apuracao_snapshots(id) ON DELETE CASCADE
            );
        """)

        # Índices para consultas rápidas nos gráficos de evolução
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cand_snap ON apuracao_candidatos (ciclo, turno, dt_hr_tse);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_cand_num ON apuracao_candidatos (ciclo, turno, numero);")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_snap_dt ON apuracao_snapshots (ciclo, turno, dt_hr_tse);")
        
        conn.commit()


def parse_brazilian_number(val: Any) -> float:
    """Converte números formatados em padrão brasileiro (ex: '48,50' ou '48.50') para float."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    val_str = str(val).strip().replace(".", "").replace(",", ".")
    try:
        return float(val_str)
    except ValueError:
        return 0.0


def parse_brazilian_int(val: Any) -> int:
    """Converte valores numéricos para int de forma segura."""
    if val is None:
        return 0
    if isinstance(val, int):
        return val
    try:
        return int(str(val).strip().replace(".", "").replace(",", ""))
    except ValueError:
        return 0


def normalize_tse_payload(dados_tse: Dict[str, Any]) -> Dict[str, Any]:
    """
    Normaliza os dados recebidos da API do TSE.
    Suporta:
    1. O formato oficial das Eleições 2026 (-u.json) com chaves 'carg', 's', 'v', etc.
    2. O formato simplificado/legado com lista 'cand' na raiz (usado em simulações locais).
    """
    if "cand" in dados_tse and isinstance(dados_tse["cand"], list):
        return dados_tse

    s_info = dados_tse.get("s", {})
    v_info = dados_tse.get("v", {})
    e_info = dados_tse.get("e", {})

    candidatos = []
    for carg in dados_tse.get("carg", []):
        for agr in carg.get("agr", []):
            agr_nm = agr.get("nm", "")
            agr_com = agr.get("com", "")
            for par in agr.get("par", []):
                partido_sg = par.get("sg", "")
                partido_coligacao = f"{partido_sg} - {agr_nm}" if agr_nm else str(partido_sg)
                if agr_com and agr_com != partido_sg:
                    partido_coligacao = f"{partido_sg} ({agr_com})"
                
                for c in par.get("cand", []):
                    vices = c.get("vs", [])
                    vice_nm = vices[0].get("nm", "") if vices else ""
                    
                    candidatos.append({
                        "seq": c.get("seq", "0"),
                        "sqcand": c.get("sqcand", ""),
                        "n": c.get("n", ""),
                        "nm": c.get("nmu") or c.get("nm", ""),
                        "cc": partido_coligacao,
                        "nv": vice_nm,
                        "e": c.get("e", "n"),
                        "st": c.get("st", ""),
                        "dvt": c.get("dvt", "Válido"),
                        "vap": str(c.get("vap", "0")),
                        "pvap": str(c.get("pvap", "0,00")),
                    })

    # Ordena os candidatos por número de votos decrescente
    candidatos.sort(key=lambda x: int(x["vap"] or 0), reverse=True)

    pst_val = s_info.get("pst", "0,00")
    normalized = {
        "ele": dados_tse.get("ele", ""),
        "tpabr": dados_tse.get("tpabr", "br"),
        "cdabr": dados_tse.get("cdabr", "br"),
        "t": dados_tse.get("t", "1"),
        "dt": dados_tse.get("dt", ""),
        "ht": dados_tse.get("ht", ""),
        "s": s_info.get("ts", "0"),
        "st": s_info.get("st", "0"),
        "pst": pst_val,
        "snt": s_info.get("snt", "0"),
        "psnt": s_info.get("psnt", "0,00"),
        "c": e_info.get("c", "0"),
        "pc": e_info.get("pc", "0,00"),
        "a": e_info.get("a", "0"),
        "pa": e_info.get("pa", "0,00"),
        "vv": v_info.get("vv", v_info.get("vvc", "0")),
        "pvv": v_info.get("pvv", v_info.get("pvvc", "0,00")),
        "vb": v_info.get("vb", "0"),
        "pvb": v_info.get("pvb", "0,00"),
        "tvn": v_info.get("tvn", v_info.get("vn", "0")),
        "ptvn": v_info.get("ptvn", "0,00"),
        "tv": v_info.get("tv", "0"),
        "cand": candidatos
    }
    return normalized


def save_snapshot(
    dados_tse: Dict[str, Any],
    ciclo: str,
    eleicao: str,
    turno: int,
    db_path: str = DB_PATH
) -> bool:
    """
    Insere uma nova fotografia da apuração no banco de dados.
    Normaliza o payload automaticamente antes de persistir.
    Retorna True se for um novo registro adicionado, ou False se já existia.
    """
    init_db(db_path)
    dados = normalize_tse_payload(dados_tse)
    
    # Tratamento de data e hora do TSE
    dt_str = dados.get("dt", "")
    ht_str = dados.get("ht", "")
    timestamp_coleta = datetime.now().isoformat()
    
    dt_hr_tse = ""
    if dt_str and ht_str:
        try:
            dt_obj = datetime.strptime(f"{dt_str} {ht_str}", "%d/%m/%Y %H:%M:%S")
            dt_hr_tse = dt_obj.strftime("%Y-%m-%d %H:%M:%S")
        except ValueError:
            dt_hr_tse = f"{dt_str} {ht_str}"
    else:
        dt_hr_tse = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    pst = parse_brazilian_number(dados.get("pst"))

    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        
        # Verifica se essa fotografia exata já foi salva para não duplicar
        cursor.execute("""
            SELECT id FROM apuracao_snapshots 
            WHERE ciclo = ? AND eleicao = ? AND turno = ? AND dt_hr_tse = ? AND pct_secoes_totalizadas = ?
        """, (ciclo, str(eleicao), turno, dt_hr_tse, pst))
        
        row = cursor.fetchone()
        if row:
            return False

        # Insere resumo geral da apuração
        cursor.execute("""
            INSERT INTO apuracao_snapshots (
                ciclo, eleicao, turno, dt_hr_tse, dt_tse, ht_tse, timestamp_coleta,
                secoes_total, secoes_totalizadas, pct_secoes_totalizadas,
                secoes_nao_totalizadas, pct_secoes_nao_totalizadas,
                comparecimento, pct_comparecimento, abstencao, pct_abstencao,
                votos_validos, pct_votos_validos, votos_brancos, pct_votos_brancos,
                votos_nulos, pct_votos_nulos, total_votos
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            ciclo,
            str(eleicao),
            turno,
            dt_hr_tse,
            dt_str,
            ht_str,
            timestamp_coleta,
            parse_brazilian_int(dados.get("s")),
            parse_brazilian_int(dados.get("st")),
            pst,
            parse_brazilian_int(dados.get("snt")),
            parse_brazilian_number(dados.get("psnt")),
            parse_brazilian_int(dados.get("c")),
            parse_brazilian_number(dados.get("pc")),
            parse_brazilian_int(dados.get("a")),
            parse_brazilian_number(dados.get("pa")),
            parse_brazilian_int(dados.get("vv") or dados.get("vnom")),
            parse_brazilian_number(dados.get("pvv")),
            parse_brazilian_int(dados.get("vb")),
            parse_brazilian_number(dados.get("pvb")),
            parse_brazilian_int(dados.get("tvn")),
            parse_brazilian_number(dados.get("ptvn")),
            parse_brazilian_int(dados.get("tv"))
        ))
        
        snapshot_id = cursor.lastrowid

        # Insere dados de cada candidato para a evolução temporal
        candidatos = dados.get("cand", [])
        for cand in candidatos:
            cursor.execute("""
                INSERT INTO apuracao_candidatos (
                    snapshot_id, ciclo, turno, dt_hr_tse, timestamp_coleta,
                    pct_secoes_totalizadas, seq, sqcand, numero, nome,
                    partido_coligacao, vice, eleito, situacao,
                    votos_apurados, pct_votos_apurados
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                snapshot_id,
                ciclo,
                turno,
                dt_hr_tse,
                timestamp_coleta,
                pst,
                parse_brazilian_int(cand.get("seq")),
                cand.get("sqcand", ""),
                str(cand.get("n", "")),
                cand.get("nm", ""),
                cand.get("cc", ""),
                cand.get("nv", ""),
                cand.get("e", "n"),
                cand.get("st", ""),
                parse_brazilian_int(cand.get("vap")),
                parse_brazilian_number(cand.get("pvap"))
            ))

        conn.commit()
        return True


def get_latest_snapshot(
    ciclo: str = "ele2026",
    turno: int = 1,
    db_path: str = DB_PATH
) -> Tuple[Optional[Dict[str, Any]], pd.DataFrame]:
    """Retorna o snapshot mais recente para o ciclo e turno informados."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM apuracao_snapshots 
            WHERE ciclo = ? AND turno = ?
            ORDER BY dt_hr_tse DESC, id DESC
            LIMIT 1
        """, (ciclo, turno))
        
        snap_row = cursor.fetchone()
        if not snap_row:
            return None, pd.DataFrame()

        snap_dict = dict(snap_row)
        snapshot_id = snap_dict["id"]

        df_cand = pd.read_sql_query("""
            SELECT numero, nome, partido_coligacao, vice, situacao, votos_apurados, pct_votos_apurados, eleito
            FROM apuracao_candidatos
            WHERE snapshot_id = ?
            ORDER BY votos_apurados DESC
        """, conn, params=(snapshot_id,))

        return snap_dict, df_cand


def get_candidates_evolution(
    ciclo: str = "ele2026",
    turno: int = 1,
    db_path: str = DB_PATH
) -> pd.DataFrame:
    """Retorna a série temporal da evolução de todos os candidatos."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        query = """
            SELECT 
                snapshot_id,
                dt_hr_tse,
                pct_secoes_totalizadas,
                numero,
                nome,
                partido_coligacao,
                votos_apurados,
                pct_votos_apurados
            FROM apuracao_candidatos
            WHERE ciclo = ? AND turno = ?
            ORDER BY dt_hr_tse ASC, votos_apurados DESC
        """
        df = pd.read_sql_query(query, conn, params=(ciclo, turno))
        return df


def get_all_snapshots(
    ciclo: str = "ele2026",
    turno: int = 1,
    db_path: str = DB_PATH
) -> pd.DataFrame:
    """Retorna todo o histórico de snapshots agregados para visualização."""
    init_db(db_path)
    with get_connection(db_path) as conn:
        query = """
            SELECT * FROM apuracao_snapshots
            WHERE ciclo = ? AND turno = ?
            ORDER BY dt_hr_tse ASC
        """
        df = pd.read_sql_query(query, conn, params=(ciclo, turno))
        return df
