# Анализ повреждения индекса documents (merge/commit failed)

## Симптомы

- Ошибка: `TransportError(503, 'search_phase_execution_exception')`
- В логах OpenSearch: `merge failed` или `lucene commit failed`
- Исключение: `ArrayIndexOutOfBoundsException: Index N out of bounds for length M`
- Индекс переходит в состояние **red**, шарды UNASSIGNED

## Корневая причина

**Известный баг в opensearch-jvector** ([#287](https://github.com/opensearch-project/opensearch-jvector/issues/287)):

> Failures (both search and merge paths) when index contains **at least one document without vector fields being populated**.

При слиянии сегментов Lucene кодек JVector не обрабатывает документы с `null` в KNN-полях. Это приводит к `ArrayIndexOutOfBoundsException` при merge/commit.

## Когда возникает

1. **Мультимодельный индекс**: документы с `embedding_model=A` имеют вектор только в `chunk_embedding_A`, в `chunk_embedding_B` — null. При merge сегментов кодек падает.

2. **Документы без эмбеддингов**: если при индексации в поле вектора попал `null` (ошибка эмбеддинга, race condition).

3. **Разные источники индексации**: backend (TaskProcessor) и Langflow (OpenSearchMultimodal) пишут в один индекс; могут использоваться разные модели → смешанное состояние.

## Меры предотвращения

### 1. Валидация перед индексацией (реализовано)

- **Langflow** (`opensearch_multimodal.py`): пропуск документов с `None` или пустым вектором.
- **Backend** (`processors.py`): `zip(chunks, embeddings)` гарантирует, что индексируются только чанки с векторами.

### 2. Один embedding model на индекс (рекомендуется)

- Не смешивать модели в одном индексе.
- При смене модели — пересоздать индекс и переиндексировать.

### 3. number_of_replicas: 0 для single-node

- В `embeddings.py` и `opensearch_multimodal.py` задано `number_of_replicas: 0`.
- Иначе реплики не назначаются → индекс red.

### 4. Альтернатива: engine lucene

- JVector (engine: jvector) подвержен багу.
- Lucene (engine: lucene, method: hnsw) может не иметь этой проблемы.
- Переход требует пересоздания индекса с новым mapping.

## Стоимость ошибки

- Потеря всех документов в индексе.
- Повторная загрузка и индексация → расход токенов на эмбеддинги (OpenAI и др.).

## Ссылки

- [opensearch-jvector #287](https://github.com/opensearch-project/opensearch-jvector/issues/287) — документы без векторов
- [OpenSearch "all shards failed"](https://opensearch.org/blog/error-logs/error-log-all-shards-failed-the-misleading-error/) — root_cause в JSON-ответе
