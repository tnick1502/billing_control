<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { Device, DeviceCreate } from '$lib/api';

  let devices: Device[] = [];
  let loading = true;
  let modalOpen = false;
  let form: DeviceCreate = { primary_name: '', model: '', description: null };
  let editingId: number | null = null;
  let searchQuery = '';

  $: filteredDevices = filterDevices(devices, searchQuery);

  onMount(load);

  async function load() {
    loading = true;
    try {
      devices = await api.devices.list();
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  function openCreate() {
    editingId = null;
    form = { primary_name: '', model: '', description: null };
    modalOpen = true;
  }

  function openEdit(d: Device) {
    editingId = d.id;
    form = { primary_name: d.primary_name, model: d.model ?? '', description: d.description ?? null };
    modalOpen = true;
  }

  function filterDevices(items: Device[], query: string) {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((d) => {
      const haystack = `${d.primary_name ?? ''} ${d.model ?? ''} ${d.description ?? ''}`.toLowerCase();
      return haystack.includes(needle);
    });
  }

  function handleRowKeydown(event: KeyboardEvent, device: Device) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openEdit(device);
    }
  }

  async function save() {
    try {
      if (editingId) {
        await api.devices.update(editingId, form);
      } else {
        await api.devices.create(form);
      }
      modalOpen = false;
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function remove(id: number) {
    if (!confirm('Удалить прибор?')) return;
    try {
      await api.devices.delete(id);
      modalOpen = false;
      editingId = null;
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }
</script>

<div class="p-8">
  <div class="flex justify-between items-center mb-6">
    <h1 class="text-2xl font-bold text-white">Приборы</h1>
    <button on:click={openCreate} class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400 transition-colors">
      Добавить
    </button>
  </div>

  <div class="mb-4 rounded-xl border border-zinc-700 bg-surface-800 p-4">
    <label class="block text-xs text-zinc-400 mb-1" for="device-search">Поиск по приборам</label>
    <input
      id="device-search"
      bind:value={searchQuery}
      placeholder="Название, модель, описание..."
      class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
    />
  </div>

  {#if loading}
    <p class="text-zinc-400">Загрузка...</p>
  {:else}
    <div class="overflow-x-auto rounded-xl border border-zinc-700">
      <table class="w-full">
        <thead class="bg-surface-800 text-zinc-400 text-left">
          <tr>
            <th class="px-4 py-3 font-medium">ID</th>
            <th class="px-4 py-3 font-medium">Название</th>
            <th class="px-4 py-3 font-medium">Модель</th>
            <th class="px-4 py-3 font-medium">Описание</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-zinc-800">
          {#each filteredDevices as d}
            <tr
              class="cursor-pointer hover:bg-zinc-800/50"
              on:click={() => openEdit(d)}
              on:keydown={(event) => handleRowKeydown(event, d)}
              role="button"
              tabindex="0"
            >
              <td class="px-4 py-3 font-mono text-sm">{d.id ?? '—'}</td>
              <td class="px-4 py-3">{d.primary_name}</td>
              <td class="px-4 py-3 text-zinc-400">{d.model || '—'}</td>
              <td class="px-4 py-3 text-zinc-400 max-w-xs truncate">{d.description || '—'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if filteredDevices.length === 0}
        <div class="px-4 py-6 text-center text-zinc-400">Ничего не найдено.</div>
      {/if}
    </div>
  {/if}
</div>

{#if modalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => modalOpen = false} role="button" tabindex="0" on:keydown={(e) => e.key === 'Escape' && (modalOpen = false)}>
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">{editingId ? `Редактировать прибор #${editingId}` : 'Новый прибор'}</h2>
      <form on:submit|preventDefault={save} class="space-y-4">
        {#if editingId}
          <div>
            <label class="block text-sm text-zinc-400 mb-1">ID</label>
            <input value={editingId} readonly class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-400" />
          </div>
        {/if}
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Название</label>
          <input bind:value={form.primary_name} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Модель</label>
          <input bind:value={form.model} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Описание</label>
          <textarea bind:value={form.description} rows="2" placeholder="Опционально" class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
          <button type="button" on:click={() => modalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
          {#if editingId}
            <button type="button" on:click={() => remove(editingId)} class="ml-auto px-4 py-2 bg-red-700 text-white rounded-lg hover:bg-red-600">Удалить</button>
          {/if}
        </div>
      </form>
    </div>
  </div>
{/if}
