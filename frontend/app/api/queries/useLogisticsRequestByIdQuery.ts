import { useQuery, type UseQueryOptions } from "@tanstack/react-query";
import type { LogisticsRequest } from "@/app/logistics-requests/types";

async function fetchLogisticsRequestById(
  documentId: string,
): Promise<LogisticsRequest> {
  const response = await fetch(`/api/logistics-requests/${encodeURIComponent(documentId)}`, {
    method: "GET",
    credentials: "include",
  });
  if (!response.ok) {
    if (response.status === 404) {
      throw new Error("Заявка не найдена");
    }
    const err = await response.json().catch(() => ({ error: response.statusText }));
    throw new Error(err.error || "Ошибка загрузки заявки");
  }
  return response.json();
}

export function useLogisticsRequestByIdQuery(
  documentId: string | null,
  options?: Omit<UseQueryOptions<LogisticsRequest>, "queryKey" | "queryFn">,
) {
  return useQuery({
    queryKey: ["logistics-request", documentId],
    queryFn: () => fetchLogisticsRequestById(documentId!),
    enabled: !!documentId,
    ...options,
  });
}
