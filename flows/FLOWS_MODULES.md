# Модули Langflow-потоков OpenRAG

Файлы `ingestion_flow.json`, `openrag_agent.json`, `openrag_nudges.json`, `openrag_url_mcp.json` — экспорты графов [Langflow](https://docs.langflow.org): узлы (`nodes`) — компоненты, рёбра (`edges`) — передача данных между выходами и входами. Ниже — назначение каждого потока и роль основных модулей.

---

## `ingestion_flow.json` — OpenSearch Ingestion Flow

**Назначение:** загрузка «сырых» документов в векторный индекс OpenSearch для RAG.

| Модуль | Роль |
|--------|------|
| **DoclingRemote** | Принимает входные документы и отдаёт таблицу (`DataFrame`) через удалённый Docling Serve. |
| **ExportDoclingDocument** | Преобразует выход Docling в единый `DataFrame` для дальнейшей обработки. |
| **DataFrameOperations** (цепочка из трёх узлов) | Построчная обработка таблицы: добавление служебных колонок (в т.ч. `filename`, `file_size`, `mimetype` согласно встроенному README узла). |
| **SplitText** | Разбиение текста на чанки для индексации. |
| **EmbeddingModel** (×3) | Три модели эмбеддингов; все подключены к одному векторному стору — мультимодельная/мультиэмбеддинговая схема. |
| **OpenSearchVectorStoreComponentMultimodalMultiEmbedding** | Запись чанков в OpenSearch: вход `ingest_data` от **SplitText**, вход `embedding` от моделей эмбеддингов. |
| **AdvancedDynamicFormBuilder** | Сбор метаданных документа для индекса; выход `form_data` → `docs_metadata` у OpenSearch. |
| **TextInput** (несколько) | Статические/глобальные поля метаданных: подключаются к динамическим полям формы (`dynamic_*`: группы, пользователи, тип коннектора, id документа, владелец, email, URL источника, имя и т.д.). |

**Поток данных:** Docling → Export → цепочка DataFrame → SplitText → ингест в OpenSearch; параллельно форма метаданных и три эмбеддинга питают тот же компонент OpenSearch.

---

## `openrag_agent.json` — OpenRAG OpenSearch Chat Agent

**Назначение:** основной чат-агент: ответы по базе знаний OpenSearch, калькулятор и MCP (в т.ч. ингест URL).

| Модуль | Роль |
|--------|------|
| **ChatInput** | Сообщение пользователя. |
| **Prompt Template** | Шаблон промпта; на вход `input` от чата; опционально **filter** от **TextInput** (доп. ограничение/контекст запроса). |
| **TextInput** | Текст для фильтра: ветвится в шаблон (`filter`) и в **OpenSearch** (`filter_expression`) — узкий поиск по метаданным/условиям. |
| **EmbeddingModel** (×3) | Эмбеддинги запроса под ту же мультимодельную схему, что и при ингесте. |
| **OpenSearchVectorStoreComponentMultimodalMultiEmbedding** | Семантический поиск по индексу; как инструмент агента: `component_as_tool` → **Agent.tools**. |
| **MCP** | Внешние MCP-инструменты (например веб/интеграции) — тоже в `Agent.tools`. |
| **CalculatorComponent** | Калькулятор как tool для агента. |
| **Agent** | Центральный агент Langflow: выбирает инструменты (OpenSearch / MCP / калькулятор), формирует ответ. |
| **ChatOutput** | Вывод итогового сообщения (`Agent.response`). |

**Поток данных:** пользователь → Prompt Template → Agent; параллельно эмбеддинги + фильтр → OpenSearch как tool; MCP и Calculator — дополнительные tools.

---

## `openrag_nudges.json` — OpenRAG OpenSearch Nudges

**Назначение:** генерация подсказок (nudges) по документам в OpenSearch и истории чата — без полноценного агента с tools, через одну языковую модель.

| Модуль | Роль |
|--------|------|
| **ChatInput** | Текущий запрос/контекст чата. |
| **Prompt Template** | Промпт подсказок; вход **`docs`** получает структурированные данные от парсера (релевантные документы/фрагменты). |
| **LanguageModelComponent** | Одна LLM: текст ответа → **ChatOutput**. |
| **EmbeddingModel** (×3) | Эмбеддинги для поиска в OpenSearch (как в других flow). |
| **OpenSearchVectorStoreComponentMultimodalMultiEmbedding** | Поиск; `search_results` → **ParserComponent**. |
| **TextInput** | `filter_expression` — фильтрация поиска в OpenSearch. |
| **ParserComponent** (×2) + **TypeConverterComponent** | Разбор результатов поиска (и при необходимости приведение типов): цепочка `search_results` → парсер → type converter → снова парсер, выход `parsed_text` уходит в промпт как **`docs`**. |

**Поток данных:** поиск в OpenSearch → парсинг/нормализация → подстановка в промпт → LLM → чат-вывод.

---

## `openrag_url_mcp.json` — OpenSearch URL Ingest

**Назначение:** ингест веб-страниц по URL в OpenSearch (обход ссылок, табличная обработка, чанки, эмбеддинги).

| Модуль | Роль |
|--------|------|
| **ChatInput** | Сообщение со списком/текстом URL → вход **`urls`** у **URLComponent**. |
| **URLComponent** | Загрузка страниц, результат в виде `page_results` (`DataFrame`). |
| **DataFrameOperations** (несколько) | Обработка таблицы по шагам; одна ветка ведёт в предпросмотр (**ChatOutput**), другая — в **SplitText** и далее в индекс. |
| **SplitText** | Чанкование текста для ингеста. |
| **EmbeddingModel** (×3) | Мультимодельные эмбеддинги для OpenSearch. |
| **OpenSearchVectorStoreComponentMultimodalMultiEmbedding** | Запись чанков (`ingest_data`) и метаданных (`docs_metadata`). |
| **AdvancedDynamicFormBuilder** | Метаданные документа; **TextInput** задают динамические поля владельца/коннектора. |
| **ParserComponent** | Разбор данных (например из промежуточного `DataFrame`); `parsed_text` может подмешиваться в колонку через **`new_column_value`** в **DataFrameOperations**. |

**Поток данных:** URL → URLComponent → цепочка DataFrame → SplitText → OpenSearch; отдельно форма метаданных и три эмбеддинга; опционально парсер для обогащения таблицы перед индексацией.

---

## Общие паттерны

- **OpenSearchVectorStoreComponentMultimodalMultiEmbedding** везде согласован с **тремя EmbeddingModel**: один векторный стор на несколько модальностей/моделей эмбеддингов.
- **AdvancedDynamicFormBuilder** + **TextInput** на `dynamic_*` — единый способ задавать метаданные индекса без хардкода в коде.
- Фильтрация поиска: **TextInput** → `filter_expression` у компонента OpenSearch (agent, nudges, URL-flow).
- Подробные пояснения в интерфейсе Langflow часто продублированы в узле **note** (README) внутри JSON экспорта.
