# Chunking и NodeBuilder

## 1. Что это

Chunking — разбиение текста документа на фрагменты (чанки) фиксированного или адаптивного размера. В OpenRAG разбиение выполняется **внутри Langflow ingestion flow** компонентом SplitText (или аналогом). NodeBuilder в коде Backend явно не выделен; «узлами» можно считать чанки, которые затем эмбедятся и записываются в OpenSearch как отдельные документы.

## 2. Зачем используется

- Ограничение размера контекста для эмбеддинг-моделей и для поиска.
- Сохранение смысловой целостности за счёт chunk_overlap и выбора разделителей (separator).

## 3. Как работает

### Создание chunks

- В Langflow flow после парсинга (Docling) текст или блоки подаются в компонент разбиения. В коде упоминается **SplitText-QIKhg**: настройки chunk_size, chunk_overlap, separator передаются через tweaks из Backend (api/langflow_files, langflow_file_service — раздел settings: chunkSize, chunkOverlap, separator маппятся в SplitText-QIKhg). Размер и перекрытие задаются в символах или токенах в зависимости от реализации компонента.

### Создание nodes

- В контексте OpenRAG «node» — это один индексируемый документ в OpenSearch: один чанк текста + метаданные (filename, mimetype, page, owner и т.д.) + вектор эмбеддинга. Создание узлов выполняется в flow: после SplitText каждый чанк идёт в эмбеддинг, затем в компонент записи в OpenSearch; там формируется структура документа с полями text, filename, chunk_embedding_*, embedding_model и др.

### Структуры данных

- **Чанк**: строка текста (и при необходимости метаданные страницы/блока). В OpenSearch хранится в поле `text`.
- **Документ индекса**: один чанк = один документ с полями: document_id, filename, mimetype, page, text, chunk_embedding_* (или chunk_embedding для legacy), embedding_model, embedding_dimensions, owner, allowed_users, allowed_groups, source_url, connector_type, created_time, modified_time, indexed_time, metadata. Имя файла в индексе — нормализованное (safe storage filename), чтобы поиск и удаление по имени были консистентны.

## 4. Где используется в системе

- **Langflow ingestion flow**: компонент SplitText (или аналог), настройки через tweaks из LangflowFileService.run_ingestion_flow (settings → SplitText-QIKhg).
- **Backend**: services/langflow_file_service.py — формирование final_tweaks для chunk_size, chunk_overlap, separator; api/langflow_files.py, router — передача settings в задачу.
- **OpenSearch**: каждый чанк — один документ в индексе (utils/opensearch_queries.py, config/settings.py INDEX_BODY, utils/embeddings.py create_dynamic_index_body).

## 5. Связанные компоненты

Langflow flow (SplitText, OpenSearch component), LangflowFileService, embedding_fields, OpenSearch index mapping.

---

## Ключевые понятия

Chunking, chunk_size, chunk_overlap, separator, node, SplitText.

## Основные сущности

Chunk, node (document in index), text field, SplitText component.

## Связанные компоненты

Langflow ingestion flow, LangflowFileService, OpenSearch, embedding_fields.
