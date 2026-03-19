"""Docling Docker service management API."""

from fastapi import Depends, HTTPException, Query

from dependencies import get_current_user, get_docling_service_manager
from services.docling_service_manager import DoclingServiceManager
from session_manager import User


async def get_status(
    user: User = Depends(get_current_user),
    manager: DoclingServiceManager = Depends(get_docling_service_manager),
):
    """Get full docling service status (container info + healthcheck)."""
    try:
        status = await manager.get_full_status()
        return status
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to get status", "detail": str(e)},
        )


async def get_logs(
    user: User = Depends(get_current_user),
    manager: DoclingServiceManager = Depends(get_docling_service_manager),
    tail: int = Query(default=200, ge=1, le=2000),
):
    """Get docling container logs."""
    if not manager.managed_by_docker:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Docling is not managed by Docker",
                "detail": "Set DOCLING_MANAGED_BY_DOCKER=true to enable container diagnostics",
            },
        )
    success, logs = await manager.get_logs(tail=tail)
    if not success:
        raise HTTPException(
            status_code=500,
            detail={"error": "Failed to get logs", "detail": logs},
        )
    return {"logs": logs}


async def restart_service(
    user: User = Depends(get_current_user),
    manager: DoclingServiceManager = Depends(get_docling_service_manager),
):
    """Restart the docling container."""
    if not manager.managed_by_docker:
        raise HTTPException(
            status_code=400,
            detail={
                "error": "Docling is not managed by Docker",
                "detail": "Set DOCLING_MANAGED_BY_DOCKER=true to enable container control",
            },
        )
    success, message = await manager.restart_container()
    if not success:
        raise HTTPException(
            status_code=500,
            detail={"error": "Restart failed", "detail": message},
        )
    status = await manager.get_full_status()
    return {"message": message, "status": status}


async def run_healthcheck(
    user: User = Depends(get_current_user),
    manager: DoclingServiceManager = Depends(get_docling_service_manager),
):
    """Run HTTP health check on docling-serve."""
    result = await manager.healthcheck()
    return result
