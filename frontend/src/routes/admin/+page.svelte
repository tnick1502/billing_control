<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { AuditLog, User, UserCreate } from '$lib/api';

  let users: User[] = [];
  let logs: AuditLog[] = [];
  let loading = true;
  let error = '';
  let modalOpen = false;
  let editingId: number | null = null;
  let form: UserCreate = emptyForm();

  onMount(load);

  function emptyForm(): UserCreate {
    return { username: '', password: '', full_name: null, role: 'employee', is_active: true };
  }

  function formatDate(value: string | null | undefined) {
    if (!value) return '—';
    return new Date(value).toLocaleString('ru-RU');
  }

  async function load() {
    loading = true;
    error = '';
    try {
      const [u, l] = await Promise.all([api.admin.users.list(), api.admin.auditLogs(300)]);
      users = u;
      logs = l;
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  function openCreate() {
    editingId = null;
    form = emptyForm();
    modalOpen = true;
  }

  function openEdit(user: User) {
    editingId = user.id;
    form = {
      username: user.username,
      password: '',
      full_name: user.full_name,
      role: user.role,
      is_active: user.is_active,
    };
    modalOpen = true;
  }

  async function save() {
    try {
      const payload = { ...form };
      if (editingId && !payload.password) {
        delete (payload as Partial<UserCreate>).password;
      }
      if (editingId) {
        await api.admin.users.update(editingId, payload);
      } else {
        await api.admin.users.create(payload);
      }
      modalOpen = false;
      await load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function handleUserRowKeydown(event: KeyboardEvent, user: User) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openEdit(user);
    }
  }

  async function removeCurrent() {
    if (!editingId) return;
    if (!confirm(`Удалить пользователя ${form.username}?`)) return;
    try {
      await api.admin.users.delete(editingId);
      modalOpen = false;
      await load();
    } catch (e) {
      alert((e as Error).message);
    }
  }
</script>

<div class="space-y-6 p-8">
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-white">Админ-панель</h1>
      <p class="text-sm text-zinc-400">Пользователи и журнал действий</p>
    </div>
    <button type="button" on:click={openCreate} class="rounded-lg bg-amber-500 px-4 py-2 font-medium text-black hover:bg-amber-400">
      Добавить пользователя
    </button>
  </div>

  {#if loading}
    <p class="text-zinc-400">Загрузка...</p>
  {:else if error}
    <div class="rounded-xl border border-red-500/50 bg-red-950/60 p-4 text-red-100">{error}</div>
  {:else}
    <section class="rounded-xl border border-zinc-700 bg-surface-800">
      <div class="border-b border-zinc-700 px-4 py-3">
        <h2 class="font-semibold text-white">Пользователи</h2>
      </div>
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-zinc-900 text-left text-zinc-300">
            <tr>
              <th class="px-4 py-3 font-medium">ID</th>
              <th class="px-4 py-3 font-medium">Логин</th>
              <th class="px-4 py-3 font-medium">Имя</th>
              <th class="px-4 py-3 font-medium">Роль</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-800">
            {#each users as user}
              <tr
                class="cursor-pointer hover:bg-zinc-800/60"
                role="button"
                tabindex="0"
                on:click={() => openEdit(user)}
                on:keydown={(event) => handleUserRowKeydown(event, user)}
              >
                <td class="px-4 py-3 font-mono text-sm">{user.id}</td>
                <td class="px-4 py-3">{user.username}</td>
                <td class="px-4 py-3 text-zinc-300">{user.full_name || '—'}</td>
                <td class="px-4 py-3">{user.role === 'admin' ? 'Админ' : 'Сотрудник'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>

    <section class="rounded-xl border border-zinc-700 bg-surface-800">
      <div class="flex items-center justify-between gap-3 border-b border-zinc-700 px-4 py-3">
        <h2 class="font-semibold text-white">Журнал действий</h2>
        <button type="button" on:click={load} class="rounded-lg bg-zinc-700 px-3 py-1.5 text-sm text-white hover:bg-zinc-600">Обновить</button>
      </div>
      <div class="max-h-[520px] overflow-auto">
        <table class="w-full">
          <thead class="sticky top-0 bg-zinc-900 text-left text-zinc-300">
            <tr>
              <th class="px-4 py-3 font-medium">Время</th>
              <th class="px-4 py-3 font-medium">Пользователь</th>
              <th class="px-4 py-3 font-medium">Действие</th>
              <th class="px-4 py-3 font-medium">Статус</th>
              <th class="px-4 py-3 font-medium">Детали</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-800">
            {#each logs as log}
              <tr class="hover:bg-zinc-800/60">
                <td class="px-4 py-3 whitespace-nowrap text-zinc-300">{formatDate(log.created_at)}</td>
                <td class="px-4 py-3">{log.username || '—'} <span class="text-zinc-500">({log.role || '—'})</span></td>
                <td class="px-4 py-3 font-mono text-sm">{log.action}</td>
                <td class="px-4 py-3">{log.status_code ?? '—'}</td>
                <td class="px-4 py-3 text-zinc-400">{log.details || '—'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>
  {/if}
</div>

{#if modalOpen}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" on:click={() => modalOpen = false} role="button" tabindex="0">
    <div class="w-full max-w-md rounded-xl border border-zinc-700 bg-surface-800 p-6" on:click|stopPropagation role="dialog">
      <h2 class="mb-4 text-lg font-semibold text-white">{editingId ? 'Редактировать пользователя' : 'Новый пользователь'}</h2>
      <form class="space-y-4" on:submit|preventDefault={save}>
        <div>
          <label class="mb-1 block text-sm text-zinc-400">Логин</label>
          <input bind:value={form.username} required class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white" />
        </div>
        <div>
          <label class="mb-1 block text-sm text-zinc-400">Пароль {editingId ? '(оставьте пустым, чтобы не менять)' : ''}</label>
          <input type="text" bind:value={form.password} required={!editingId} class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white" />
        </div>
        <div>
          <label class="mb-1 block text-sm text-zinc-400">Имя</label>
          <input bind:value={form.full_name} class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white" />
        </div>
        <div>
          <label class="mb-1 block text-sm text-zinc-400">Роль</label>
          <select bind:value={form.role} class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white">
            <option value="admin">Админ</option>
            <option value="employee">Сотрудник</option>
          </select>
        </div>
        <div class="flex flex-wrap items-center justify-between gap-2 pt-2">
          <div class="flex gap-2">
            <button type="submit" class="rounded-lg bg-amber-500 px-4 py-2 font-medium text-black hover:bg-amber-400">Сохранить</button>
            <button type="button" on:click={() => modalOpen = false} class="rounded-lg bg-zinc-700 px-4 py-2 text-white hover:bg-zinc-600">Отмена</button>
          </div>
          {#if editingId}
            <button type="button" on:click={removeCurrent} class="rounded-lg bg-red-950 px-4 py-2 text-red-100 ring-1 ring-red-700/60 hover:bg-red-900">
              Удалить
            </button>
          {/if}
        </div>
      </form>
    </div>
  </div>
{/if}
