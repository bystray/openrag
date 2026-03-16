# Сервис извлечения структурированных данных из логистических заявок (пайплайн документы → LLM → logistics_requests_structured).

import json
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from opensearchpy import AsyncOpenSearch
from openai import AsyncOpenAI

from config.settings import get_index_name, get_openrag_config
from services.logistics_requests_service import LOGISTICS_REQUESTS_INDEX
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Ключевые фразы для отбора кандидатов на логистическую заявку (хотя бы одна в тексте)
LOGISTICS_KEYWORDS = [
    "заявка на перевозку",
    "заявка",
    "маршрут",
    "место загрузки",
    "место разгрузки",
    "стоимость",
    "без НДС",
    "с НДС",
    "температурный режим",
]

# Ожидаемые поля результата extraction (для валидации и записи)
EXTRACTION_FIELDS = [
    "is_logistics_request",
    "request_number",
    "request_date",
    "route_from",
    "route_to",
    "loading_address",
    "unloading_address",
    "customer",
    "carrier",
    "cargo",
    "weight_kg",
    "temperature",
    "vehicle",
    "driver_name",
    "driver_phone",
    "price_without_vat",
    "price_with_vat",
    "vat_included",
    "vat_rate",
    "payment_terms",
]


def build_logistics_extraction_prompt(
    document_id: str, original_filename: str, document_text: str
) -> str:
    """
    Собирает промпт для LLM: извлечь структурированные поля из текста логистической заявки.
    Явные правила по НДС, дате, весу и температуре зашиты в инструкцию.
    """
    return f"""Ты — экстрактор структурированных данных. Задача: по тексту документа определить, является ли он логистической заявкой на перевозку, и извлечь поля в строго заданном JSON.

Идентификатор документа: {document_id}
Имя файла: {original_filename}

Правила извлечения:
- НДС: если в документе указано "без НДС" — vat_included = false, price_without_vat = указанная цена, price_with_vat = null. Если "с НДС" — vat_included = true, price_with_vat = цена, price_without_vat = null. vat_rate оставляй null, если явно не указан.
- Дата: нормализуй в формат YYYY-MM-DD, если возможно.
- Вес: всегда в килограммах. Если в документе "10 тонн" — weight_kg = 10000.
- Температура: нормализуй к строке вида "-18" или "от +2 до +6" по смыслу.
- Текст может содержать OCR-ошибки, повторы и обрывки — извлекай по смыслу, пустые поля — пустая строка или null для чисел.

Ответ — только один валидный JSON без markdown и пояснений, с полями:
is_logistics_request (boolean),
request_number, request_date, route_from, route_to, loading_address, unloading_address,
customer, carrier, cargo, weight_kg (number или null), temperature, vehicle, driver_name, driver_phone,
price_without_vat (number или null), price_with_vat (number или null), vat_included (boolean или null), vat_rate (number или null), payment_terms.

Текст документа:
---
{document_text[:120000]}
---
Ответ (только JSON):"""


def build_document_text(texts: List[str]) -> str:
    """
    Сборка полного текста документа из списка текстов чанков:
    удаление полных дублей, пустых строк, склейка через \\n\\n.
    """
    seen: set[str] = set()
    parts: List[str] = []
    for t in texts:
        s = (t or "").strip()
        if not s or s in seen:
            continue
        seen.add(s)
        parts.append(s)
    return "\n\n".join(parts)


def _normalize_date(value: Any) -> Optional[str]:
    """Пытается привести дату к YYYY-MM-DD."""
    if value is None or value == "":
        return None
    s = str(value).strip()
    if not s:
        return None
    # Уже YYYY-MM-DD
    if re.match(r"^\d{4}-\d{2}-\d{2}$", s):
        return s
    # DD.MM.YYYY или DD/MM/YYYY
    m = re.search(r"(\d{1,2})[./](\d{1,2})[./](\d{4})", s)
    if m:
        d, mon, y = m.group(1), m.group(2), m.group(3)
        return f"{y}-{mon.zfill(2)}-{d.zfill(2)}"
    m = re.search(r"(\d{4})[./-](\d{1,2})[./-](\d{1,2})", s)
    if m:
        y, mon, d = m.group(1), m.group(2), m.group(3)
        return f"{y}-{mon.zfill(2)}-{d.zfill(2)}"
    return s


def _normalize_weight_kg(value: Any) -> Optional[float]:
    """Приведение веса к килограммам (тонны → *1000)."""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip().lower().replace(",", ".")
    m = re.search(r"([\d.]+)\s*(т|тонн|тонны|t)", s)
    if m:
        return float(m.group(1)) * 1000.0
    m = re.search(r"([\d.]+)\s*(кг|kg)", s)
    if m:
        return float(m.group(1))
    try:
        return float(re.sub(r"[^\d.]", "", s) or 0) or None
    except ValueError:
        return None


