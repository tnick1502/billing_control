<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { Order, OrderCreate, OrderItem, OrderItemCreate } from '$lib/api';

  let orders: Order[] = [];
  let devices: { id: number; primary_name: string }[] = [];
  let loading = true;
  let modalOpen = false;
  let form: OrderCreate = { order_no: '', status: 'draft', order_date: new Date().toISOString().slice(0, 10) };
  let editingId: number | null = null;
  let selectedOrder: Order | null = null;
  let orderItems: OrderItem[] = [];
  let itemModalOpen = false;
  let itemForm: OrderItemCreate = { device_id: 0, qty: '1', price: null, note: null };
  let editingItemId: number | null = null;

  onMount(load);

  async function load() {
    loading = true;
    try {
      orders = await api.orders.list();
      const devs = await api.devices.list();
      devices = devs.map((d) => ({ id: d.id, primary_name: d.primary_name }));
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  function openCreate() {
    editingId = null;
    form = { order_no: '', status: 'draft', order_date: new Date().toISOString().slice(0, 10) };
    modalOpen = true;
  }

  function openEdit(o: Order) {
    editingId = o.id;
    form = { order_no: o.order_no, status: o.status, order_date: o.order_date };
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
    orderItems = await api.orders.items.list(o.id);
  }

  function openAddItem() {
    if (!selectedOrder) return;
    editingItemId = null;
    itemForm = { device_id: devices[0]?.id ?? 0, qty: '1', price: null, note: null };
    itemModalOpen = true;
  }

  function openEditItem(item: OrderItem) {
    editingItemId = item.id;
    itemForm = { device_id: item.device_id, qty: item.qty, price: item.price, note: item.note };
    itemModalOpen = true;
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
            <th class="px-4 py-3 font-medium">№ заказа</th>
            <th class="px-4 py-3 font-medium">Дата</th>
            <th class="px-4 py-3 font-medium">Статус</th>
            <th class="px-4 py-3 w-32"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-zinc-800">
          {#each orders as o}
            <tr class="hover:bg-zinc-800/50">
              <td class="px-4 py-3 font-mono">{o.order_no}</td>
              <td class="px-4 py-3">{o.order_date}</td>
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
      <h2 class="text-lg font-semibold text-white mb-4">Позиции заказа {selectedOrder.order_no}</h2>
      <button on:click={openAddItem} class="mb-4 px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 text-sm">Добавить позицию</button>
      <table class="w-full">
        <thead class="text-zinc-400 text-left text-sm">
          <tr>
            <th class="px-3 py-2">Прибор</th>
            <th class="px-3 py-2">Кол-во</th>
            <th class="px-3 py-2">Цена</th>
            <th></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-zinc-700">
          {#each orderItems as i}
            <tr>
              <td class="px-3 py-2">{deviceName(i.device_id)}</td>
              <td class="px-3 py-2 font-mono">{i.qty}</td>
              <td class="px-3 py-2">{i.price ?? '—'}</td>
              <td>
                <button on:click={() => openEditItem(i)} class="text-amber-500 text-sm mr-2">Изм.</button>
                <button on:click={() => removeItem(i.id)} class="text-red-400 text-sm">Удал.</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      <button on:click={() => selectedOrder = null} class="mt-4 px-4 py-2 bg-zinc-700 rounded-lg hover:bg-zinc-600">Закрыть</button>
    </div>
  </div>
{/if}

{#if modalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-[60]" on:click={() => modalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">{editingId ? 'Редактировать' : 'Новый заказ'}</h2>
      <form on:submit|preventDefault={save} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">№ заказа</label>
          <input bind:value={form.order_no} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
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
      <h2 class="text-lg font-semibold text-white mb-4">{editingItemId ? 'Редактировать' : 'Добавить'} позицию</h2>
      <form on:submit|preventDefault={saveItem} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Прибор</label>
          <select bind:value={itemForm.device_id} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required>
            {#each devices as d}
              <option value={d.id}>{d.primary_name}</option>
            {/each}
          </select>
        </div>
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
