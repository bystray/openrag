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
