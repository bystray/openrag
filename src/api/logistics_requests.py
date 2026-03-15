# API эндпоинты для структурированных логистических заявок.

from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from dependencies import get_current_user, get_logistics_requests_service
from session_manager import User
from services.logistics_requests_service import LogisticsRequestsService


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
