export type ID = number | string;
export interface Region { id: ID; label: string; latitude: number; longitude: number; radius_miles: number; precision?: string; source_url?: string }
export interface Location { label: string; latitude: number; longitude: number; precision: string; source_url?: string }
export interface Endpoint { id: ID; store_id?: ID; store_name?: string; provider: string; url?: string; license_type: string; status: string; last_attempt_at?: string; last_success_at?: string; latest_attempt_result?: string; error?: string; last_error?: string; product_count?: number }
export interface Dispensary { id: ID; name: string; address: string; city: string; state: string; latitude: number | null; longitude: number | null; distance_miles: number | null; serves_medical: boolean; menu_status: string; resolution?: {message?:string;status?:string}; product_count: number; endpoints: Endpoint[] }
export interface Offer { id: ID; endpoint_id: ID; store_id: ID; store_name: string; license_type: string; name: string; brand?: string; category: string; source_category?: string; strain_type?: string; thc_pct?: string; weight_grams: string | null; weight_label?: string; regular_price: string | null; effective_price: string | null; price_per_gram: string | null; conditional: boolean; available: boolean | null; status: string; last_diff_action?: string; last_seen_at?: string; source_url?: string; freshness: string; distance_miles?: number; exclusion_reason?: string; exclusion_reasons?: string[] }
export interface Page<T> { items: T[]; total: number; page: number; page_size: number; data_version?: string }
export interface MenuPage extends Page<Offer> { snapshot: { id: ID; status: string; observed_at: string; source_count: number; expected_count: number | null; errors: unknown[] } | null; total_products?: number; total_variants?: number; eligible_offers?: number; menu: Endpoint }
export interface Coverage { region: Region | null; source: { status: string; last_success_at?: string; published_at?: string; row_count?: number; error?: string }; counts: { known_stores: number; menu_endpoints: number; fresh_menus: number; stale_menus: number; failed_menus: number; unsupported_menus: number; unresolved_menus: number; products: number; eligible_offers: number; [key: string]: number }; territory: { supported_jurisdictions: string[]; unsupported_jurisdictions: string[]; status: string; message?: string }; limitations: string[]; endpoints: Endpoint[] }
export interface Run { payload?: { pipeline_version?: string }; id: ID; status: string; started_at?: string; finished_at?: string; results: unknown[]; error?: string; status_url?: string }
export interface Schedule { frequency_per_day: number; timezone: string; slots: string[]; next_run_at: string | null }
export interface Diff { id: ID; action: string; store_name: string; license_type: string; name: string; old_price: string | null; new_price: string | null; created_at: string; details: unknown }
export class ApiError extends Error { constructor(public code: string, message: string, public status: number) { super(message); } }
export async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api/v1${path}`, { ...init, headers: { 'Content-Type': 'application/json', ...init?.headers } });
  if (!response.ok) {
    let detail: unknown;
    try { detail = (await response.json()).detail; } catch { /* Non-JSON gateway failure */ }
    const structured = detail && typeof detail === 'object' && !Array.isArray(detail) ? detail as Record<string, unknown> : null;
    throw new ApiError(String(structured?.code ?? `http_${response.status}`), String(structured?.message ?? (typeof detail === 'string' ? detail : `Request failed (${response.status})`)), response.status);
  }
  return response.json() as Promise<T>;
}
export function params(values: Record<string, string | number | boolean | undefined>): string {
  const query = new URLSearchParams();
  Object.entries(values).forEach(([key, value]) => { if (value !== undefined && value !== '') query.set(key, String(value)); });
  return query.toString();
}
export const money = (value: string | number | null | undefined) => value == null || value === '' ? '—' : new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value));
export const date = (value: string | null | undefined) => value ? /^\d{4}-\d{2}-\d{2}$/.test(value) ? value : new Date(value).toLocaleString() : 'Never';
export const safeUrl = (value?: string) => { try { const url = new URL(value ?? ''); return ['https:', 'http:'].includes(url.protocol) ? url.href : undefined; } catch { return undefined; } };

