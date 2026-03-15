# Конфигурация Cursor для проекта OpenRAG

## MCP Server (Langflow Starter Project)

Чтобы подключить Langflow MCP Server (Starter Project) к Cursor:

1. Скопируйте содержимое `mcp.example.json` в ваш файл конфигурации MCP:
   - **macOS/Linux:** `~/.cursor/mcp.json`
   - Либо объедините с уже существующими `mcpServers` в этом файле.

2. Подставьте свои значения:
   - `YOUR_LANGFLOW_API_KEY` — API-ключ из Langflow (Starter Project → MCP Server → Edit Auth).
   - `YOUR_PROJECT_ID` — UUID проекта из URL страницы MCP Server в Langflow (например `cad92c93-261d-412c-8a55-1b048408ce3e`).
   - При необходимости замените `localhost:7868` на хост и порт вашего Langflow.

3. Перезапустите Cursor после изменения конфигурации.

Транспорт **Streamable HTTP** используется по умолчанию в примере; при необходимости можно переключиться на SSE в интерфейсе Langflow и скорректировать аргументы в `args`.
