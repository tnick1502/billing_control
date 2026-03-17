<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { MonthlyPlan, MonthlyPlanDevice, MonthlyPlanPart } from '$lib/api';

  let plans: MonthlyPlan[] = [];
  let devices: { id: number; primary_name: string }[] = [];
  let parts: { id: number; name: string }[] = [];
  let loading = true;
  let generateModalOpen = false;
  let generateMonthInput = new Date().toISOString().slice(0, 7);
  let selectedPlan: MonthlyPlan | null = null;
  let planDevices: MonthlyPlanDevice[] = [];
  let planParts: MonthlyPlanPart[] = [];

  onMount(load);

  async function load() {
    loading = true;
    try {
      plans = await api.monthlyPlans.list();
      const devs = await api.devices.list();
      devices = devs.map((d) => ({ id: d.id, primary_name: d.primary_name }));
      const p = await api.parts.list();
      parts = p.map((x) => ({ id: x.id, name: x.name }));
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  async function generate() {
    try {
      await api.monthlyPlans.generate({ month: generateMonthInput + '-01' });
      generateModalOpen = false;
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function selectPlan(p: MonthlyPlan) {
    selectedPlan = p;
    planDevices = await api.monthlyPlans.devices(p.id);
    planParts = await api.monthlyPlans.parts(p.id);
  }

  function deviceName(id: number) {
    return devices.find((d) => d.id === id)?.primary_name ?? id;
  }
  function partName(id: number) {
    return parts.find((p) => p.id === id)?.name ?? id;
  }
</script>

<div class="p-8">
  <div class="flex justify-between items-center mb-6">
    <h1 class="text-2xl font-bold text-white">Месячные планы</h1>
    <button on:click={() => generateModalOpen = true} class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400 transition-colors">
      Сгенерировать план
    </button>
  </div>

  {#if loading}
    <p class="text-zinc-400">Загрузка...</p>
  {:else}
    <div class="flex gap-6">
      <div class="w-72 shrink-0">
        <h2 class="text-sm font-medium text-zinc-400 mb-2">Планы</h2>
        <div class="space-y-1">
          {#each plans as p}
            <button
              on:click={() => selectPlan(p)}
              class="block w-full text-left px-3 py-2 rounded-lg {selectedPlan?.id === p.id ? 'bg-amber-500/20 text-amber-400' : 'hover:bg-zinc-800 text-zinc-300'}"
            >
              {new Date(p.month).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })} (r{p.revision})
            </button>
          {/each}
        </div>
      </div>

      <div class="flex-1">
        {#if selectedPlan}
          <div class="mb-6">
            <h2 class="text-lg text-white mb-4">Приборы в плане</h2>
            <table class="w-full rounded-xl border border-zinc-700 overflow-hidden">
              <thead class="bg-surface-800 text-zinc-400 text-left">
                <tr>
                  <th class="px-4 py-3 font-medium">Прибор</th>
                  <th class="px-4 py-3 font-medium">Кол-во</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-zinc-800">
                {#each planDevices as d}
                  <tr class="hover:bg-zinc-800/50">
                    <td class="px-4 py-3">{deviceName(d.device_id)}</td>
                    <td class="px-4 py-3 font-mono">{d.qty_total}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
          <div>
            <h2 class="text-lg text-white mb-4">Детали (сводка)</h2>
            <table class="w-full rounded-xl border border-zinc-700 overflow-hidden">
              <thead class="bg-surface-800 text-zinc-400 text-left">
                <tr>
                  <th class="px-4 py-3 font-medium">Деталь</th>
                  <th class="px-4 py-3 font-medium">Требуется</th>
                  <th class="px-4 py-3 font-medium">Буфер</th>
                  <th class="px-4 py-3 font-medium">Итого</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-zinc-800">
                {#each planParts as p}
                  <tr class="hover:bg-zinc-800/50">
                    <td class="px-4 py-3">{partName(p.part_id)}</td>
                    <td class="px-4 py-3 font-mono">{p.qty_required}</td>
                    <td class="px-4 py-3 font-mono">{p.qty_buffered ?? '—'}</td>
                    <td class="px-4 py-3 font-mono">{p.qty_final}</td>
                  </tr>
                {/each}
              </tbody>
            </table>
          </div>
        {:else}
          <p class="text-zinc-400">Выберите план</p>
        {/if}
      </div>
    </div>
  {/if}
</div>

{#if generateModalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => generateModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">Сгенерировать месячный план</h2>
      <form on:submit|preventDefault={generate} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Месяц</label>
          <input type="month" bind:value={generateMonthInput} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сгенерировать</button>
          <button type="button" on:click={() => generateModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}
