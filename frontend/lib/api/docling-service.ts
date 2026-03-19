import type {
  FullStatusResponse,
  HealthcheckResult,
  LogsResponse,
} from "@/types/docling-service";

const BASE = "/api/docling/service";

async function handleResponse<T>(response: Response): Promise<T> {
  if (!response.ok) {
    const err = await response
      .json()
      .catch(() => ({ detail: response.statusText }));
    const d = err.detail;
    const msg =
      typeof d === "string"
        ? d
        : d && typeof d === "object" && "detail" in d
          ? (d as { detail?: string }).detail
          : d && typeof d === "object" && "error" in d
            ? (d as { error?: string }).error
            : "Request failed";
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  return response.json();
}

export async function getStatus(): Promise<FullStatusResponse> {
  const response = await fetch(BASE + "/status", {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
  });
  return handleResponse<FullStatusResponse>(response);
}

export async function getLogs(tail: number = 200): Promise<LogsResponse> {
  const response = await fetch(`${BASE}/logs?tail=${tail}`, {
    method: "GET",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
  });
  return handleResponse<LogsResponse>(response);
}

export async function restartService(): Promise<{
  message: string;
  status: FullStatusResponse;
}> {
  const response = await fetch(BASE + "/restart", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
  });
  return handleResponse(response);
}

export async function runHealthcheck(): Promise<HealthcheckResult> {
  const response = await fetch(BASE + "/healthcheck", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    credentials: "include",
  });
  return handleResponse<HealthcheckResult>(response);
}
