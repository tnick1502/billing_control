<script lang="ts">
  import { onDestroy, onMount } from 'svelte';
  import '../app.css';
  import { page } from '$app/stores';
  import {
    api,
    ApiError,
    AUTH_EXPIRED_EVENT,
    clearAuthToken,
    FORBIDDEN_EVENT,
    getAuthToken,
  } from '$lib/api';
  import type { CurrentUser } from '$lib/api';
  import { can, canOpenPath, currentUser as currentUserStore, firstAllowedPath } from '$lib/permissions';

  let currentUser: CurrentUser | null = null;
  let authReady = false;
  let authError = '';
  let rightsNotice = '';
  let rightsNoticeTimer: ReturnType<typeof setTimeout> | undefined;

  $: isLoginPage = $page.url.pathname === '/login';
  $: currentUserStore.set(currentUser);
  // Защита от захода в скрытый раздел по прямой ссылке (API всё равно ответит 403).
  $: pageAllowed = !currentUser || canOpenPath(currentUser, $page.url.pathname);
  $: fallbackPath = currentUser ? firstAllowedPath(currentUser) : null;
  // Раздел закрыт — возможно, права только что расширили: один раз на путь перечитываем /auth/me.
  let guardRefreshedFor = '';
  $: if (currentUser && !pageAllowed && guardRefreshedFor !== $page.url.pathname) {
    guardRefreshedFor = $page.url.pathname;
    void refreshMe();
  }
  $: showProduction = $can('parts') || $can('devices') || $can('bom') || $can('import');
  $: showFinance = $can('orders') || $can('invoices') || $can('statistics');

  function permissionsKey(u: CurrentUser | null) {
    return u ? JSON.stringify([u.role, u.is_superuser, u.permissions]) : '';
  }

  /** Перечитать права: роль могли поменять, пока вкладка открыта. */
  let refreshing = false;
  async function refreshMe() {
    if (refreshing || !getAuthToken()) return;
    refreshing = true;
    try {
      const fresh = await api.auth.me();
      if (permissionsKey(fresh) !== permissionsKey(currentUser)) {
        rightsNotice = 'Права доступа изменились — меню и кнопки обновлены.';
        clearTimeout(rightsNoticeTimer);
        rightsNoticeTimer = setTimeout(() => (rightsNotice = ''), 6000);
      }
      currentUser = fresh;
    } catch (e) {
      if (e instanceof ApiError && e.status === 401) onAuthExpired();
    } finally {
      refreshing = false;
    }
  }

  function onAuthExpired() {
    if (isLoginPage) return;
    clearAuthToken();
    currentUser = null;
    if (typeof window !== 'undefined') window.location.replace(`${window.location.origin}/login`);
  }

  function onForbidden() {
    void refreshMe();
  }

  function onVisibility() {
    if (document.visibilityState === 'visible') void refreshMe();
  }

  onDestroy(() => {
    if (typeof window === 'undefined') return;
    window.removeEventListener(AUTH_EXPIRED_EVENT, onAuthExpired);
    window.removeEventListener(FORBIDDEN_EVENT, onForbidden);
    document.removeEventListener('visibilitychange', onVisibility);
    clearTimeout(rightsNoticeTimer);
  });

  /**
   * path должен приходить из шаблона как `$page.url.pathname`, иначе Svelte не подписывается
   * на store и классы не обновляются при клиентской навигации.
   */
  function navClass(href: string, path: string) {
    const active = path === href || (href !== '/' && path.startsWith(href + '/'));
    return `block px-3 py-2 rounded-md text-sm transition-colors ${
      active ? 'bg-zinc-800 text-amber-400 font-medium' : 'text-zinc-300 hover:bg-zinc-800/80 hover:text-white'
    }`;
  }

  function roleLabel(user: CurrentUser) {
    return (user.role_name || user.role).toLowerCase();
  }

  onMount(async () => {
    window.addEventListener(AUTH_EXPIRED_EVENT, onAuthExpired);
    window.addEventListener(FORBIDDEN_EVENT, onForbidden);
    document.addEventListener('visibilitychange', onVisibility);

    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    const goLogin = () => {
      if (typeof window !== 'undefined') window.location.replace(`${origin}/login`);
    };
    const goStart = () => {
      if (typeof window !== 'undefined') window.location.replace(`${origin}/`);
    };

    if (!getAuthToken()) {
      authReady = true;
      if (!isLoginPage) goLogin();
      return;
    }

    const ME_MS = 15000;
    try {
      const mePromise = api.auth.me();
      const timeoutPromise = new Promise<never>((_, reject) =>
        setTimeout(() => reject(new Error('me_timeout')), ME_MS)
      );
      currentUser = await Promise.race([mePromise, timeoutPromise]);
      authReady = true;
      if (isLoginPage) goStart();
    } catch (e) {
      currentUser = null;
      authReady = true;
      const authRejected = e instanceof ApiError && (e.status === 401 || e.status === 403);
      if (authRejected) {
        clearAuthToken();
        if (!isLoginPage) goLogin();
      } else {
        authError = e instanceof ApiError
          ? e.message
          : 'Сервер временно недоступен. Токен сохранён.';
      }
    }
  });

  async function logout() {
    currentUser = null;
    try {
      await api.auth.logout();
    } catch {
      clearAuthToken();
    }
    if (typeof window !== 'undefined') {
      window.location.replace(`${window.location.origin}/login`);
    }
  }
