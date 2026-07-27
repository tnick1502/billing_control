<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { Part, PartCreate } from '$lib/api';

  const NO_TYPE_LABEL = 'Без типа';
  const EXPANDED_STORAGE_KEY = 'parts:expandedGroups';
  const PART_NAME_COLLATOR = new Intl.Collator('ru', { sensitivity: 'base', numeric: true });

  let parts: Part[] = [];
  let partTypes: string[] = [];
  let loading = true;
  let loadError = '';
  let modalOpen = false;
  let form: PartCreate = { name: '', cipher: null, article: null, part_type: null, supplier: null, description: null };
  let editingId: number | null = null;
  let editingIsArchived = false;
  let searchQuery = '';
  let showArchived = false;
  let typeQuery = '';
  let typeDropdownOpen = false;
  let expanded: Record<string, boolean> = loadExpanded();

  $: filteredParts = filterParts(parts, searchQuery, showArchived);
  $: groupedParts = groupParts(filteredParts);
  $: groupKeys = Object.keys(groupedParts).sort(compareGroupKeys);
  $: filteredTypeOptions = filterTypeOptions(partTypes, typeQuery);

  onMount(() => {
    void loadPage();
  });

  async function loadPage() {
    await load();
    await loadTypes();
  }

  function loadExpanded(): Record<string, boolean> {
    if (typeof localStorage === 'undefined') return {};
    try {
      const raw = localStorage.getItem(EXPANDED_STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function saveExpanded() {
    if (typeof localStorage === 'undefined') return;
    try {
      localStorage.setItem(EXPANDED_STORAGE_KEY, JSON.stringify(expanded));
    } catch {
      /* ignore */
    }
  }

  async function load() {
    loading = true;
    loadError = '';
    try {
      parts = await api.parts.list(true);
    } catch (e) {
      console.error(e);
      parts = [];
      loadError = (e as Error).message || 'Не удалось загрузить детали';
    } finally {
      loading = false;
    }
  }

  async function loadTypes() {
    try {
      partTypes = await api.parts.listTypes();
    } catch (e) {
      console.error(e);
    }
  }

  function openCreate() {
    editingId = null;
    editingIsArchived = false;
    form = { name: '', cipher: null, article: null, part_type: null, supplier: null, description: null };
    typeQuery = '';
    typeDropdownOpen = false;
    modalOpen = true;
  }

  function openEdit(p: Part) {
    editingId = p.id;
    editingIsArchived = p.is_archived;
    form = {
      name: p.name,
      cipher: p.cipher ?? null,
      article: p.article ?? null,
      part_type: p.part_type ?? null,
      supplier: p.supplier ?? null,
      description: p.description ?? null,
    };
    typeQuery = p.part_type ?? '';
    typeDropdownOpen = false;
    modalOpen = true;
  }

  function filterParts(items: Part[], query: string, archived: boolean) {
    const visible = archived ? items : items.filter((p) => !p.is_archived);
    const needle = query.trim().toLowerCase();
    if (!needle) return visible;
    return visible.filter((p) => {
      const haystack = `${p.name ?? ''} ${p.cipher ?? ''} ${p.article ?? ''} ${p.part_type ?? ''} ${p.supplier ?? ''} ${p.description ?? ''}`.toLowerCase();
      return haystack.includes(needle);
    });
  }

  function groupKey(p: Part): string {
    const t = (p.part_type ?? '').trim();
    return t || NO_TYPE_LABEL;
  }

  function groupParts(items: Part[]): Record<string, Part[]> {
    const groups: Record<string, Part[]> = {};
    for (const p of items) {
      const key = groupKey(p);
      (groups[key] ??= []).push(p);
    }
    for (const group of Object.values(groups)) {
      group.sort((a, b) => PART_NAME_COLLATOR.compare(a.name, b.name) || a.id - b.id);
    }
    return groups;
  }

  function compareGroupKeys(a: string, b: string) {
    if (a === NO_TYPE_LABEL) return 1;
    if (b === NO_TYPE_LABEL) return -1;
    return PART_NAME_COLLATOR.compare(a, b);
  }

  function isExpanded(key: string): boolean {
    return expanded[key] !== false;
  }

  function toggleGroup(key: string) {
    expanded = { ...expanded, [key]: !isExpanded(key) };
    saveExpanded();
  }

  $: anyGroupExpanded = groupKeys.some((k) => expanded[k] !== false);

  function toggleAllGroups() {
    const next = !anyGroupExpanded;
    expanded = Object.fromEntries(groupKeys.map((k) => [k, next]));
    saveExpanded();
  }

  function filterTypeOptions(types: string[], query: string): string[] {
    const needle = query.trim().toLowerCase();
    if (!needle) return types;
    return types.filter((t) => t.toLowerCase().includes(needle));
  }

  function selectType(t: string) {
    form.part_type = t;
    typeQuery = t;
    typeDropdownOpen = false;
  }

  function onTypeInput(value: string) {
    typeQuery = value;
    form.part_type = value.trim() || null;
    typeDropdownOpen = true;
  }

  function handleRowKeydown(event: KeyboardEvent, part: Part) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openEdit(part);
    }
  }

  function handleGroupKeydown(event: KeyboardEvent, key: string) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      toggleGroup(key);
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
      await load();
      await loadTypes();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function toggleArchive(id: number, currentlyArchived: boolean) {
    try {
      await api.parts.archive(id, !currentlyArchived);
      modalOpen = false;
      editingId = null;
      await load();
      await loadTypes();
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
      await load();
      await loadTypes();
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
        placeholder="Название, шифр, артикул, поставщик, описание..."
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
  {:else if loadError}
    <div class="rounded-xl border border-red-800 bg-red-950/40 px-4 py-4 text-red-200">
      <p class="font-medium">Не удалось загрузить детали</p>
      <p class="mt-1 text-sm text-red-300">{loadError}</p>
      <button
        type="button"
        on:click={loadPage}
        class="mt-3 rounded-lg border border-red-700 px-3 py-1.5 text-sm hover:bg-red-900/60"
      >
        Повторить
      </button>
    </div>
  {:else if filteredParts.length === 0}
    <div class="rounded-xl border border-zinc-700 px-4 py-6 text-center text-zinc-400">Ничего не найдено.</div>
  {:else}
    <div class="mb-3 flex justify-end">
      <button
        type="button"
        on:click={toggleAllGroups}
        class="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-700 hover:text-white transition-colors"
      >
        {#if anyGroupExpanded}
          <span class="text-[10px] leading-none">▴▾</span> Свернуть все
        {:else}
          <span class="text-[10px] leading-none">▾▴</span> Развернуть все
        {/if}
      </button>
    </div>
    <div class="space-y-4">
      {#each groupKeys as key (key)}
        <div class="overflow-hidden rounded-xl border border-zinc-700">
          <button
            type="button"
            on:click={() => toggleGroup(key)}
            on:keydown={(e) => handleGroupKeydown(e, key)}
            class="flex w-full items-center gap-2 bg-surface-800 px-4 py-3 text-left hover:bg-zinc-800"
          >
            <span class="text-zinc-400 text-xs">{expanded[key] !== false ? '▾' : '▸'}</span>
            <span class="font-medium text-white">{key}</span>
            <span class="text-xs text-zinc-400">({groupedParts[key].length})</span>
          </button>
          {#if expanded[key] !== false}
            <div class="overflow-x-auto">
              <table class="w-full min-w-[1200px] table-fixed">
                <colgroup>
                  <col class="w-[7%]" />
                  <col class="w-[35%]" />
                  <col class="w-[14%]" />
                  <col class="w-[10%]" />
                  <col class="w-[14%]" />
                  <col class="w-[20%]" />
                </colgroup>
                <thead class="bg-zinc-900 text-zinc-400 text-left">
                  <tr>
                    <th class="px-4 py-2 font-medium text-sm">ID</th>
                    <th class="px-4 py-2 font-medium text-sm">Название</th>
                    <th class="px-4 py-2 font-medium text-sm">Шифр</th>
                    <th class="px-4 py-2 font-medium text-sm">Артикул</th>
                    <th class="px-4 py-2 font-medium text-sm">Поставщик</th>
                    <th class="px-4 py-2 font-medium text-sm">Описание</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-zinc-800">
                  {#each groupedParts[key] as p (p.id)}
                    <tr
                      class="cursor-pointer hover:bg-zinc-800/50 {p.is_archived ? 'opacity-50' : ''}"
                      on:click={() => openEdit(p)}
                      on:keydown={(event) => handleRowKeydown(event, p)}
                      role="button"
                      tabindex="0"
                    >
                      <td class="px-4 py-3 font-mono text-sm whitespace-nowrap">{p.id ?? '—'}</td>
                      <td class="px-4 py-3 min-w-0">
                        <div class="flex min-w-0 items-center">
                          <span class="truncate {p.is_archived ? 'line-through text-zinc-500' : ''}" title={p.name}>{p.name}</span>
                          {#if p.is_archived}
                            <span class="ml-2 shrink-0 px-1.5 py-0.5 text-[10px] bg-zinc-700 text-zinc-400 rounded">Архив</span>
                          {/if}
                        </div>
                      </td>
                      <td class="px-4 py-3 text-zinc-300 truncate" title={p.cipher || undefined}>{p.cipher || '—'}</td>
                      <td class="px-4 py-3 text-zinc-300 truncate" title={p.article || undefined}>{p.article || '—'}</td>
                      <td class="px-4 py-3 text-zinc-300 truncate" title={p.supplier || undefined}>{p.supplier || '—'}</td>
                      <td class="px-4 py-3 text-zinc-400 truncate" title={p.description || undefined}>{p.description || '—'}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>
            </div>
          {/if}
        </div>
      {/each}
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
          <label class="block text-sm text-zinc-400 mb-1">Поставщик</label>
          <input
            bind:value={form.supplier}
            maxlength="255"
            placeholder="Опционально, до 255 символов"
            class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
          />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1" for="part-type-input">Тип детали</label>
          <input
            id="part-type-input"
            type="search"
            value={typeQuery}
            on:input={(e) => onTypeInput(e.currentTarget.value)}
            on:focus={() => (typeDropdownOpen = true)}
            placeholder="Выберите из списка или введите новый"
            class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
            autocomplete="off"
          />
          {#if typeDropdownOpen && filteredTypeOptions.length > 0}
            <div class="mt-1 rounded-lg border border-zinc-700 bg-zinc-950/90 max-h-40 overflow-y-auto">
              {#each filteredTypeOptions as t}
                <button
                  type="button"
                  on:click={() => selectType(t)}
                  class="w-full text-left px-3 py-1.5 text-sm text-zinc-200 hover:bg-zinc-800"
                >
                  {t}
                </button>
              {/each}
            </div>
          {/if}
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
