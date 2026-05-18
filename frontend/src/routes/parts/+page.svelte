<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { Part, PartCreate } from '$lib/api';

  let parts: Part[] = [];
  let loading = true;
  let modalOpen = false;
  let form: PartCreate = { name: '', cipher: null, article: null, description: null };
  let editingId: number | null = null;
  let editingIsArchived = false;
  let searchQuery = '';
  let showArchived = false;

  $: filteredParts = filterParts(parts, searchQuery, showArchived);

  onMount(load);

  async function load() {
    loading = true;
    try {
      parts = await api.parts.list(true);
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  function openCreate() {
    editingId = null;
    editingIsArchived = false;
    form = { name: '', cipher: null, article: null, description: null };
    modalOpen = true;
  }

  function openEdit(p: Part) {
    editingId = p.id;
    editingIsArchived = p.is_archived;
    form = { name: p.name, cipher: p.cipher ?? null, article: p.article ?? null, description: p.description ?? null };
    modalOpen = true;
  }

  function filterParts(items: Part[], query: string, archived: boolean) {
    const visible = archived ? items : items.filter((p) => !p.is_archived);
    const needle = query.trim().toLowerCase();
    if (!needle) return visible;
    return visible.filter((p) => {
      const haystack = `${p.name ?? ''} ${p.cipher ?? ''} ${p.article ?? ''} ${p.description ?? ''}`.toLowerCase();
      return haystack.includes(needle);
    });
  }

  function handleRowKeydown(event: KeyboardEvent, part: Part) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openEdit(part);
    }
  }

  async function save() {
    try {
      if (editingId) {
        await api.parts.update(editingId, form);
      } else {
        await api.parts.create(form);
      }
      modalOpen = false;
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function toggleArchive(id: number, currentlyArchived: boolean) {
    try {
      await api.parts.archive(id, !currentlyArchived);
      modalOpen = false;
      editingId = null;
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function remove(id: number) {
    if (!confirm('Удалить деталь? Это действие нельзя отменить.')) return;
    try {
      await api.parts.delete(id);
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
    <h1 class="text-2xl font-bold text-white">Детали</h1>
    <button on:click={openCreate} class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400 transition-colors">
      Добавить
    </button>
  </div>

  <div class="mb-4 rounded-xl border border-zinc-700 bg-surface-800 p-4 flex flex-col gap-3 sm:flex-row sm:items-end">
    <div class="flex-1">
      <label class="block text-xs text-zinc-400 mb-1" for="part-search">Поиск по деталям</label>
      <input
        id="part-search"
        bind:value={searchQuery}
        placeholder="Название, шифр, артикул, описание..."
        class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
      />
    </div>
    <label class="flex items-center gap-2 text-sm text-zinc-400 cursor-pointer select-none">
      <input type="checkbox" bind:checked={showArchived} class="w-4 h-4 accent-amber-500" />
      Показать архивные
    </label>
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
            <th class="px-4 py-3 font-medium">Шифр</th>
            <th class="px-4 py-3 font-medium">Артикул</th>
            <th class="px-4 py-3 font-medium">Описание</th>
          </tr>
        </thead>
        <tbody class="divide-y divide-zinc-800">
          {#each filteredParts as p}
            <tr
              class="cursor-pointer hover:bg-zinc-800/50 {p.is_archived ? 'opacity-50' : ''}"
              on:click={() => openEdit(p)}
              on:keydown={(event) => handleRowKeydown(event, p)}
              role="button"
              tabindex="0"
            >
              <td class="px-4 py-3 font-mono text-sm">{p.id ?? '—'}</td>
              <td class="px-4 py-3">
                <span class="{p.is_archived ? 'line-through text-zinc-500' : ''}">{p.name}</span>
                {#if p.is_archived}
                  <span class="ml-2 px-1.5 py-0.5 text-[10px] bg-zinc-700 text-zinc-400 rounded">Архив</span>
                {/if}
              </td>
              <td class="px-4 py-3 text-zinc-300">{p.cipher || '—'}</td>
              <td class="px-4 py-3 text-zinc-300">{p.article || '—'}</td>
              <td class="px-4 py-3 text-zinc-400 max-w-xs truncate">{p.description || '—'}</td>
            </tr>
          {/each}
        </tbody>
      </table>
      {#if filteredParts.length === 0}
        <div class="px-4 py-6 text-center text-zinc-400">Ничего не найдено.</div>
      {/if}
    </div>
  {/if}
</div>

{#if modalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => modalOpen = false} role="button" tabindex="0" on:keydown={(e) => e.key === 'Escape' && (modalOpen = false)}>
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">
        {editingId ? `Редактировать деталь #${editingId}` : 'Новая деталь'}
        {#if editingIsArchived}
          <span class="ml-2 text-sm px-2 py-0.5 bg-zinc-700 text-zinc-400 rounded">Архив</span>
        {/if}
      </h2>
      <form on:submit|preventDefault={save} class="space-y-4">
        {#if editingId}
          <div>
            <label class="block text-sm text-zinc-400 mb-1">ID</label>
            <input value={editingId} readonly class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-400" />
          </div>
        {/if}
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Название</label>
          <input bind:value={form.name} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Шифр</label>
          <input bind:value={form.cipher} placeholder="Опционально" class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Артикул</label>
          <input bind:value={form.article} placeholder="Опционально" class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Описание</label>
          <textarea bind:value={form.description} rows="2" placeholder="Опционально" class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div class="flex flex-wrap gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
          <button type="button" on:click={() => modalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
          {#if editingId !== null}
            <button
              type="button"
              on:click={() => toggleArchive(editingId, editingIsArchived)}
              class="px-4 py-2 rounded-lg text-white {editingIsArchived ? 'bg-emerald-700 hover:bg-emerald-600' : 'bg-zinc-600 hover:bg-zinc-500'}"
            >
              {editingIsArchived ? 'Восстановить' : 'Архивировать'}
            </button>
            <button type="button" on:click={() => remove(editingId)} class="ml-auto px-4 py-2 bg-red-700 text-white rounded-lg hover:bg-red-600">Удалить</button>
          {/if}
        </div>
      </form>
    </div>
  </div>
{/if}
