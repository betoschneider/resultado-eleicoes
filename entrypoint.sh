#!/bin/bash
set -e

# Encerramento gracioso ao receber sinal de parada
cleanup() {
    echo "[Entrypoint] Recebido sinal de término. Encerrando processos..."
    if [ -n "$WORKER_PID" ] && kill -0 "$WORKER_PID" 2>/dev/null; then
        kill -TERM "$WORKER_PID" 2>/dev/null || true
    fi
    if [ -n "$APP_PID" ] && kill -0 "$APP_PID" 2>/dev/null; then
        kill -TERM "$APP_PID" 2>/dev/null || true
    fi
    wait "$WORKER_PID" 2>/dev/null || true
    wait "$APP_PID" 2>/dev/null || true
    echo "[Entrypoint] Processos finalizados com segurança."
    exit 0
}

trap cleanup SIGINT SIGTERM

echo "=========================================================="
echo "🗳️  Sistema de Apuração Presidencial - TSE"
echo "Porta: ${STREAMLIT_SERVER_PORT:-8540}"
echo "Ciclo Eleitoral: ${TSE_CICLO:-ele2026}"
echo "Turno: ${TURNO:-1}"
echo "Usuário em execução: $(whoami) (UID: $(id -u))"
echo "=========================================================="

# Inicia o worker de coleta contínua em segundo plano
python worker.py &
WORKER_PID=$!
echo "[Entrypoint] Worker de coleta iniciado (PID: $WORKER_PID)"

# Inicia a interface Streamlit na porta configurada (8540)
streamlit run app.py \
    --server.port="${STREAMLIT_SERVER_PORT:-8540}" \
    --server.address="${STREAMLIT_SERVER_ADDRESS:-0.0.0.0}" \
    --server.headless=true \
    --browser.gatherUsageStats=false &
APP_PID=$!
echo "[Entrypoint] Streamlit iniciado na porta ${STREAMLIT_SERVER_PORT:-8540} (PID: $APP_PID)"

# Aguarda qualquer um dos processos encerrar
wait -n "$WORKER_PID" "$APP_PID" || true
cleanup
