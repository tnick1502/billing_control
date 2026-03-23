<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import { formatQty, formatDate } from '$lib/format';
  import type { Order, OrderCreate, OrderItem, OrderItemCreate, OrderPartItem, OrderPartItemCreate, BomVersion } from '$lib/api';

  let orders: Order[] = [];
  let devices: { id: number; primary_name: string }[] = [];
  let parts: { id: number; name: string }[] = [];
  let loading = true;
  let modalOpen = false;
  let form: OrderCreate = { status: 'draft', order_date: new Date().toISOString().slice(0, 10) };
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

  onMount(load);

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

  function openCreate() {
    editingId = null;
    form = { status: 'draft', order_date: new Date().toISOString().slice(0, 10) };
    modalOpen = true;
  }

  function openEdit(o: Order) {
    editingId = o.id;
    form = { status: o.status, order_date: o.order_date };
    modalOpen = true;
  }

  async function save() {
    try {
      if (editingId) {
        await api.orders.update(editingId, form);
      } else {
        await api.orders.create(form);
      }
      modalOpen = false;
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function remove(id: number) {
    if (!confirm('Удалить заказ?')) return;
    try {
      await api.orders.delete(id);
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function openItems(o: Order) {
    selectedOrder = o;
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
    current: 'Текущая',
    archived: 'Архив',
    draft: 'Черновик',
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
    <h1 class="text-2xl font-bold text-white">Заказы</h1>
    <button on:click={openCreate} class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400 transition-colors">
      Добавить
    </button>
  </div>

  {#if loading}
    <p class="text-zinc-400">Загрузка...</p>
  {:else}
    <div class="overflow-x-auto rounded-xl border border-zinc-700">
      <table class="w-full">
        <thead class="bg-surface-800 text-zinc-400 text-left">
          <tr>
            <th class="px-4 py-3 font-medium">ID</th>
            <th class="px-4 py-3 font-medium">Дата</th>
            <th class="px-4 py-3 font-medium">Статус</th>
            <th class="px-4 py-3 w-32"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-zinc-800">
          {#each orders as o}
            <tr class="hover:bg-zinc-800/50">
              <td class="px-4 py-3 font-mono">{o.id ?? '—'}</td>
              <td class="px-4 py-3">{formatDate(o.order_date)}</td>
              <td class="px-4 py-3"><span class="px-2 py-0.5 rounded text-sm bg-zinc-700">{o.status}</span></td>
              <td class="px-4 py-3">
                <button on:click={() => openItems(o)} class="text-emerald-500 hover:text-emerald-400 mr-2">Позиции</button>
                <button on:click={() => openEdit(o)} class="text-amber-500 hover:text-amber-400 mr-2">Изм.</button>
                <button on:click={() => remove(o.id)} class="text-red-400 hover:text-red-300">Удал.</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

{#if selectedOrder}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => selectedOrder = null} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-2xl max-h-[80vh] overflow-auto border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">Позиции заказа #{selectedOrder.id}</h2>
      <div class="flex gap-2 mb-4">
        <button on:click={openAddItem} class="px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 text-sm">+ Прибор</button>
        <button on:click={openAddPartItem} class="px-3 py-1.5 bg-amber-600 text-white rounded-lg hover:bg-amber-500 text-sm">+ Деталь</button>
      </div>
      <h3 class="text-sm text-zinc-400 mb-2">Приборы</h3>
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
      <h3 class="text-sm text-zinc-400 mb-2">Детали (прямой заказ)</h3>
      <table class="w-full mb-4">
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
      <button on:click={() => selectedOrder = null} class="px-4 py-2 bg-zinc-700 rounded-lg hover:bg-zinc-600">Закрыть</button>
    </div>
  </div>
{/if}

{#if modalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-[60]" on:click={() => modalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">{editingId ? `Редактировать заказ #${editingId}` : 'Новый заказ'}</h2>
      <form on:submit|preventDefault={save} class="space-y-4">
        {#if editingId}
          <div>
            <label class="block text-sm text-zinc-400 mb-1">ID</label>
            <input value={editingId} readonly class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-400" />
          </div>
        {/if}
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Дата</label>
          <input type="date" bind:value={form.order_date} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Статус</label>
          <input bind:value={form.status} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
          <button type="button" on:click={() => modalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
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
            {#each devices as d}
              <option value={d.id}>{d.primary_name}</option>
            {/each}
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
          <input type="number" step="0.001" bind:value={itemForm.qty} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
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
            {#each parts as p}
              <option value={p.id}>{p.name}</option>
            {/each}
          </select>
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Кол-во</label>
          <input type="number" step="0.001" bind:value={partItemForm.qty} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
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
