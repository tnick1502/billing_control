const API_BASE = '/api';
const AUTH_TOKEN_KEY = 'billing_control_auth_token';

export function getAuthToken() {
  if (typeof localStorage === 'undefined') return '';
  return localStorage.getItem(AUTH_TOKEN_KEY) ?? '';
}

export function setAuthToken(token: string) {
  if (typeof localStorage !== 'undefined') localStorage.setItem(AUTH_TOKEN_KEY, token);
}

export function clearAuthToken() {
  if (typeof localStorage !== 'undefined') localStorage.removeItem(AUTH_TOKEN_KEY);
}

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getAuthToken();
  const hasBody = options?.body != null && options.body !== '';
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      ...(hasBody ? { 'Content-Type': 'application/json' } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    const d = err.detail;
    const msg =
      typeof d === 'string'
        ? d
        : Array.isArray(d)
          ? d.map((x: { msg?: string }) => x?.msg).filter(Boolean).join('; ') || JSON.stringify(d)
          : d != null
            ? JSON.stringify(d)
            : res.statusText;
    throw new Error(msg || 'Ошибка запроса');
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

function filenameFromResponse(res: Response, fallback: string): string {
  const cd = res.headers.get('content-disposition') ?? '';
  const m = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(cd);
  return m ? decodeURIComponent(m[1]) : fallback;
}

function parseApiError(res: Response, bodyText: string): Error {
  try {
    const err = JSON.parse(bodyText) as { detail?: unknown };
    const d = err.detail;
    const msg =
      typeof d === 'string'
        ? d
        : Array.isArray(d)
          ? d.map((x: { msg?: string }) => x?.msg).filter(Boolean).join('; ') || bodyText
          : d != null
            ? JSON.stringify(d)
            : res.statusText;
    return new Error(msg || 'Ошибка запроса');
  } catch {
    return new Error(bodyText || res.statusText || 'Ошибка запроса');
  }
}

export const api = {
  auth: {
    login: async (data: UserLogin) => {
      /** Без Authorization: после выхода старый токен не должен уходить на /auth/login (иначе возможны зависания прокси). */
      const controller = new AbortController();
      const timeoutId = setTimeout(() => controller.abort(), 20000);
      try {
        const res = await fetch(`${API_BASE}/auth/login`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(data),
          signal: controller.signal,
        });
        const raw = await res.text();
        if (!res.ok) {
          throw parseApiError(res, raw);
        }
        const result = JSON.parse(raw) as AuthToken;
        setAuthToken(result.token);
        return result;
      } catch (e) {
        if (e instanceof Error && e.name === 'AbortError') {
          throw new Error('Превышено время ожидания входа');
        }
        throw e;
      } finally {
        clearTimeout(timeoutId);
      }
    },
    me: () => fetchApi<User>('/auth/me'),
    logout: async () => {
      const token = getAuthToken();
      try {
        if (token) {
          const controller = new AbortController();
          const timeoutId = setTimeout(() => controller.abort(), 8000);
          try {
            const res = await fetch(`${API_BASE}/auth/logout`, {
              method: 'POST',
              headers: { Authorization: `Bearer ${token}` },
              signal: controller.signal,
            });
            if (!res.ok) {
              const t = await res.text().catch(() => '');
              throw new Error(t || res.statusText);
            }
          } finally {
            clearTimeout(timeoutId);
          }
        }
      } finally {
        clearAuthToken();
      }
    },
  },
  admin: {
    users: {
      list: () => fetchApi<User[]>('/admin/users'),
      create: (data: UserCreate) => fetchApi<User>('/admin/users', { method: 'POST', body: JSON.stringify(data) }),
      update: (id: number, data: Partial<UserCreate>) => fetchApi<User>(`/admin/users/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
      delete: (id: number) => fetchApi<void>(`/admin/users/${id}`, { method: 'DELETE' }),
    },
    auditLogs: (limit = 200) => fetchApi<AuditLog[]>(`/admin/audit-logs?${new URLSearchParams({ limit: String(limit) })}`),
  },
  devices: {
    list: (includeArchived = false) => fetchApi<Device[]>(`/devices${includeArchived ? '?include_archived=true' : ''}`),
    get: (id: number) => fetchApi<Device>(`/devices/${id}`),
    create: (data: DeviceCreate) => fetchApi<Device>('/devices', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: Partial<DeviceCreate>) => fetchApi<Device>(`/devices/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    archive: (id: number, is_archived: boolean) => fetchApi<Device>(`/devices/${id}/archive`, { method: 'PATCH', body: JSON.stringify({ is_archived }) }),
    delete: (id: number) => fetchApi<void>(`/devices/${id}`, { method: 'DELETE' }),
    aliases: {
      list: (deviceId: number) => fetchApi<DeviceAlias[]>(`/devices/${deviceId}/aliases`),
      create: (deviceId: number, data: { alias_name: string }) => fetchApi<DeviceAlias>(`/devices/${deviceId}/aliases`, { method: 'POST', body: JSON.stringify(data) }),
      delete: (deviceId: number, aliasId: number) => fetchApi<void>(`/devices/${deviceId}/aliases/${aliasId}`, { method: 'DELETE' }),
    },
  },
  parts: {
    list: (includeArchived = false) => fetchApi<Part[]>(`/parts${includeArchived ? '?include_archived=true' : ''}`),
    listTypes: () => fetchApi<string[]>('/parts/types'),
    get: (id: number) => fetchApi<Part>(`/parts/${id}`),
    create: (data: PartCreate) => fetchApi<Part>('/parts', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: Partial<PartCreate>) => fetchApi<Part>(`/parts/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    archive: (id: number, is_archived: boolean) => fetchApi<Part>(`/parts/${id}/archive`, { method: 'PATCH', body: JSON.stringify({ is_archived }) }),
    delete: (id: number) => fetchApi<void>(`/parts/${id}`, { method: 'DELETE' }),
  },
  orders: {
    list: () => fetchApi<Order[]>('/orders'),
    get: (id: number) => fetchApi<Order>(`/orders/${id}`),
    create: (data: OrderCreate) => fetchApi<Order>('/orders', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: Partial<OrderCreate>) => fetchApi<Order>(`/orders/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: number) => fetchApi<void>(`/orders/${id}`, { method: 'DELETE' }),
    items: {
      list: (orderId: number) => fetchApi<OrderItem[]>(`/orders/${orderId}/items`),
      create: (orderId: number, data: OrderItemCreate) => fetchApi<OrderItem>(`/orders/${orderId}/items`, { method: 'POST', body: JSON.stringify(data) }),
      update: (orderId: number, itemId: number, data: Partial<OrderItemCreate>) => fetchApi<OrderItem>(`/orders/${orderId}/items/${itemId}`, { method: 'PATCH', body: JSON.stringify(data) }),
      delete: (orderId: number, itemId: number) => fetchApi<void>(`/orders/${orderId}/items/${itemId}`, { method: 'DELETE' }),
    },
    partItems: {
      list: (orderId: number) => fetchApi<OrderPartItem[]>(`/orders/${orderId}/part-items`),
      create: (orderId: number, data: OrderPartItemCreate) => fetchApi<OrderPartItem>(`/orders/${orderId}/part-items`, { method: 'POST', body: JSON.stringify(data) }),
      update: (orderId: number, itemId: number, data: Partial<OrderPartItemCreate>) => fetchApi<OrderPartItem>(`/orders/${orderId}/part-items/${itemId}`, { method: 'PATCH', body: JSON.stringify(data) }),
      delete: (orderId: number, itemId: number) => fetchApi<void>(`/orders/${orderId}/part-items/${itemId}`, { method: 'DELETE' }),
    },
  },
  bom: {
    list: (deviceId: number) => fetchApi<BomVersion[]>(`/devices/${deviceId}/bom`),
    create: (deviceId: number, data: BomVersionCreate) => fetchApi<BomVersion>(`/devices/${deviceId}/bom`, { method: 'POST', body: JSON.stringify(data) }),
    get: (bomId: number) => fetchApi<BomVersion>(`/bom/${bomId}`),
    update: (bomId: number, data: Partial<BomVersionCreate>) => fetchApi<BomVersion>(`/bom/${bomId}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (bomId: number) => fetchApi<void>(`/bom/${bomId}`, { method: 'DELETE' }),
    items: {
      list: (bomId: number) => fetchApi<BomItem[]>(`/bom/${bomId}/items`),
      create: (bomId: number, data: BomItemCreate) => fetchApi<BomItem>(`/bom/${bomId}/items`, { method: 'POST', body: JSON.stringify(data) }),
      update: (bomId: number, itemId: number, data: Partial<BomItemCreate>) => fetchApi<BomItem>(`/bom/${bomId}/items/${itemId}`, { method: 'PATCH', body: JSON.stringify(data) }),
      delete: (bomId: number, itemId: number) => fetchApi<void>(`/bom/${bomId}/items/${itemId}`, { method: 'DELETE' }),
    },
  },
  monthlyPlans: {
    list: () => fetchApi<MonthlyPlan[]>('/monthly-plans'),
    get: (id: number) => fetchApi<MonthlyPlan>(`/monthly-plans/${id}`),
    create: (data: MonthlyPlanCreate) => fetchApi<MonthlyPlan>('/monthly-plans', { method: 'POST', body: JSON.stringify(data) }),
    generate: (data: { month: string; replace?: boolean }) => fetchApi<MonthlyPlan>('/monthly-plans/generate', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: Partial<MonthlyPlanCreate>) => fetchApi<MonthlyPlan>(`/monthly-plans/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: number) => fetchApi<void>(`/monthly-plans/${id}`, { method: 'DELETE' }),
    devices: (planId: number) => fetchApi<MonthlyPlanDevice[]>(`/monthly-plans/${planId}/devices`),
    parts: (planId: number) => fetchApi<MonthlyPlanPart[]>(`/monthly-plans/${planId}/parts`),
    partsWithCoverage: (planId: number) => fetchApi<MonthlyPlanPartWithCoverage[]>(`/monthly-plans/${planId}/parts-with-coverage`),
    updatePlanPartDelivered: (planId: number, planPartId: number, qty_delivered: string) =>
      fetchApi<MonthlyPlanPart>(`/monthly-plans/${planId}/parts/${planPartId}`, {
        method: 'PATCH',
        body: JSON.stringify({ qty_delivered }),
      }),
    partFiles: {
      list: (planId: number, planPartId: number) =>
        fetchApi<PlanPartFile[]>(`/monthly-plans/${planId}/parts/${planPartId}/files`),
      upload: async (planId: number, planPartId: number, files: FileList): Promise<PlanPartFile[]> => {
        const fd = new FormData();
        for (let i = 0; i < files.length; i++) {
          fd.append('files', files[i]);
        }
        const token = getAuthToken();
        const res = await fetch(`${API_BASE}/monthly-plans/${planId}/parts/${planPartId}/files`, {
          method: 'POST',
          body: fd,
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) throw parseApiError(res, await res.text());
        return res.json();
      },
      delete: (planId: number, planPartId: number, fileId: number) =>
        fetchApi<void>(`/monthly-plans/${planId}/parts/${planPartId}/files/${fileId}`, { method: 'DELETE' }),
    },
  },
  invoices: {
    list: () => fetchApi<Invoice[]>('/invoices'),
    get: (id: number) => fetchApi<Invoice>(`/invoices/${id}`),
    create: async (data: InvoiceCreate, file: File) => {
      const fd = new FormData();
      fd.append('invoice_no', data.invoice_no);
      fd.append('invoice_date', data.invoice_date);
      if (data.supplier != null && data.supplier !== '') fd.append('supplier', data.supplier);
      if (data.total_amount != null && data.total_amount !== '') fd.append('total_amount', String(data.total_amount));
      if (data.payment_date != null && data.payment_date !== '') fd.append('payment_date', data.payment_date);
      if (data.description != null && data.description !== '') fd.append('description', data.description);
      if (data.note != null && data.note !== '') fd.append('note', data.note);
      fd.append('file', file);
      const token = getAuthToken();
      const res = await fetch(`${API_BASE}/invoices`, {
        method: 'POST',
        body: fd,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw parseApiError(res, await res.text());
      return res.json() as Promise<Invoice>;
    },
    update: (id: number, data: Partial<InvoiceCreate>) => fetchApi<Invoice>(`/invoices/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: number) => fetchApi<void>(`/invoices/${id}`, { method: 'DELETE' }),
    files: (id: number) => fetchApi<InvoiceFileInfo[]>(`/invoices/${id}/files`),
    upload: async (id: number, file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      const token = getAuthToken();
      const res = await fetch(`${API_BASE}/invoices/${id}/upload`, {
        method: 'POST',
        body: fd,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw parseApiError(res, await res.text());
      return res.json();
    },
    parts: {
      list: (invoiceId: number) => fetchApi<InvoicePartLink[]>(`/invoices/${invoiceId}/parts`),
      create: (invoiceId: number, data: InvoicePartLinkCreate) => fetchApi<InvoicePartLink>(`/invoices/${invoiceId}/parts`, { method: 'POST', body: JSON.stringify(data) }),
      update: (invoiceId: number, linkId: number, data: Partial<InvoicePartLinkCreate>) => fetchApi<InvoicePartLink>(`/invoices/${invoiceId}/parts/${linkId}`, { method: 'PATCH', body: JSON.stringify(data) }),
      delete: (invoiceId: number, linkId: number) => fetchApi<void>(`/invoices/${invoiceId}/parts/${linkId}`, { method: 'DELETE' }),
    },
  },
  imports: {
    uploadBom: async (
      file: File,
      opts?: { dryRun?: boolean; updateExisting?: boolean }
    ): Promise<ImportResult> => {
      const q = new URLSearchParams();
      if (opts?.dryRun) q.set('dry_run', 'true');
      if (opts?.updateExisting) q.set('update_existing', 'true');
      const fd = new FormData();
      fd.append('file', file);
      const token = getAuthToken();
      const res = await fetch(`${API_BASE}/imports/bom?${q}`, {
        method: 'POST',
        body: fd,
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw parseApiError(res, await res.text());
      return res.json() as Promise<ImportResult>;
    },
    exportBom: async (): Promise<{ blob: Blob; filename: string }> => {
      const token = getAuthToken();
      const res = await fetch(`${API_BASE}/imports/bom/export`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw parseApiError(res, await res.text());
      return { blob: await res.blob(), filename: filenameFromResponse(res, 'billing_control_bom.json') };
    },
    dumpDb: async (): Promise<{ blob: Blob; filename: string }> => {
      const token = getAuthToken();
      const res = await fetch(`${API_BASE}/imports/db/dump`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw parseApiError(res, await res.text());
      return { blob: await res.blob(), filename: filenameFromResponse(res, 'billing_control_dump.sql') };
    },
  },
  files: {
    downloadBlob: async (fileId: number): Promise<Blob> => {
      const token = getAuthToken();
      const res = await fetch(`${API_BASE}/files/${fileId}/download`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {},
      });
      if (!res.ok) throw parseApiError(res, await res.text());
      return res.blob();
    },
  },
  stats: {
    ordersDevicesTimeseries: (dateFrom: string, dateTo: string) => {
      const q = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
      return fetchApi<StatsChartPayload>(`/stats/orders-devices-timeseries?${q}`);
    },
    ordersPartsMonthlyTimeseries: (dateFrom: string, dateTo: string) => {
      const q = new URLSearchParams({ date_from: dateFrom, date_to: dateTo });
      return fetchApi<StatsChartPayload>(`/stats/orders-parts-monthly-timeseries?${q}`);
    },
    ordersPartsTimeseries: (partId: number, dateFrom: string, dateTo: string) => {
      const q = new URLSearchParams({
        part_id: String(partId),
        date_from: dateFrom,
        date_to: dateTo,
      });
      return fetchApi<StatsPartChartPayload>(`/stats/orders-parts-timeseries?${q}`);
    },
  },
};

export interface User {
  id: number;
  username: string;
  full_name: string | null;
  role: 'admin' | 'employee';
  is_active: boolean;
  created_at: string;
  updated_at: string;
}
export interface UserLogin {
  username: string;
  password: string;
}
export interface UserCreate {
  username: string;
  password: string;
  full_name?: string | null;
  role: 'admin' | 'employee';
  is_active: boolean;
}
export interface AuthToken {
  token: string;
  user: User;
}
export interface AuditLog {
  id: number;
  user_id: number | null;
  username: string | null;
  role: string | null;
  action: string;
  method: string;
  path: string;
  status_code: number | null;
  details: string | null;
  created_at: string;
}

export interface StatsDataset {
  label: string;
  data: number[];
  borderColor?: string;
  backgroundColor?: string;
  device_id?: number;
  part_id?: number;
}
export interface StatsChartPayload {
  labels: string[];
  datasets: StatsDataset[];
}
export interface StatsPartChartPayload extends StatsChartPayload {
  part_id: number;
  part_name: string;
  date_from: string;
  date_to: string;
}

export interface Device {
  id: number;
  primary_name: string;
  model: string | null;
  description: string | null;
  is_archived: boolean;
  created_at: string;
}
export interface DeviceCreate {
  primary_name: string;
  model?: string | null;
  description?: string | null;
}
export interface DeviceAlias {
  id: number;
  device_id: number;
  alias_name: string;
  created_at: string;
}

export interface Part {
  id: number;
  name: string;
  cipher: string | null;
  article: string | null;
  part_type: string | null;
  description: string | null;
  is_archived: boolean;
  created_at: string;
}
export interface PartCreate {
  name: string;
  cipher?: string | null;
  article?: string | null;
  part_type?: string | null;
  description?: string | null;
}

export interface Order {
  id: number;
  order_date: string;
  customer: string | null;
  contract_no: string | null;
  description: string | null;
  created_at: string;
}
export interface OrderCreate {
  order_date: string;
  customer?: string | null;
  contract_no?: string | null;
  description?: string | null;
}
export interface BomVersionBrief {
  id: number;
  name: string | null;
  version: number;
}

export interface OrderItem {
  id: number;
  order_id: number;
  device_id: number;
  bom_version_id: number | null;
  bom_version: BomVersionBrief | null;
  qty: string;
  price: string | null;
  note: string | null;
}
export interface OrderPartItem {
  id: number;
  order_id: number;
  part_id: number;
  qty: string;
  price: string | null;
  note: string | null;
}
export interface OrderPartItemCreate {
  part_id: number;
  qty: string;
  price?: string | null;
  note?: string | null;
}
export interface OrderItemCreate {
  device_id: number;
  bom_version_id?: number | null;
  qty: string;
  price?: string | null;
  note?: string | null;
}

export interface BomVersion {
  id: number;
  device_id: number;
  name: string | null;
  description: string | null;
  version: number;
  status: string;
  valid_from: string;
  valid_to: string | null;
  created_at: string;
}
export interface BomVersionCreate {
  name?: string | null;
  description?: string | null;
  version: number;
  status?: string;
}
export interface BomItem {
  id: number;
  bom_version_id: number;
  part_id: number | null;
  sub_device_id: number | null;
  sub_bom_version_id: number | null;
  qty_per_device: number;
  scrap_rate: string | null;
  note: string | null;
  item_type: 'part' | 'sub_device';
}
export interface BomItemCreate {
  part_id?: number | null;
  sub_device_id?: number | null;
  sub_bom_version_id?: number | null;
  qty_per_device: number;
  scrap_rate?: string | null;
  note?: string | null;
}

export interface MonthlyPlan {
  id: number;
  month: string;
  revision: number;
  status: string;
  generated_at: string;
  generated_by: string | null;
  note: string | null;
}
export interface MonthlyPlanCreate {
  month: string;
  revision?: number;
  status?: string;
  note?: string | null;
}
export interface MonthlyPlanDevice {
  id: number;
  plan_id: number;
  device_id: number;
  qty_total: string;
  bom_version_id: number;
  created_at: string;
}
export interface MonthlyPlanPart {
  id: number;
  plan_id: number;
  part_id: number;
  qty_required: string;
  qty_final: string;
  /** После миграции БД всегда есть; до миграции может отсутствовать */
  qty_delivered?: string;
  created_at: string;
}
export interface PartInvoiceCoverage {
  link_id: number;
  invoice_id: number;
  invoice_no: string;
  supplier: string | null;
  payment_date: string | null;
  qty_covered: string | null;
}
export interface PlanPartFile {
  id: number;
  filename: string;
  content_type: string | null;
  size_bytes: number | null;
  uploaded_at: string;
}
export interface MonthlyPlanPartWithCoverage extends MonthlyPlanPart {
  has_invoice: boolean;
  invoices?: PartInvoiceCoverage[];
  qty_covered_total?: string;
  coverage_complete?: boolean;
  /** После обновления API; иначе считается по qty_delivered и qty_required */
  delivery_complete?: boolean;
  files?: PlanPartFile[];
}

export interface ImportResult {
  dry_run: boolean;
  parts_created: number;
  parts_reused: number;
  devices_created: number;
  devices_reused: number;
  boms_created: number;
  boms_updated: number;
  boms_skipped: number;
  items_created: number;
  items_skipped: number;
  warnings: string[];
}

export interface InvoiceFileInfo {
  id: number;
  filename: string;
  content_type: string | null;
  size_bytes: number | null;
  uploaded_at: string;
}
export interface Invoice {
  id: number;
  invoice_no: string;
  invoice_date: string;
  supplier: string | null;
  total_amount: string | null;
  payment_date: string | null;
  description: string | null;
  note: string | null;
  created_at: string;
}
export interface InvoiceCreate {
  invoice_no: string;
  invoice_date: string;
  supplier?: string | null;
  total_amount?: string | null;
  payment_date?: string | null;
  description?: string | null;
  note?: string | null;
}
export interface InvoicePartLink {
  id: number;
  invoice_id: number;
  plan_id: number;
  part_id: number;
  qty_covered: string | null;
  note: string | null;
  created_at: string;
}
export interface InvoicePartLinkCreate {
  plan_id: number;
  part_id: number;
  qty_covered?: string | null;
  note?: string | null;
}