def _ensure_extraction_shape(data: Dict[str, Any]) -> Dict[str, Any]:
    """Приводит ответ LLM к единой форме полей и нормализует дату/вес."""
    out: Dict[str, Any] = {}
    for key in EXTRACTION_FIELDS:
        out[key] = data.get(key)
    if out.get("request_date") is not None:
        out["request_date"] = _normalize_date(out["request_date"]) or out["request_date"]
    if out.get("weight_kg") is not None:
        out["weight_kg"] = _normalize_weight_kg(out["weight_kg"]) or out["weight_kg"]
    return out


def validate_extraction_result(data: Dict[str, Any]) -> Tuple[bool, Optional[str]]:
    """
    Валидация результата extraction перед записью в индекс.
    Возвращает (ok, error_message).
    """
    if not isinstance(data.get("is_logistics_request"), bool):
        return False, "is_logistics_request должен быть boolean"
    if data.get("is_logistics_request") is not True:
        return True, None  # не заявка — сохраняем как есть
    # Для заявки проверяем минимум: маршрут/адреса, заказчик/перевозчик, цена или вес
    has_route = bool(
        (data.get("route_from") or "").strip()
        or (data.get("route_to") or "").strip()
        or (data.get("loading_address") or "").strip()
        or (data.get("unloading_address") or "").strip()
    )
    has_party = bool(
        (data.get("customer") or "").strip() or (data.get("carrier") or "").strip()
    )
    has_price_or_weight = (
        data.get("price_without_vat") is not None
        or data.get("price_with_vat") is not None
        or data.get("weight_kg") is not None
    )
    if not (has_route or has_party or has_price_or_weight):
        return False, "для заявки нужны хотя бы маршрут/адреса, заказчик/перевозчик или цена/вес"
    return True, None


