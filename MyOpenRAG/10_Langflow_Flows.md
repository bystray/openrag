# Langflow Flows

## 1. Что это

Langflow — визуальный конструктор потоков (flow): граф узлов (компонентов), связанных входами/выходами. В OpenRAG используются готовые flow для инжеста документов и для чата (RAG). Flow загружаются по ID (LANGFLOW_INGEST_FLOW_ID, LANGFLOW_CHAT_FLOW_ID, LANGFLOW_URL_INGEST_FLOW_ID) и запускаются через REST API.

## 2. Зачем используется

- Единая среда для парсинга (Docling), чанкинга (SplitText), эмбеддингов и записи в OpenSearch без жёсткой привязки к коду Backend.
- Гибкая настройка параметров (tweaks, settings) и подмена компонентов (модели, провайдеры).

## 3. Как работает

### Langflow

- Сервис в отдельном контейнере. URL: LANGFLOW_URL (например http://langflow:7860). Аутентификация: API key (LANGFLOW_KEY), генерируется при старте из LANGFLOW_SUPERUSER / LANGFLOW_SUPERUSER_PASSWORD. Backend держит клиент (AsyncOpenAI base_url Langflow) и httpx для запросов (clients.langflow_request).

### Flows

- **Ingestion flow**: ID в LANGFLOW_INGEST_FLOW_ID. Запуск: POST /api/v1/run/{flow_id}, body: input_value, input_type, output_type, tweaks (в т.ч. DoclingRemote-Dp3PX.path — пути к файлам). Заголовки: X-Langflow-Global-Var-* (JWT, OWNER, FILENAME, MIMETYPE, FILESIZE, SELECTED_EMBEDDING_MODEL, OPENSEARCH_*, DOCLING_SERVE_URL и др.). Результат — ответ run (JSON).
- **Chat flow**: ID в LANGFLOW_CHAT_FLOW_ID. Запуск через FlowsService/patched client для чата; передаётся история и запрос, flow выполняет retrieval по OpenSearch и вызов LLM.
- **URL ingestion flow**: LANGFLOW_URL_INGEST_FLOW_ID — инжест по URL (например документация); при отсутствии/невалидном ID flow может импортироваться из flows/openrag_url_mcp.json.

### Nodes

- Узлы flow: DoclingRemote (парсинг), SplitText (чанки), эмбеддинги (OpenAI Embeddings и др.), OpenSearch (запись/поиск), LLM, Chat Input/Output и т.д. Идентификаторы в tweaks (например DoclingRemote-Dp3PX, SplitText-QIKhg, OpenAIEmbeddings-joRJ6) задаются в определении flow.

### Global variables

- Передаются из окружения в Langflow через LANGFLOW_VARIABLES_TO_GET_FROM_ENVIRONMENT (docker-compose): JWT, OPENRAG-QUERY-FILTER, OPENSEARCH_PASSWORD, OPENSEARCH_URL, DOCLING_SERVE_URL, OWNER, OWNER_NAME, OWNER_EMAIL, CONNECTOR_TYPE, DOCUMENT_ID, SOURCE_URL, ALLOWED_USERS, ALLOWED_GROUPS, FILENAME, MIMETYPE, FILESIZE, SELECTED_EMBEDDING_MODEL, OPENAI_API_KEY, ANTHROPIC_API_KEY, WATSONX_*, OLLAMA_BASE_URL, OPENSEARCH_INDEX_NAME. При запуске run дополнительно передаются заголовки X-Langflow-Global-Var-* для переопределения на запрос.

## 4. Где используется в системе

- **Backend**: services/langflow_file_service.py (upload_user_file, run_ingestion_flow, upload_and_ingest_file, run_url_ingestion_flow), services/flows_service.py (чат), config/settings.py (LANGFLOW_*), utils/langflow_headers.py (add_provider_credentials_to_headers).
- **Загрузка**: TaskService + LangflowFileProcessor вызывают LangflowFileService.upload_and_ingest_file.
- **Чат**: ChatService использует FlowsService/клиент для вызова chat flow.
- **Коннекторы**: LangflowConnectorService вызывает process_connector_document, внутри — загрузка в Langflow и run ingestion flow.

## 5. Связанные компоненты

LangflowFileService, FlowsService, TaskService, LangflowFileProcessor, LangflowConnectorService, config/settings, OpenSearch, Docling.

---

## Ключевые понятия

Flow, node, tweaks, global variables, ingestion flow, chat flow, run API.

## Основные сущности

LANGFLOW_INGEST_FLOW_ID, LANGFLOW_CHAT_FLOW_ID, DoclingRemote, SplitText, OpenSearch component, X-Langflow-Global-Var-*.

## Связанные компоненты

LangflowFileService, FlowsService, TaskService, LangflowConnectorService, config/settings.
