"use client";

import {
  Activity,
  AlertTriangle,
  FileText,
  Loader2,
  RefreshCw,
  Server,
} from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import { toast } from "sonner";
import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  getLogs,
  getStatus,
  restartService,
  runHealthcheck,
} from "@/lib/api/docling-service";
import type { FullStatusResponse } from "@/types/docling-service";

const TAIL_OPTIONS = [100, 200, 500];

function DoclingServiceContent() {
  const [status, setStatus] = useState<FullStatusResponse | null>(null);
  const [logs, setLogs] = useState<string>("");
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [logsLoading, setLogsLoading] = useState(false);
  const [restarting, setRestarting] = useState(false);
  const [healthchecking, setHealthchecking] = useState(false);
  const [tail, setTail] = useState(200);

  const fetchStatus = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await getStatus();
      setStatus(data);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Failed to load status");
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const fetchLogs = useCallback(async () => {
    if (!status?.managed_by_docker) return;
    setLogsLoading(true);
    try {
      const res = await getLogs(tail);
      setLogs(res.logs);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Failed to load logs");
    } finally {
      setLogsLoading(false);
    }
  }, [status?.managed_by_docker, tail]);

  const handleRestart = async () => {
    if (!status?.managed_by_docker) return;
    setRestarting(true);
    try {
      const res = await restartService();
      setStatus(res.status);
      toast.success(res.message);
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Restart failed");
    } finally {
      setRestarting(false);
    }
  };

  const handleHealthcheck = async () => {
    setHealthchecking(true);
    try {
      const result = await runHealthcheck();
      if (status) {
        setStatus({
          ...status,
          healthcheck: result,
        });
      }
      toast.info(
        result.ok
          ? `Health OK (${result.latency_ms}ms)`
          : `Health check failed: ${JSON.stringify(result.payload)}`,
      );
    } catch (e) {
      toast.error(e instanceof Error ? e.message : "Health check failed");
    } finally {
      setHealthchecking(false);
    }
  };

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  if (loading) {
    return (
      <div className="flex items-center justify-center min-h-[400px]">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error && !status) {
    return (
      <div className="space-y-4 p-4">
        <div className="flex items-center gap-2 text-destructive">
          <AlertTriangle className="h-5 w-5" />
          <span>{error}</span>
        </div>
        <Button onClick={fetchStatus} variant="outline">
          <RefreshCw className="h-4 w-4 mr-2" />
          Retry
        </Button>
      </div>
    );
  }

  if (status && !status.managed_by_docker) {
    return (
      <div className="space-y-4 p-4">
        <Card>
          <CardHeader>
            <CardTitle>Docling Service</CardTitle>
            <CardDescription>
              Docling is not managed by Docker. Set
              DOCLING_MANAGED_BY_DOCKER=true in your .env to enable container
              diagnostics.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <p className="text-sm text-muted-foreground mb-4">
              Use the TUI for native docling-serve management, or run docling in
              Docker and enable this feature.
            </p>
            <div className="space-y-2 text-sm">
              <p>
                <strong>URL:</strong> {status.docling_url}
              </p>
            </div>
          </CardContent>
        </Card>
      </div>
    );
  }

  const container = status?.container;
  const healthcheck = status?.healthcheck;
  const config = status?.config;

  const isOomKilled = container?.oom_killed ?? false;
  const hasCrash = !container?.running && (container?.exit_code ?? 0) !== 0;
  const isUnhealthy = container?.running && healthcheck && !healthcheck.ok;
  const notFound = container?.status === "not_found";

  return (
    <div className="space-y-6 p-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Docling Service</h1>
          <p className="text-muted-foreground">
            Container diagnostics and management
          </p>
        </div>
        <Link href="/settings">
          <Button variant="outline">Back to Settings</Button>
        </Link>
      </div>

      {/* Diagnostic banners */}
      {isOomKilled && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-500/30">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <span>
            Container was killed by OOM (out of memory). Consider increasing
            memory limits.
          </span>
        </div>
      )}
      {hasCrash && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/20 text-destructive border border-destructive/30">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <span>
            Container crashed (exit code: {container?.exit_code}). Check logs
            for details.
          </span>
        </div>
      )}
      {isUnhealthy && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-amber-500/20 text-amber-700 dark:text-amber-400 border border-amber-500/30">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <span>
            Container is running but health check failed. Service may be
            starting or unhealthy.
          </span>
        </div>
      )}
      {notFound && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-destructive/20 text-destructive border border-destructive/30">
          <AlertTriangle className="h-5 w-5 shrink-0" />
          <span>
            Container not found. Start it with: docker compose -f
            infra/docker-compose.docling.yml up -d
          </span>
        </div>
      )}

      {/* Summary */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Server className="h-5 w-5" />
            Summary
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-sm">
            <div>
              <span className="text-muted-foreground">Status</span>
              <p className="font-medium">
                {container?.running ? "Running" : "Stopped"}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">Health</span>
              <p className="font-medium">
                {healthcheck?.ok ? "OK" : healthcheck ? "Unhealthy" : "—"}
              </p>
            </div>
            <div>
              <span className="text-muted-foreground">OOM Killed</span>
              <p className="font-medium">{isOomKilled ? "Yes" : "No"}</p>
            </div>
            <div>
              <span className="text-muted-foreground">Restart count</span>
              <p className="font-medium">{container?.restart_count ?? "—"}</p>
            </div>
            <div>
              <span className="text-muted-foreground">URL</span>
              <p className="font-medium break-all">
                {status?.docling_url ?? "—"}
              </p>
            </div>
          </div>
        </CardContent>
      </Card>

      {/* Container Details */}
      <Card>
        <CardHeader>
          <CardTitle>Container Details</CardTitle>
          <CardDescription>Docker container information</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="grid grid-cols-2 gap-2">
            <span className="text-muted-foreground">Image</span>
            <span>{container?.image ?? "—"}</span>
            <span className="text-muted-foreground">Started at</span>
            <span>{container?.started_at ?? "—"}</span>
            <span className="text-muted-foreground">Exit code</span>
            <span>{container?.exit_code ?? "—"}</span>
            <span className="text-muted-foreground">Status</span>
            <span>{container?.status ?? "—"}</span>
          </div>
        </CardContent>
      </Card>

      {/* Health Panel */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Activity className="h-5 w-5" />
            Health Check
          </CardTitle>
          <CardDescription>HTTP health check on docling-serve</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2">
          <div className="flex items-center gap-4">
            <div>
              <span className="text-muted-foreground text-sm">Status: </span>
              <span className="font-medium">
                {healthcheck?.ok ? "OK" : healthcheck ? "Failed" : "—"}
              </span>
            </div>
            {healthcheck?.latency_ms != null && (
              <div>
                <span className="text-muted-foreground text-sm">Latency: </span>
                <span className="font-medium">{healthcheck.latency_ms}ms</span>
              </div>
            )}
            <Button
              size="sm"
              variant="outline"
              onClick={handleHealthcheck}
              disabled={healthchecking}
            >
              {healthchecking ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                "Run health check"
              )}
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Service Config (read-only) */}
      <Card>
        <CardHeader>
          <CardTitle>Service Config</CardTitle>
          <CardDescription>Read-only configuration</CardDescription>
        </CardHeader>
        <CardContent className="space-y-2 text-sm">
          <div className="grid grid-cols-2 gap-2">
            <span className="text-muted-foreground">URL</span>
            <span>{status?.docling_url ?? "—"}</span>
            <span className="text-muted-foreground">Container name</span>
            <span>{container?.container_name ?? "—"}</span>
            <span className="text-muted-foreground">Managed by Docker</span>
            <span>{status?.managed_by_docker ? "Yes" : "No"}</span>
            <span className="text-muted-foreground">Workers</span>
            <span>{config?.workers ?? "—"}</span>
            <span className="text-muted-foreground">OCR engine</span>
            <span>{config?.ocr_engine ?? "—"}</span>
          </div>
        </CardContent>
      </Card>

      {/* Logs Viewer */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <FileText className="h-5 w-5" />
                Logs
              </CardTitle>
              <CardDescription>Container logs</CardDescription>
            </div>
            <div className="flex items-center gap-2">
              <select
                className="rounded border px-2 py-1 text-sm"
                value={tail}
                onChange={(e) => setTail(Number(e.target.value))}
              >
                {TAIL_OPTIONS.map((n) => (
                  <option key={n} value={n}>
                    Last {n} lines
                  </option>
                ))}
              </select>
              <Button
                size="sm"
                variant="outline"
                onClick={fetchLogs}
                disabled={logsLoading}
              >
                {logsLoading ? (
                  <Loader2 className="h-4 w-4 animate-spin" />
                ) : (
                  <RefreshCw className="h-4 w-4" />
                )}
              </Button>
            </div>
          </div>
        </CardHeader>
        <CardContent>
          <pre className="bg-muted p-4 rounded-lg text-xs overflow-auto max-h-[400px] whitespace-pre-wrap">
            {logs || "No logs loaded. Click Refresh."}
          </pre>
        </CardContent>
      </Card>

      {/* Actions */}
      <Card>
        <CardHeader>
          <CardTitle>Actions</CardTitle>
          <CardDescription>Container control</CardDescription>
        </CardHeader>
        <CardContent className="flex gap-2">
          <Button variant="outline" onClick={fetchStatus} disabled={loading}>
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh status
          </Button>
          <Button
            variant="outline"
            onClick={fetchLogs}
            disabled={logsLoading || !status?.managed_by_docker}
          >
            <RefreshCw className="h-4 w-4 mr-2" />
            Refresh logs
          </Button>
          <Button
            variant="destructive"
            onClick={handleRestart}
            disabled={restarting || !container?.running}
          >
            {restarting ? (
              <Loader2 className="h-4 w-4 animate-spin mr-2" />
            ) : null}
            Restart service
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}

export default function DoclingServicePage() {
  return (
    <ProtectedRoute>
      <DoclingServiceContent />
    </ProtectedRoute>
  );
}
