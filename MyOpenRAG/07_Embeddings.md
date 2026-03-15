# Embeddings

## 1. Что это

Эмбеддинги — векторные представления текста (чанков и запросов), используемые для семантического поиска. В OpenRAG векторы создаются **внутри Langflow flow** (компоненты эмбеддингов); Backend задаёт модель через настройки и глобальные переменные и обеспечивает соответствие полей в OpenSearch размерности модели (ensure_embedding_field_exists).

## 2. Зачем используется

- Семантический поиск по базе знаний (kNN по векторам чанков).
- Единая модель для инжеста и запросов, чтобы векторы были в одном пространстве.

## 3. Как работает

### Модели эмбеддингов

- Задаются в конфигурации (knowledge.embedding_model, knowledge.embedding_provider). Поддерживаются: OpenAI (text-embedding-3-small, text-embedding-3-large, text-embedding-ada-002), Watsonx (ibm/granite-*, ibm/slate-*, intfloat/multilingual-e5-large, sentence-transformers/all-minilm-l6-v2), Ollama (модель и endpoint). Размерности для известных моделей заданы в config/settings.py: OPENAI_EMBEDDING_DIMENSIONS, WATSONX_EMBEDDING_DIMENSIONS; для Ollama — probing через utils/embeddings.py (_probe_ollama_embedding_dimension).

### Создание векторов

- В **ingestion flow**: компонент эмбеддингов (например OpenAI Embeddings) получает текст чанков и модель из глобальной переменной SELECTED_EMBEDDING_MODEL (передаётся в заголовках X-Langflow-Global-Var-SELECTED_EMBEDDING_MODEL из LangflowFileService.run_ingestion_flow). В **chat flow**: запрос пользователя эмбедится той же (или выбранной) моделью для kNN поиска.

### Структура эмбеддингов в OpenSearch

- Поле вектора: `chunk_embedding_{normalized_model_name}` (например chunk_embedding_text_embedding_3_small). Нормализация имени модели: utils/embedding_fields.py normalize_model_name (нижний регистр, дефисы/двоеточия/слэши/точки → подчёркивания). Тип поля: knn_vector, dimension — по модели, method: disk_ann, engine: jvector, space_type: l2. Дополнительно в документе: embedding_model (keyword), embedding_dimensions (integer) для совместимости и отладки.

## 4. Где используется в системе

- **Langflow flows**: компоненты эмбеддингов в ingestion и chat flows; глобальные переменные SELECTED_EMBEDDING_MODEL, провайдерские ключи (OPENAI_API_KEY и т.д.) передаются через add_provider_credentials_to_headers (utils/langflow_headers.py).
- **Backend**: config/settings.py (размерности, EMBED_MODEL), utils/embeddings.py (get_embedding_dimensions, create_dynamic_index_body), utils/embedding_fields.py (get_embedding_field_name, ensure_embedding_field_exists). SearchService использует get_embedding_field_name(embedding_model) для выбора поля при поиске.

## 5. Связанные компоненты

Langflow (ingestion flow, chat flow), OpenSearch (mapping полей), config/settings, embedding_fields, embeddings, SearchService.

---

## Ключевые понятия

Embedding, vector, dimension, knn_vector, embedding_model, normalize_model_name.

## Основные сущности

chunk_embedding_*, embedding_model, embedding_dimensions, get_embedding_field_name, get_embedding_dimensions.

## Связанные компоненты

Langflow, OpenSearch, config/settings, utils/embeddings, utils/embedding_fields, SearchService.
