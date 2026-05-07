<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import { formatQty, formatDate } from '$lib/format';
  import type { Order, OrderCreate, OrderItem, OrderItemCreate, OrderPartItem, OrderPartItemCreate, BomVersion } from '$lib/api';

  type CalendarDay = {
    date: string;
    day: number;
    inCurrentMonth: boolean;
    isToday: boolean;
    orders: Order[];
  };

  let orders: Order[] = [];
  let devices: { id: number; primary_name: string }[] = [];
  let parts: { id: number; name: string }[] = [];
  let loading = true;
  let modalOpen = false;
  let form: OrderCreate = { order_date: new Date().toISOString().slice(0, 10), customer: null, contract_no: null, description: null };
  let editingId: number | null = null;
  let selectedOrder: Order | null = null;
  let orderItems: OrderItem[] = [];
  let orderPartItems: OrderPartItem[] = [];
  let itemModalOpen = false;
  let itemForm: OrderItemCreate = { device_id: 0, bom_version_id: null, qty: '1', price: null, note: null };
  let bomsForDevice: BomVersion[] = [];
  let bomsByDevice: Map<number, BomVersion[]> = new Map();
  let editingItemId: number | null = null;
  let partItemModalOpen = false;
  let partItemForm: OrderPartItemCreate = { part_id: 0, qty: '1', price: null, note: null };
  let editingPartItemId: number | null = null;
  let calendarMonth = monthKey(new Date());
  let selectedDayDate: string | null = null;
  let viewMode: 'calendar' | 'list' = 'calendar';
  let orderSortDir: 'asc' | 'desc' = 'desc';
  let orderDateFrom = '';
  let orderDateTo = '';
  let orderCustomerFilter = '';
  let orderListPage = 1;
  let orderFormSnapshot = '';
  let orderSaveMessage = '';
  let orderSaveOk = true;

  const PAGE_SIZE = 50;
  const weekDays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

  $: calendarDays = buildCalendarDays(calendarMonth, orders);
  $: calendarMonthLabel = monthLabel(calendarMonth);
  $: selectedDayOrders = selectedDayDate ? ordersForDate(selectedDayDate) : [];
  $: filteredOrders = filterAndSortOrders(orders, orderDateFrom, orderDateTo, orderCustomerFilter, orderSortDir);
  $: orderTotalPages = Math.max(1, Math.ceil(filteredOrders.length / PAGE_SIZE));
  $: orderListPage = Math.min(Math.max(orderListPage, 1), orderTotalPages);
  $: pagedOrders = filteredOrders.slice((orderListPage - 1) * PAGE_SIZE, orderListPage * PAGE_SIZE);
  $: orderFormDirty = modalOpen && serializeOrderForm(form) !== orderFormSnapshot;

  onMount(load);

  function pad2(n: number) {
    return String(n).padStart(2, '0');
  }

  function isoDate(d: Date) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  }

  function monthKey(d: Date) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`;
  }

  function dateFromIso(date: string) {
    const [year, month, day] = date.split('-').map(Number);
    return new Date(year, month - 1, day);
  }

  function addMonths(month: string, delta: number) {
    const [year, monthNo] = month.split('-').map(Number);
    return monthKey(new Date(year, monthNo - 1 + delta, 1));
  }

  function monthLabel(month: string) {
    const [year, monthNo] = month.split('-').map(Number);
    return new Date(year, monthNo - 1, 1).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
  }

  function dayLabel(date: string) {
    return dateFromIso(date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
  }

  function ordersForDate(date: string) {
    return orders.filter((o) => o.order_date === date);
  }

  function buildCalendarDays(month: string, items: Order[]): CalendarDay[] {
    const [year, monthNo] = month.split('-').map(Number);
    const firstDay = new Date(year, monthNo - 1, 1);
    const mondayOffset = (firstDay.getDay() + 6) % 7;
    const start = new Date(year, monthNo - 1, 1 - mondayOffset);
    const today = isoDate(new Date());
    const byDate: Record<string, Order[]> = {};

    for (const order of items) {
      (byDate[order.order_date] ??= []).push(order);
    }

    return Array.from({ length: 42 }, (_, idx) => {
      const d = new Date(start);
      d.setDate(start.getDate() + idx);
      const date = isoDate(d);
      const dayOrders = [...(byDate[date] ?? [])].sort((a, b) => (a.id ?? 0) - (b.id ?? 0));

      return {
        date,
        day: d.getDate(),
        inCurrentMonth: d.getMonth() === monthNo - 1,
        isToday: date === today,
        orders: dayOrders,
      };
    });
  }

  function filterAndSortOrders(items: Order[], dateFrom: string, dateTo: string, customerFilter: string, sortDir: 'asc' | 'desc') {
    const customerNeedle = customerFilter.trim().toLowerCase();
    return [...items]
      .filter((order) => !dateFrom || order.order_date >= dateFrom)
      .filter((order) => !dateTo || order.order_date <= dateTo)
      .filter((order) => {
        if (!customerNeedle) return true;
        const haystack = `${order.customer ?? ''} ${order.contract_no ?? ''} ${order.description ?? ''} ${order.id ?? ''}`.toLowerCase();
        return haystack.includes(customerNeedle);
      })
      .sort((a, b) => {
        const byDate = a.order_date.localeCompare(b.order_date);
        if (byDate !== 0) return sortDir === 'asc' ? byDate : -byDate;
        return (a.id ?? 0) - (b.id ?? 0);
      });
  }

  function resetOrderListPage() {
    orderListPage = 1;
  }

  function serializeOrderForm(data: OrderCreate) {
    return JSON.stringify({
      order_date: data.order_date || '',
      customer: data.customer || null,
      contract_no: data.contract_no || null,
      description: data.description || null,
    });
  }

  function setOrderFormSnapshot() {
    orderFormSnapshot = serializeOrderForm(form);
  }

  function showPrevMonth() {
    calendarMonth = addMonths(calendarMonth, -1);
  }

  function showNextMonth() {
    calendarMonth = addMonths(calendarMonth, 1);
  }

  function showCurrentMonth() {
    calendarMonth = monthKey(new Date());
  }

  async function load() {
    loading = true;
    try {
      orders = await api.orders.list();
      const [devs, pts] = await Promise.all([api.devices.list(), api.parts.list()]);
      devices = devs.map((d) => ({ id: d.id, primary_name: d.primary_name }));
      parts = pts.map((p) => ({ id: p.id, name: p.name }));
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  function closeOrderModal() {
    if (orderFormDirty && !confirm('Изменения не сохранятся. Закрыть без сохранения?')) {
      return;
    }
    modalOpen = false;
    selectedOrder = null;
    editingId = null;
    orderItems = [];
    orderPartItems = [];
    itemModalOpen = false;
    partItemModalOpen = false;
    orderSaveMessage = '';
    orderFormSnapshot = '';
  }

  function openCreate(date = isoDate(new Date())) {
    editingId = null;
    selectedOrder = null;
    orderItems = [];
    orderPartItems = [];
    form = { order_date: date, customer: null, contract_no: null, description: null };
    setOrderFormSnapshot();
    orderSaveMessage = '';
    modalOpen = true;
  }

  function openDayModal(date: string) {
    selectedDayDate = date;
  }

  async function save() {
    try {
      let current: Order;
      if (editingId) {
        current = await api.orders.update(editingId, form);
      } else {
        current = await api.orders.create(form);
      }
      await load();
      await openItems(current, { preserveMessage: true });
      orderSaveOk = true;
      orderSaveMessage = 'Заказ сохранён';
    } catch (e) {
      orderSaveOk = false;
      orderSaveMessage = 'Не удалось сохранить заказ: ' + (e as Error).message;
    }
  }

  async function remove(id: number) {
    if (!confirm('Удалить заказ?')) return;
    try {
      await api.orders.delete(id);
      if (editingId === id || selectedOrder?.id === id) {
        modalOpen = false;
        selectedOrder = null;
        editingId = null;
        orderItems = [];
        orderPartItems = [];
        itemModalOpen = false;
        partItemModalOpen = false;
        orderSaveMessage = '';
        orderFormSnapshot = '';
      }
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function openItems(o: Order, opts?: { preserveMessage?: boolean }) {
    selectedDayDate = null;
    selectedOrder = o;
    editingId = o.id;
    form = { order_date: o.order_date, customer: o.customer ?? null, contract_no: o.contract_no ?? null, description: o.description ?? null };
    setOrderFormSnapshot();
    if (!opts?.preserveMessage) orderSaveMessage = '';
    modalOpen = true;
    try {
      if (devices.length === 0 || parts.length === 0) {
        const [devs, pts] = await Promise.all([api.devices.list(), api.parts.list()]);
        devices = devs.map((d) => ({ id: d.id, primary_name: d.primary_name }));
        parts = pts.map((p) => ({ id: p.id, name: p.name }));
      }
    } catch (e) {
      alert('Не удалось загрузить приборы и детали: ' + (e as Error).message);
    }
    const [items, partItems, ...bomsArrays] = await Promise.all([
      api.orders.items.list(o.id),
      api.orders.partItems.list(o.id),
      ...devices.map((d) => api.bom.list(d.id)),
    ]);
    orderItems = items;
    orderPartItems = partItems;
    const map = new Map<number, BomVersion[]>();
    devices.forEach((d, i) => map.set(d.id, bomsArrays[i] as BomVersion[]));
    bomsByDevice = map;
  }

  async function openAddItem() {
    if (!selectedOrder) return;
    editingItemId = null;
    itemForm = { device_id: devices[0]?.id ?? 0, bom_version_id: null, qty: '1', price: null, note: null };
    itemModalOpen = true;
    setBomsForDeviceAndDefault();
  }

  async function openEditItem(item: OrderItem) {
    editingItemId = item.id;
    itemForm = { device_id: item.device_id, bom_version_id: item.bom_version_id ?? null, qty: item.qty, price: item.price, note: item.note };
    itemModalOpen = true;
    setBomsForDeviceAndDefault();
  }

  function setBomsForDeviceAndDefault() {
    bomsForDevice = bomsByDevice.get(itemForm.device_id) ?? [];
    if (!itemForm.bom_version_id && bomsForDevice.length > 0) {
      const active = bomsForDevice.find((b) => b.status === 'active') ?? bomsForDevice[0];
      itemForm = { ...itemForm, bom_version_id: active.id };
    }
  }

  async function onDeviceChangeInItem() {
    bomsForDevice = bomsByDevice.get(itemForm.device_id) ?? [];
    if (bomsForDevice.length > 0) {
      const active = bomsForDevice.find((b) => b.status === 'active') ?? bomsForDevice[0];
      itemForm = { ...itemForm, bom_version_id: active.id };
    } else {
      itemForm = { ...itemForm, bom_version_id: null };
    }
  }

  const BOM_STATUS_LABELS: Record<string, string> = {
    active: 'Активная',
    current: 'Рабочая',
    archived: 'Архивная',
  };
  function bomStatusLabel(s: string) {
    return BOM_STATUS_LABELS[s] ?? s;
  }

  function handleDeviceChangeInItem(e: Event) {
    const el = e.currentTarget;
    if (el instanceof HTMLSelectElement) {
      itemForm.device_id = Number(el.value);
      onDeviceChangeInItem();
    }
  }

  async function saveItem() {
    if (!selectedOrder) return;
    try {
      if (editingItemId) {
        await api.orders.items.update(selectedOrder.id, editingItemId, itemForm);
      } else {
        await api.orders.items.create(selectedOrder.id, itemForm);
      }
      itemModalOpen = false;
      orderItems = await api.orders.items.list(selectedOrder.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function openAddPartItem() {
    if (!selectedOrder) return;
    editingPartItemId = null;
    partItemForm = { part_id: parts[0]?.id ?? 0, qty: '1', price: null, note: null };
    partItemModalOpen = true;
  }

  function openEditPartItem(item: OrderPartItem) {
    editingPartItemId = item.id;
    partItemForm = { part_id: item.part_id, qty: item.qty, price: item.price, note: item.note };
    partItemModalOpen = true;
  }

  async function savePartItem() {
    if (!selectedOrder) return;
    try {
      if (editingPartItemId) {
        await api.orders.partItems.update(selectedOrder.id, editingPartItemId, partItemForm);
      } else {
        await api.orders.partItems.create(selectedOrder.id, partItemForm);
      }
      partItemModalOpen = false;
      orderPartItems = await api.orders.partItems.list(selectedOrder.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function removePartItem(itemId: number) {
    if (!selectedOrder || !confirm('Удалить позицию?')) return;
    try {
      await api.orders.partItems.delete(selectedOrder.id, itemId);
      orderPartItems = await api.orders.partItems.list(selectedOrder.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function removeItem(itemId: number) {
    if (!selectedOrder || !confirm('Удалить позицию?')) return;
    try {
      await api.orders.items.delete(selectedOrder.id, itemId);
      orderItems = await api.orders.items.list(selectedOrder.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function deviceName(id: number) {
    return devices.find((d) => d.id === id)?.primary_name ?? id;
  }
  function partName(id: number) {
    return parts.find((p) => p.id === id)?.name ?? id;
  }
</script>

<div class="p-8">
  <div class="flex justify-between items-center mb-6">
    <div>
      <h1 class="text-2xl font-bold text-white">Заказы</h1>
      <p class="text-sm text-zinc-400">Календарь по дате заказа</p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex rounded-lg border border-zinc-700 bg-zinc-900 p-0.5">
        <button
          type="button"
          on:click={() => viewMode = 'calendar'}
          class="rounded-md px-3 py-1.5 {viewMode === 'calendar' ? 'bg-amber-500 text-black' : 'text-zinc-300 hover:bg-zinc-700'}"
        >
          Календарь
        </button>
        <button
          type="button"
          on:click={() => viewMode = 'list'}
          class="rounded-md px-3 py-1.5 {viewMode === 'list' ? 'bg-amber-500 text-black' : 'text-zinc-300 hover:bg-zinc-700'}"
        >
          Список
        </button>
      </div>
      {#if viewMode === 'calendar'}
        <button type="button" on:click={showPrevMonth} class="px-3 py-1.5 bg-zinc-800 text-white rounded-lg hover:bg-zinc-700">
          ←
        </button>
        <button type="button" on:click={showCurrentMonth} class="px-3 py-1.5 bg-zinc-800 text-white rounded-lg hover:bg-zinc-700">
          Сегодня
        </button>
        <button type="button" on:click={showNextMonth} class="px-3 py-1.5 bg-zinc-800 text-white rounded-lg hover:bg-zinc-700">
          →
        </button>
      {/if}
      <button type="button" on:click={() => openCreate()} class="px-4 py-1.5 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400 transition-colors">
        Добавить
      </button>
    </div>
  </div>

  {#if loading}
    <p class="text-zinc-400">Загрузка...</p>
  {:else if viewMode === 'calendar'}
    <div class="rounded-xl border border-zinc-600 overflow-hidden bg-zinc-950 shadow-lg shadow-black/25">
      <div class="flex items-center justify-between border-b border-zinc-700 bg-surface-800 px-4 py-2">
        <h2 class="text-lg font-semibold capitalize text-white">{calendarMonthLabel}</h2>
        <div class="flex items-center gap-3 text-xs text-zinc-300">
          <span class="inline-flex items-center gap-1 rounded bg-sky-950 px-2 py-1 text-sky-100"><span class="h-2 w-2 rounded-full bg-sky-400"></span>Заказ</span>
        </div>
      </div>
      <div class="grid grid-cols-7 border-b border-zinc-700 bg-zinc-900 text-center text-xs font-semibold uppercase tracking-wide text-zinc-200">
        {#each weekDays as day}
          <div class="px-2 py-2">{day}</div>
        {/each}
      </div>
      <div class="grid grid-cols-7">
        {#each calendarDays as day}
          <div
            class="min-h-36 border-r border-b border-zinc-700 p-2 shadow-inner {day.inCurrentMonth ? 'bg-surface-800/90' : 'bg-zinc-950 text-zinc-600'}"
          >
            {#if day.inCurrentMonth}
              <div class="mb-2 flex items-center justify-between gap-1 rounded-md bg-zinc-950/70 px-1.5 py-1 ring-1 ring-zinc-700/60">
                <button
                  type="button"
                  on:click={() => openDayModal(day.date)}
                  class="h-8 min-w-8 rounded px-1 text-left font-mono text-lg font-bold leading-none {day.isToday ? 'bg-amber-400 text-black' : 'text-zinc-50 hover:bg-zinc-700'}"
                >
                  {day.day}
                </button>
                <button
                  type="button"
                  on:click={() => openCreate(day.date)}
                  class="rounded bg-zinc-700 px-1.5 py-0.5 text-[10px] font-medium text-zinc-100 hover:bg-amber-400 hover:text-black"
                >
                  + Заказ
                </button>
              </div>

              {#if day.orders.length > 0}
                <div class="space-y-1 overflow-hidden">
                  {#each day.orders.slice(0, 3) as order}
                    <button
                      type="button"
                      on:click={() => openItems(order)}
                      class="block w-full rounded border-l-4 border-y border-r border-sky-400 bg-sky-950/70 px-2 py-1 text-left text-[11px] leading-tight text-sky-50 shadow-sm transition-colors hover:bg-sky-900/80"
                    >
                      <div class="flex items-center justify-between gap-1">
                        <span class="min-w-0 truncate font-mono">#{order.id}</span>
                        <span class="shrink-0 rounded bg-black/30 px-1 text-[10px]">{order.contract_no || 'без договора'}</span>
                      </div>
                      <div class="truncate text-zinc-100">{order.customer || order.description || 'без заказчика'}</div>
                    </button>
                  {/each}
                  {#if day.orders.length > 3}
                    <button
                      type="button"
                      on:click={() => openDayModal(day.date)}
                      class="w-full rounded bg-amber-950/60 px-2 py-1 text-left text-[11px] font-medium text-amber-100 hover:bg-amber-900/70"
                    >
                      +{day.orders.length - 3} ещё
                    </button>
                  {/if}
                </div>
              {/if}
            {/if}
          </div>
        {/each}
      </div>
    </div>
  {:else}
    <div class="space-y-4">
      <div class="rounded-xl border border-zinc-700 bg-surface-800 p-4">
        <div class="grid gap-3 md:grid-cols-5">
          <div>
            <label class="block text-xs text-zinc-400 mb-1">Дата от</label>
            <input type="date" bind:value={orderDateFrom} on:input={resetOrderListPage} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div>
            <label class="block text-xs text-zinc-400 mb-1">Дата до</label>
            <input type="date" bind:value={orderDateTo} on:input={resetOrderListPage} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div>
            <label class="block text-xs text-zinc-400 mb-1">Заказчик / договор</label>
            <input bind:value={orderCustomerFilter} on:input={resetOrderListPage} placeholder="Поиск..." class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div>
            <label class="block text-xs text-zinc-400 mb-1">Сортировка даты</label>
            <select bind:value={orderSortDir} on:change={resetOrderListPage} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white">
              <option value="desc">Сначала новые</option>
              <option value="asc">Сначала старые</option>
            </select>
          </div>
          <div class="flex items-end">
            <button
              type="button"
              on:click={() => {
                orderDateFrom = '';
                orderDateTo = '';
                orderCustomerFilter = '';
                orderSortDir = 'desc';
                resetOrderListPage();
              }}
              class="w-full px-3 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600"
            >
              Сбросить
            </button>
          </div>
        </div>
      </div>

      <div class="overflow-x-auto rounded-xl border border-zinc-700 bg-surface-800">
        <table class="w-full">
          <thead class="bg-zinc-900 text-zinc-300 text-left">
            <tr>
              <th class="px-4 py-3 font-medium">Дата</th>
              <th class="px-4 py-3 font-medium">ID</th>
              <th class="px-4 py-3 font-medium">Заказчик</th>
              <th class="px-4 py-3 font-medium">Номер договора</th>
              <th class="px-4 py-3 font-medium">Описание</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-800">
            {#each pagedOrders as order}
              <tr on:click={() => openItems(order)} class="cursor-pointer hover:bg-zinc-800/60">
                <td class="px-4 py-3">{formatDate(order.order_date)}</td>
                <td class="px-4 py-3 font-mono">#{order.id}</td>
                <td class="px-4 py-3">{order.customer || '—'}</td>
                <td class="px-4 py-3">{order.contract_no || '—'}</td>
                <td class="px-4 py-3 text-zinc-400 max-w-xs truncate">{order.description || '—'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-zinc-700 bg-surface-800 px-4 py-3 text-sm text-zinc-300">
        <div>
          Показано {pagedOrders.length} из {filteredOrders.length}, страница {orderListPage} из {orderTotalPages}
        </div>
        <div class="flex gap-2">
          <button type="button" disabled={orderListPage <= 1} on:click={() => orderListPage -= 1} class="px-3 py-1.5 bg-zinc-700 rounded-lg hover:bg-zinc-600 disabled:opacity-40">
            Назад
          </button>
          <button type="button" disabled={orderListPage >= orderTotalPages} on:click={() => orderListPage += 1} class="px-3 py-1.5 bg-zinc-700 rounded-lg hover:bg-zinc-600 disabled:opacity-40">
            Вперед
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

{#if selectedDayDate}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-40" on:click={() => selectedDayDate = null} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-3xl max-h-[80vh] overflow-auto border border-zinc-700" on:click|stopPropagation role="dialog">
      <div class="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-white">Заказы за {dayLabel(selectedDayDate)}</h2>
          <p class="text-sm text-zinc-400">Всего: {selectedDayOrders.length}</p>
        </div>
        <button
          type="button"
          on:click={() => {
            const date = selectedDayDate ?? isoDate(new Date());
            selectedDayDate = null;
            openCreate(date);
          }}
          class="px-3 py-1.5 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400"
        >
          + Заказ
        </button>
      </div>

      {#if selectedDayOrders.length === 0}
        <div class="rounded-xl border border-dashed border-zinc-700 p-6 text-center text-zinc-400">
          На этот день заказов нет.
        </div>
      {:else}
        <div class="space-y-2">
          {#each selectedDayOrders as order}
            <div
              class="cursor-pointer rounded-xl border border-sky-400/70 bg-sky-950/70 p-3 hover:bg-sky-900/80"
              on:click={() => openItems(order)}
              on:keydown={(e) => {
                if (e.key === 'Enter' || e.key === ' ') {
                  e.preventDefault();
                  openItems(order);
                }
              }}
              role="button"
              tabindex="0"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-mono text-white">#{order.id}</span>
                <span class="min-w-0 flex-1 truncate text-zinc-200">{order.customer || order.description || 'без заказчика'}</span>
                <span class="rounded bg-black/30 px-2 py-0.5 text-sky-100">{order.contract_no || 'без договора'}</span>
              </div>
              {#if order.description}
                <div class="mt-1 text-sm text-zinc-300">{order.description}</div>
              {/if}
            </div>
          {/each}
        </div>
      {/if}

      <button on:click={() => selectedDayDate = null} class="mt-4 px-4 py-2 bg-zinc-700 rounded-lg hover:bg-zinc-600">Закрыть</button>
    </div>
  </div>
{/if}

{#if modalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-[60]" on:click={closeOrderModal} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-5xl max-h-[86vh] overflow-auto border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">{editingId ? `Заказ #${editingId}` : 'Новый заказ'}</h2>

      <form on:submit|preventDefault={save} class="rounded-xl border border-zinc-700 bg-zinc-900/35 p-4">
        <div class="grid gap-4 md:grid-cols-2">
          {#if editingId}
            <div>
              <label class="block text-sm text-zinc-400 mb-1">ID</label>
              <input value={editingId} readonly class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-zinc-400" />
            </div>
          {/if}
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Дата</label>
            <input type="date" bind:value={form.order_date} class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-white" required />
          </div>
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Заказчик</label>
            <input bind:value={form.customer} class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Номер договора</label>
            <input bind:value={form.contract_no} class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div class="md:col-span-2">
            <label class="block text-sm text-zinc-400 mb-1">Описание</label>
            <textarea bind:value={form.description} rows="2" placeholder="Опционально" class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-white" />
          </div>
        </div>

        <div class="flex flex-wrap gap-2 pt-4">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">
            {selectedOrder ? 'Сохранить заказ' : 'Создать заказ'}
          </button>
          <button type="button" on:click={closeOrderModal} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Закрыть</button>
          {#if selectedOrder}
            <button type="button" on:click={() => remove(selectedOrder.id)} class="ml-auto px-4 py-2 bg-red-700 text-white rounded-lg hover:bg-red-600">Удалить</button>
          {/if}
        </div>
        {#if orderSaveMessage}
          <div class="mt-3 rounded-lg border px-3 py-2 text-sm {orderSaveOk ? 'border-emerald-500/50 bg-emerald-950/60 text-emerald-100' : 'border-red-500/50 bg-red-950/60 text-red-100'}">
            {orderSaveMessage}
          </div>
        {/if}
      </form>

      <div class="mt-5 rounded-xl border border-zinc-700 bg-zinc-950/30 p-4">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-base font-semibold text-white">Позиции заказа</h3>
          {#if selectedOrder}
            <div class="flex gap-2">
              <button on:click={openAddItem} class="px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 text-sm">+ Прибор</button>
              <button on:click={openAddPartItem} class="px-3 py-1.5 bg-amber-600 text-white rounded-lg hover:bg-amber-500 text-sm">+ Деталь</button>
            </div>
          {/if}
        </div>

        {#if !selectedOrder}
          <div class="rounded-lg border border-dashed border-zinc-700 p-4 text-zinc-400">
            Сначала создайте заказ, затем в этом же окне появится добавление приборов и деталей.
          </div>
        {:else}
          <h4 class="text-sm text-zinc-400 mb-2">Приборы</h4>
          <table class="w-full mb-6">
            <thead class="text-zinc-400 text-left text-sm">
              <tr>
                <th class="px-3 py-2">Прибор</th>
                <th class="px-3 py-2">Спецификация</th>
                <th class="px-3 py-2">Кол-во</th>
                <th class="px-3 py-2">Цена</th>
                <th></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-zinc-700">
              {#each orderItems as i}
                <tr>
                  <td class="px-3 py-2">{deviceName(i.device_id)}</td>
                  <td class="px-3 py-2 text-zinc-400">
                    {i.bom_version ? (i.bom_version.name || `v${i.bom_version.version}`) : '—'}
                  </td>
                  <td class="px-3 py-2 font-mono">{formatQty(i.qty)}</td>
                  <td class="px-3 py-2">{formatQty(i.price)}</td>
                  <td>
                    <button on:click={() => openEditItem(i)} class="text-amber-500 text-sm mr-2">Изм.</button>
                    <button on:click={() => removeItem(i.id)} class="text-red-400 text-sm">Удал.</button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>

          <h4 class="text-sm text-zinc-400 mb-2">Детали (прямой заказ)</h4>
          <table class="w-full">
            <thead class="text-zinc-400 text-left text-sm">
              <tr>
                <th class="px-3 py-2">Деталь</th>
                <th class="px-3 py-2">Кол-во</th>
                <th class="px-3 py-2">Цена</th>
                <th></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-zinc-700">
              {#each orderPartItems as i}
                <tr>
                  <td class="px-3 py-2">{partName(i.part_id)}</td>
                  <td class="px-3 py-2 font-mono">{formatQty(i.qty)}</td>
                  <td class="px-3 py-2">{formatQty(i.price)}</td>
                  <td>
                    <button on:click={() => openEditPartItem(i)} class="text-amber-500 text-sm mr-2">Изм.</button>
                    <button on:click={() => removePartItem(i.id)} class="text-red-400 text-sm">Удал.</button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>
    </div>
  </div>
{/if}

{#if itemModalOpen && selectedOrder}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-[70]" on:click={() => itemModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">{editingItemId ? 'Редактировать' : 'Добавить'} прибор</h2>
      <form on:submit|preventDefault={saveItem} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Прибор</label>
          <select
            value={itemForm.device_id}
            on:change={handleDeviceChangeInItem}
            class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
            required
          >
            {#if devices.length === 0}
              <option value="" disabled>Нет приборов — добавьте в разделе «Приборы»</option>
            {:else}
              {#each devices as d}
                <option value={d.id}>{d.primary_name}</option>
              {/each}
            {/if}
          </select>
        </div>
        {#if bomsForDevice.length > 0}
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Спецификация <span class="text-amber-400">*</span></label>
            <select
              bind:value={itemForm.bom_version_id}
              class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
              required
            >
              {#each bomsForDevice as b}
                <option value={b.id}>
                  {b.name || `v${b.version}`} ({bomStatusLabel(b.status)})
                </option>
              {/each}
            </select>
          </div>
        {/if}
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Кол-во</label>
          <input type="number" step="1" min="1" bind:value={itemForm.qty} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Цена</label>
          <input type="number" step="0.01" bind:value={itemForm.price} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
          <button type="button" on:click={() => itemModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}

{#if partItemModalOpen && selectedOrder}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-[70]" on:click={() => partItemModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">{editingPartItemId ? 'Редактировать' : 'Добавить'} деталь</h2>
      <form on:submit|preventDefault={savePartItem} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Деталь</label>
          <select bind:value={partItemForm.part_id} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required>
            {#if parts.length === 0}
              <option value="" disabled>Нет деталей — добавьте в разделе «Детали»</option>
            {:else}
              {#each parts as p}
                <option value={p.id}>{p.name}</option>
              {/each}
            {/if}
          </select>
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Кол-во</label>
          <input type="number" step="1" min="1" bind:value={partItemForm.qty} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Цена</label>
          <input type="number" step="0.01" bind:value={partItemForm.price} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
          <button type="button" on:click={() => partItemModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}