class LogisticsExtractionService:
    """
    Пайплайн: документы из индекса documents → отбор кандидатов → сборка текста →
    LLM extraction (напрямую или через Langflow flow) → валидация → запись в logistics_requests_structured.
    """

    def __init__(
        self,
        opensearch: AsyncOpenSearch,
        llm_client: Optional[AsyncOpenAI] = None,
        langflow_file_service: Optional[Any] = None,
        logistics_flow_id: Optional[str] = None,
    ):
        self.opensearch = opensearch
        self._llm_client = llm_client
        self._langflow_file_service = langflow_file_service
        self._logistics_flow_id = logistics_flow_id
        self._documents_index = get_index_name()
        self._logistics_index = LOGISTICS_REQUESTS_INDEX

    def _get_llm_client(self) -> AsyncOpenAI:
        if self._llm_client is not None:
            return self._llm_client
        from config.settings import clients
        return clients.patched_async_client

    async def get_candidate_filenames(
        self,
        limit: Optional[int] = None,
        only_filename: Optional[str] = None,
    ) -> List[str]:
        """
        Возвращает список уникальных filename — кандидатов на логистические заявки.
        Фильтр: mimetype = application/pdf, в тексте хотя бы одна из ключевых фраз.
        """
        if only_filename:
            # Проверяем, что файл есть и pdf
            body = {
                "query": {
                    "bool": {
                        "filter": [
                            {"term": {"filename": only_filename}},
                            {"term": {"mimetype": "application/pdf"}},
                        ]
                    }
                },
                "size": 0,
                "aggs": {"names": {"terms": {"field": "filename", "size": 1}}},
            }
        else:
            should_clauses = [
                {"match_phrase": {"text": kw}} for kw in LOGISTICS_KEYWORDS
            ]
            body = {
                "query": {
                    "bool": {
                        "filter": [{"term": {"mimetype": "application/pdf"}}],
                        "must": [{"bool": {"should": should_clauses, "minimum_should_match": 1}}],
                    }
                },
                "size": 0,
                "aggs": {
                    "unique_filenames": {
                        "terms": {"field": "filename", "size": 10000}
                    }
                },
            }
        try:
            resp = await self.opensearch.search(
                index=self._documents_index,
                body=body,
                ignore_unavailable=True,
            )
        except Exception as e:
            logger.error("Ошибка поиска кандидатов", error=str(e))
            return []
        buckets = (
            resp.get("aggregations") or {}
        ).get("unique_filenames", {}).get("buckets", []) or (
            resp.get("aggregations") or {}
        ).get("names", {}).get("buckets", [])
        filenames = [b["key"] for b in buckets]
        if limit is not None and limit > 0:
            filenames = filenames[:limit]
        return filenames

    async def load_chunk_texts_by_filename(self, filename: str) -> List[str]:
        """Загружает все поля text из индекса documents для данного filename."""
        from utils.opensearch_queries import build_filename_query
        body = {
            "query": build_filename_query(filename),
            "size": 10000,
            "_source": ["text"],
        }
        try:
            resp = await self.opensearch.search(
                index=self._documents_index,
                body=body,
                ignore_unavailable=True,
            )
        except Exception as e:
            logger.warning("Ошибка загрузки чанков", filename=filename, error=str(e))
            return []
        hits = resp.get("hits", {}).get("hits", [])
        return [h.get("_source", {}).get("text") or "" for h in hits]

    async def already_processed(self, document_id: str) -> bool:
        """Проверяет, есть ли уже запись в logistics_requests_structured с данным document_id."""
        body = {
            "query": {"term": {"document_id": document_id}},
            "size": 1,
        }
        try:
            resp = await self.opensearch.search(
                index=self._logistics_index,
                body=body,
                ignore_unavailable=True,
            )
        except Exception as e:
            logger.warning("Ошибка проверки idempotency", document_id=document_id, error=str(e))
            return False
        total = resp.get("hits", {}).get("total", 0)
        if isinstance(total, dict):
            total = total.get("value", 0)
        return total > 0

    async def call_llm_extraction(
        self,
        document_id: str,
        original_filename: str,
        document_text: str,
        llm_model: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        """
        Вызов LLM для извлечения JSON. При наличии LANGFLOW_LOGISTICS_EXTRACT_FLOW_ID
        использует Langflow flow, иначе — chat.completions.
        """
        if not document_text.strip():
            logger.warning("Пустой document_text", document_id=document_id)
            return None
        if self._langflow_file_service and self._logistics_flow_id:
            extraction = await self._langflow_file_service.run_logistics_extraction_flow(
                document_id=document_id,
                filename=original_filename,
                document_text=document_text,
            )
            if extraction is not None:
                return _ensure_extraction_shape(extraction)
            return None
        prompt = build_logistics_extraction_prompt(
            document_id, original_filename, document_text
        )
        model = llm_model or get_openrag_config().agent.llm_model or "gpt-4o-mini"
        client = self._get_llm_client()
        try:
            kwargs: Dict[str, Any] = {
                "model": model,
                "messages": [
                    {"role": "user", "content": prompt},
                ],
                "max_tokens": 4096,
                "temperature": 0.1,
            }
            # Ответ в виде JSON (OpenAI и совместимые API поддерживают response_format)
            kwargs["response_format"] = {"type": "json_object"}
            resp = await client.chat.completions.create(**kwargs)
            content = (
                (resp.choices or [{}])[0].message.content
                if resp.choices
                else None
            )
            if not content or not content.strip():
                logger.warning("Пустой ответ LLM", document_id=document_id)
                return None
            # Убрать обёртку markdown если есть
            raw = content.strip()
            if raw.startswith("```"):
                raw = re.sub(r"^```\w*\n?", "", raw)
                raw = re.sub(r"\n?```\s*$", "", raw)
            data = json.loads(raw)
            if not isinstance(data, dict):
                logger.warning("Ответ LLM не объект", document_id=document_id)
                return None
            return _ensure_extraction_shape(data)
        except json.JSONDecodeError as e:
            logger.warning(
                "Не удалось распарсить JSON ответа LLM",
                document_id=document_id,
                error=str(e),
            )
            return None
        except Exception as e:
            logger.error(
                "Ошибка вызова LLM",
                document_id=document_id,
                error=str(e),
            )
            return None

    def build_doc_for_index(
        self,
        document_id: str,
        original_filename: str,
        extraction: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Формирует документ для записи в logistics_requests_structured с processed_at."""
        doc = {
            "document_id": document_id,
            "original_filename": original_filename,
            "processed_at": datetime.now(tz=timezone.utc).isoformat(),
        }
        for key in EXTRACTION_FIELDS:
            doc[key] = extraction.get(key)
        return doc

    async def save_to_index(
        self,
        doc: Dict[str, Any],
        dry_run: bool = False,
    ) -> bool:
        """Индексирует документ в logistics_requests_structured. При dry_run не пишет."""
        if dry_run:
            logger.info("dry-run: запись в индекс пропущена", document_id=doc.get("document_id"))
            return True
        try:
            # Используем document_id как id документа в индексе для идемпотентности перезаписи
            doc_id = doc.get("document_id") or ""
            await self.opensearch.index(
                index=self._logistics_index,
                id=doc_id,
                body=doc,
                refresh=True,
            )
            return True
        except Exception as e:
            logger.error(
                "Ошибка записи в индекс",
                document_id=doc.get("document_id"),
                error=str(e),
            )
            return False

    async def process_one(
        self,
        filename: str,
        force: bool = False,
        dry_run: bool = False,
        llm_model: Optional[str] = None,
    ) -> str:
        """
        Обрабатывает один документ по filename.
        Возвращает: "success" | "skipped" | "failed".
        """
        document_id = filename
        original_filename = filename

        if not force:
            if await self.already_processed(document_id):
                logger.info(
                    "Документ уже обработан, пропуск (idempotency)",
                    filename=filename,
                    document_id=document_id,
                )
                return "skipped"

        texts = await self.load_chunk_texts_by_filename(filename)
        document_text = build_document_text(texts)
        logger.info(
            "Собран текст документа",
            filename=filename,
            assembled_length=len(document_text),
            chunks_count=len(texts),
        )

        extraction = await self.call_llm_extraction(
            document_id, original_filename, document_text, llm_model=llm_model
        )
        if extraction is None:
            return "failed"

        ok, err = validate_extraction_result(extraction)
        if not ok:
            logger.warning("Валидация не пройдена", filename=filename, reason=err)
            return "failed"

        doc = self.build_doc_for_index(document_id, original_filename, extraction)
        saved = await self.save_to_index(doc, dry_run=dry_run)
        return "success" if saved else "failed"
