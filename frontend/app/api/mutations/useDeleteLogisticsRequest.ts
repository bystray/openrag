"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

const deleteLogisticsRequest = async (
  documentId: string,
): Promise<{ success: boolean; deleted: boolean }> => {
  const response = await fetch(
    `/api/logistics-requests/${encodeURIComponent(documentId)}`,
    { method: "DELETE", credentials: "include" },
  );

  if (!response.ok) {
    const err = await response.json().catch(() => ({}));
    throw new Error(err.detail || err.error || "Не удалось удалить заявку");
  }

  return response.json();
};

export const useDeleteLogisticsRequest = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: deleteLogisticsRequest,
    onSettled: () => {
      queryClient.invalidateQueries({ queryKey: ["logistics-requests"], exact: false });
      queryClient.invalidateQueries({ queryKey: ["logistics-request"], exact: false });
    },
  });
};
