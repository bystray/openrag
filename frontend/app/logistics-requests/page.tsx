"use client";

import {
  type ColDef,
  type GetRowIdParams,
  themeQuartz,
  type ValueFormatterParams,
} from "ag-grid-community";
import { AgGridReact } from "ag-grid-react";
import { useQueryClient } from "@tanstack/react-query";
import { Loader2, FileSearch, Trash2 } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { ProtectedRoute } from "@/components/protected-route";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import {
  Sheet,
  SheetContent,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  formatDisplayPrice,
  formatRequestDate,
  formatRoute,
  formatVatLabel,
  formatWeightKg,
  EMPTY,
} from "@/app/logistics-requests/format";
import type {
  LogisticsRequest,
  ExtractResponse,
} from "@/app/logistics-requests/types";
import {
  EXTRACT_ERROR_HINTS,
  EXTRACT_ERROR_LABELS,
} from "@/app/logistics-requests/types";
import { useLogisticsRequestByIdQuery } from "@/app/api/queries/useLogisticsRequestByIdQuery";
import { useLogisticsRequestsQuery } from "@/app/api/queries/useLogisticsRequestsQuery";
import { useDeleteLogisticsRequest } from "@/app/api/mutations/useDeleteLogisticsRequest";
import { toast } from "sonner";
import "@/components/AgGrid/registerAgGridModules";
import "@/components/AgGrid/agGridStyles.css";
import { Label } from "@/components/ui/label";

const PAGE_SIZE = 25;
const SORT_FIELDS = [
  { value: "request_date", label: "Дата заявки" },
  { value: "price_with_vat", label: "Цена" },
  { value: "weight_kg", label: "Вес" },
  { value: "processed_at", label: "Обработано" },
] as const;

