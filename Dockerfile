# Multi-stage build utilizando uv para máxima velocidade e segurança
FROM python:3.12-slim

# Metadados
LABEL maintainer="Roberto Schneider"
LABEL description="Monitoramento e visualização da apuração presidencial do TSE"

# Instalação do uv a partir da imagem oficial
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Variáveis de ambiente para o Python
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_SYSTEM_PYTHON=1 \
    STREAMLIT_SERVER_PORT=8540 \
    STREAMLIT_SERVER_ADDRESS=0.0.0.0

WORKDIR /app

# Criação de usuário e grupo não-root para segurança
RUN groupadd -g 1000 appgroup && \
    useradd -u 1000 -g appgroup -m -s /bin/bash appuser

# Instalação de dependências do sistema necessárias para curl/saúde se desejado
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copia e instala dependências do projeto com uv
COPY requirements.txt ./
RUN uv pip install --system --no-cache -r requirements.txt

# Copia os arquivos do projeto
COPY . .

# Ajusta permissões dos diretórios para o usuário não-root
RUN mkdir -p /app/data && \
    chown -R appuser:appgroup /app && \
    chmod +x /app/entrypoint.sh

# Segurança: troca para o usuário não-root
USER appuser

# Porta do Streamlit
EXPOSE 8540

# Healthcheck do container
HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl --fail http://localhost:8540/_stcore/health || exit 1

# Executa o entrypoint gerenciador (worker + streamlit)
ENTRYPOINT ["/app/entrypoint.sh"]
