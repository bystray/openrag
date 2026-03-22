# Langflow и локальный репозиторий OpenRAG (dev sync)

Цель: предсказуемо связывать JSON flow в git, контейнер Langflow, переменные `.env` и поведение backend (поиск Knowledge, ingest, chat).

## Цепочка: host → контейнер → загрузка

| Шаг | Значение |
|-----|----------|
| Переменная | `OPENRAG_FLOWS_PATH` (в `.env`; по умолчанию в compose: `./flows` от каталога compose) |
| Монтирование | `${OPENRAG_FLOWS_PATH:-./flows}` → `/app/flows` в сервисе `langflow` |
| Загрузка | `LANGFLOW_LOAD_FLOWS_PATH=/app/flows` — при старте Langflow подхватывает `*.json` из этой папки |

Если `OPENRAG_FLOWS_PATH` указывает вне клона (например `~/.openrag/flows`), UI будет отражать **файлы из этой папки**, а не из `flows/` репозитория. Для dev рекомендуется явно задать:

```bash
OPENRAG_FLOWS_PATH=./flows
```

(путь относительно каталога, где лежит `docker-compose.yml`).

## Критичные переменные окружения

| Переменная | Назначение |
|------------|------------|
| `OPENRAG_FLOWS_PATH` | Откуда на хосте брать JSON для `/app/flows` |
| `LANGFLOW_CHAT_FLOW_ID` | UUID chat/RAG flow (`flows/openrag_agent.json`) |
| `LANGFLOW_INGEST_FLOW_ID` | UUID ingest (`flows/ingestion_flow.json`) |
| `LANGFLOW_URL_INGEST_FLOW_ID` | URL ingest (`flows/openrag_url_mcp.json`) |
| `NUDGES_FLOW_ID` | Nudges (`flows/openrag_nudges.json`) |
| `OPENSEARCH_INDEX_NAME` | Базовое имя алиаса (обычно `documents`); не путать с индексом `documents_*` под модель |
| `SELECTED_EMBEDDING_MODEL` | Модель эмбеддинга; вместе с конфигом задаёт, куда пишет ingest |

Backend читает flow по **ID из `.env`**, а не по имени файла. Имя файла в UI не отображается; в списке видно **name** из JSON и UUID в URL `/flow/<uuid>`.

## Индексы: Knowledge search vs chat vs ingest

- **Поиск Knowledge** (`SearchService`, alias): `get_index_name()` → обычно алиас **`documents`** (покрывает все `documents_*` с нужными маппингами).
- **Ingest через Langflow**: в заголовках передаётся **модельный** индекс `get_index_name_for_model(embedding_model)` — в него пишутся чанки для выбранной модели.
- **Chat / nudges** (после выравнивания): в запрос к Langflow передаётся **`X-LANGFLOW-GLOBAL-VAR-OPENSEARCH_INDEX_NAME`** = алиас `documents`, чтобы retrieval совпадал с поиском в Knowledge по охвату индексов.

Глобальные переменные Langflow, которые выставляет backend при старте (`OPENSEARCH_INDEX_NAME` в сторону модельного индекса), отражают удобный default для **ручного** запуска flow в UI; **API чата** переопределяет индекс заголовком на алиас.

## Фильтры (filename / mimetype / owner / connector_type)

Один источник правды: `src/utils/openrag_query_filters.py` — имена полей как в маппинге индекса (`filename`, `mimetype`, … как **keyword**, без подполя `.keyword`, иначе на стандартном индексе OpenRAG будет ошибка «field not found»).

## Проверка синхронизации (без Docker)

```bash
make langflow-sync-check
# или
uv run python scripts/langflow_dev_sync_check.py
```

Скрипт сравнивает UUID в `flows/*.json` с `LANGFLOW_*_FLOW_ID` в `.env` и предупреждает, если `OPENRAG_FLOWS_PATH` не указывает на каталог репозитория.

## Мягкая пересборка Langflow (данные OpenSearch не трогаем)

```bash
make langflow-soft-rebuild
```

Пересобирает образ, пересоздаёт контейнер `langflow`, заново читает JSON из смонтированного каталога. Индексы и документы в OpenSearch не удаляются.

Алиас `documents` обновляется при старте backend; после смены конфигов имеет смысл:

```bash
docker compose restart openrag-backend
```

## Переимпорт flow из репозитория

То же, что «мягкая пересборка» — контейнер без отдельного volume БД Langflow в compose перезагружается и снова импортирует файлы из `OPENRAG_FLOWS_PATH`:

```bash
make langflow-reimport-flows
```

Если API `make flow-upload` создал flow с **новым** UUID, обновите соответствующий `LANGFLOW_*_FLOW_ID` в `.env`.

## Как понять, что открыт «не тот» flow

- URL не совпадает с `LANGFLOW_CHAT_FLOW_ID` / `LANGFLOW_INGEST_FLOW_ID` из `.env`.
- В проекте несколько копий с одинаковым именем (Starter Project) — оставьте flow с UUID из репо или удалите дубликат в UI.

## Типовые симптомы рассинхрона

| Симптом | Возможная причина |
|---------|-------------------|
| Правки в `flows/*.json` не видны в UI | Другой `OPENRAG_FLOWS_PATH` или не перезапущен контейнер |
| README/ноды не как в git | Смотрите не тот UUID или старую копию в UI |
| Chat не находит то, что видно в Knowledge | Раньше: индекс в chat не алиас; проверьте версию backend с заголовком `OPENSEARCH_INDEX_NAME` для chat |
| Ingest пишет не туда | `SELECTED_EMBEDDING_MODEL`, заголовки ingest, `ensure_documents_alias` в логах backend |

## Полное сброс состояния только Langflow (осторожно)

По умолчанию в `docker-compose` у `langflow` нет именованного volume под БД; пересоздание контейнера сбрасывает локальное состояние Langflow. **Не** выполняйте `make db-reset` / удаление индексов, если нужно сохранить знания — см. разделы выше.

## Чеклист после изменений в `flows/` или `.env`

1. `OPENRAG_FLOWS_PATH` → каталог `flows` репозитория (или скопируйте JSON в используемый каталог).
2. `make langflow-sync-check` — UUID совпадают с `.env`.
3. `make langflow-soft-rebuild` при необходимости.
4. `docker compose restart openrag-backend` — алиас и глобальные переменные Langflow.
5. Проверка: `GET _alias/documents` в OpenSearch; чат и Knowledge на одном наборе индексов под алиасом.