function LogisticsRequestsPageContent() {
  const [searchQuery, setSearchQuery] = useState("");
  const [routeFrom, setRouteFrom] = useState("");
  const [routeTo, setRouteTo] = useState("");
  const [customer, setCustomer] = useState("");
  const [carrier, setCarrier] = useState("");
  const [temperature, setTemperature] = useState("");
  const [vatIncluded, setVatIncluded] = useState<boolean | null>(null);
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [priceFrom, setPriceFrom] = useState("");
  const [priceTo, setPriceTo] = useState("");
  const [weightFrom, setWeightFrom] = useState("");
  const [weightTo, setWeightTo] = useState("");
  const [page, setPage] = useState(1);
  const [sortField, setSortField] = useState("request_date");
  const [sortOrder, setSortOrder] = useState<"asc" | "desc">("desc");
  const [selectedDocumentId, setSelectedDocumentId] = useState<string | null>(
    null,
  );
  const [deletingDocumentId, setDeletingDocumentId] = useState<string | null>(
    null,
  );
  const [extractLoading, setExtractLoading] = useState(false);
  const [extractResult, setExtractResult] = useState<
    (ExtractResponse & { error?: string }) | null
  >(null);

  const queryClient = useQueryClient();

  const params = useMemo(
    () => ({
      searchQuery: searchQuery || undefined,
      routeFrom: routeFrom || undefined,
      routeTo: routeTo || undefined,
      customer: customer || undefined,
      carrier: carrier || undefined,
      temperature: temperature || undefined,
      vatIncluded: vatIncluded ?? undefined,
      dateFrom: dateFrom || undefined,
      dateTo: dateTo || undefined,
      priceFrom: priceFrom ? Number(priceFrom) : undefined,
      priceTo: priceTo ? Number(priceTo) : undefined,
      weightFrom: weightFrom ? Number(weightFrom) : undefined,
      weightTo: weightTo ? Number(weightTo) : undefined,
      page,
      size: PAGE_SIZE,
      sortField,
      sortOrder,
      includeAggregations: true,
    }),
    [
      searchQuery,
      routeFrom,
      routeTo,
      customer,
      carrier,
      temperature,
      vatIncluded,
      dateFrom,
      dateTo,
      priceFrom,
      priceTo,
      weightFrom,
      weightTo,
      page,
      sortField,
      sortOrder,
    ],
  );

  const { data, isFetching } = useLogisticsRequestsQuery(params);
  const { data: detail, isLoading: detailLoading } =
    useLogisticsRequestByIdQuery(selectedDocumentId);
  const deleteMutation = useDeleteLogisticsRequest();

  const items = data?.items ?? [];
  const total = data?.total ?? 0;
  const aggregations = data?.aggregations;

  const columnDefs: ColDef<LogisticsRequest>[] = useMemo(
    () => [
      {
        field: "request_date",
        headerName: "Дата заявки",
        valueFormatter: (p: ValueFormatterParams<LogisticsRequest>) =>
          formatRequestDate(p.data?.request_date),
        width: 110,
      },
      {
        field: "request_number",
        headerName: "№ заявки",
        width: 110,
      },
      {
        field: "route_from",
        headerName: "Маршрут",
        valueFormatter: (p: ValueFormatterParams<LogisticsRequest>) =>
          formatRoute(p.data?.route_from, p.data?.route_to),
        flex: 1,
        minWidth: 160,
      },
      { field: "customer", headerName: "Заказчик", width: 120 },
      { field: "carrier", headerName: "Перевозчик", width: 120 },
      { field: "cargo", headerName: "Груз", width: 120 },
      {
        field: "weight_kg",
        headerName: "Вес, т",
        valueFormatter: (p: ValueFormatterParams<LogisticsRequest>) => {
          const kg = p.data?.weight_kg;
          if (kg == null) return EMPTY;
          if (kg >= 1000) return (kg / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 2 });
          return (kg / 1000).toLocaleString("ru-RU", { maximumFractionDigits: 3 });
        },
        width: 90,
      },
      {
        field: "temperature",
        headerName: "Температура",
        valueFormatter: (p: ValueFormatterParams<LogisticsRequest>) =>
          p.data?.temperature ?? EMPTY,
        width: 100,
      },
      {
        field: "price_with_vat",
        headerName: "Цена",
        valueFormatter: (p: ValueFormatterParams<LogisticsRequest>) =>
          formatDisplayPrice(p.data?.price_with_vat, p.data?.price_without_vat),
        width: 110,
      },
      {
        field: "vat_included",
        headerName: "НДС",
        valueFormatter: (p: ValueFormatterParams<LogisticsRequest>) =>
          formatVatLabel(p.data?.vat_included),
        width: 95,
      },
      {
        field: "driver_name",
        headerName: "Водитель",
        valueFormatter: (p: ValueFormatterParams<LogisticsRequest>) =>
          p.data?.driver_name ?? EMPTY,
        width: 110,
      },
      {
        headerName: "",
        width: 52,
        sortable: false,
        cellRenderer: (p: { data?: LogisticsRequest }) => {
          const docId = p.data?.document_id;
          if (!docId) return null;
          const isDeleting = deletingDocumentId === docId;
          return (
            <button
              type="button"
              onClick={(e) => {
                e.stopPropagation();
                setDeletingDocumentId(docId);
                deleteMutation.mutate(docId, {
                  onSettled: () => setDeletingDocumentId(null),
                  onSuccess: () => toast.success("Заявка удалена"),
                  onError: (err) =>
                    toast.error(err instanceof Error ? err.message : "Ошибка удаления"),
                });
              }}
              disabled={isDeleting}
              className="p-1.5 rounded hover:bg-muted text-muted-foreground hover:text-destructive transition-colors disabled:opacity-50"
              title="Удалить заявку"
            >
              {isDeleting ? (
                <Loader2 className="h-4 w-4 animate-spin" />
              ) : (
                <Trash2 className="h-4 w-4" />
              )}
            </button>
          );
        },
      },
    ],
    [deleteMutation, deletingDocumentId],
  );

  const defaultColDef = useMemo<ColDef<LogisticsRequest>>(
    () => ({
      resizable: true,
      sortable: false,
    }),
    [],
  );

  const onRowClicked = useCallback((event: { data?: LogisticsRequest }) => {
    const id = event.data?.document_id;
    if (id) setSelectedDocumentId(id);
  }, []);

  const runExtract = useCallback(async () => {
    setExtractLoading(true);
    setExtractResult(null);
    try {
      const res = await fetch("/api/logistics-requests/extract", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          limit: null,
          force: false,
          dry_run: false,
          filename: null,
        }),
        credentials: "include",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        setExtractResult({
          status: "error",
          started: true,
          mode: "batch",
          limit: null,
          force: false,
          dry_run: false,
          filename: null,
          summary: {
            found_candidates: 0,
            processed: 0,
            success: 0,
            skipped: 0,
            failed: 0,
          },
          items: [],
          error_summary: {},
          error: (data as { error?: string }).error ?? "Ошибка запуска извлечения",
        } as ExtractResponse & { error?: string });
      } else {
        setExtractResult(data as ExtractResponse);
        await queryClient.invalidateQueries({ queryKey: ["logistics-requests"] });
      }
    } catch (err) {
      setExtractResult({
        status: "error",
        started: true,
        mode: "batch",
        limit: null,
        force: false,
        dry_run: false,
        filename: null,
        summary: {
          found_candidates: 0,
          processed: 0,
          success: 0,
          skipped: 0,
          failed: 0,
        },
        items: [],
        error_summary: {},
        error: err instanceof Error ? err.message : "Ошибка сети",
      } as ExtractResponse & { error?: string });
    } finally {
      setExtractLoading(false);
    }
  }, [queryClient]);

  const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE));

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between mb-4">
        <h2 className="text-lg font-semibold">Логистические заявки</h2>
        <Button
          variant="outline"
          size="sm"
          disabled={extractLoading}
          onClick={runExtract}
          className="gap-2"
        >
          {extractLoading ? (
            <>
              <Loader2 className="h-4 w-4 animate-spin" />
              Идёт извлечение…
            </>
          ) : (
            <>
              <FileSearch className="h-4 w-4" />
              Извлечь заявки из базы знаний
            </>
          )}
        </Button>
      </div>

      {/* Фильтры */}
      <div className="flex flex-wrap gap-3 mb-4 p-3 rounded-lg bg-muted/50 border">
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Поиск</Label>
          <Input
            placeholder="№ заявки, заказчик, перевозчик, груз..."
            value={searchQuery}
            onChange={(e) => setSearchQuery(e.target.value)}
            className="w-64 h-8 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Откуда</Label>
          <Input
            placeholder="Маршрут от"
            value={routeFrom}
            onChange={(e) => setRouteFrom(e.target.value)}
            className="w-40 h-8 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Куда</Label>
          <Input
            placeholder="Маршрут до"
            value={routeTo}
            onChange={(e) => setRouteTo(e.target.value)}
            className="w-40 h-8 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Заказчик</Label>
          <Input
            placeholder="Заказчик"
            value={customer}
            onChange={(e) => setCustomer(e.target.value)}
            className="w-40 h-8 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Перевозчик</Label>
          <Input
            placeholder="Перевозчик"
            value={carrier}
            onChange={(e) => setCarrier(e.target.value)}
            className="w-40 h-8 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Температура</Label>
          <Input
            placeholder="Температура"
            value={temperature}
            onChange={(e) => setTemperature(e.target.value)}
            className="w-28 h-8 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">НДС</Label>
          <select
            value={vatIncluded === null ? "" : vatIncluded ? "yes" : "no"}
            onChange={(e) => {
              const v = e.target.value;
              setVatIncluded(v === "" ? null : v === "yes");
            }}
            className="h-8 w-32 rounded-md border border-input bg-background px-2 text-sm"
          >
            <option value="">Все</option>
            <option value="yes">с НДС</option>
            <option value="no">без НДС</option>
          </select>
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Дата от</Label>
          <Input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="w-36 h-8 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Дата до</Label>
          <Input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="w-36 h-8 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Цена от</Label>
          <Input
            type="number"
            placeholder="₽"
            value={priceFrom}
            onChange={(e) => setPriceFrom(e.target.value)}
            className="w-28 h-8 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Цена до</Label>
          <Input
            type="number"
            placeholder="₽"
            value={priceTo}
            onChange={(e) => setPriceTo(e.target.value)}
            className="w-28 h-8 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Вес от (кг)</Label>
          <Input
            type="number"
            value={weightFrom}
            onChange={(e) => setWeightFrom(e.target.value)}
            className="w-24 h-8 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Вес до (кг)</Label>
          <Input
            type="number"
            value={weightTo}
            onChange={(e) => setWeightTo(e.target.value)}
            className="w-24 h-8 text-sm"
          />
        </div>
        <div className="flex flex-col gap-1">
          <Label className="text-xs">Сортировка</Label>
          <div className="flex gap-1">
            <select
              value={sortField}
              onChange={(e) => setSortField(e.target.value)}
              className="h-8 rounded-md border border-input bg-background px-2 text-sm"
            >
              {SORT_FIELDS.map((s) => (
                <option key={s.value} value={s.value}>
                  {s.label}
                </option>
              ))}
            </select>
            <select
              value={sortOrder}
              onChange={(e) => setSortOrder(e.target.value as "asc" | "desc")}
              className="h-8 rounded-md border border-input bg-background px-2 text-sm"
            >
              <option value="desc">Сначала новые</option>
              <option value="asc">Сначала старые</option>
            </select>
          </div>
        </div>
      </div>

      {/* Аналитика (summary) */}
      {aggregations != null && (
        <div className="grid grid-cols-2 sm:grid-cols-5 gap-3 mb-4">
          <Card className="bg-card">
            <CardHeader className="p-3 pb-0">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Всего заявок
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-1">
              <span className="text-lg font-semibold">{aggregations.total}</span>
            </CardContent>
          </Card>
          <Card className="bg-card">
            <CardHeader className="p-3 pb-0">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Средняя цена
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-1">
              <span className="text-lg font-semibold">
                {aggregations.avg_price != null
                  ? `${aggregations.avg_price.toLocaleString("ru-RU", { maximumFractionDigits: 0 })} ₽`
                  : EMPTY}
              </span>
            </CardContent>
          </Card>
          <Card className="bg-card">
            <CardHeader className="p-3 pb-0">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Средний вес
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-1">
              <span className="text-lg font-semibold">
                {aggregations.avg_weight_kg != null
                  ? formatWeightKg(aggregations.avg_weight_kg)
                  : EMPTY}
              </span>
            </CardContent>
          </Card>
          <Card className="bg-card">
            <CardHeader className="p-3 pb-0">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Уник. перевозчиков
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-1">
              <span className="text-lg font-semibold">
                {aggregations.unique_carriers}
              </span>
            </CardContent>
          </Card>
          <Card className="bg-card">
            <CardHeader className="p-3 pb-0">
              <CardTitle className="text-xs font-medium text-muted-foreground">
                Уник. маршрутов
              </CardTitle>
            </CardHeader>
            <CardContent className="p-3 pt-1">
              <span className="text-lg font-semibold">
                {aggregations.unique_routes}
              </span>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Таблица */}
      <div className="flex-1 min-h-0 rounded-lg border overflow-hidden">
        <AgGridReact<LogisticsRequest>
          className="w-full h-full"
          columnDefs={columnDefs}
          defaultColDef={defaultColDef}
          rowData={items}
          getRowId={(params: GetRowIdParams<LogisticsRequest>) =>
            params.data?.document_id ?? params.data?.request_number ?? params.data?.original_filename ?? ''
          }
          onRowClicked={onRowClicked}
          loading={isFetching}
          theme={themeQuartz.withParams({ browserColorScheme: "inherit" })}
          domLayout="normal"
          rowSelection={undefined}
          suppressRowClickSelection
          noRowsOverlayComponent={() => (
            <div className="text-center py-8 text-muted-foreground">
              Нет заявок
            </div>
          )}
        />
      </div>

      {/* Пагинация */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-3 text-sm">
          <span className="text-muted-foreground">
            Всего: {total} • Страница {page} из {totalPages}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={page <= 1}
              onClick={() => setPage((p) => Math.max(1, p - 1))}
            >
              Назад
            </Button>
            <Button
              variant="outline"
              size="sm"
              disabled={page >= totalPages}
              onClick={() => setPage((p) => p + 1)}
            >
              Вперёд
            </Button>
          </div>
        </div>
      )}

      {/* Диалог результата извлечения */}
      <Dialog
        open={!!extractResult}
        onOpenChange={(open) => !open && setExtractResult(null)}
      >
        <DialogContent className="max-w-2xl max-h-[85vh] flex flex-col">
          <DialogHeader>
            <DialogTitle>
              {extractResult?.error
                ? "Ошибка извлечения"
                : "Результат извлечения заявок"}
            </DialogTitle>
          </DialogHeader>
          {extractResult?.error ? (
            <p className="text-sm text-destructive">{extractResult.error}</p>
          ) : extractResult ? (
            <div className="flex flex-col gap-4 overflow-hidden">
              <div className="grid grid-cols-2 sm:grid-cols-5 gap-2 text-sm">
                <div className="rounded bg-muted/50 p-2">
                  <span className="text-muted-foreground">Найдено кандидатов</span>
                  <p className="font-semibold">{extractResult.summary.found_candidates}</p>
                </div>
                <div className="rounded bg-muted/50 p-2">
                  <span className="text-muted-foreground">Обработано</span>
                  <p className="font-semibold">{extractResult.summary.processed}</p>
                </div>
                <div className="rounded bg-green-500/10 p-2">
                  <span className="text-muted-foreground">Успешно</span>
                  <p className="font-semibold text-green-600 dark:text-green-400">
                    {extractResult.summary.success}
                  </p>
                </div>
                <div className="rounded bg-muted/50 p-2">
                  <span className="text-muted-foreground">Пропущено</span>
                  <p className="font-semibold">{extractResult.summary.skipped}</p>
                </div>
                <div className="rounded bg-destructive/10 p-2">
                  <span className="text-muted-foreground">Ошибки</span>
                  <p className="font-semibold text-destructive">
                    {extractResult.summary.failed}
                  </p>
                </div>
              </div>
              {extractResult.summary.found_candidates > 0 && (
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-2 rounded-full bg-muted overflow-hidden">
                    <div
                      className="h-full bg-primary transition-all"
                      style={{
                        width: `${Math.round(
                          (extractResult.summary.processed /
                            extractResult.summary.found_candidates) *
                            100
                        )}%`,
                      }}
                    />
                  </div>
                  <span className="text-xs text-muted-foreground whitespace-nowrap">
                    Обработано {extractResult.summary.processed} из{" "}
                    {extractResult.summary.found_candidates} (
                    {Math.round(
                      (extractResult.summary.processed /
                        extractResult.summary.found_candidates) *
                        100
                    )}
                    %)
                  </span>
                </div>
              )}
              {extractResult.error_summary &&
                Object.keys(extractResult.error_summary).length > 0 && (
                  <div className="rounded border p-3 space-y-2">
                    <h4 className="text-sm font-medium">Подробнее об ошибках</h4>
                    <ul className="space-y-1.5 text-sm">
                      {Object.entries(extractResult.error_summary).map(
                        ([cat, count]) => (
                          <li key={cat} className="flex flex-col gap-0.5">
                            <span className="font-medium">
                              {EXTRACT_ERROR_LABELS[cat] ?? cat}: {count}
                            </span>
                            <span className="text-muted-foreground text-xs">
                              {EXTRACT_ERROR_HINTS[cat] ?? "—"}
                            </span>
                          </li>
                        )
                      )}
                    </ul>
                  </div>
                )}
              {extractResult.dry_run && (
                <p className="text-xs text-muted-foreground">
                  Режим «без записи» (dry run) — в индекс ничего не записано.
                </p>
              )}
              {extractResult.items.filter((i) => i.status === "failed").length >
                0 && (
                <div className="flex-1 min-h-0 overflow-auto">
                  <p className="text-xs text-muted-foreground mb-2">
                    По файлам (с ошибками):
                  </p>
                  <ul className="space-y-1 text-sm max-h-60 overflow-y-auto pr-2">
                    {extractResult.items
                      .filter((item) => item.status === "failed")
                      .map((item, i) => {
                        const fileUrl = `/api/logistics-requests/original-file?filename=${encodeURIComponent(item.filename)}`;
                        return (
                          <li
                            key={`${item.filename}-${i}`}
                            className="flex flex-col gap-0.5 py-1 border-b border-border/50 last:border-0"
                          >
                            <div className="flex justify-between gap-2">
                              <a
                                href={fileUrl}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="truncate cursor-pointer hover:underline text-primary"
                                title={item.filename}
                              >
                                {item.filename}
                              </a>
                              <span className="text-destructive shrink-0">
                                ошибка
                              </span>
                            </div>
                            {item.error_message &&
                              item.error_message.length > 0 && (
                                <span
                                  className="text-xs text-muted-foreground"
                                  title={item.error_message}
                                >
                                  {item.error_message}
                                </span>
                              )}
                          </li>
                        );
                      })}
                  </ul>
                </div>
              )}
            </div>
          ) : null}
        </DialogContent>
      </Dialog>

      {/* Drawer карточки заявки */}
      <Sheet
        open={!!selectedDocumentId}
        onOpenChange={(open) => !open && setSelectedDocumentId(null)}
      >
        <SheetContent side="right" className="w-full sm:max-w-lg overflow-y-auto">
          <SheetHeader>
            <SheetTitle>Заявка</SheetTitle>
          </SheetHeader>
          {detailLoading && <p className="text-sm text-muted-foreground">Загрузка…</p>}
          {detail && !detailLoading && (
            <div className="mt-4 space-y-6">
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">
                  Основная информация
                </h4>
                <ul className="text-sm space-y-1">
                  <li>Номер: {detail.request_number ?? EMPTY}</li>
                  <li>Дата: {formatRequestDate(detail.request_date)}</li>
                  <li>Файл: {detail.original_filename ?? EMPTY}</li>
                </ul>
              </div>
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">
                  Маршрут
                </h4>
                <ul className="text-sm space-y-1">
                  <li>Откуда: {detail.route_from ?? EMPTY}</li>
                  <li>Куда: {detail.route_to ?? EMPTY}</li>
                  <li>Адрес загрузки: {detail.loading_address ?? EMPTY}</li>
                  <li>Адрес разгрузки: {detail.unloading_address ?? EMPTY}</li>
                </ul>
              </div>
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">
                  Участники
                </h4>
                <ul className="text-sm space-y-1">
                  <li>Заказчик: {detail.customer ?? EMPTY}</li>
                  <li>Перевозчик: {detail.carrier ?? EMPTY}</li>
                  <li>
                    Ответственный заказчика:{" "}
                    {detail.customer_responsible_name ?? EMPTY}
                    {detail.customer_responsible_phone
                      ? ` (${detail.customer_responsible_phone})`
                      : ""}
                  </li>
                  <li>
                    Ответственный исполнителя:{" "}
                    {detail.carrier_responsible_name ?? EMPTY}
                    {detail.carrier_responsible_phone
                      ? ` (${detail.carrier_responsible_phone})`
                      : ""}
                  </li>
                </ul>
              </div>
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">
                  Груз
                </h4>
                <ul className="text-sm space-y-1">
                  <li>Наименование: {detail.cargo ?? EMPTY}</li>
                  <li>Вес: {formatWeightKg(detail.weight_kg)}</li>
                  <li>Температура: {detail.temperature ?? EMPTY}</li>
                </ul>
              </div>
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">
                  Транспорт
                </h4>
                <ul className="text-sm space-y-1">
                  <li>Машина: {detail.vehicle ?? EMPTY}</li>
                  <li>Водитель: {detail.driver_name ?? EMPTY}</li>
                  <li>Телефон: {detail.driver_phone ?? EMPTY}</li>
                </ul>
              </div>
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">
                  Коммерческие условия
                </h4>
                <ul className="text-sm space-y-1">
                  <li>Цена без НДС: {formatDisplayPrice(null, detail.price_without_vat)}</li>
                  <li>Цена с НДС: {formatDisplayPrice(detail.price_with_vat, null)}</li>
                  <li>НДС: {formatVatLabel(detail.vat_included)}</li>
                  <li>Условия оплаты: {detail.payment_terms ?? EMPTY}</li>
                </ul>
              </div>
              <div>
                <h4 className="text-sm font-medium text-muted-foreground mb-2">
                  Технические поля
                </h4>
                <ul className="text-sm space-y-1 text-muted-foreground">
                  <li>document_id: {detail.document_id ?? EMPTY}</li>
                  <li>processed_at: {detail.processed_at ?? EMPTY}</li>
                </ul>
              </div>
            </div>
          )}
        </SheetContent>
      </Sheet>
    </div>
  );
}

export default function LogisticsRequestsPage() {
  return (
    <ProtectedRoute>
      <LogisticsRequestsPageContent />
    </ProtectedRoute>
  );
}
