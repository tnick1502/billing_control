<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { Part, PartCreate } from '$lib/api';

  let parts: Part[] = [];
  let loading = true;
  let modalOpen = false;
  let form: PartCreate = { name: '', uom: 'шт', is_active: true };
  let editingId: number | null = null;

  onMount(load);

  async function load() {
    loading = true;
    try {
      parts = await api.parts.list();
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  function openCreate() {
    editingId = null;
    form = { name: '', uom: 'шт', is_active: true };
    modalOpen = true;
  }

  function openEdit(p: Part) {
    editingId = p.id;
    form = { name: p.name, uom: p.uom, is_active: p.is_active };
    modalOpen = true;
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

  async function remove(id: number) {
    if (!confirm('Удалить деталь?')) return;
    try {
      await api.parts.delete(id);
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

  {#if loading}
    <p class="text-zinc-400">Загрузка...</p>
  {:else}
    <div class="overflow-x-auto rounded-xl border border-zinc-700">
      <table class="w-full">
        <thead class="bg-surface-800 text-zinc-400 text-left">
          <tr>
            <th class="px-4 py-3 font-medium">ID</th>
            <th class="px-4 py-3 font-medium">Название</th>
            <th class="px-4 py-3 font-medium">Ед. изм.</th>
            <th class="px-4 py-3 font-medium">Активна</th>
            <th class="px-4 py-3 w-24"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-zinc-800">
          {#each parts as p}
            <tr class="hover:bg-zinc-800/50">
              <td class="px-4 py-3 font-mono text-sm">{p.id}</td>
              <td class="px-4 py-3">{p.name}</td>
              <td class="px-4 py-3 text-zinc-400">{p.uom}</td>
              <td class="px-4 py-3">{p.is_active ? 'Да' : 'Нет'}</td>
              <td class="px-4 py-3">
                <button on:click={() => openEdit(p)} class="text-amber-500 hover:text-amber-400 mr-2">Изм.</button>
                <button on:click={() => remove(p.id)} class="text-red-400 hover:text-red-300">Удал.</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

{#if modalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => modalOpen = false} role="button" tabindex="0" on:keydown={(e) => e.key === 'Escape' && (modalOpen = false)}>
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">{editingId ? 'Редактировать' : 'Новая деталь'}</h2>
      <form on:submit|preventDefault={save} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Название</label>
          <input bind:value={form.name} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Ед. изм.</label>
          <input bind:value={form.uom} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div class="flex items-center gap-2">
          <input type="checkbox" bind:checked={form.is_active} id="active" />
          <label for="active" class="text-sm text-zinc-400">Активна</label>
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
          <button type="button" on:click={() => modalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}
