<script lang="ts">
  import { onMount } from 'svelte';
  import '../app.css';
  import { page } from '$app/stores';
  import { api, clearAuthToken, getAuthToken } from '$lib/api';
  import type { User } from '$lib/api';

  let currentUser: User | null = null;
  let authReady = false;

  $: isLoginPage = $page.url.pathname === '/login';

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

  function roleLabel(role: User['role']) {
    return role === 'admin' ? 'админ' : 'сотрудник';
  }

  onMount(async () => {
    const origin = typeof window !== 'undefined' ? window.location.origin : '';
    const goLogin = () => {
      if (typeof window !== 'undefined') window.location.replace(`${origin}/login`);
    };
    const goPlans = () => {
      if (typeof window !== 'undefined') window.location.replace(`${origin}/monthly-plans`);
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
      if (isLoginPage) goPlans();
    } catch {
      clearAuthToken();
      currentUser = null;
      authReady = true;
      if (!isLoginPage) goLogin();
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
{:else}
<div class="min-h-screen flex">
  <aside class="w-56 shrink-0 bg-surface-900 border-r border-zinc-800 flex flex-col">
    <div class="p-4 border-b border-zinc-800">
      {#if currentUser}
        <div class="space-y-2">
          <div class="truncate text-sm font-semibold text-zinc-100">
            {currentUser.full_name || currentUser.username} ({roleLabel(currentUser.role)})
          </div>
          {#if currentUser.role === 'admin'}
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
      <div>
        <a href="/monthly-plans" class={navClass('/monthly-plans', $page.url.pathname)}>Месячные планы</a>
      </div>

      <!-- Производство -->
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
          <a href="/parts" class={navClass('/parts', $page.url.pathname)}>Детали</a>
          <a href="/devices" class={navClass('/devices', $page.url.pathname)}>Приборы</a>
          <a href="/bom" class={navClass('/bom', $page.url.pathname)}>Спецификации</a>
          {#if currentUser?.role === 'admin'}
            <a href="/import" class={navClass('/import', $page.url.pathname)}>Загрузка спецификаций</a>
          {/if}
        </div>
      </div>

      <!-- Финансы -->
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
          <a href="/orders" class={navClass('/orders', $page.url.pathname)}>Заказы клиентов</a>
          <a href="/invoices" class={navClass('/invoices', $page.url.pathname)}>Счета от поставщиков</a>
          <a href="/statistics" class={navClass('/statistics', $page.url.pathname)}>Статистика</a>
        </div>
      </div>
    </nav>
  </aside>
  <main class="flex-1 overflow-auto min-w-0">
    <slot />
  </main>
</div>
{/if}
