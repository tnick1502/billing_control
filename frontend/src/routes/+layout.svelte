<script lang="ts">
  import '../app.css';
</script>

<div class="min-h-screen flex">
  <aside class="w-56 bg-surface-900 border-r border-zinc-800 flex flex-col">
    <div class="p-4 border-b border-zinc-800">
      <a href="/monthly-plans" class="text-lg font-semibold text-amber-500 hover:text-amber-400 transition-colors">
        MRP BOM
      </a>
    </div>
    <nav class="flex-1 p-3 space-y-1">
      <a href="/monthly-plans" class="block px-3 py-2 rounded-lg text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors">Месячные планы</a>
      <a href="/devices" class="block px-3 py-2 rounded-lg text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors">Приборы</a>
      <a href="/parts" class="block px-3 py-2 rounded-lg text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors">Детали</a>
      <a href="/orders" class="block px-3 py-2 rounded-lg text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors">Заказы</a>
      <a href="/bom" class="block px-3 py-2 rounded-lg text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors">Спецификации</a>
      <a href="/invoices" class="block px-3 py-2 rounded-lg text-zinc-300 hover:bg-zinc-800 hover:text-white transition-colors">Счета</a>
    </nav>
  </aside>
  <main class="flex-1 overflow-auto">
    <slot />
  </main>
</div>
