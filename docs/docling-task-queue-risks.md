# Как формируются задачи Docling и где риски перегрузки

Этот документ описывает текущий pipeline ingestion (без Langflow) и риски, которые могут привести к переполнению/перегрузке Docling.

## 1) Как формируются задачи на обработку документов

### Точка входа
- Folder upload идет через `POST /upload_path` в `src/api/upload.py`.
- Backend проходит по папке рекурсивно (`os.walk`), формирует:
  - `file_paths` (абсолютные пути),
  - `relative_paths` (путь с корневой папкой, например `docs/finance/a.pdf`).
- Затем создается bulk-задача через `TaskService.create_upload_task(...)`.

### Создание task в памяти
- В `src/services/task_service.py`:
  - `create_upload_task(...)` создает `DocumentFileProcessor`.
  - `create_custom_task(...)` создает `UploadTask` + `FileTask` для каждого файла.
  - `FileTask` хранит `file_path`, `filename`, `relative_path` и статусы.
- После создания запускается background корутина `background_custom_processor(...)`.

### Параллелизм и ограничение нагрузки
- В `TaskService` используется глобальный семафор:
  - `self._processing_semaphore = asyncio.Semaphore(self._worker_count)`.
- `_worker_count` берется из `utils.gpu_detection.get_worker_count()`:
  - по умолчанию `max(1, min(4, cpu_count // 2))`,
  - можно переопределить через `MAX_WORKERS`.
- Это ограничивает одновременную обработку файлов во всех задачах (системно, а не только внутри одной задачи).

### Обработка одного файла
- Для каждого файла вызывается `processor.process_item(...)` (`DocumentFileProcessor`).
- Далее идет `TaskProcessor.process_document_standard(...)`:
  - если `.txt`/`.md` -> bypass Docling (`process_text_file`);
  - иначе -> `utils.docling_client.convert_file(...)` (HTTP в docling-serve);
  - после этого chunking + embeddings + запись в OpenSearch.

### Таймауты
- На файл действует timeout через `TaskService._process_with_timeout(...)`.
- Значение берется из `INGESTION_TIMEOUT` (по умолчанию 3600 сек) в `src/config/settings.py`.

## 2) Где возникает риск переполнения/перегрузки Docling

## Основные риски
- Слишком высокий `MAX_WORKERS`:
  - backend начнет параллельно отправлять много документов в Docling,
  - Docling может начать отвечать медленно/ошибками по timeout.
- Большой batch folder upload:
  - один запрос может поставить в очередь сразу много тяжелых PDF.
- Много одновременных задач от разных пользователей:
  - даже с лимитом на worker, очередь может расти быстрее, чем Docling успевает обрабатывать.
- Длинные/тяжелые PDF:
  - один файл занимает worker надолго, очередь блокируется.
- Нестабильность Docling сервиса:
  - retry/повторные запуски задач создают дополнительную нагрузку на тот же узкий канал.

## Что уже защищает систему
- Глобальный семафор в `TaskService` ограничивает общий параллелизм.
- Пер-файловый timeout (`INGESTION_TIMEOUT`) не дает зависать бесконечно.
- Статусы задач позволяют видеть рост `pending/running/failed`.
- Для `.txt/.md` Docling не используется (снимает часть нагрузки).

## 3) Практические ограничения, чтобы не перегружать Docling

Рекомендуемые безопасные настройки:

- `MAX_WORKERS`:
  - стартовать с `2` (консервативно),
  - повышать до `3-4` только после наблюдения стабильной работы Docling.
- `UPLOAD_BATCH_SIZE`:
  - держать `10-25` для mixed-набора файлов,
  - при тяжелых PDF снижать до `5-10`.
- `INGESTION_TIMEOUT`:
  - не ставить слишком маленьким (чтобы не делать ложные таймауты),
  - ориентир: `>=` реального p95 времени на тяжелый документ.

Операционный контроль:
- Мониторить endpoints:
  - `/docling/health`,
  - `/docling/service/status`,
  - `/docling/service/logs`.
- Смотреть динамику задач:
  - рост `pending` при стабильном `running` = Docling узкое место,
  - всплеск `failed` с timeout = перегрузка или деградация Docling.

## 4) Риски в текущей модели очереди (важно)

- Очередь задач в памяти процесса:
  - при рестарте backend незавершенные задачи теряются.
- Нет отдельного внешнего брокера:
  - backpressure реализован только семафором приложения.
- Нагрузка от нескольких источников суммируется в один pool:
  - folder upload, S3 и другие ingestion пути конкурируют за один и тот же лимит worker-ов.

## 5) Минимальный anti-overflow чеклист перед production

- Установить `MAX_WORKERS=2` на старте.
- Ограничить `UPLOAD_BATCH_SIZE` под типичный размер документов.
- Проверить, что `INGESTION_TIMEOUT` покрывает реальные долгие документы.
- Нагрузочно прогнать сценарий "несколько folder upload одновременно".
- Зафиксировать пороги алертов:
  - много `pending` дольше N минут,
  - резкий рост `failed` по timeout,
  - деградация `/docling/health`.

