# API эндпоинты для структурированных логистических заявок.

import os
from typing import Any, Dict, List, Optional

from fastapi import Depends, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel, Field

from config.settings import get_documents_dir
from dependencies import get_current_user, get_langflow_file_service, get_logistics_requests_service
from session_manager import User
from services.logistics_extraction_service import LogisticsExtractionService
from services.logistics_requests_service import LogisticsRequestsService
from utils.file_utils import make_safe_storage_filename


class LogisticsListBody(BaseModel):
    """Тело запроса списка заявок с фильтрами и пагинацией."""

    search_query: Optional[str] = Field(None, alias="searchQuery")
    route_from: Optional[str] = Field(None, alias="routeFrom")
    route_to: Optional[str] = Field(None, alias="routeTo")
    customer: Optional[str] = None
    carrier: Optional[str] = None
    temperature: Optional[str] = None
    vat_included: Optional[bool] = Field(None, alias="vatIncluded")
    date_from: Optional[str] = Field(None, alias="dateFrom")
    date_to: Optional[str] = Field(None, alias="dateTo")
    price_from: Optional[float] = Field(None, alias="priceFrom")
    price_to: Optional[float] = Field(None, alias="priceTo")
    weight_from: Optional[float] = Field(None, alias="weightFrom")
    weight_to: Optional[float] = Field(None, alias="weightTo")
    page: int = 1
    size: int = 25
    sort_field: str = Field("request_date", alias="sortField")
    sort_order: str = Field("desc", alias="sortOrder")
    include_aggregations: bool = Field(False, alias="includeAggregations")

    model_config = {"populate_by_name": True}


async def list_logistics_requests(
    body: LogisticsListBody,
    user: User = Depends(get_current_user),
    service: LogisticsRequestsService = Depends(get_logistics_requests_service),
):
    """Список логистических заявок с фильтрами, пагинацией и сортировкой."""
    try:
        result = await service.list_requests(
            user_id=user.user_id,
            jwt_token=user.jwt_token,
            search_query=body.search_query,
            route_from=body.route_from,
            route_to=body.route_to,
            customer=body.customer,
            carrier=body.carrier,
            temperature=body.temperature,
            vat_included=body.vat_included,
            date_from=body.date_from,
            date_to=body.date_to,
            price_from=body.price_from,
            price_to=body.price_to,
            weight_from=body.weight_from,
            weight_to=body.weight_to,
            page=body.page,
            size=body.size,
            sort_field=body.sort_field,
            sort_order=body.sort_order,
        )
        if body.include_aggregations:
            agg = await service.get_aggregations_with_filters(
                user_id=user.user_id,
                jwt_token=user.jwt_token,
                search_query=body.search_query,
                route_from=body.route_from,
                route_to=body.route_to,
                customer=body.customer,
                carrier=body.carrier,
                temperature=body.temperature,
                vat_included=body.vat_included,
                date_from=body.date_from,
                date_to=body.date_to,
                price_from=body.price_from,
                price_to=body.price_to,
                weight_from=body.weight_from,
                weight_to=body.weight_to,
            )
            result["aggregations"] = agg
        return JSONResponse(result, status_code=200)
    except Exception as e:
        error_msg = str(e)
        if "AuthenticationException" in error_msg or "access denied" in error_msg.lower():
            return JSONResponse({"error": error_msg}, status_code=403)
        return JSONResponse({"error": error_msg}, status_code=500)


