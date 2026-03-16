/** Модель одной логистической заявки из индекса logistics_requests_structured */
export interface LogisticsRequest {
  document_id?: string;
  original_filename?: string;
  is_logistics_request?: boolean;
  request_number?: string;
  request_date?: string;
  route_from?: string;
  route_to?: string;
  loading_address?: string;
  unloading_address?: string;
  customer?: string;
  carrier?: string;
  cargo?: string;
  weight_kg?: number | null;
  temperature?: string | null;
  vehicle?: string | null;
  driver_name?: string | null;
  driver_phone?: string | null;
  price_without_vat?: number | null;
  price_with_vat?: number | null;
  vat_included?: boolean | null;
  vat_rate?: number | string | null;
  payment_terms?: string | null;
  processed_at?: string | null;
}

export interface LogisticsListParams {
  searchQuery?: string;
  routeFrom?: string;
  routeTo?: string;
  customer?: string;
  carrier?: string;
  temperature?: string;
  vatIncluded?: boolean | null;
  dateFrom?: string;
  dateTo?: string;
  priceFrom?: number;
  priceTo?: number;
  weightFrom?: number;
  weightTo?: number;
  page?: number;
  size?: number;
  sortField?: string;
  sortOrder?: string;
  includeAggregations?: boolean;
}

export interface LogisticsListResponse {
  items: LogisticsRequest[];
  total: number;
  page: number;
  size: number;
  aggregations?: LogisticsAggregations;
}

export interface LogisticsAggregations {
  total: number;
  avg_price: number | null;
  avg_weight_kg: number | null;
  unique_carriers: number;
  unique_routes: number;
}

/** Параметры запроса извлечения заявок из базы знаний */
export interface ExtractParams {
  limit?: number | null;
  force?: boolean;
  dry_run?: boolean;
  filename?: string | null;
}

/** Категории ошибок при извлечении */
export type ExtractErrorCategory =
  | "already_processed"
  | "opensearch_error"
  | "parsing_error"
  | "validation_error"
  | "config_error"
  | "unknown_error";

/** Итог по одному файлу в ответе extract */
export interface ExtractItem {
  filename: string;
  status: "success" | "skipped" | "failed";
  error_category?: ExtractErrorCategory;
  error_message?: string;
}

/** Ответ API POST /logistics-requests/extract */
export interface ExtractResponse {
  status: string;
  started: boolean;
  mode: "single" | "batch";
  limit: number | null;
  force: boolean;
  dry_run: boolean;
  filename: string | null;
  summary: {
    found_candidates: number;
    processed: number;
    success: number;
    skipped: number;
    failed: number;
  };
  items: ExtractItem[];
  error_summary?: Record<string, number>;
}

/** Подсказки по категориям ошибок для пользователя */
export const EXTRACT_ERROR_HINTS: Record<string, string> = {
  already_processed:
    "Файл уже был ранее успешно извлечён. Используйте опцию «Переобработать» для повторной обработки.",
  opensearch_error:
    "Проверьте доступность OpenSearch и права роли openrag_user_role.",
  parsing_error:
    "Проверьте формат заявок и промпт LLM. Возможно, текст документа пуст или LLM не вернул валидный JSON.",
  validation_error:
    "Проверьте обязательные поля (маршрут/адреса, заказчик/перевозчик, цена или вес).",
  config_error:
    "Проверьте настройки LANGFLOW_LOGISTICS_EXTRACT_FLOW_ID и ключи API.",
};

/** Человекочитаемые названия категорий ошибок */
export const EXTRACT_ERROR_LABELS: Record<string, string> = {
  already_processed: "Уже обработан",
  opensearch_error: "Ошибка OpenSearch",
  parsing_error: "Ошибка парсинга",
  validation_error: "Ошибка валидации",
  config_error: "Ошибка конфигурации",
  unknown_error: "Неизвестная ошибка",
};
