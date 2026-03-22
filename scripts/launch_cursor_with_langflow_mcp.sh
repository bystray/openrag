#!/usr/bin/env bash
# Запуск Cursor из каталога репозитория с подхватом LANGFLOW_* из .env.
# Remote MCP в .cursor/mcp.json не читает .env сам — переменные должны быть в окружении процесса.
# LANGFLOW_URL: для Cursor на Windows и Langflow в WSL задайте в .env тот хост:порт, с которого клиент реально
# достучится до Langflow (часто IP из hostname -I в WSL, если localhost Windows не проброшен на Docker в WSL).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ENV_FILE="${ROOT}/.env"
if [[ -f "${ENV_FILE}" ]]; then
  set -a
  # shellcheck disable=SC1090
  source "${ENV_FILE}"
  set +a
fi
if [[ -z "${LANGFLOW_KEY:-}" || -z "${LANGFLOW_MCP_PROJECT_ID:-}" ]]; then
  echo "Задайте в ${ENV_FILE} переменные LANGFLOW_KEY и LANGFLOW_MCP_PROJECT_ID (см. .env.example)." >&2
  exit 1
fi
# Без завершающего / — подставляется в .cursor/mcp.json как база URL.
# На Windows Cursor + Langflow в WSL задайте в .env LANGFLOW_URL=http://<IP_из_hostname_-I>:7860
export LANGFLOW_URL="${LANGFLOW_URL:-http://127.0.0.1:7860}"
export LANGFLOW_URL="${LANGFLOW_URL%/}"
export LANGFLOW_KEY LANGFLOW_MCP_PROJECT_ID
CURSOR_BIN="${CURSOR_BIN:-cursor}"
exec "${CURSOR_BIN}" "${ROOT}"
