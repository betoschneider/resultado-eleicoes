# -*- coding: utf-8 -*-
"""
Dashboard Interativo Streamlit para Acompanhamento em Tempo Real
da Apuração das Eleições Presidenciais 2026 (TSE).
Visualizações dinâmicas com Plotly, métricas em tempo real e tabelas.
Em total conformidade com as especificações técnicas oficiais de 2026 (-u.json).
"""

import time
import os
import random
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime

from config import (
    CICLO_PADRAO,
    TURNO_PADRAO,
    COD_ELEICAO_1T,
    COD_ELEICAO_2T,
    DB_PATH,
    SIMULATE,
    POLL_INTERVAL_SECONDS,
    build_tse_url
)
from database import (
    init_db,
    get_connection,
    get_latest_snapshot,
    get_candidates_evolution,
    get_all_snapshots,
    save_snapshot
)
from tse_client import TSEClient
from worker import generate_simulated_snapshot

# Cores fixas por número do candidato. Os demais recebem uma cor pseudoaleatória
# estável (mesma a cada renderização, mesmo com a auto-atualização ligada).
CORES_FIXAS_CANDIDATO = {
    "22": "#00008B",  # FLAVIO BOLSONARO - azul escuro
    "13": "#FF0000",  # LULA - vermelho
}

# Quantos candidatos (melhores colocados por % de votos válidos) aparecem nos
# gráficos de evolução e, consequentemente, no tooltip.
TOP_N_EVOLUCAO = 6


def _cor_pseudoaleatoria(numero) -> str:
    """Gera uma cor estável (derivada do número do candidato) em formato hexadecimal."""
    rnd = random.Random(str(numero))
    return f"#{rnd.randint(0, 0xFFFFFF):06X}"


def mapa_cores_candidatos(df: pd.DataFrame) -> dict:
    """Mapeia o nome de cada candidato para uma cor fixa (principais) ou pseudoaleatória."""
    cores = {}
    for numero, nome in df[["numero", "nome"]].drop_duplicates().itertuples(index=False):
        cores[nome] = CORES_FIXAS_CANDIDATO.get(str(numero), _cor_pseudoaleatoria(numero))
    return cores


