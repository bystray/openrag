# Индексация OpenSearch

## 1. Что это

Запись обработанных чанков в индекс OpenSearch с текстом, метаданными и векторным полем. Индекс — основное хранилище базы знаний OpenRAG.

## 2. Зачем используется

- Хранение чанков и их векторов для последующего семантического поиска.
- Фильтрация по filename, owner, mimetype, connector_type и др.

## 3. Как работает

### Структура индекса

- Имя индекса: OPENSEARCH_INDEX_NAME (по умолчанию `documents`). Создание при старте приложения (main.py): если индекс не существует, создаётся с INDEX_BODY; при включённом динамическом индексе вызывается create_dynamic_index_body для текущей embedding-модели и при необходимости обновляется mapping (ensure_embedding_field_exists добавляет поле chunk_embedding_* для новой модели).

### Структура документа (маппинг)

- **Ключевые поля**: document_id (keyword), filename (keyword), mimetype (keyword), page (integer), text (text).
- **Вектор**: chunk_embedding (legacy, dimension из VECTOR_DIM) и/или chunk_embedding_{normalized_model} (knn_vector, dimension по модели, method disk_ann, engine jvector, space_type l2, ef_construction, m).
- **Метаданные и ACL**: embedding_model (keyword), embedding_dimensions (integer), source_url (keyword), connector_type (keyword), owner (keyword), allowed_users (keyword), allowed_groups (keyword), user_permissions (object), group_permissions (object), created_time (date), modified_time (date), indexed_time (date), metadata (object).

### Metadata

- Передаётся из Backend в Langflow через заголовки и tweaks (owner, owner_name, owner_email, FILENAME, MIMETYPE, FILESIZE, CONNECTOR_TYPE, DOCUMENT_ID, SOURCE_URL, ALLOWED_USERS, ALLOWED_GROUPS). В flow компонент OpenSearch записывает их в соответствующие поля документа.

### Embedding-поля

- Имя поля: get_embedding_field_name(model_name) → chunk_embedding_{normalized_model}. При смене модели эмбеддингов новое поле добавляется через put_mapping (ensure_embedding_field_exists); поиск в SearchService идёт по полю, соответствующему выбранной модели.

## 4. Где используется в системе

- **Создание/обновление индекса**: main.py (create index, create_dynamic_index_body), config/settings.py INDEX_BODY, utils/embeddings.py create_dynamic_index_body, utils/embedding_fields.py ensure_embedding_field_exists.
- **Запись документов**: выполняется в **Langflow flow** компонентом OpenSearch; Backend не пишет чанки напрямую, только задаёт переменные и параметры flow.
- **Поиск и удаление**: services/search_service.py (search по индексу), api/documents.py (delete_documents_by_filename_core через build_filename_delete_body), utils/opensearch_queries.py (build_filename_query, build_filename_search_body, build_filename_delete_body).

## 5. Связанные компоненты

Langflow (OpenSearch component в flow), config/settings, utils/embeddings, utils/embedding_fields, utils/opensearch_queries, SearchService, DocumentService, api/documents.

---

## Ключевые понятия

Index, mapping, knn_vector, keyword, document_id, filename, owner, metadata.

## Основные сущности

Индекс documents, chunk document, INDEX_BODY, create_dynamic_index_body, ensure_embedding_field_exists.

## Связанные компоненты

OpenSearch, Langflow flow, embedding_fields, opensearch_queries, SearchService, api/documents.
