# API OpenRAG

## 1. Что это

REST API Backend (FastAPI), через который Frontend и внешние клиенты выполняют загрузку, поиск, чат, управление задачами, настройками и коннекторами. Все маршруты регистрируются в main.py (create_app).

## 2. Зачем используется

Единая точка входа для всех операций с базой знаний, чатом, задачами и конфигурацией; возможность интеграции с другими системами и автоматизации.

## 3. Как работает

### /search

- POST /search. Тело: query (str), filters (dict), limit (int), scoreThreshold (float). Зависимости: get_search_service, get_session_manager, get_current_user. Вызов search_service.search(...); ответ — JSON с результатами поиска (чанки, скоры). Коды: 200 OK, 403 при ошибках аутентификации, 500 при прочих ошибках.

### /knowledge-filter, /knowledge-filter/search

- POST /knowledge-filter — создание фильтра знаний. POST /knowledge-filter/search — поиск фильтров. GET/PUT/DELETE /knowledge-filter/{filter_id} — получение, обновление, удаление. Подписки и webhook: POST .../subscribe, GET .../subscriptions, DELETE .../subscribe/{subscription_id}, POST .../webhook/{subscription_id}.

### /tasks

- GET /tasks — список задач пользователя. GET /tasks/{task_id} — статус задачи (task_status). POST /tasks/{task_id}/cancel — отмена задачи.

### /settings

- GET /settings — получение настроек (get_settings). POST /settings — обновление (update_settings). POST /onboarding/state — состояние онбординга. POST /openrag-docs/refresh — обновление документации OpenRAG.

### /provider/health

- Эндпоинт проверки здоровья провайдера (OpenAI, Ollama, Watsonx, Anthropic). Параметры: provider (опционально), test_completion. Зависимости: get_current_user. Используется api/provider_health.check_provider_health.

### /docling/health

- Проверка доступности Docling Serve (api/docling). Определение хоста (контейнер/хост), запрос к Docling, возврат статуса.

### /logistics-requests

- **POST /logistics-requests** — список логистических заявок с фильтрами, пагинацией и сортировкой. Тело: searchQuery, routeFrom, routeTo, customer, carrier, temperature, vatIncluded, dateFrom, dateTo, priceFrom, priceTo, weightFrom, weightTo, page, size, sortField, sortOrder, includeAggregations. Ответ: items, total, page, size, опционально aggregations (total, avg_price, avg_weight_kg, unique_carriers, unique_routes).
- **GET /logistics-requests/aggregations** — агрегации по заявкам с опциональными query-параметрами фильтров (для блока аналитики).
- **GET /logistics-requests/{document_id}** — одна заявка по document_id.
- **POST /logistics-requests/extract** — запуск пайплайна извлечения заявок из базы знаний. Тело: limit (int | null), force (bool), dry_run (bool), filename (str | null). Логика: поиск кандидатов в индексе documents (PDF + ключевые слова), сборка текста по filename, вызов LLM, запись в logistics_requests_structured (если не dry_run). Ответ: status, started, mode (single | batch), limit, force, dry_run, filename, summary (found_candidates, processed, success, skipped, failed), items (массив { filename, status }). Требует аутентификации.

### Прочие группы

- **Upload**: /upload_context, /upload_path, /upload_options, /upload_bucket; роут загрузки с инжестом — через router (upload_ingest_router) на путь, заданный в main (например /upload_ingest или аналог).
- **Langflow**: /langflow/files/upload, /langflow/ingest, /langflow/files (DELETE), /langflow/upload_ingest; /chat, /langflow (chat); /chat/history, /langflow/history; /sessions/{session_id} (DELETE).
- **Documents**: GET /documents/check-filename, POST /documents/delete-by-filename.
- **Connectors**: GET /connectors, POST /connectors/{connector_type}/sync, POST /connectors/sync-all, GET /connectors/{connector_type}/status, GET .../token, DELETE .../disconnect, POST|GET .../webhook.
- **Auth**: /auth/init, /auth/callback, /auth/me, /auth/logout; OIDC: /.well-known/openid-configuration, /auth/jwks, /auth/introspect.

## 4. Где используется в системе

- main.py — app.add_api_route для всех перечисленных групп. Роутер загрузки подключается к приложению и маршрутизирует на Langflow task-based или традиционный upload.
- Frontend вызывает эти эндпоинты для экранов Knowledge, Chat, Settings, Connectors, Tasks.

## 5. Связанные компоненты

search (api/search), knowledge_filter, tasks (api/tasks), settings (api/settings), provider_health, docling, router, chat, connectors, documents, logistics_requests (api/logistics_requests), auth, oidc.

---

## Ключевые понятия

REST API, FastAPI, search, tasks, settings, provider health, knowledge filter.

## Основные сущности

/search, /tasks, /settings, /knowledge-filter, /logistics-requests, /logistics-requests/extract, /provider/health, /docling/health.

## Связанные компоненты

main.py, api/search, api/tasks, api/settings, api/provider_health, api/docling, api/knowledge_filter, api/logistics_requests, router, dependencies.
