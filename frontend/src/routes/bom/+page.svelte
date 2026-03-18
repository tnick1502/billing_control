<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import { formatQty } from '$lib/format';
  import type { Device, BomVersion, BomItem, BomVersionCreate, BomItemCreate } from '$lib/api';

  let devices: Device[] = [];
  let parts: { id: number; name: string }[] = [];
  let selectedDevice: Device | null = null;
  let boms: BomVersion[] = [];
  let selectedBom: BomVersion | null = null;
  let bomItems: BomItem[] = [];
  let loading = true;
  let bomModalOpen = false;
  let bomForm: BomVersionCreate = { version: 1, status: 'draft' };
  let itemModalOpen = false;
  let itemForm: BomItemCreate = { part_id: 0, qty_per_device: '1', note: null };
  let editingItemId: number | null = null;

  onMount(load);

  async function load() {
    loading = true;
    try {
      devices = await api.devices.list();
      const p = await api.parts.list();
      parts = p.map((x) => ({ id: x.id, name: x.name }));
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  async function selectDevice(d: Device) {
    selectedDevice = d;
    selectedBom = null;
    bomItems = [];
    try {
      boms = await api.bom.list(d.id);
      const activeBom = boms.find((b) => b.status === 'active') ?? boms[0];
      if (activeBom) {
        selectedBom = activeBom;
        bomItems = await api.bom.items.list(activeBom.id);
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function selectBom(b: BomVersion) {
    selectedBom = b;
    try {
      bomItems = await api.bom.items.list(b.id);
    } catch (e) {
      console.error(e);
    }
  }

  function openCreateBom() {
    if (!selectedDevice) return;
    bomForm = { version: (boms.length + 1), status: 'draft' };
    bomModalOpen = true;
  }

  async function saveBom() {
    if (!selectedDevice) return;
    try {
      await api.bom.create(selectedDevice.id, bomForm);
      bomModalOpen = false;
      boms = await api.bom.list(selectedDevice.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function setBomStatus(bomId: number, status: string) {
    try {
      await api.bom.update(bomId, { status });
      if (selectedDevice) boms = await api.bom.list(selectedDevice.id);
      if (selectedBom?.id === bomId) selectedBom = { ...selectedBom, status };
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function openAddItem() {
    if (!selectedBom) return;
    editingItemId = null;
    itemForm = { part_id: parts[0]?.id ?? 0, qty_per_device: '1', note: null };
    itemModalOpen = true;
  }

  function openEditItem(item: BomItem) {
    editingItemId = item.id;
    itemForm = { part_id: item.part_id, qty_per_device: item.qty_per_device, note: item.note };
    itemModalOpen = true;
  }

  async function saveItem() {
    if (!selectedBom) return;
    try {
      if (editingItemId) {
        await api.bom.items.update(selectedBom.id, editingItemId, itemForm);
      } else {
        await api.bom.items.create(selectedBom.id, itemForm);
      }
      itemModalOpen = false;
      bomItems = await api.bom.items.list(selectedBom.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function removeItem(itemId: number) {
    if (!selectedBom || !confirm('Удалить позицию?')) return;
    try {
      await api.bom.items.delete(selectedBom.id, itemId);
      bomItems = await api.bom.items.list(selectedBom.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function partName(id: number) {
    return parts.find((p) => p.id === id)?.name ?? id;
  }
</script>

<div class="p-8">
  <h1 class="text-2xl font-bold text-white mb-6">Спецификации (BOM)</h1>

  <div class="flex gap-6">
    <div class="w-64 shrink-0">
      <h2 class="text-sm font-medium text-zinc-400 mb-2">Приборы</h2>
      <div class="space-y-1">
        {#each devices as d}
          <button
            on:click={() => selectDevice(d)}
            class="block w-full text-left px-3 py-2 rounded-lg {selectedDevice?.id === d.id ? 'bg-amber-500/20 text-amber-400' : 'hover:bg-zinc-800 text-zinc-300'}"
          >
            {d.primary_name}
          </button>
        {/each}
      </div>
    </div>

    <div class="flex-1">
      {#if selectedDevice}
        <div class="mb-4 flex justify-between items-center">
          <h2 class="text-lg text-white">BOM для {selectedDevice.primary_name}</h2>
          <button on:click={openCreateBom} class="px-3 py-1.5 bg-amber-500 text-black rounded-lg hover:bg-amber-400 text-sm">Новая версия</button>
        </div>
        <div class="space-y-2 mb-4">
          {#each boms as b}
            <button
              on:click={() => selectBom(b)}
              class="w-full flex items-center gap-4 p-3 bg-surface-800 rounded-lg border text-left {selectedBom?.id === b.id ? 'border-amber-500' : 'border-zinc-700'}"
            >
              <span class="font-mono">v{b.version}</span>
              <span class="px-2 py-0.5 rounded text-sm bg-zinc-700">{b.status}</span>
              {#if b.status === 'draft'}
                <button on:click={(e) => { e.stopPropagation(); setBomStatus(b.id, 'active'); }} class="text-emerald-500 text-sm">Активировать</button>
              {/if}
            </button>
          {/each}
        </div>

        {#if selectedBom}
          <div>
            <button on:click={openAddItem} class="mb-4 px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 text-sm">Добавить деталь</button>
            <table class="w-full rounded-xl border border-zinc-700 overflow-hidden">
              <thead class="bg-surface-800 text-zinc-400 text-left">
                <tr>
                  <th class="px-4 py-3 font-medium">Деталь</th>
                  <th class="px-4 py-3 font-medium">Кол-во на прибор</th>
                  <th class="px-4 py-3 w-24"></th>
                </tr>
              </thead>
              <tbody class="divide-y divide-zinc-800">
                {#each bomItems as i}
                  <tr class="hover:bg-zinc-800/50">
                    <td class="px-4 py-3">{partName(i.part_id)}</td>
                    <td class="px-4 py-3 font-mono">{formatQty(i.qty_per_device)}</td>
                    <td class="px-4 py-3">
                      <button on:click={() => openEditItem(i)} class="text-amber-500 text-sm mr-2">Изм.</button>
                      <button on:click={() => removeItem(i.id)} class="text-red-400 text-sm">Удал.</button>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      {:else}
        <p class="text-zinc-400">Выберите прибор</p>
      {/if}
    </div>
  </div>
</div>

{#if bomModalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => bomModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">Новая версия BOM</h2>
      <form on:submit|preventDefault={saveBom} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Версия</label>
          <input type="number" bind:value={bomForm.version} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Статус</label>
          <input bind:value={bomForm.status} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Создать</button>
          <button type="button" on:click={() => bomModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}

{#if itemModalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => itemModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">{editingItemId ? 'Редактировать' : 'Добавить'} позицию</h2>
      <form on:submit|preventDefault={saveItem} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Деталь</label>
          <select bind:value={itemForm.part_id} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required>
            {#each parts as p}
              <option value={p.id}>{p.name}</option>
            {/each}
          </select>
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Кол-во на прибор</label>
          <input type="number" step="any" bind:value={itemForm.qty_per_device} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
          <button type="button" on:click={() => itemModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}
