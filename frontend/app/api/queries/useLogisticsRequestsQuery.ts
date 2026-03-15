import { useQuery, type UseQueryOptions } from "@tanstack/react-query";
import type {
  LogisticsListParams,
  LogisticsListResponse,
} from "@/app/logistics-requests/types";

async function fetchLogisticsRequests(
  params: LogisticsListParams,
): Promise<LogisticsListResponse> {
  const response = await fetch("/api/logistics-requests", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      searchQuery: params.searchQuery ?? undefined,
      routeFrom: params.routeFrom ?? undefined,
      routeTo: params.routeTo ?? undefined,
      customer: params.customer ?? undefined,
      carrier: params.carrier ?? undefined,
      temperature: params.temperature ?? undefined,
      vatIncluded: params.vatIncluded ?? undefined,
      dateFrom: params.dateFrom ?? undefined,
      dateTo: params.dateTo ?? undefined,
      priceFrom: params.priceFrom ?? undefined,
      priceTo: params.priceTo ?? undefined,
      weightFrom: params.weightFrom ?? undefined,
      weightTo: params.weightTo ?? undefined,
      page: params.page ?? 1,
      size: params.size ?? 25,
      sortField: params.sortField ?? "request_date",
      sortOrder: params.sortOrder ?? "desc",
      includeAggregations: params.includeAggregations ?? true,
    }),
    credentials: "include",
  });
  if (!response.ok) {
    const err = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(err.error || "Ошибка загрузки заявок");
  }
  return response.json();
}

export function useLogisticsRequestsQuery(
  params: LogisticsListParams,
  options?: Omit<UseQueryOptions<LogisticsListResponse>, "queryKey" | "queryFn">,
) {
  return useQuery({
    queryKey: ["logistics-requests", params],
    queryFn: () => fetchLogisticsRequests(params),
    ...options,
  });
}
