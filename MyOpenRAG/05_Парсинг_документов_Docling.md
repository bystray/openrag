# Парсинг документов (Docling)

## 1. Что это

Docling — сервис конвертации документов (PDF, Office, HTML и др.) в структурированный формат. В OpenRAG используется **Docling Serve** (HTTP API). Парсинг вызывается из Langflow flow через компонент DoclingRemote; при альтернативном пайплайне — через utils/docling_client.

## 2. Зачем используется

Преобразование «сырых» файлов в единый структурированный вид (блоки, текст, разметка), пригодный для разбиения на чанки и индексации. Поддерживаются сложные PDF (таблицы, OCR при необходимости).

## 3. Как работает

### Docling

- Отдельный сервис (контейнер или процесс). Endpoint задаётся через DOCLING_SERVE_URL (например http://host.docker.internal:5001 или внутренний адрес в Docker). Переменная передаётся в Langflow как глобальная (LANGFLOW_VARIABLES_TO_GET_FROM_ENVIRONMENT).

### DoclingDocument

- Результат конвертации — JSON. В ответе API поле `document.json_content` содержит структурированное представление документа (узлы/блоки, текст, метаданные страниц). Точная схема зависит от версии Docling; в коде Backend используется только факт наличия `document.json_content` (utils/docling_client.py).

### parsed_blocks

- Внутри Langflow flow компонент DoclingRemote возвращает путь к файлу или структуру блоков, которая передаётся в следующий компонент (например извлечение текста или разбиение). Блоки соответствуют логическим частям документа (параграфы, заголовки, таблицы и т.д.).

### Markdown extraction

- При необходимости flow может извлекать markdown или плоский текст из блоков для последующего SplitText. В OpenRAG основной сценарий — передача пути файла в DoclingRemote; формат выхода задаётся в flow (to_formats и т.п.). В docling_client при вызове из Backend используется to_formats: "json".

### Вызов из Backend (docling_client)

- `convert_file(file_path, httpx_client)` — читает файл с диска, отправляет POST на `{DOCLING_SERVICE_URL}/v1/convert/file`, data: do_ocr, ocr_engine (из DOCLING_OCR_ENGINE), files: (filename, file_bytes). Ответ: document.json_content. Исключения: DoclingServeError при ошибке соединения, таймаута или HTTP/ошибках в ответе.

## 4. Где используется в системе

- **Langflow ingestion flow**: компонент DoclingRemote получает path (список путей из tweaks DoclingRemote-Dp3PX), вызывает Docling и отдаёт результат следующим узлам.
- **Backend**: utils/docling_client.py — convert_file, convert_bytes; api/docling.py — определение хоста для health check и прокси к Docling.
- **Конфигурация**: DOCLING_SERVE_URL, DOCLING_OCR_ENGINE; в docker-compose передаётся DOCLING_SERVE_URL в Langflow.

## 5. Связанные компоненты

Langflow (DoclingRemote), LangflowFileService (передаёт пути в flow), OpenSearch (результат парсинга после чанкинга и эмбеддингов попадает в индекс), utils/docling_client, api/docling.

---

## Ключевые понятия

Docling, Docling Serve, parsed blocks, json_content, OCR, DoclingRemote.

## Основные сущности

DoclingDocument, document.json_content, DoclingServeError, convert_file, convert_bytes.

## Связанные компоненты

Langflow ingestion flow, docling_client, api/docling, LangflowFileService.
