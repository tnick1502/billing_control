<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import { formatQty } from '$lib/format';
  import type { MonthlyPlan, MonthlyPlanDevice, MonthlyPlanPartWithCoverage, InvoiceCreate } from '$lib/api';

  let plans: MonthlyPlan[] = [];
  let plansData: Map<number, { devices: MonthlyPlanDevice[]; parts: MonthlyPlanPartWithCoverage[] }> = new Map();
  let devices: { id: number; primary_name: string }[] = [];
  let parts: { id: number; name: string }[] = [];
  let invoices: { id: number; invoice_no: string }[] = [];
  let loading = true;
  let generateModalOpen = false;
  let generateMonthInput = new Date().toISOString().slice(0, 7);
  let updatingPlanId: number | null = null;

  let linkModalOpen = false;
  let linkPlanId: number | null = null;
  let linkPartIds: number[] = [];
  let linkInvoiceId = 0;

  let createInvoiceModalOpen = false;
  let createInvoicePlanId: number | null = null;
  let createInvoicePartIds: number[] = [];
  let createInvoiceForm: InvoiceCreate = { invoice_date: new Date().toISOString().slice(0, 10), currency: 'RUB', status: 'received' };
  let createInvoiceFileInput: HTMLInputElement;

  onMount(load);

  async function load() {
    loading = true;
    try {
      plans = await api.monthlyPlans.list();
      const [devs, pts, invs] = await Promise.all([
        api.devices.list(),
        api.parts.list(),
        api.invoices.list(),
      ]);
      devices = devs.map((d) => ({ id: d.id, primary_name: d.primary_name }));
      parts = pts.map((x) => ({ id: x.id, name: x.name }));
      invoices = invs.map((i) => ({ id: i.id, invoice_no: i.invoice_no }));

      for (const p of plans) {
        const [devsList, partsList] = await Promise.all([
          api.monthlyPlans.devices(p.id),
          api.monthlyPlans.partsWithCoverage(p.id),
        ]);
        plansData.set(p.id, { devices: devsList, parts: partsList });
      }
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  async function generate() {
    try {
      await api.monthlyPlans.generate({ month: generateMonthInput + '-01', replace: true });
      generateModalOpen = false;
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function updatePlan(plan: MonthlyPlan) {
    const month = plan.month.slice(0, 7);
    if (!confirm(`Обновить план за ${month}? Существующие данные будут пересчитаны по заказам.`)) return;
    updatingPlanId = plan.id;
    try {
      await api.monthlyPlans.generate({ month: plan.month.slice(0, 7) + '-01', replace: true });
      load();
    } catch (e) {
      alert((e as Error).message);
    } finally {
      updatingPlanId = null;
    }
  }

  function deviceName(id: number) {
    return devices.find((d) => d.id === id)?.primary_name ?? id;
  }
  function deviceId(id: number) {
    return devices.find((d) => d.id === id)?.id ?? id;
  }
  function partName(id: number) {
    return parts.find((p) => p.id === id)?.name ?? id;
  }
  function partId(id: number) {
    return parts.find((p) => p.id === id)?.id ?? id;
  }

  function openLinkModal(planId: number, partIds: number[]) {
    if (invoices.length === 0) {
      alert('Сначала создайте счёт в разделе Счета');
      return;
    }
    linkPlanId = planId;
    linkPartIds = partIds;
    linkInvoiceId = invoices[0].id;
    linkModalOpen = true;
  }

  async function saveLinks() {
    if (!linkPlanId || !linkInvoiceId) return;
    try {
      for (const partId of linkPartIds) {
        await api.invoices.parts.create(linkInvoiceId, { plan_id: linkPlanId, part_id: partId });
      }
      linkModalOpen = false;
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function openCreateInvoiceModal(planId: number, partIds: number[]) {
    createInvoicePlanId = planId;
    createInvoicePartIds = partIds;
    createInvoiceForm = { invoice_date: new Date().toISOString().slice(0, 10), currency: 'RUB', status: 'received' };
    if (createInvoiceFileInput) createInvoiceFileInput.value = '';
    createInvoiceModalOpen = true;
  }

  async function saveCreateInvoice() {
    if (!createInvoicePlanId || !createInvoiceFileInput?.files?.length) {
      alert('При создании счёта обязательно приложите файл');
      return;
    }
    try {
      const inv = await api.invoices.create(createInvoiceForm);
      await api.invoices.upload(inv.id, createInvoiceFileInput.files[0]);
      for (const partId of createInvoicePartIds) {
        await api.invoices.parts.create(inv.id, { plan_id: createInvoicePlanId, part_id: partId });
      }
      createInvoiceModalOpen = false;
      load();
    } catch (e) {
      alert((e as Error).message);
    }
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
    <div class="space-y-6">
      {#each plans as plan}
        {@const data = plansData.get(plan.id)}
        <div class="bg-surface-800 rounded-xl border border-zinc-700 overflow-hidden">
          <div class="px-6 py-4 border-b border-zinc-700 flex justify-between items-center">
            <h2 class="text-lg font-semibold text-white">
              {new Date(plan.month).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })}
            </h2>
            <button
              on:click={() => updatePlan(plan)}
              disabled={updatingPlanId === plan.id}
              class="px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 disabled:opacity-50 text-sm"
            >
              {updatingPlanId === plan.id ? 'Обновление...' : 'Обновить'}
            </button>
          </div>

          {#if data}
            {@const uncovered = data.parts.filter((p) => !p.has_invoice)}
            <div class="p-6">
              <h3 class="text-sm font-medium text-zinc-400 mb-2">Приборы</h3>
              <table class="w-full mb-6 rounded-xl border border-zinc-700 overflow-hidden">
                <thead class="bg-zinc-800 text-zinc-400 text-left">
                  <tr>
                    <th class="px-4 py-3 font-medium">ID</th>
                    <th class="px-4 py-3 font-medium">Прибор</th>
                    <th class="px-4 py-3 font-medium">Кол-во</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-zinc-800">
                  {#each data.devices as d}
                    <tr class="hover:bg-zinc-800/50">
                      <td class="px-4 py-3 font-mono text-sm">{deviceId(d.device_id) ?? '—'}</td>
                      <td class="px-4 py-3">{deviceName(d.device_id)}</td>
                      <td class="px-4 py-3 font-mono">{formatQty(d.qty_total)}</td>
                    </tr>
                  {/each}
                </tbody>
              </table>

              <h3 class="text-sm font-medium text-zinc-400 mb-2">Детали</h3>
              <table class="w-full rounded-xl border border-zinc-700 overflow-hidden">
                <thead class="bg-zinc-800 text-zinc-400 text-left">
                  <tr>
                    <th class="px-4 py-3 font-medium">ID</th>
                    <th class="px-4 py-3 font-medium">Деталь</th>
                    <th class="px-4 py-3 font-medium">Требуется</th>
                    <th class="px-4 py-3 font-medium">Покрытие счётом</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-zinc-800">
                  {#each data.parts as p}
                    <tr class="{p.has_invoice ? 'bg-emerald-500/10' : 'bg-red-500/10'}">
                      <td class="px-4 py-3 font-mono text-sm">{partId(p.part_id) ?? '—'}</td>
                      <td class="px-4 py-3">{partName(p.part_id)}</td>
                      <td class="px-4 py-3 font-mono">{formatQty(p.qty_required)}</td>
                      <td class="px-4 py-3">
                        {#if p.has_invoice}
                          <span class="text-emerald-400 font-mono text-sm">
                            {(p.invoices ?? []).map((i) => `№${i.invoice_id}`).join(', ')}
                          </span>
                        {:else}
                          <button
                            on:click={() => openLinkModal(plan.id, [p.part_id])}
                            class="text-amber-500 hover:text-amber-400 text-sm"
                          >
                            Привязать счёт
                          </button>
                        {/if}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
              {#if uncovered.length > 0}
                <div class="mt-4 flex gap-2">
                  <button
                    on:click={() => openLinkModal(plan.id, uncovered.map((p) => p.part_id))}
                    class="px-3 py-1.5 bg-amber-600 text-white rounded-lg hover:bg-amber-500 text-sm"
                  >
                    Привязать к существующему счёту ({uncovered.length})
                  </button>
                  <button
                    on:click={() => openCreateInvoiceModal(plan.id, uncovered.map((p) => p.part_id))}
                    class="px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 text-sm"
                  >
                    Создать счёт и привязать ({uncovered.length})
                  </button>
                </div>
              {/if}
            </div>
          {/if}
        </div>
      {/each}

      {#if plans.length === 0}
        <p class="text-zinc-400">Нет месячных планов. Сгенерируйте план.</p>
      {/if}
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

{#if linkModalOpen && linkPlanId}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => linkModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">Привязать счёт к {linkPartIds.length} деталям</h2>
      <form on:submit|preventDefault={saveLinks} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Счёт</label>
          <select bind:value={linkInvoiceId} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required>
            {#each invoices as i}
              <option value={i.id}>№{i.id}</option>
            {/each}
          </select>
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Привязать</button>
          <button type="button" on:click={() => linkModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}

{#if createInvoiceModalOpen && createInvoicePlanId}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => createInvoiceModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">Создать счёт и привязать к {createInvoicePartIds.length} деталям</h2>
      <form on:submit|preventDefault={saveCreateInvoice} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Дата</label>
          <input type="date" bind:value={createInvoiceForm.invoice_date} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Валюта</label>
          <input bind:value={createInvoiceForm.currency} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" placeholder="RUB" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Файл счёта <span class="text-red-400">*</span></label>
          <input type="file" bind:this={createInvoiceFileInput} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white text-sm" required />
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-emerald-500 text-black font-medium rounded-lg hover:bg-emerald-400">Создать и привязать</button>
          <button type="button" on:click={() => createInvoiceModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}
