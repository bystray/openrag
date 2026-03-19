export interface ContainerInfo {
  exists: boolean;
  running: boolean;
  status: string;
  health_status: string | null;
  exit_code: number | null;
  oom_killed: boolean;
  restart_count: number;
  started_at: string | null;
  finished_at: string | null;
  image: string | null;
  container_name: string;
  error?: string;
}

export interface HealthcheckResult {
  ok: boolean;
  status_code: number | null;
  latency_ms: number;
  payload: Record<string, unknown>;
}

export interface DoclingConfig {
  workers: number | null;
  ocr_engine: string;
}

export interface FullStatusResponse {
  managed_by_docker: boolean;
  docling_url: string;
  container: ContainerInfo;
  healthcheck: HealthcheckResult | null;
  config: DoclingConfig;
}

export interface LogsResponse {
  logs: string;
}
