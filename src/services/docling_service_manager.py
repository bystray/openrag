"""Docling Docker container management and diagnostics."""

import asyncio
import json
import shutil
import time
from typing import Any

import httpx

from config.settings import (
    DOCLING_DOCKER_CONTAINER_NAME,
    DOCLING_MANAGED_BY_DOCKER,
    DOCLING_OCR_ENGINE,
    DOCLING_WORKERS,
)
from utils.logging_config import get_logger

logger = get_logger(__name__)

# Default tail for logs
DEFAULT_LOG_TAIL = 200
MAX_LOG_TAIL = 2000

# Timeouts
HEALTHCHECK_TIMEOUT = 5.0
LOGS_TIMEOUT = 10.0
RESTART_TIMEOUT = 30.0
INSPECT_TIMEOUT = 5.0


def _get_runtime_command() -> list[str] | None:
    """Return docker or podman command, preferring docker."""
    if shutil.which("docker"):
        return ["docker"]
    if shutil.which("podman"):
        return ["podman"]
    return None


class DoclingServiceManager:
    """Manages Docling Docker container diagnostics and control."""

    def __init__(
        self,
        container_name: str | None = None,
        docling_url: str | None = None,
    ):
        self.container_name = container_name or DOCLING_DOCKER_CONTAINER_NAME
        self.docling_url = docling_url or "http://localhost:5001"
        self.managed_by_docker = DOCLING_MANAGED_BY_DOCKER

    async def _run_runtime(self, args: list[str], timeout: float = 5.0) -> tuple[bool, str, str]:
        """Run docker/podman command. Returns (success, stdout, stderr)."""
        cmd = _get_runtime_command()
        if not cmd:
            return False, "", "Docker or Podman not found"

        full_cmd = cmd + args
        try:
            process = await asyncio.create_subprocess_exec(
                *full_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(),
                timeout=timeout,
            )
            stdout_text = stdout.decode(errors="replace") if stdout else ""
            stderr_text = stderr.decode(errors="replace") if stderr else ""
            return process.returncode == 0, stdout_text, stderr_text
        except asyncio.TimeoutError:
            return False, "", f"Command timed out after {timeout}s"
        except Exception as e:
            logger.exception("Docling runtime command failed")
            return False, "", str(e)

    async def get_container_info(self) -> dict[str, Any]:
        """Get container info via docker inspect."""
        if not self.managed_by_docker:
            return {
                "exists": False,
                "running": False,
                "status": "not_managed",
                "health_status": None,
                "exit_code": None,
                "oom_killed": False,
                "restart_count": 0,
                "started_at": None,
                "finished_at": None,
                "image": None,
                "container_name": self.container_name,
                "error": "Docling is not managed by Docker (DOCLING_MANAGED_BY_DOCKER=false)",
            }

        success, stdout, stderr = await self._run_runtime(
            ["inspect", self.container_name, "--format", "{{json .}}"],
            timeout=INSPECT_TIMEOUT,
        )

        if not success:
            if "No such object" in stderr or "no such container" in stderr.lower():
                return {
                    "exists": False,
                    "running": False,
                    "status": "not_found",
                    "health_status": None,
                    "exit_code": None,
                    "oom_killed": False,
                    "restart_count": 0,
                    "started_at": None,
                    "finished_at": None,
                    "image": None,
                    "container_name": self.container_name,
                    "error": f"Container '{self.container_name}' not found",
                }
            return {
                "exists": False,
                "running": False,
                "status": "error",
                "health_status": None,
                "exit_code": None,
                "oom_killed": False,
                "restart_count": 0,
                "started_at": None,
                "finished_at": None,
                "image": None,
                "container_name": self.container_name,
                "error": stderr or "Docker inspect failed",
            }

        try:
            data = json.loads(stdout.strip())
        except json.JSONDecodeError:
            return {
                "exists": True,
                "running": False,
                "status": "unknown",
                "health_status": None,
                "exit_code": None,
                "oom_killed": False,
                "restart_count": 0,
                "started_at": None,
                "finished_at": None,
                "image": None,
                "container_name": self.container_name,
                "error": "Failed to parse docker inspect output",
            }

        state = data.get("State", {})
        config = data.get("Config", {})
        health = state.get("Health", {})

        return {
            "exists": True,
            "running": state.get("Running", False),
            "status": state.get("Status", "unknown"),
            "health_status": health.get("Status") if health else None,
            "exit_code": state.get("ExitCode"),
            "oom_killed": state.get("OOMKilled", False),
            "restart_count": data.get("RestartCount", 0),
            "started_at": state.get("StartedAt"),
            "finished_at": state.get("FinishedAt"),
            "image": config.get("Image") or (data.get("Config", {}).get("Image", "")),
            "container_name": data.get("Name", "").lstrip("/") or self.container_name,
        }

    async def get_logs(self, tail: int = DEFAULT_LOG_TAIL) -> tuple[bool, str]:
        """Get container logs. Returns (success, logs_text)."""
        if not self.managed_by_docker:
            return False, "Docling is not managed by Docker (DOCLING_MANAGED_BY_DOCKER=false)"

        tail = min(max(tail, 1), MAX_LOG_TAIL)
        success, stdout, stderr = await self._run_runtime(
            ["logs", "--tail", str(tail), self.container_name],
            timeout=LOGS_TIMEOUT,
        )
        if not success:
            return False, stderr or "Failed to get logs"
        return True, stdout or ""

    async def restart_container(self) -> tuple[bool, str]:
        """Restart the container. Returns (success, message)."""
        if not self.managed_by_docker:
            return False, "Docling is not managed by Docker (DOCLING_MANAGED_BY_DOCKER=false)"

        success, stdout, stderr = await self._run_runtime(
            ["restart", self.container_name],
            timeout=RESTART_TIMEOUT,
        )
        if not success:
            return False, stderr or "Restart failed"
        return True, "Container restarted successfully"

    async def healthcheck(self) -> dict[str, Any]:
        """Perform HTTP health check on docling-serve."""
        url = f"{self.docling_url.rstrip('/')}/health"
        start = time.perf_counter()
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(url, timeout=HEALTHCHECK_TIMEOUT)
            latency_ms = (time.perf_counter() - start) * 1000
            try:
                payload = response.json()
            except Exception:
                payload = {"raw": response.text[:500]}

            return {
                "ok": response.status_code == 200,
                "status_code": response.status_code,
                "latency_ms": round(latency_ms, 2),
                "payload": payload,
            }
        except httpx.TimeoutException:
            return {
                "ok": False,
                "status_code": None,
                "latency_ms": (time.perf_counter() - start) * 1000,
                "payload": {"error": "Connection timeout"},
            }
        except Exception as e:
            return {
                "ok": False,
                "status_code": None,
                "latency_ms": (time.perf_counter() - start) * 1000,
                "payload": {"error": str(e)},
            }

    async def get_full_status(self) -> dict[str, Any]:
        """Combine container info, healthcheck, and config."""
        if not self.managed_by_docker:
            container_info = await self.get_container_info()
            return {
                "managed_by_docker": False,
                "docling_url": self.docling_url,
                "container": container_info,
                "healthcheck": None,
                "config": {
                    "workers": None,
                    "ocr_engine": DOCLING_OCR_ENGINE or "default",
                },
            }

        container_info = await self.get_container_info()
        healthcheck_result = await self.healthcheck()

        workers = DOCLING_WORKERS
        ocr_engine = DOCLING_OCR_ENGINE or "easyocr"

        return {
            "managed_by_docker": True,
            "docling_url": self.docling_url,
            "container": container_info,
            "healthcheck": healthcheck_result,
            "config": {
                "workers": workers,
                "ocr_engine": ocr_engine,
            },
        }
