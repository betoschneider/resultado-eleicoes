# Apuração Presidencial - TSE 🗳️

Sistema completo para monitoramento, coleta contínua e visualização da evolução da apuração para o **Pleito Presidencial** (2026, 2030 ou qualquer eleição), utilizando a API oficial do Tribunal Superior Eleitoral (TSE), persistência incremental em SQLite (com sincronização em Excel) e frontend interativo em **Streamlit**.

---

## 📌 Principais Características

- **Conformidade com as Especificações Técnicas Oficiais do TSE (2026)**:
  - Totalmente adaptado para a nova estrutura de arquivos e diretórios (`-u.json` em `dados/br/br-c0001-e{cod}-u.json`).
  - Compatibilidade com o arquivo de configuração oficial `ele-c.json` / [`lista-eleicoes.json`](file:///lista-eleicoes.json).
  - Suporte ao ambiente de **Simulado Oficial do TSE** e ao ambiente de **Produção Oficial**.
- **Totalmente desacoplado de anos fixos**: Todos os parâmetros (ciclo eleitoral, códigos de eleição no TSE, turno e cargo) são configurados via arquivo [`.env`](file:///.env).
- **Execução em Container Docker seguro**:
  - Container roda com usuário **não-root** (`appuser`, UID 1000).
  - Porta mapeada: **`8540`**.
  - Gerenciamento inteligente de processos via script [`entrypoint.sh`](file:///entrypoint.sh) (inicia o worker de coleta contínua em background e a interface Streamlit em foreground com captura de sinais para shutdown gracioso).
  - Construído com **`uv`** para máxima performance e reprodutibilidade.
- **Worker com persistência incremental**: As fotografias da apuração são appendadas continuamente ao SQLite com modo WAL ativado sem duplicar registros inalterados e sincronizando com `resultado.xlsx`.
- **Dashboard Streamlit**:
  - Gráficos de evolução histórica dos votos válidos e nominais por candidato.
  - Métricas de totalização (% urnas apuradas, abstenção, válidos, brancos e nulos).
  - Tabela de classificação com situação no TSE, vices e exportação para Excel/CSV.

---

## ⚙️ Configuração via `.env`

O arquivo [`.env`](file:///.env) permite alternar facilmente entre o ambiente de testes oficial (Simulado TSE) e o dia do pleito oficial:

### Modo 1: Simulado Oficial do TSE (Ativo e com dados de teste)

```env
TSE_BASE_URL=https://resultados-sim.tse.jus.br/simulado
TSE_AMBIENTE=simulado2026
TSE_CICLO=ele2026
TURNO=1
TSE_COD_ELEICAO_1T=21270
TSE_COD_ELEICAO_2T=21271
TSE_COD_CARGO=c0001
TSE_SIMULATE=false
POLL_INTERVAL_SECONDS=60
STREAMLIT_SERVER_PORT=8540
```

### Modo 2: Dia da Eleição Real (Produção Oficial do TSE)

```env
TSE_BASE_URL=https://resultados.tse.jus.br/oficial
TSE_AMBIENTE=
TSE_CICLO=ele2026
TURNO=1
TSE_COD_ELEICAO_1T=21270
TSE_COD_ELEICAO_2T=21271
TSE_COD_CARGO=c0001
TSE_SIMULATE=false
```

---

## 🐳 Executando com Docker (Recomendado)

### 1. Iniciar o Container na Porta 8540

```bash
docker compose up -d --build
```

### 2. Acessar o Dashboard

Abra no navegador:
👉 **`http://localhost:8540`**

### 3. Visualizar os Logs do Worker e do Streamlit

```bash
docker compose logs -f
```

### 4. Parar o Container

```bash
docker compose stop
```

---

## 💻 Executando Localmente (Sem Docker)

Caso prefira rodar diretamente no host com `uv`:

```bash
# 1. Criar ambiente e instalar dependências com uv
uv venv .venv
source .venv/bin/activate
uv pip install -r requirements.txt

# 2. Executar os testes automatizados
python test_system.py

# 3. Iniciar o Worker em um terminal
python worker.py

# 4. Iniciar o Streamlit em outro terminal
streamlit run app.py --server.port 8540
```
