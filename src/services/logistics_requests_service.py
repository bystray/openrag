# Сервис для работы с индексом структурированных логистических заявок в OpenSearch.

from typing import Any, Dict, List, Optional

from utils.logging_config import get_logger

logger = get_logger(__name__)

# Имя индекса со структурированными заявками (отдельно от documents).
LOGISTICS_REQUESTS_INDEX = "logistics_requests_structured"


class LogisticsRequestsService:
    """Чтение и поиск по индексу logistics_requests_structured."""

    def __init__(self, session_manager=None):
        self.session_manager = session_manager

    def _build_list_query(
        self,
        search_query: Optional[str] = None,
        route_from: Optional[str] = None,
        route_to: Optional[str] = None,
        customer: Optional[str] = None,
        carrier: Optional[str] = None,
        temperature: Optional[str] = None,
        vat_included: Optional[bool] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        price_from: Optional[float] = None,
        price_to: Optional[float] = None,
        weight_from: Optional[float] = None,
        weight_to: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Собирает bool-запрос для фильтров и опционального полнотекстового поиска."""
        must: List[Dict[str, Any]] = []
        if search_query and search_query.strip():
            # Поиск по нескольким полям (multi_match или отдельные match)
            must.append({
                "multi_match": {
                    "query": search_query.strip(),
                    "fields": [
                        "request_number",
                        "customer",
                        "carrier",
                        "cargo",
                        "route_from",
                        "route_to",
                        "original_filename",
                    ],
                    "type": "best_fields",
                    "operator": "or",
                }
            })
        filter_clauses: List[Dict[str, Any]] = []
        if route_from:
            filter_clauses.append({"term": {"route_from": route_from}})
        if route_to:
            filter_clauses.append({"term": {"route_to": route_to}})
        if customer:
            filter_clauses.append({"term": {"customer": customer}})
        if carrier:
            filter_clauses.append({"term": {"carrier": carrier}})
        if temperature is not None and str(temperature).strip() != "":
            filter_clauses.append({"term": {"temperature": str(temperature).strip()}})
        if vat_included is not None:
            filter_clauses.append({"term": {"vat_included": vat_included}})
        if date_from:
            filter_clauses.append({"range": {"request_date": {"gte": date_from}}})
        if date_to:
            filter_clauses.append({"range": {"request_date": {"lte": date_to}}})
        if price_from is not None:
            # Фильтр по цене: может быть price_with_vat или price_without_vat
            filter_clauses.append({
                "bool": {
                    "should": [
                        {"range": {"price_with_vat": {"gte": price_from}}},
                        {"range": {"price_without_vat": {"gte": price_from}}},
                    ],
                    "minimum_should_match": 1,
                }
            })
        if price_to is not None:
            filter_clauses.append({
                "bool": {
                    "should": [
                        {"range": {"price_with_vat": {"lte": price_to}}},
                        {"range": {"price_without_vat": {"lte": price_to}}},
                    ],
                    "minimum_should_match": 1,
                }
            })
        if weight_from is not None:
            filter_clauses.append({"range": {"weight_kg": {"gte": weight_from}}})
        if weight_to is not None:
            filter_clauses.append({"range": {"weight_kg": {"lte": weight_to}}})

        query: Dict[str, Any] = {"match_all": {}}
        if must or filter_clauses:
            query = {
                "bool": {},
            }
            if must:
                query["bool"]["must"] = must
            if filter_clauses:
                query["bool"]["filter"] = filter_clauses
        return {"query": query}

    async def list_requests(
        self,
        user_id: str,
        jwt_token: Optional[str],
        *,
        search_query: Optional[str] = None,
        route_from: Optional[str] = None,
        route_to: Optional[str] = None,
        customer: Optional[str] = None,
        carrier: Optional[str] = None,
        temperature: Optional[str] = None,
        vat_included: Optional[bool] = None,
        date_from: Optional[str] = None,
        date_to: Optional[str] = None,
        price_from: Optional[float] = None,
        price_to: Optional[float] = None,
        weight_from: Optional[float] = None,
        weight_to: Optional[float] = None,
        page: int = 1,
        size: int = 25,
        sort_field: str = "request_date",
        sort_order: str = "desc",
    ) -> Dict[str, Any]:
        """Список заявок с фильтрами, пагинацией и сортировкой."""
        opensearch = self.session_manager.get_user_opensearch_client(
            user_id, jwt_token
        )
        from_index = (page - 1) * size
        sort_key = sort_field if sort_field else "request_date"
        if sort_key not in ("request_date", "price_with_vat", "price_without_vat", "weight_kg", "processed_at"):
            sort_key = "request_date"
        order = "desc" if (sort_order or "desc").lower() == "desc" else "asc"
        body = self._build_list_query(
            search_query=search_query,
            route_from=route_from,
            route_to=route_to,
            customer=customer,
            carrier=carrier,
            temperature=temperature,
            vat_included=vat_included,
            date_from=date_from,
            date_to=date_to,
            price_from=price_from,
            price_to=price_to,
            weight_from=weight_from,
            weight_to=weight_to,
        )
        # Всего записей (для пагинации)
        count_body = {**body, "size": 0}
        count_resp = await opensearch.search(
            index=LOGISTICS_REQUESTS_INDEX,
            body=count_body,
            ignore_unavailable=True,
        )
        total = count_resp.get("hits", {}).get("total", 0)
        if isinstance(total, dict):
            total = total.get("value", 0)
        # Выборка с сортировкой
        body["from"] = from_index
        body["size"] = size
        body["sort"] = [{sort_key: {"order": order, "missing": "_last"}}]
        resp = await opensearch.search(
            index=LOGISTICS_REQUESTS_INDEX,
            body=body,
            ignore_unavailable=True,
        )
        hits = resp.get("hits", {}).get("hits", [])
        items = [h.get("_source") or {} for h in hits]
        result = {
            "items": items,
            "total": total,
            "page": page,
            "size": size,
        }
        return result

    async def get_by_id(
        self,
        user_id: str,
        jwt_token: Optional[str],
        document_id: str,
    ) -> Optional[Dict[str, Any]]:
        """Получить одну заявку по document_id."""
        opensearch = self.session_manager.get_user_opensearch_client(
            user_id, jwt_token
        )
        body = {
            "query": {"term": {"document_id": document_id}},
            "size": 1,
        }
        resp = await opensearch.search(
            index=LOGISTICS_REQUESTS_INDEX,
            body=body,
            ignore_unavailable=True,
        )
        hits = resp.get("hits", {}).get("hits", [])
        if not hits:
            return None
        return hits[0].get("_source")

    async def delete_by_document_id(
        self,
        user_id: str,
        jwt_token: Optional[str],
        document_id: str,
    ) -> bool:
        """Удалить заявку по document_id. Возвращает True, если удалено."""
        if not document_id or not document_id.strip():
            return False
        opensearch = self.session_manager.get_user_opensearch_client(
            user_id, jwt_token
        )
        body = {"query": {"term": {"document_id": document_id.strip()}}}
        try:
            result = await opensearch.delete_by_query(
                index=LOGISTICS_REQUESTS_INDEX,
                body=body,
                conflicts="proceed",
                ignore_unavailable=True,
            )
            deleted = result.get("deleted", 0)
            if deleted > 0:
                logger.info(
                    "Удалена логистическая заявка",
                    document_id=document_id,
                    deleted=deleted,
                )
            return deleted > 0
        except Exception as e:
            logger.warning(
                "Ошибка удаления заявки",
                document_id=document_id,
                error=str(e),
            )
            return False

    async def get_aggregations_with_filters(
        self,
        user_id: str,
        jwt_token: Optional[str],
        **filter_kwargs: Any,
    ) -> Dict[str, Any]:
        """Агрегации с теми же фильтрами, что и list_requests."""
        body = self._build_list_query(**filter_kwargs)
        return await self.get_aggregations(user_id, jwt_token, filter_body=body)

    async def get_aggregations(
        self,
        user_id: str,
        jwt_token: Optional[str],
        filter_body: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Агрегации для блока аналитики: всего заявок, средняя цена, средний вес, уникальные перевозчики/маршруты."""
        opensearch = self.session_manager.get_user_opensearch_client(
            user_id, jwt_token
        )
        query = (filter_body or {}).get("query", {"match_all": {}})
        body = {
            "size": 0,
            "query": query,
            "aggs": {
                "avg_price_with_vat": {"avg": {"field": "price_with_vat"}},
                "avg_price_without_vat": {"avg": {"field": "price_without_vat"}},
                "avg_weight": {"avg": {"field": "weight_kg"}},
                "unique_carriers": {"cardinality": {"field": "carrier"}},
                "unique_route_from": {"cardinality": {"field": "route_from"}},
                "unique_route_to": {"cardinality": {"field": "route_to"}},
            },
        }
        try:
            resp = await opensearch.search(
                index=LOGISTICS_REQUESTS_INDEX,
                body=body,
                ignore_unavailable=True,
            )
        except Exception as e:
            logger.warning("logistics aggregations failed", error=str(e))
            return {
                "total": 0,
                "avg_price": None,
                "avg_weight_kg": None,
                "unique_carriers": 0,
                "unique_routes": 0,
            }
        aggs = resp.get("aggregations", {})
        total = resp.get("hits", {}).get("total", 0)
        if isinstance(total, dict):
            total = total.get("value", 0)
        avg_vat = aggs.get("avg_price_with_vat", {}).get("value")
        avg_no_vat = aggs.get("avg_price_without_vat", {}).get("value")
        avg_price = avg_vat if avg_vat is not None else avg_no_vat
        avg_weight_kg = aggs.get("avg_weight", {}).get("value")
        unique_carriers = aggs.get("unique_carriers", {}).get("value", 0) or 0
        from_r = aggs.get("unique_route_from", {}).get("value", 0) or 0
        to_r = aggs.get("unique_route_to", {}).get("value", 0) or 0
        unique_routes = max(int(from_r), int(to_r))
        return {
            "total": total,
            "avg_price": avg_price,
            "avg_weight_kg": avg_weight_kg,
            "unique_carriers": unique_carriers,
            "unique_routes": unique_routes,
        }
