# Поиск и Retrieval

## 1. Что это

Retrieval — получение релевантных чанков из OpenSearch по запросу пользователя: эмбеддинг запроса, kNN-поиск по векторному полю, применение фильтров и порога скора, возврат списка чанков с текстом и метаданными для сборки контекста LLM.

## 2. Зачем используется

- Обеспечение контекста для RAG: только релевантные фрагменты передаются в LLM.
- Фильтрация по источнику, типу документа, владельцу (multi-tenancy и ACL).

## 3. Как работает

### Semantic search

- Запрос пользователя преобразуется в вектор той же эмбеддинг-моделью, что используется для чанков. В Langflow chat flow это делает компонент эмбеддингов; в Backend SearchService получает уже сформированный запрос и использует get_embedding_model() или переданную embedding_model для выбора поля (get_embedding_field_name).

### Vector search

- kNN-запрос к OpenSearch: поле chunk_embedding_* (или chunk_embedding), вектор запроса, k (limit), num_candidates и др. Метрика — L2 (space_type: l2). Фильтры (bool/filter) применяются по полям: filename (data_sources), mimetype (document_types), owner (owners), connector_type. score_threshold отсекает результаты с низким скором.

### Retrieval pipeline

- В **Backend** (SearchService.search_tool / search): получение user_id, jwt_token, filters, limit, score_threshold; opensearch_client по пользователю (OIDC/JWT); определение embedding_model и embedding_field_name; при запросе "*" — агрегации без семантического поиска; иначе — построение kNN-запроса с фильтрами, выполнение search, возврат results с чанками и скорами.
- В **Langflow chat flow**: запрос → эмбеддинг → компонент поиска по OpenSearch → чанки → сборка контекста → LLM.

## 4. Где используется в системе

- **API**: POST /search (api/search.py) — body: query, filters, limit, scoreThreshold; вызывает search_service.search.
- **Агент**: SearchService.search_tool используется как инструмент агента (agent.py) для поиска по базе знаний.
- **Чат**: ChatService вызывает Langflow chat flow, внутри flow выполняется retrieval по OpenSearch.
- **Фильтры**: data_sources → filename, document_types → mimetype, owners → owner, connector_types → connector_type (SearchService).

## 5. Связанные компоненты

SearchService, OpenSearch, Langflow chat flow, embedding_fields, auth_context (get_search_filters, get_search_limit, get_score_threshold), api/search.

---

## Ключевые понятия

Semantic search, vector search, kNN, score_threshold, retrieval, context assembly.

## Основные сущности

SearchService, search_tool, embedding_field_name, filters, limit, score_threshold.

## Связанные компоненты

SearchService, OpenSearch, Langflow chat flow, api/search, auth_context, embedding_fields.