async def get_logistics_aggregations(
    user: User = Depends(get_current_user),
    service: LogisticsRequestsService = Depends(get_logistics_requests_service),
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
):
    """Агрегации по заявкам (для блока аналитики) с опциональными фильтрами."""
    try:
        result = await service.get_aggregations_with_filters(
            user_id=user.user_id,
            jwt_token=user.jwt_token,
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
        return JSONResponse(result, status_code=200)
    except Exception as e:
        error_msg = str(e)
        if "AuthenticationException" in error_msg or "access denied" in error_msg.lower():
            return JSONResponse({"error": error_msg}, status_code=403)
        return JSONResponse({"error": error_msg}, status_code=500)


async def get_logistics_request_by_id(
    document_id: str,
    user: User = Depends(get_current_user),
    service: LogisticsRequestsService = Depends(get_logistics_requests_service),
):
    """Получить одну заявку по document_id."""
    try:
        item = await service.get_by_id(
            user_id=user.user_id,
            jwt_token=user.jwt_token,
            document_id=document_id,
        )
        if item is None:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        return JSONResponse(item, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "AuthenticationException" in error_msg or "access denied" in error_msg.lower():
            return JSONResponse({"error": error_msg}, status_code=403)
        return JSONResponse({"error": error_msg}, status_code=500)


async def delete_logistics_request(
    document_id: str,
    user: User = Depends(get_current_user),
    service: LogisticsRequestsService = Depends(get_logistics_requests_service),
):
    """Удалить заявку по document_id."""
    if not document_id or not document_id.strip():
        raise HTTPException(status_code=400, detail="document_id обязателен")
    try:
        deleted = await service.delete_by_document_id(
            user_id=user.user_id,
            jwt_token=user.jwt_token,
            document_id=document_id.strip(),
        )
        if not deleted:
            raise HTTPException(status_code=404, detail="Заявка не найдена")
        return JSONResponse({"success": True, "deleted": True}, status_code=200)
    except HTTPException:
        raise
    except Exception as e:
        error_msg = str(e)
        if "AuthenticationException" in error_msg or "access denied" in error_msg.lower():
            return JSONResponse({"error": error_msg}, status_code=403)
        return JSONResponse({"error": error_msg}, status_code=500)


# --- Извлечение заявок из базы знаний (extraction pipeline) ---


class ExtractBody(BaseModel):
    """Параметры запуска извлечения логистических заявок из индекса documents."""

    limit: Optional[int] = Field(None, description="Обработать только первые N кандидатов")
    force: bool = Field(False, description="Переобработать уже сохранённые документы")
    dry_run: bool = Field(False, description="Не писать в индекс, только вернуть результат")
    filename: Optional[str] = Field(None, description="Обработать только указанный файл")


async def extract_logistics_requests(
    body: ExtractBody,
    user: User = Depends(get_current_user),
    langflow_file_service=Depends(get_langflow_file_service),
):
    """
    Запуск пайплайна извлечения: документы из индекса documents → LLM (или Langflow flow) → logistics_requests_structured.
    """
    try:
        from config.settings import clients, LANGFLOW_LOGISTICS_EXTRACT_FLOW_ID

        if clients.opensearch is None:
            return JSONResponse(
                {"error": "OpenSearch не инициализирован. Запустите приложение полностью."},
                status_code=503,
            )

        service = LogisticsExtractionService(
            opensearch=clients.opensearch,
            langflow_file_service=langflow_file_service,
            logistics_flow_id=LANGFLOW_LOGISTICS_EXTRACT_FLOW_ID or None,
        )

        if body.filename:
            candidates = await service.get_candidate_filenames(only_filename=body.filename)
            if not candidates:
                return JSONResponse(
                    {
                        "status": "ok",
                        "started": True,
                        "mode": "single",
                        "limit": None,
                        "force": body.force,
                        "dry_run": body.dry_run,
                        "filename": body.filename,
                        "summary": {
                            "found_candidates": 0,
                            "processed": 0,
                            "success": 0,
                            "skipped": 0,
                            "failed": 0,
                        },
                        "items": [],
                        "error_summary": {},
                    },
                    status_code=200,
                )
        else:
            candidates = await service.get_candidate_filenames(limit=body.limit)

        success_count = 0
        skipped_count = 0
        failed_count = 0
        items: List[Dict[str, Any]] = []
        error_summary: Dict[str, int] = {}

        for fn in candidates:
            result = await service.process_one(
                filename=fn,
                force=body.force,
                dry_run=body.dry_run,
            )
            status = result["status"]
            err_cat = result.get("error_category")
            err_msg = result.get("error_message")

            items.append({
                "filename": fn,
                "status": status,
                "error_category": err_cat,
                "error_message": err_msg,
            })

            if status == "success":
                success_count += 1
            elif status == "skipped":
                skipped_count += 1
                if err_cat:
                    error_summary[err_cat] = error_summary.get(err_cat, 0) + 1
            else:
                failed_count += 1
                if err_cat:
                    error_summary[err_cat] = error_summary.get(err_cat, 0) + 1

        response: Dict[str, Any] = {
            "status": "ok",
            "started": True,
            "mode": "single" if body.filename else "batch",
            "limit": body.limit,
            "force": body.force,
            "dry_run": body.dry_run,
            "filename": body.filename,
            "summary": {
                "found_candidates": len(candidates),
                "processed": len(candidates),
                "success": success_count,
                "skipped": skipped_count,
                "failed": failed_count,
            },
            "items": items,
            "error_summary": error_summary,
        }
        return JSONResponse(response, status_code=200)
    except Exception as e:
        error_msg = str(e)
        if "AuthenticationException" in error_msg or "access denied" in error_msg.lower():
            return JSONResponse({"error": error_msg}, status_code=403)
        return JSONResponse({"error": error_msg}, status_code=500)


def _find_file_in_documents_dir(filename: str) -> Optional[str]:
    """Find file in openrag-documents by filename (exact or safe_name match, case-insensitive). Returns path or None."""
    if not filename or not filename.strip():
        return None
    base_dir = get_documents_dir()
    if not os.path.isdir(base_dir):
        return None
    base_real = os.path.realpath(base_dir)
    filename_clean = filename.strip()
    safe_target = make_safe_storage_filename(filename_clean).lower()

    def matches(fn: str) -> bool:
        if fn == filename_clean:
            return True
        if fn.lower() == filename_clean.lower():
            return True
        if make_safe_storage_filename(fn).lower() == safe_target:
            return True
        return False

    # Exact match
    candidate = os.path.join(base_dir, filename_clean)
    if os.path.isfile(candidate) and os.path.realpath(candidate).startswith(base_real):
        return candidate

    # Recursive search: match by filename or safe_name (case-insensitive)
    for root, _, files in os.walk(base_dir):
        for fn in files:
            if matches(fn):
                path = os.path.join(root, fn)
                if os.path.realpath(path).startswith(base_real):
                    return path
    return None


async def get_original_file(
    filename: Optional[str] = None,
    user: User = Depends(get_current_user),
):
    """Отдать исходный PDF из openrag-documents по имени файла."""
    if not filename or not filename.strip():
        raise HTTPException(status_code=400, detail="filename обязателен")
    file_path = _find_file_in_documents_dir(filename)
    if not file_path:
        raise HTTPException(status_code=404, detail="Файл не найден в openrag-documents")
    return FileResponse(file_path, media_type="application/pdf", filename=os.path.basename(file_path))
