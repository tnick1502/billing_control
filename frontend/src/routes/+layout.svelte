<script lang="ts">
  import '../app.css';
  import { page } from '$app/stores';

  function navClass(href: string) {
    const path = $page.url.pathname;
    const active = path === href || (href !== '/' && path.startsWith(href + '/'));
    return `block px-3 py-2 rounded-md text-sm transition-colors ${
      active ? 'bg-zinc-800 text-amber-400 font-medium' : 'text-zinc-300 hover:bg-zinc-800/80 hover:text-white'
    }`;
  }
</script>

<div class="min-h-screen flex">
  <aside class="w-56 shrink-0 bg-surface-900 border-r border-zinc-800 flex flex-col">
    <div class="p-4 border-b border-zinc-800">
      <a href="/monthly-plans" class="text-lg font-semibold text-amber-500 hover:text-amber-400 transition-colors">
        MRP BOM
      </a>
    </div>
    <nav class="flex-1 py-3 px-2 space-y-4 overflow-y-auto">
      <!-- отдельно: планы -->
      <div>
        <a href="/monthly-plans" class={navClass('/monthly-plans')}>Месячные планы</a>
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
          <a href="/parts" class={navClass('/parts')}>Детали</a>
          <a href="/devices" class={navClass('/devices')}>Приборы</a>
          <a href="/bom" class={navClass('/bom')}>Спецификации</a>
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
          <a href="/orders" class={navClass('/orders')}>Заказы</a>
          <a href="/bom" class={navClass('/bom')}>Спецификации</a>
          <a href="/invoices" class={navClass('/invoices')}>Счета</a>
        </div>
      </div>

      <!-- Статистика -->
      <div class="px-1">
        <a href="/statistics" class={navClass('/statistics')}>Статистика</a>
      </div>
    </nav>
  </aside>
  <main class="flex-1 overflow-auto min-w-0">
    <slot />
  </main>
</div>
