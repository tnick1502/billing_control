<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';

  let plans: { count: number } = { count: 0 };
  let orders: { count: number } = { count: 0 };
  let invoices: { count: number } = { count: 0 };
  let loading = true;

  onMount(async () => {
    try {
      const [p, o, i] = await Promise.all([
        api.monthlyPlans.list(),
        api.orders.list(),
        api.invoices.list(),
      ]);
      plans = { count: p.length };
      orders = { count: o.length };
      invoices = { count: i.length };
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  });
</script>

<div class="p-8">
  <h1 class="text-2xl font-bold text-white mb-8">Dashboard</h1>
  {#if loading}
    <p class="text-zinc-400">Загрузка...</p>
  {:else}
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      <a href="/monthly-plans" class="block p-6 bg-surface-800 rounded-xl border border-zinc-700 hover:border-amber-500/50 transition-colors">
        <div class="text-3xl font-mono font-bold text-amber-500">{plans.count}</div>
        <div class="text-zinc-400 mt-1">Месячных планов</div>
      </a>
      <a href="/orders" class="block p-6 bg-surface-800 rounded-xl border border-zinc-700 hover:border-emerald-500/50 transition-colors">
        <div class="text-3xl font-mono font-bold text-emerald-500">{orders.count}</div>
        <div class="text-zinc-400 mt-1">Заказов</div>
      </a>
      <a href="/invoices" class="block p-6 bg-surface-800 rounded-xl border border-zinc-700 hover:border-amber-500/50 transition-colors">
        <div class="text-3xl font-mono font-bold text-amber-500">{invoices.count}</div>
        <div class="text-zinc-400 mt-1">Счетов</div>
      </a>
    </div>
  {/if}
</div>
