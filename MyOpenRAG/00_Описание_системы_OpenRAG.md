# Описание системы OpenRAG

## 1. Что это

OpenRAG — платформа Retrieval-Augmented Generation (RAG) с открытым исходным кодом. Система объединяет загрузку документов, их парсинг, создание векторных представлений и семантический поиск с генерацией ответов на основе извлечённого контекста.

## 2. Зачем используется

- **Индексация документов**: загрузка файлов (PDF, Office, Markdown и др.), парсинг через Docling, разбиение на чанки, создание эмбеддингов и запись в OpenSearch.
- **Семантический поиск**: поиск по базе знаний по смыслу запроса (vector search).
- **RAG-чат**: ответы агента с опорой на найденные фрагменты документов и вызов LLM.
- **Коннекторы**: синхронизация документов из Google Drive, OneDrive, SharePoint.

## 3. Как работает

High-level workflow:

1. Пользователь загружает файлы через UI или коннектор.
2. Backend создаёт задачу (UploadTask), файлы обрабатываются через Langflow ingestion flow.
3. В flow: загрузка в Langflow Files API → вызов Docling (парсинг) → разбиение на чанки (SplitText) → эмбеддинги → запись в OpenSearch.
4. При запросе: эмбеддинг запроса → векторный поиск в OpenSearch → сборка контекста → вызов LLM (Chat flow).
5. Файл после инжеста по умолчанию удаляется из Langflow (delete_after_ingest=true).

## 4. Где используется в системе

- **Frontend**: Next.js, экраны Knowledge, Chat, настройки, загрузка файлов/папок.
- **Backend**: FastAPI, роуты `/upload_ingest`, `/search`, `/chat`, `/tasks`, `/settings`, `/connectors`, `/documents/*`.
- **Langflow**: два основных flow — инжест (LANGFLOW_INGEST_FLOW_ID) и чат (LANGFLOW_CHAT_FLOW_ID).
- **OpenSearch**: индекс `documents` (или OPENSEARCH_INDEX_NAME) — хранилище чанков и векторов.

## 5. Связанные компоненты

- Backend (FastAPI), Langflow, Docling Serve, OpenSearch, TaskService, LangflowFileService, SearchService, ChatService, Connectors.

---

## Ключевые понятия

RAG, инжест, семантический поиск, эмбеддинг, чанк, векторный индекс, flow, коннектор.

## Основные сущности

UploadTask, FileTask, документ, чанк, индекс OpenSearch, ingestion flow, chat flow.

## Связанные компоненты

Frontend, Backend, Langflow, Docling, OpenSearch, TaskService, SearchService, ChatService, ConnectorService.
