# Docling Service (Docker)

This document describes how to run Docling as a Docker container and use the backend diagnostics and Docling Service UI.

## Running Docling in Docker

### Start the container

```bash
docker compose -f infra/docker-compose.docling.yml up -d
```

The container will:
- Expose port 5001
- Use 4GB memory limit and 2 CPU limit
- Run with `restart: unless-stopped`
- Perform health checks every 30 seconds

### Stop the container

```bash
docker compose -f infra/docker-compose.docling.yml down
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `DOCLING_MANAGED_BY_DOCKER` | `false` | Set to `true` to enable backend diagnostics and Docling Service UI. When `false`, the backend will not attempt to inspect or control the container. |
| `DOCLING_DOCKER_CONTAINER_NAME` | `openrag-docling` | Name of the Docling container for `docker inspect` and `docker logs`. |
| `DOCLING_DOCKER_COMPOSE_FILE` | — | Optional path to the compose file (for reference; not used by backend). |
| `DOCLING_SERVE_URL` | `http://localhost:5001` | URL of the Docling Serve instance. Set this if Docling runs on a different host or port. |
| `DOCLING_OCR_ENGINE` | — | OCR engine (e.g. `easyocr`). Passed to the container and used by the ingest pipeline. |
| `DOCLING_WORKERS` | `1` | Number of worker processes (used when starting docling via TUI; for Docker, set in `infra/docker-compose.docling.yml`). |

## How Diagnostics Work

The backend uses the Docker (or Podman) CLI to:

1. **Container info** — `docker inspect <container_name>` to get status, exit code, OOMKilled, restart count, started/finished times, image.
2. **Logs** — `docker logs --tail N <container_name>` to retrieve the last N lines.
3. **Restart** — `docker restart <container_name>` to restart the container.
4. **Health check** — HTTP GET to `DOCLING_SERVE_URL/health` to verify the service is responding.

If Docker or Podman is not available, or the container is not found, the backend returns structured errors without crashing.

## Interpreting Status

### OOMKilled

If `oom_killed` is `true`, the container was terminated by the system due to memory exhaustion. Consider:

- Increasing the `memory` limit in `infra/docker-compose.docling.yml`
- Reducing `DOCLING_WORKERS` if applicable
- Processing fewer or smaller documents concurrently

### Exit Code

If the container is stopped and `exit_code` is non-zero, the process exited with an error. Check the logs for stack traces or error messages.

### Unhealthy

If the container is `running` but the health check fails:

- The service may still be starting (wait a minute and retry)
- The service may be overloaded or stuck
- Network or firewall issues may prevent the backend from reaching the container

### Container Not Found

If the container does not exist:

- Start it with `docker compose -f infra/docker-compose.docling.yml up -d`
- Ensure `DOCLING_DOCKER_CONTAINER_NAME` matches the actual container name

## Docling Service UI

When `DOCLING_MANAGED_BY_DOCKER=true`, open **Settings → Docling Service** (or navigate to `/settings/docling-service`) to:

- View container status (running/stopped, health, OOMKilled, restart count)
- See container details (image, started at, exit code)
- Run health checks and view latency
- View and refresh logs (with configurable tail: 100, 200, 500)
- Restart the service

If `DOCLING_MANAGED_BY_DOCKER=false`, the UI shows an informational message and suggests enabling the feature or using the TUI for native docling management.

## Ingest Pipeline

The ingest pipeline is unchanged. It continues to use `DOCLING_SERVE_URL` to send conversion requests to Docling. Whether Docling runs as a native process (TUI) or in Docker, the backend and Langflow use the same URL. Ensure `DOCLING_SERVE_URL` points to the correct host and port (e.g. `http://localhost:5001` for local Docker, or `http://host.docker.internal:5001` when the backend runs inside Docker).
