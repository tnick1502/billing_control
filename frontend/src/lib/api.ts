const API_BASE = '/api';

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  });
  if (!res.ok) {
    const err = await res.json().catch(() => ({ detail: res.statusText }));
    throw new Error(err.detail || JSON.stringify(err));
  }
  if (res.status === 204) return undefined as T;
  return res.json();
}

export const api = {
  devices: {
    list: () => fetchApi<Device[]>('/devices'),
    get: (id: number) => fetchApi<Device>(`/devices/${id}`),
    create: (data: DeviceCreate) => fetchApi<Device>('/devices', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: Partial<DeviceCreate>) => fetchApi<Device>(`/devices/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: number) => fetchApi<void>(`/devices/${id}`, { method: 'DELETE' }),
    aliases: {
      list: (deviceId: number) => fetchApi<DeviceAlias[]>(`/devices/${deviceId}/aliases`),
      create: (deviceId: number, data: { alias_name: string }) => fetchApi<DeviceAlias>(`/devices/${deviceId}/aliases`, { method: 'POST', body: JSON.stringify(data) }),
      delete: (deviceId: number, aliasId: number) => fetchApi<void>(`/devices/${deviceId}/aliases/${aliasId}`, { method: 'DELETE' }),
    },
  },
  parts: {
    list: () => fetchApi<Part[]>('/parts'),
    get: (id: number) => fetchApi<Part>(`/parts/${id}`),
    create: (data: PartCreate) => fetchApi<Part>('/parts', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: Partial<PartCreate>) => fetchApi<Part>(`/parts/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
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
    generate: (data: { month: string; order_status?: string }) => fetchApi<MonthlyPlan>('/monthly-plans/generate', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: Partial<MonthlyPlanCreate>) => fetchApi<MonthlyPlan>(`/monthly-plans/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: number) => fetchApi<void>(`/monthly-plans/${id}`, { method: 'DELETE' }),
    devices: (planId: number) => fetchApi<MonthlyPlanDevice[]>(`/monthly-plans/${planId}/devices`),
    parts: (planId: number) => fetchApi<MonthlyPlanPart[]>(`/monthly-plans/${planId}/parts`),
  },
  invoices: {
    list: () => fetchApi<Invoice[]>('/invoices'),
    get: (id: number) => fetchApi<Invoice>(`/invoices/${id}`),
    create: (data: InvoiceCreate) => fetchApi<Invoice>('/invoices', { method: 'POST', body: JSON.stringify(data) }),
    update: (id: number, data: Partial<InvoiceCreate>) => fetchApi<Invoice>(`/invoices/${id}`, { method: 'PATCH', body: JSON.stringify(data) }),
    delete: (id: number) => fetchApi<void>(`/invoices/${id}`, { method: 'DELETE' }),
    upload: async (id: number, file: File) => {
      const fd = new FormData();
      fd.append('file', file);
      const res = await fetch(`${API_BASE}/invoices/${id}/upload`, { method: 'POST', body: fd });
      if (!res.ok) throw new Error(await res.text());
      return res.json();
    },
    parts: {
      list: (invoiceId: number) => fetchApi<InvoicePartLink[]>(`/invoices/${invoiceId}/parts`),
      create: (invoiceId: number, data: InvoicePartLinkCreate) => fetchApi<InvoicePartLink>(`/invoices/${invoiceId}/parts`, { method: 'POST', body: JSON.stringify(data) }),
      update: (invoiceId: number, linkId: number, data: Partial<InvoicePartLinkCreate>) => fetchApi<InvoicePartLink>(`/invoices/${invoiceId}/parts/${linkId}`, { method: 'PATCH', body: JSON.stringify(data) }),
      delete: (invoiceId: number, linkId: number) => fetchApi<void>(`/invoices/${invoiceId}/parts/${linkId}`, { method: 'DELETE' }),
    },
  },
  files: {
    presignedUrl: (fileId: number) => fetchApi<{ url: string }>(`/files/${fileId}/presigned-url`),
  } as { presignedUrl: (fileId: number) => Promise<{ url: string }> },
};

export interface Device {
  id: number;
  sku: string;
  primary_name: string;
  model: string | null;
  is_active: boolean;
  created_at: string;
}
export interface DeviceCreate {
  sku: string;
  primary_name: string;
  model?: string | null;
  is_active?: boolean;
}
export interface DeviceAlias {
  id: number;
  device_id: number;
  alias_name: string;
  created_at: string;
}

export interface Part {
  id: number;
  sku: string;
  name: string;
  uom: string;
  is_active: boolean;
  created_at: string;
}
export interface PartCreate {
  sku: string;
  name: string;
  uom: string;
  is_active?: boolean;
}

export interface Order {
  id: number;
  order_no: string;
  status: string;
  order_date: string;
  created_at: string;
}
export interface OrderCreate {
  order_no: string;
  status?: string;
  order_date: string;
}
export interface OrderItem {
  id: number;
  order_id: number;
  device_id: number;
  qty: string;
  price: string | null;
  note: string | null;
}
export interface OrderItemCreate {
  device_id: number;
  qty: string;
  price?: string | null;
  note?: string | null;
}

export interface BomVersion {
  id: number;
  device_id: number;
  version: number;
  status: string;
  valid_from: string;
  valid_to: string | null;
  created_at: string;
}
export interface BomVersionCreate {
  version: number;
  status?: string;
}
export interface BomItem {
  id: number;
  bom_version_id: number;
  part_id: number;
  qty_per_device: string;
  scrap_rate: string | null;
  note: string | null;
}
export interface BomItemCreate {
  part_id: number;
  qty_per_device: string;
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
  qty_buffered: string | null;
  qty_final: string;
  created_at: string;
}

export interface Invoice {
  id: number;
  invoice_no: string;
  invoice_date: string;
  currency: string;
  total_amount: string | null;
  status: string;
  note: string | null;
  created_at: string;
}
export interface InvoiceCreate {
  invoice_no: string;
  invoice_date: string;
  currency?: string;
  total_amount?: string | null;
  status?: string;
  note?: string | null;
}
export interface InvoicePartLink {
  id: number;
  invoice_id: number;
  plan_id: number;
  part_id: number;
  qty_covered: string | null;
  amount_allocated: string | null;
  note: string | null;
  created_at: string;
}
export interface InvoicePartLinkCreate {
  plan_id: number;
  part_id: number;
  qty_covered?: string | null;
  amount_allocated?: string | null;
  note?: string | null;
}