# Configuração da página do Streamlit
st.set_page_config(
    page_title="Apuração Presidencial 2026 - TSE",
    page_icon="🗳️",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Inicializa banco de dados se necessário
init_db(DB_PATH)

# Configurações carregadas do .env (sem seleção manual na interface)
ciclo_selecionado = CICLO_PADRAO
turno_selecionado = TURNO_PADRAO
cod_eleicao_selecionado = COD_ELEICAO_1T if turno_selecionado == 1 else COD_ELEICAO_2T
tse_url = build_tse_url(ciclo=ciclo_selecionado, cod_eleicao=cod_eleicao_selecionado, turno=turno_selecionado)

# ==============================================================================
# CABEÇALHO E CONTROLES
# ==============================================================================
st.title(f"🗳️ Eleições Presidenciais 2026 — {turno_selecionado}º Turno")

col_auto, col_atualizar, col_consultar = st.columns([1, 1, 1])

with col_auto:
    auto_refresh = st.checkbox("Auto-atualização periódica", value=True)
    refresh_interval = None
    if auto_refresh:
        refresh_interval = st.slider("Intervalo de atualização (segundos)", min_value=5, max_value=300, value=60, step=5)

with col_atualizar:
    if st.button("🔄 Atualizar", use_container_width=True, help="Recarrega a visualização"):
        st.rerun()

# with col_consultar:
    # if st.button("🌐 Consultar TSE", use_container_width=True, help="Faz uma requisição imediata à API oficial do TSE"):
    #     with st.spinner("Consultando API do TSE..."):
    #         client = TSEClient()
    #         data = client.fetch_url(tse_url)
    #         if data and ("cand" in data or "carg" in data):
    #             novo = save_snapshot(data, ciclo_selecionado, cod_eleicao_selecionado, turno_selecionado, DB_PATH)
    #             if novo:
    #                 st.success("Novo snapshot coletado com sucesso!")
    #             else:
    #                 st.info("Dados do TSE sem alterações desde a última consulta.")
    #         else:
    #             st.info("ℹ️ Dados ainda não disponibilizados pelo TSE no ambiente oficial.")
    #     st.rerun()

# refresh_interval = None
# if auto_refresh:
#     refresh_interval = st.slider("Intervalo de atualização (segundos)", min_value=5, max_value=300, value=60, step=5)

# ==============================================================================
# CARREGAMENTO DOS DADOS
# ==============================================================================
resumo, df_candidatos = get_latest_snapshot(ciclo_selecionado, turno_selecionado, DB_PATH)
df_evolucao = get_candidates_evolution(ciclo_selecionado, turno_selecionado, DB_PATH)
df_snapshots = get_all_snapshots(ciclo_selecionado, turno_selecionado, DB_PATH)

if resumo is None:
    st.info(
        f"### ⏳ Dados ainda não disponíveis no ambiente oficial do TSE\n\n"
        f"A totalização dos votos para as **Eleições Presidenciais 2026 ({turno_selecionado}º Turno)** ainda não foi aberta pela Justiça Eleitoral no ambiente oficial de produção.\n\n"
        f"📡 **Monitoramento em andamento:**\n"
        f"- **Endpoint Oficial:** `{tse_url}`\n"
        f"- **Status da Coleta:** O worker continuará consultando o TSE automaticamente a cada {POLL_INTERVAL_SECONDS} segundos. Assim que os dados forem publicados oficialmente, o dashboard exibirá automaticamente o progresso das urnas e os votos apurados."
    )
else:
    # Barra de Progresso e Métricas Gerais
    pct_secoes = resumo.get("pct_secoes_totalizadas", 0.0)
    secoes_tot = resumo.get("secoes_totalizadas", 0)
    secoes_totais = resumo.get("secoes_total", 0)
    dt_hr = resumo.get("dt_hr_tse", "N/A")

    st.subheader(f"Progresso da Apuração: {pct_secoes:.2f}% das Seções Totalizadas")
    st.progress(min(1.0, max(0.0, pct_secoes / 100.0)))
    st.caption(f"🕒 Última atualização do TSE: **{dt_hr}** | Seções Totalizadas: **{secoes_tot:,}** de **{secoes_totais:,}**".replace(",", "."))

    # Cards com métricas principais
    m1, m2, m3, m4, m5 = st.columns(5)

    with m1:
        v_validos = resumo.get("votos_validos", 0)
        pv_validos = resumo.get("pct_votos_validos", 0.0)
        st.metric(
            label="Votos Válidos",
            value=f"{v_validos:,}".replace(",", "."),
            delta=f"{pv_validos:.2f}%"
        )
    with m2:
        v_brancos = resumo.get("votos_brancos", 0)
        pv_brancos = resumo.get("pct_votos_brancos", 0.0)
        st.metric(
            label="Votos Brancos",
            value=f"{v_brancos:,}".replace(",", "."),
            delta=f"{pv_brancos:.2f}%"
        )
    with m3:
        v_nulos = resumo.get("votos_nulos", 0)
        pv_nulos = resumo.get("pct_votos_nulos", 0.0)
        st.metric(
            label="Votos Nulos",
            value=f"{v_nulos:,}".replace(",", "."),
            delta=f"{pv_nulos:.2f}%"
        )
    with m4:
        abst = resumo.get("abstencao", 0)
        p_abst = resumo.get("pct_abstencao", 0.0)
        st.metric(
            label="Abstenção",
            value=f"{abst:,}".replace(",", "."),
            delta=f"{p_abst:.2f}%",
            delta_color="inverse"
        )
    with m5:
        total = resumo.get("total_votos", 0)
        st.metric(
            label="Total de Votos",
            value=f"{total:,}".replace(",", ".")
        )

    st.divider()

    # ==========================================================================
    # VISUALIZAÇÃO DOS CANDIDATOS
    # ==========================================================================
    tab_evolucao, tab_classificacao, tab_historico = st.tabs([
        "📈 Evolução Temporal dos Votos",
        "🏆 Classificação Atual",
        "📋 Histórico de Snapshots"
    ])

    with tab_evolucao:
        st.subheader("Evolução Temporal da Apuração")
        st.caption(f"Dica: o tooltip mostra apenas os {TOP_N_EVOLUCAO} candidatos mais bem colocados (por % de votos válidos).")

        if not df_evolucao.empty and len(df_snapshots) > 1:
            # Ranking mais recente por % de votos (decrescente).
            ordem_candidatos = (
                df_evolucao.sort_values("dt_hr_tse")
                .groupby("nome", as_index=False)
                .tail(1)
                .sort_values("pct_votos_apurados", ascending=False)["nome"]
                .tolist()
            )
            # Mantém nos gráficos apenas os N melhores colocados, de modo que o
            # tooltip (hover unificado) exiba exatamente esses candidatos.
            top_candidatos = ordem_candidatos[:TOP_N_EVOLUCAO]
            df_evolucao_top = df_evolucao[df_evolucao["nome"].isin(top_candidatos)]
            cores_mapa = mapa_cores_candidatos(df_evolucao_top)

            fig_line = px.line(
                df_evolucao_top,
                x="pct_secoes_totalizadas",
                y="pct_votos_apurados",
                color="nome",
                color_discrete_map=cores_mapa,
                category_orders={"nome": top_candidatos},
                markers=True,
                labels={
                    "pct_secoes_totalizadas": "% Seções Apuradas",
                    "pct_votos_apurados": "% Votos Válidos do Candidato",
                    "nome": "Candidato"
                },
                title="Curva de Evolução dos Candidatos vs Progresso das Seções"
            )
            fig_line.update_layout(
                height=500,
                hovermode="x unified",
                xaxis=dict(title="% Seções Totalizadas", range=[0, 105]),
                yaxis=dict(title="% Votos Válidos", range=[0, 100])
            )
            st.plotly_chart(fig_line, use_container_width=True)

            fig_abs = px.line(
                df_evolucao_top,
                x="pct_secoes_totalizadas",
                y="votos_apurados",
                color="nome",
                color_discrete_map=cores_mapa,
                category_orders={"nome": top_candidatos},
                markers=True,
                labels={
                    "pct_secoes_totalizadas": "% Seções Apuradas",
                    "votos_apurados": "Votos Absolutos",
                    "nome": "Candidato"
                },
                title="Evolução Absoluta de Votos por Candidato"
            )
            fig_abs.update_layout(
                height=450,
                hovermode="x unified"
            )
            st.plotly_chart(fig_abs, use_container_width=True)
        else:
            st.info("Aguardando novas fotografias (snapshots) do TSE para traçar a evolução temporal.")

    with tab_classificacao:
        st.subheader("Classificação dos Candidatos")

        if not df_candidatos.empty:
            df_plot = df_candidatos.copy()
            df_plot["rotulo"] = df_plot["nome"] + " (" + df_plot["numero"] + ")"
            df_plot = df_plot.sort_values(by="votos_apurados", ascending=True)

            fig_bar = px.bar(
                df_plot,
                x="pct_votos_apurados",
                y="rotulo",
                orientation="h",
                text=df_plot["pct_votos_apurados"].apply(lambda x: f"{x:.2f}%"),
                labels={"pct_votos_apurados": "% Votos Válidos", "rotulo": "Candidato"},
                title=f"Percentual de Votos por Candidato — Eleições 2026 ({turno_selecionado}º Turno)",
                color="pct_votos_apurados",
                color_continuous_scale="Viridis"
            )
            fig_bar.update_layout(height=450, showlegend=False, xaxis=dict(range=[0, max(20.0, df_candidatos['pct_votos_apurados'].max() + 5)]))
            st.plotly_chart(fig_bar, use_container_width=True)

            # Tabela de dados formatada
            st.markdown("#### Detalhes por Candidato")
            df_show = df_candidatos[[
                "numero", "nome", "partido_coligacao", "vice", "votos_apurados", "pct_votos_apurados", "situacao"
            ]].copy()

            df_show.columns = [
                "Nº", "Candidato(a)", "Partido / Coligação", "Vice", "Votos Apurados", "% Votos Válidos", "Situação"
            ]

            df_show["Votos Apurados"] = df_show["Votos Apurados"].apply(lambda v: f"{v:,}".replace(",", "."))
            df_show["% Votos Válidos"] = df_show["% Votos Válidos"].apply(lambda p: f"{p:.2f}%")

            st.dataframe(
                df_show,
                use_container_width=True,
                hide_index=True
            )
        else:
            st.info("Nenhum dado de candidatos disponível para este snapshot.")



    with tab_historico:
        st.subheader("Histórico Completo de Fotografias (Snapshots)")
        if not df_snapshots.empty:
            df_snap_view = df_snapshots[[
                "id", "dt_hr_tse", "pct_secoes_totalizadas", "secoes_totalizadas", "secoes_total",
                "votos_validos", "votos_brancos", "votos_nulos", "total_votos", "timestamp_coleta"
            ]].copy()
            df_snap_view.columns = [
                "ID", "Data/Hora TSE", "% Seções", "Seções Apuradas", "Total Seções",
                "Votos Válidos", "Votos Brancos", "Votos Nulos", "Total Votos", "Horário Coleta"
            ]
            st.dataframe(df_snap_view, use_container_width=True, hide_index=True)
        else:
            st.info("Nenhum snapshot gravado no banco de dados.")

    # ==========================================================================
    # EXPORTAÇÃO DE DADOS
    # ==========================================================================
    st.divider()
    st.subheader("📥 Exportação de Dados")
    if not df_evolucao.empty:
        csv_data = df_evolucao.to_csv(index=False).encode("utf-8")
        st.download_button(
            label="📄 Baixar Série Histórica Completa (CSV)",
            data=csv_data,
            file_name="apuracao_presidencial_2026.csv",
            mime="text/csv",
            use_container_width=True
        )

# ==============================================================================
# PAINEL DE SIMULAÇÃO (apenas se TSE_SIMULATE estiver ativo no .env)
# ==============================================================================
if SIMULATE:
    with st.expander("🛠️ Simulação para Testes (Modo Mock)"):
        st.caption("Gera snapshots com porcentagens progressivas para testar os gráficos sem conexão com o TSE.")
        sim_pct = st.slider("Avanço das Seções (%)", min_value=1.0, max_value=100.0, value=50.0, step=5.0)
        if st.button("Adicionar Snapshot Simulado"):
            sim_data = generate_simulated_snapshot(ciclo_selecionado, turno_selecionado, sim_pct)
            save_snapshot(sim_data, ciclo_selecionado, cod_eleicao_selecionado, turno_selecionado, DB_PATH)
            st.success(f"Snapshot com {sim_pct}% adicionado ao banco!")
            st.rerun()

# ==============================================================================
# ENDPOINT OFICIAL DO TSE
# ==============================================================================
st.divider()
st.markdown(f"""
<small><b>Endpoint Oficial do TSE:</b><br>
<a href="{tse_url}" target="_blank" style="word-break: break-all;">{tse_url}</a></small>
""", unsafe_allow_html=True)

# ==============================================================================
# AUTO-ATUALIZAÇÃO (ao final, para não bloquear a renderização da página)
# ==============================================================================
if auto_refresh and refresh_interval:
    time.sleep(refresh_interval)
    st.rerun()
