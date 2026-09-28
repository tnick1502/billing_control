<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type {
    AuditLog,
    DbStatus,
    PermissionLevel,
    Role,
    RoleSectionsInfo,
    SectionKey,
    User,
    UserCreate,
  } from '$lib/api';
  import { currentUser } from '$lib/permissions';

  type Tab = 'users' | 'roles' | 'logs' | 'db';
  let tab: Tab = 'users';

  let users: User[] = [];
  let roles: Role[] = [];
  let logs: AuditLog[] = [];
  let meta: RoleSectionsInfo | null = null;
  let db: DbStatus | null = null;
  let dbLoading = false;
  let loading = true;
  let error = '';

  // --- пользователи ---
  let userModalOpen = false;
  let editingUserId: number | null = null;
  let userForm: UserCreate = emptyUserForm();
  let userSaving = false;

  // --- роли ---
  let roleModalOpen = false;
  let editingRole: Role | null = null;
  let roleForm: { name: string; description: string; permissions: Record<SectionKey, PermissionLevel> } =
    emptyRoleForm();
  let roleSaving = false;

  onMount(load);

  function emptyUserForm(): UserCreate {
    // По умолчанию — «Сотрудник», если такая роль есть, иначе первая не-админская.
    const fallback =
      roles.find((r) => r.code === 'employee') ?? roles.find((r) => !r.is_superuser) ?? roles[0];
    return { username: '', password: '', full_name: null, role: fallback?.code ?? 'employee', is_active: true };
  }

  function emptyRoleForm() {
    const permissions = {} as Record<SectionKey, PermissionLevel>;
    for (const s of meta?.sections ?? []) permissions[s.key] = 'none';
    return { name: '', description: '', permissions };
  }

  function formatDate(value: string | null | undefined) {
    if (!value) return '—';
    return new Date(value).toLocaleString('ru-RU');
  }

  async function load() {
    loading = true;
    error = '';
    try {
      const [u, r, l, m] = await Promise.all([
        api.admin.users.list(),
        api.admin.roles.list(),
        api.admin.auditLogs(300),
        api.admin.roles.sections(),
      ]);
      users = u;
      roles = r;
      logs = l;
      meta = m;
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }

  async function loadDb() {
    dbLoading = true;
    try {
      db = await api.admin.dbStatus();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      dbLoading = false;
    }
  }

  function selectTab(next: Tab) {
    tab = next;
    if (next === 'db' && !db) void loadDb();
  }

  $: roleByCode = new Map(roles.map((r) => [r.code, r]));
  $: groupedSections = (() => {
    const groups: { group: string; items: RoleSectionsInfo['sections'] }[] = [];
    for (const s of meta?.sections ?? []) {
      let g = groups.find((x) => x.group === s.group);
      if (!g) groups.push((g = { group: s.group, items: [] }));
      g.items.push(s);
    }
    return groups;
  })();
  $: levelLabel = new Map((meta?.levels ?? []).map((l) => [l.key, l.label]));

  // --- пользователи ---

  function openCreateUser() {
    editingUserId = null;
    userForm = emptyUserForm();
    userModalOpen = true;
  }

  function openEditUser(user: User) {
    editingUserId = user.id;
    userForm = {
      username: user.username,
      password: '',
      full_name: user.full_name,
      role: user.role,
      is_active: user.is_active,
    };
    userModalOpen = true;
  }

  $: editingSelf = editingUserId !== null && editingUserId === $currentUser?.id;

  async function saveUser() {
    userSaving = true;
    try {
      const payload: Partial<UserCreate> = { ...userForm };
      if (editingUserId && !payload.password) delete payload.password;
      if (editingUserId) {
        await api.admin.users.update(editingUserId, payload);
      } else {
        await api.admin.users.create(payload as UserCreate);
      }
      userModalOpen = false;
      await load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      userSaving = false;
    }
  }

  async function removeUser() {
    if (!editingUserId) return;
    if (!confirm(`Удалить пользователя ${userForm.username}?`)) return;
    try {
      await api.admin.users.delete(editingUserId);
      userModalOpen = false;
      await load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function handleRowKeydown(event: KeyboardEvent, action: () => void) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      action();
    }
  }

  // --- роли ---

  function openCreateRole() {
    editingRole = null;
    roleForm = emptyRoleForm();
    roleModalOpen = true;
  }

  function openRole(role: Role) {
    editingRole = role;
    roleForm = {
      name: role.name,
      description: role.description ?? '',
      permissions: { ...role.permissions },
    };
    roleModalOpen = true;
  }

  $: roleReadOnly = !!editingRole?.is_system;

  function setAll(level: PermissionLevel) {
    if (roleReadOnly) return;
    const next = { ...roleForm.permissions };
    for (const key of Object.keys(next) as SectionKey[]) next[key] = level;
    roleForm = { ...roleForm, permissions: next };
  }

  async function saveRole() {
    roleSaving = true;
    try {
      const payload = {
        name: roleForm.name.trim(),
        description: roleForm.description.trim() || null,
        permissions: roleForm.permissions,
      };
      if (editingRole) {
        await api.admin.roles.update(editingRole.id, { ...payload, revision: editingRole.revision });
      } else {
        await api.admin.roles.create(payload);
      }
      roleModalOpen = false;
      await load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      roleSaving = false;
    }
  }

  async function copyRole(role: Role) {
    try {
      const created = await api.admin.roles.copy(role.id);
      await load();
      const fresh = roles.find((r) => r.id === created.id);
      if (fresh) openRole(fresh);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function removeRole(role: Role) {
    if (!confirm(`Удалить роль «${role.name}»?`)) return;
    try {
      await api.admin.roles.delete(role.id);
      roleModalOpen = false;
      await load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function levelClass(level: PermissionLevel, active: boolean) {
    if (!active) return 'bg-zinc-900 text-zinc-400 hover:bg-zinc-800 hover:text-zinc-200';
    return {
      none: 'bg-zinc-600 text-white',
      view: 'bg-sky-600 text-white',
      edit: 'bg-amber-500 text-black',
      full: 'bg-emerald-600 text-white',
    }[level];
  }

  function badgeClass(level: PermissionLevel) {
    return {
      none: 'text-zinc-500',
      view: 'text-sky-300',
      edit: 'text-amber-300',
      full: 'text-emerald-300',
    }[level];
  }

  const tabs: { key: Tab; label: string }[] = [
    { key: 'users', label: 'Пользователи' },
    { key: 'roles', label: 'Роли и доступ' },
    { key: 'logs', label: 'Журнал действий' },
    { key: 'db', label: 'База данных' },
  ];
</script>

<div class="space-y-6 p-8">
  <div class="flex flex-wrap items-center justify-between gap-3">
    <div>
      <h1 class="text-2xl font-bold text-white">Админ-панель</h1>
      <p class="text-sm text-zinc-400">Пользователи, роли, журнал действий и состояние БД</p>
    </div>
    {#if tab === 'users'}
      <button type="button" on:click={openCreateUser} class="rounded-lg bg-amber-500 px-4 py-2 font-medium text-black hover:bg-amber-400">
        Добавить пользователя
      </button>
    {:else if tab === 'roles'}
      <button type="button" on:click={openCreateRole} class="rounded-lg bg-amber-500 px-4 py-2 font-medium text-black hover:bg-amber-400">
        Создать роль
      </button>
    {/if}
  </div>

  <div class="flex flex-wrap gap-1 border-b border-zinc-800" role="tablist">
    {#each tabs as t}
      <button
        type="button"
        role="tab"
        aria-selected={tab === t.key}
        on:click={() => selectTab(t.key)}
        class="-mb-px rounded-t-lg border px-4 py-2 text-sm transition-colors {tab === t.key
          ? 'border-zinc-700 border-b-surface-950 bg-surface-800 text-amber-400'
          : 'border-transparent text-zinc-400 hover:text-white'}"
      >
        {t.label}
      </button>
    {/each}
  </div>

  {#if loading}
    <p class="text-zinc-400">Загрузка...</p>
  {:else if error}
    <div class="rounded-xl border border-red-500/50 bg-red-950/60 p-4 text-red-100">{error}</div>
  {:else if tab === 'users'}
    <section class="rounded-xl border border-zinc-700 bg-surface-800">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-zinc-900 text-left text-zinc-300">
            <tr>
              <th class="px-4 py-3 font-medium">ID</th>
              <th class="px-4 py-3 font-medium">Логин</th>
              <th class="px-4 py-3 font-medium">Имя</th>
              <th class="px-4 py-3 font-medium">Роль</th>
              <th class="px-4 py-3 font-medium">Статус</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-800">
            {#each users as user}
              <tr
                class="cursor-pointer hover:bg-zinc-800/60"
                role="button"
                tabindex="0"
                on:click={() => openEditUser(user)}
                on:keydown={(event) => handleRowKeydown(event, () => openEditUser(user))}
              >
                <td class="px-4 py-3 font-mono text-sm">{user.id}</td>
                <td class="px-4 py-3">{user.username}</td>
                <td class="px-4 py-3 text-zinc-300">{user.full_name || '—'}</td>
                <td class="px-4 py-3">{user.role_name || roleByCode.get(user.role)?.name || user.role}</td>
                <td class="px-4 py-3">
                  {#if user.is_active}
                    <span class="text-emerald-300">активен</span>
                  {:else}
                    <span class="text-zinc-500">отключён</span>
                  {/if}
                </td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>
  {:else if tab === 'roles'}
    <p class="max-w-3xl text-sm text-zinc-400">
      Уровни: <b class="text-zinc-200">Просмотр</b> — чтение и выгрузки;
      <b class="text-zinc-200">Изменение</b> — создание и правка без удаления;
      <b class="text-zinc-200">Полный</b> — всё, включая удаление и архивацию.
      Изменения прав действуют сразу, перелогиниваться не нужно.
    </p>
    <section class="rounded-xl border border-zinc-700 bg-surface-800">
      <div class="overflow-x-auto">
        <table class="w-full">
          <thead class="bg-zinc-900 text-left text-zinc-300">
            <tr>
              <th class="px-4 py-3 font-medium">Роль</th>
              <th class="px-4 py-3 font-medium">Пользователей</th>
              {#each meta?.sections ?? [] as s}
                <th class="px-2 py-3 text-xs font-medium">{s.label}</th>
              {/each}
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-800">
            {#each roles as role}
              <tr
                class="cursor-pointer hover:bg-zinc-800/60"
                role="button"
                tabindex="0"
                on:click={() => openRole(role)}
                on:keydown={(event) => handleRowKeydown(event, () => openRole(role))}
              >
                <td class="px-4 py-3">
                  <div class="font-medium text-white">{role.name}</div>
                  {#if role.is_system}
                    <div class="text-xs text-amber-400/80">системная</div>
                  {:else if role.description}
                    <div class="max-w-xs truncate text-xs text-zinc-500">{role.description}</div>
                  {/if}
                </td>
                <td class="px-4 py-3 text-zinc-300">{role.users_count}</td>
                {#each meta?.sections ?? [] as s}
                  <td class="px-2 py-3 text-xs {badgeClass(role.permissions[s.key])}">
                    {levelLabel.get(role.permissions[s.key]) ?? role.permissions[s.key]}
                  </td>
                {/each}
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>
  {:else if tab === 'logs'}
    <section class="rounded-xl border border-zinc-700 bg-surface-800">
      <div class="flex items-center justify-between gap-3 border-b border-zinc-700 px-4 py-3">
        <h2 class="font-semibold text-white">Журнал действий</h2>
        <button type="button" on:click={load} class="rounded-lg bg-zinc-700 px-3 py-1.5 text-sm text-white hover:bg-zinc-600">Обновить</button>
      </div>
      <div class="max-h-[620px] overflow-auto">
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
                <td class="whitespace-nowrap px-4 py-3 text-zinc-300">{formatDate(log.created_at)}</td>
                <td class="px-4 py-3">
                  {log.username || '—'}
                  <span class="text-zinc-500">({(log.role && roleByCode.get(log.role)?.name) || log.role || '—'})</span>
                </td>
                <td class="px-4 py-3 font-mono text-sm">{log.action}</td>
                <td class="px-4 py-3">{log.status_code ?? '—'}</td>
                <td class="px-4 py-3 text-zinc-400">{log.details || '—'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>
    </section>
  {:else if tab === 'db'}
    <section class="space-y-4 rounded-xl border border-zinc-700 bg-surface-800 p-4">
      <div class="flex items-center justify-between gap-3">
        <h2 class="font-semibold text-white">Подключения к базе данных</h2>
        <button type="button" on:click={loadDb} disabled={dbLoading} class="rounded-lg bg-zinc-700 px-3 py-1.5 text-sm text-white hover:bg-zinc-600 disabled:opacity-50">
          {dbLoading ? 'Обновление…' : 'Обновить'}
        </button>
      </div>
      {#if !db}
        <p class="text-zinc-400">{dbLoading ? 'Загрузка…' : 'Нет данных'}</p>
      {:else}
        <div class="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <div class="rounded-lg border border-zinc-700 bg-zinc-900/60 p-3">
            <div class="text-xs text-zinc-400">Пул приложения</div>
            <div class="mt-1 text-lg text-white">{db.pool.checked_out} занято / {db.pool.size}</div>
            <div class="text-xs text-zinc-500">лимит {db.pool.connection_budget}, свободно в пуле {db.pool.checked_in}</div>
          </div>
          {#if db.server}
            <div class="rounded-lg border border-zinc-700 bg-zinc-900/60 p-3">
              <div class="text-xs text-zinc-400">Сервер PostgreSQL</div>
              <div class="mt-1 text-lg text-white">{db.server.server_version.split(' ')[0]}</div>
              <div class="text-xs text-zinc-500">всего соединений {db.server.total_connections} из {db.server.max_connections ?? '—'}</div>
            </div>
          {/if}
          <div class="rounded-lg border border-zinc-700 bg-zinc-900/60 p-3">
            <div class="text-xs text-zinc-400">Кеш авторизации</div>
            <div class="mt-1 text-lg text-white">{db.auth_cache.enabled ? `включён, ${db.auth_cache.ttl_seconds} с` : 'выключен'}</div>
            <div class="text-xs text-zinc-500">записей {db.auth_cache.entries}</div>
          </div>
        </div>
        {#if db.server_error}
          <div class="rounded-lg border border-red-500/50 bg-red-950/60 p-3 text-sm text-red-100">{db.server_error}</div>
        {/if}
        {#if db.server}
          <div>
            <div class="mb-2 text-sm text-zinc-400">
              Соединения под пользователем БД приложения (наше имя: <span class="font-mono text-zinc-200">{db.server.application_name}</span>)
            </div>
            <table class="w-full max-w-2xl">
              <thead class="bg-zinc-900 text-left text-zinc-300">
                <tr>
                  <th class="px-3 py-2 font-medium">application_name</th>
                  <th class="px-3 py-2 font-medium">Состояние</th>
                  <th class="px-3 py-2 font-medium">Кол-во</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-zinc-800">
                {#each db.server.own_role_connections as row}
                  <tr class={row.application_name === db.server.application_name ? 'text-white' : 'text-zinc-400'}>
                    <td class="px-3 py-2 font-mono text-sm">{row.application_name || '—'}</td>
                    <td class="px-3 py-2">{row.state || '—'}</td>
                    <td class="px-3 py-2">{row.count}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {/if}
      {/if}
    </section>
  {/if}
</div>

{#if userModalOpen}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" on:click={() => (userModalOpen = false)} role="button" tabindex="0" on:keydown={(e) => e.key === 'Escape' && (userModalOpen = false)}>
    <div class="w-full max-w-md rounded-xl border border-zinc-700 bg-surface-800 p-6" on:click|stopPropagation on:keydown|stopPropagation role="dialog" tabindex="-1">
      <h2 class="mb-4 text-lg font-semibold text-white">{editingUserId ? 'Редактировать пользователя' : 'Новый пользователь'}</h2>
      <form class="space-y-4" on:submit|preventDefault={saveUser}>
        <div>
          <label class="mb-1 block text-sm text-zinc-400" for="u-login">Логин</label>
          <input id="u-login" bind:value={userForm.username} required class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white" />
        </div>
        <div>
          <label class="mb-1 block text-sm text-zinc-400" for="u-pass">Пароль {editingUserId ? '(оставьте пустым, чтобы не менять)' : ''}</label>
          <input id="u-pass" type="text" autocomplete="new-password" bind:value={userForm.password} required={!editingUserId} minlength="6" class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white" />
          {#if editingUserId}
            <p class="mt-1 text-xs text-zinc-500">После смены пароля все сеансы пользователя будут завершены.</p>
          {/if}
        </div>
        <div>
          <label class="mb-1 block text-sm text-zinc-400" for="u-name">Имя</label>
          <input id="u-name" bind:value={userForm.full_name} class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white" />
        </div>
        <div>
          <label class="mb-1 block text-sm text-zinc-400" for="u-role">Роль</label>
          <select id="u-role" bind:value={userForm.role} disabled={editingSelf} class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white disabled:opacity-60">
            {#each roles as r}
              <option value={r.code}>{r.name}</option>
            {/each}
          </select>
          {#if editingSelf}
            <p class="mt-1 text-xs text-zinc-500">Свою роль сменить нельзя — попросите другого администратора.</p>
          {/if}
        </div>
        <label class="flex items-center gap-2 text-sm text-zinc-300">
          <input type="checkbox" bind:checked={userForm.is_active} disabled={editingSelf} class="h-4 w-4 accent-amber-500" />
          Активен (может входить в систему)
        </label>
        <div class="flex flex-wrap items-center justify-between gap-2 pt-2">
          <div class="flex gap-2">
            <button type="submit" disabled={userSaving} class="rounded-lg bg-amber-500 px-4 py-2 font-medium text-black hover:bg-amber-400 disabled:opacity-60">Сохранить</button>
            <button type="button" on:click={() => (userModalOpen = false)} class="rounded-lg bg-zinc-700 px-4 py-2 text-white hover:bg-zinc-600">Отмена</button>
          </div>
          {#if editingUserId && !editingSelf}
            <button type="button" on:click={removeUser} class="rounded-lg bg-red-950 px-4 py-2 text-red-100 ring-1 ring-red-700/60 hover:bg-red-900">
              Удалить
            </button>
          {/if}
        </div>
      </form>
    </div>
  </div>
{/if}

{#if roleModalOpen}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" on:click={() => (roleModalOpen = false)} role="button" tabindex="0" on:keydown={(e) => e.key === 'Escape' && (roleModalOpen = false)}>
    <div class="max-h-[92vh] w-full max-w-3xl overflow-y-auto rounded-xl border border-zinc-700 bg-surface-800 p-6" on:click|stopPropagation on:keydown|stopPropagation role="dialog" tabindex="-1">
      <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h2 class="text-lg font-semibold text-white">
          {editingRole ? (roleReadOnly ? 'Системная роль' : 'Редактировать роль') : 'Новая роль'}
        </h2>
        {#if roleReadOnly}
          <span class="rounded bg-amber-950/60 px-2 py-0.5 text-xs text-amber-300 ring-1 ring-amber-700/60">
            Системная роль не редактируется
          </span>
        {/if}
      </div>
      <form class="space-y-4" on:submit|preventDefault={saveRole}>
        <div class="grid gap-4 sm:grid-cols-2">
          <div>
            <label class="mb-1 block text-sm text-zinc-400" for="r-name">Название</label>
            <input id="r-name" bind:value={roleForm.name} required maxlength="128" disabled={roleReadOnly} class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white disabled:opacity-60" />
          </div>
          <div>
            <label class="mb-1 block text-sm text-zinc-400" for="r-desc">Описание</label>
            <input id="r-desc" bind:value={roleForm.description} disabled={roleReadOnly} class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white disabled:opacity-60" />
          </div>
        </div>

        {#if roleReadOnly}
          <p class="text-sm text-zinc-400">Полный доступ ко всем разделам, управление пользователями и ролями.</p>
        {:else}
          <div class="flex flex-wrap items-center gap-2 text-xs text-zinc-400">
            Для всех разделов:
            {#each meta?.levels ?? [] as l}
              <button type="button" on:click={() => setAll(l.key)} class="rounded bg-zinc-800 px-2 py-1 text-zinc-200 hover:bg-zinc-700">{l.label}</button>
            {/each}
          </div>
          <div class="space-y-4">
            {#each groupedSections as g}
              <div>
                <div class="mb-1 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-500/80">{g.group}</div>
                <div class="divide-y divide-zinc-800 rounded-lg border border-zinc-800">
                  {#each g.items as s}
                    <div class="flex flex-wrap items-center justify-between gap-2 px-3 py-2">
                      <span class="text-sm text-zinc-200">{s.label}</span>
                      <div class="flex overflow-hidden rounded-lg ring-1 ring-zinc-700" role="radiogroup" aria-label={s.label}>
                        {#each meta?.levels ?? [] as l}
                          <button
                            type="button"
                            role="radio"
                            aria-checked={roleForm.permissions[s.key] === l.key}
                            title={l.hint}
                            on:click={() => (roleForm.permissions = { ...roleForm.permissions, [s.key]: l.key })}
                            class="px-3 py-1.5 text-xs transition-colors {levelClass(l.key, roleForm.permissions[s.key] === l.key)}"
                          >
                            {l.label}
                          </button>
                        {/each}
                      </div>
                    </div>
                  {/each}
                </div>
              </div>
            {/each}
          </div>
          <p class="text-xs text-zinc-500">
            Страницы разделов подтягивают нужные им справочники (например, план — список деталей) только для чтения,
            даже если сам справочник в роли закрыт.
          </p>
        {/if}

        <div class="flex flex-wrap items-center justify-between gap-2 pt-2">
          <div class="flex gap-2">
            {#if !roleReadOnly}
              <button type="submit" disabled={roleSaving} class="rounded-lg bg-amber-500 px-4 py-2 font-medium text-black hover:bg-amber-400 disabled:opacity-60">Сохранить</button>
            {/if}
            <button type="button" on:click={() => (roleModalOpen = false)} class="rounded-lg bg-zinc-700 px-4 py-2 text-white hover:bg-zinc-600">
              {roleReadOnly ? 'Закрыть' : 'Отмена'}
            </button>
          </div>
          {#if editingRole && !editingRole.is_superuser}
            <div class="flex gap-2">
              <button type="button" on:click={() => editingRole && copyRole(editingRole)} class="rounded-lg bg-zinc-700 px-4 py-2 text-white hover:bg-zinc-600">
                Копировать
              </button>
              {#if !editingRole.is_system}
                <button
                  type="button"
                  on:click={() => editingRole && removeRole(editingRole)}
                  disabled={editingRole.users_count > 0}
                  title={editingRole.users_count > 0 ? `Роль назначена пользователям: ${editingRole.users_count}. Сначала смените им роль.` : ''}
                  class="rounded-lg bg-red-950 px-4 py-2 text-red-100 ring-1 ring-red-700/60 hover:bg-red-900 disabled:cursor-not-allowed disabled:opacity-40"
                >
                  Удалить
                </button>
              {/if}
            </div>
          {/if}
        </div>
      </form>
    </div>
  </div>
{/if}
