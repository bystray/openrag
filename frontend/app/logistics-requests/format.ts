/** Пустое значение для отображения */
export const EMPTY = "—";

/** Дата в формате ДД.ММ.ГГГГ */
export function formatRequestDate(value: string | undefined | null): string {
  if (value == null || value === "") return EMPTY;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleDateString("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "numeric",
  });
}

/** Вес: кг или т (если >= 1000) */
export function formatWeightKg(kg: number | undefined | null): string {
  if (kg == null || typeof kg !== "number") return EMPTY;
  if (kg >= 1000) {
    return `${(kg / 1000).toLocaleString("ru-RU", { minimumFractionDigits: 0, maximumFractionDigits: 2 })} т`;
  }
  return `${kg.toLocaleString("ru-RU")} кг`;
}

/** Цена с разделителями и ₽ */
export function formatPrice(value: number | undefined | null): string {
  if (value == null || typeof value !== "number") return EMPTY;
  return `${value.toLocaleString("ru-RU", { minimumFractionDigits: 0, maximumFractionDigits: 2 })} ₽`;
}

/** НДС: с НДС / без НДС / не указано */
export function formatVatLabel(vatIncluded: boolean | undefined | null): string {
  if (vatIncluded === true) return "с НДС";
  if (vatIncluded === false) return "без НДС";
  return "не указано";
}

/** Маршрут "откуда → куда" */
export function formatRoute(routeFrom?: string | null, routeTo?: string | null): string {
  const from = (routeFrom ?? "").trim();
  const to = (routeTo ?? "").trim();
  if (!from && !to) return EMPTY;
  if (!from) return to;
  if (!to) return from;
  return `${from} → ${to}`;
}

/** Цена для отображения: приоритет price_with_vat, иначе price_without_vat */
export function getDisplayPrice(
  priceWithVat: number | undefined | null,
  priceWithoutVat: number | undefined | null,
): number | null {
  if (priceWithVat != null && typeof priceWithVat === "number") return priceWithVat;
  if (priceWithoutVat != null && typeof priceWithoutVat === "number") return priceWithoutVat;
  return null;
}

export function formatDisplayPrice(
  priceWithVat: number | undefined | null,
  priceWithoutVat: number | undefined | null,
): string {
  const p = getDisplayPrice(priceWithVat, priceWithoutVat);
  return formatPrice(p);
}