</script>

{#if isLoginPage}
  <slot />
{:else if !authReady}
  <div class="min-h-screen flex items-center justify-center bg-zinc-950 text-zinc-300">Проверка авторизации...</div>
{:else if authError}
  <div class="min-h-screen flex items-center justify-center bg-zinc-950 px-4 text-zinc-200">
    <div class="w-full max-w-md rounded-xl border border-amber-800/70 bg-amber-950/30 p-6 text-center">
      <h1 class="text-lg font-semibold text-amber-200">Не удалось проверить авторизацию</h1>
      <p class="mt-2 text-sm text-zinc-300">{authError}</p>
      <p class="mt-2 text-xs text-zinc-500">Сохранённый токен не удалён.</p>
      <button
        type="button"
        on:click={() => window.location.reload()}
        class="mt-4 rounded-lg bg-amber-500 px-4 py-2 font-medium text-black hover:bg-amber-400"
      >
        Повторить
      </button>
    </div>
  </div>
{:else}
<div class="min-h-screen flex">
  <aside class="w-56 shrink-0 bg-surface-900 border-r border-zinc-800 flex flex-col">
    <div class="p-4 border-b border-zinc-800">
      {#if currentUser}
        <div class="space-y-2">
          <div class="truncate text-sm font-semibold text-zinc-100">
            {currentUser.full_name || currentUser.username} ({roleLabel(currentUser)})
          </div>
          {#if currentUser.is_superuser}
            <a href="/admin" class={navClass('/admin', $page.url.pathname)}>Админ-панель</a>
          {/if}
          <button
            type="button"
            on:click={logout}
            class="mt-0.5 rounded border border-red-800/80 bg-red-950/90 px-2 py-0.5 text-[11px] font-medium text-red-100 hover:bg-red-900"
          >
            Выйти
          </button>
        </div>
      {/if}
    </div>
    <nav class="flex-1 py-3 px-2 space-y-4 overflow-y-auto">
      <!-- отдельно: планы -->
      {#if $can('monthly_plans')}
        <div>
          <a href="/monthly-plans" class={navClass('/monthly-plans', $page.url.pathname)}>Месячные планы</a>
        </div>
      {/if}

      <!-- Производство -->
      {#if showProduction}
      <div class="px-1">
        <p
          class="px-2 mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-amber-500/80"
          role="presentation"
        >
          Производство
        </p>
        <div
          class="rounded-xl border border-zinc-800/90 bg-zinc-950/40 p-1 space-y-0.5 shadow-inner shadow-black/20"
          role="group"
          aria-label="Производство"
        >
          {#if $can('parts')}
            <a href="/parts" class={navClass('/parts', $page.url.pathname)}>Детали</a>
          {/if}
          {#if $can('devices')}
            <a href="/devices" class={navClass('/devices', $page.url.pathname)}>Приборы</a>
          {/if}
          {#if $can('bom')}
            <a href="/bom" class={navClass('/bom', $page.url.pathname)}>Спецификации</a>
          {/if}
          {#if $can('import')}
            <a href="/import" class={navClass('/import', $page.url.pathname)}>Загрузка спецификаций</a>
          {/if}
        </div>
      </div>
      {/if}

      <!-- Финансы -->
      {#if showFinance}
      <div class="px-1">
        <p
          class="px-2 mb-2 text-[10px] font-semibold uppercase tracking-[0.12em] text-emerald-500/80"
          role="presentation"
        >
          Финансы
        </p>
        <div
          class="rounded-xl border border-zinc-800/90 bg-zinc-950/40 p-1 space-y-0.5 shadow-inner shadow-black/20"
          role="group"
          aria-label="Финансы"
        >
          {#if $can('orders')}
            <a href="/orders" class={navClass('/orders', $page.url.pathname)}>Заказы клиентов</a>
          {/if}
          {#if $can('invoices')}
            <a href="/invoices" class={navClass('/invoices', $page.url.pathname)}>Счета от поставщиков</a>
          {/if}
          {#if $can('statistics')}
            <a href="/statistics" class={navClass('/statistics', $page.url.pathname)}>Статистика</a>
          {/if}
        </div>
      </div>
      {/if}
    </nav>
  </aside>
  <main class="flex-1 overflow-auto min-w-0">
    {#if rightsNotice}
      <div class="mx-8 mt-4 rounded-lg border border-amber-700/60 bg-amber-950/40 px-4 py-2 text-sm text-amber-100">
        {rightsNotice}
      </div>
    {/if}
    {#if pageAllowed}
      <slot />
    {:else}
      <div class="p-8">
        <div class="max-w-lg rounded-xl border border-zinc-700 bg-surface-800 p-6">
          <h1 class="text-lg font-semibold text-white">Нет доступа к разделу</h1>
          <p class="mt-2 text-sm text-zinc-400">
            У вашей роли нет доступа к этой странице. Если он нужен, обратитесь к администратору.
          </p>
          {#if fallbackPath}
            <a
              href={fallbackPath}
              class="mt-4 inline-block rounded-lg bg-amber-500 px-4 py-2 font-medium text-black hover:bg-amber-400"
            >
              Перейти в доступный раздел
            </a>
          {/if}
        </div>
      </div>
    {/if}
  </main>
</div>
{/if}
