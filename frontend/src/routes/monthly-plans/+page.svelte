<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import { formatQty, formatIntegerQty, formatAmount, formatDate } from '$lib/format';
  import type { MonthlyPlan, MonthlyPlanDevice, MonthlyPlanPartWithCoverage, InvoiceCreate, Invoice, PartInvoiceCoverage } from '$lib/api';

  type PlanDetail = { devices: MonthlyPlanDevice[]; parts: MonthlyPlanPartWithCoverage[] };

  let plans: MonthlyPlan[] = [];
  let plansDetail: Record<number, PlanDetail> = {};
  let devices: { id: number; primary_name: string }[] = [];
  let parts: { id: number; name: string }[] = [];
  let invoices: Invoice[] = [];
  let loading = true;
  let loadError = '';
  let generateModalOpen = false;
  let generateMonthInput = new Date().toISOString().slice(0, 7);
  let updatingPlanId: number | null = null;

  /** Черновики «поставлено» по id строки плана (monthly_plan_parts.id) */
  let deliverDraft: Record<number, string> = {};
  let savingDeliveredId: number | null = null;

  let linkModalOpen = false;
  let linkPlanId: number | null = null;
  let linkPartIds: number[] = [];
  let linkInvoiceId = 0;
  let linkInvoiceSearchQuery = '';
  let linkQtyByPart: Record<number, string> = {};

  let createInvoiceModalOpen = false;
  let createInvoicePlanId: number | null = null;
  let createInvoicePartIds: number[] = [];
  let createInvoiceQtyByPart: Record<number, string> = {};
  let createInvoiceForm: InvoiceCreate = emptyInvoiceForm();
  let createInvoiceFileInput: HTMLInputElement;

  let editInvoiceModalOpen = false;
  let editInvoiceId = 0;
  let editInvoiceLinkId = 0;
  let editInvoiceForm: InvoiceCreate = emptyInvoiceForm();
  let editInvoiceLinkQty = '';
  let expandedInvoiceLinks: Record<number, boolean> = {};
  let expandedPlans: Record<number, boolean> = {};
  let planExpansionInitialized = false;

  function refreshDeliverDrafts() {
    const d: Record<number, string> = {};
    for (const pl of plans) {
      const det = plansDetail[Number(pl.id)];
      det?.parts?.forEach((p) => {
        d[p.id] = formatIntegerQty(p.qty_delivered);
      });
    }
    deliverDraft = d;
  }

  onMount(() => {
    void load();
  });

  async function load(opts?: { quiet?: boolean }) {
    const quiet = opts?.quiet === true;
    if (!quiet) {
      loading = true;
      loadError = '';
    }
    const next: Record<number, PlanDetail> = {};
    try {
      const list = await api.monthlyPlans.list();
      const [devs, pts, invs] = await Promise.all([
        api.devices.list(),
        api.parts.list(),
        api.invoices.list(),
      ]);
      devices = devs.map((d) => ({ id: d.id, primary_name: d.primary_name }));
      parts = pts.map((x) => ({ id: x.id, name: x.name }));
      invoices = invs;

      for (const p of list) {
        const pid = Number(p.id);
        const [devsList, partsList] = await Promise.all([
          api.monthlyPlans.devices(pid),
          api.monthlyPlans.partsWithCoverage(pid),
        ]);
        next[pid] = { devices: devsList, parts: partsList };
      }
      plans = list;
      plansDetail = next;
      syncPlanExpansion(list);
      refreshDeliverDrafts();
    } catch (e) {
      console.error(e);
      loadError = (e as Error).message || 'Не удалось загрузить данные';
      plansDetail = {};
    } finally {
      if (!quiet) loading = false;
    }
  }

  async function generate() {
    try {
      await api.monthlyPlans.generate({ month: generateMonthInput + '-01', replace: true });
      generateModalOpen = false;
      await load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function updatePlan(plan: MonthlyPlan) {
    const month = String(plan.month).slice(0, 7);
    if (!confirm(`Обновить план за ${month}? Существующие данные будут пересчитаны по заказам.`)) return;
    updatingPlanId = plan.id;
    try {
      await api.monthlyPlans.generate({ month: month + '-01', replace: true });
      await load({ quiet: true });
    } catch (e) {
      alert((e as Error).message);
    } finally {
      updatingPlanId = null;
    }
  }

  async function submitDelivered(planId: number, row: MonthlyPlanPartWithCoverage) {
    const raw = deliverDraft[row.id] ?? formatIntegerQty(row.qty_delivered);
    const v = Math.round(Number(raw));
    const max = Number(row.qty_required);
    if (!Number.isFinite(v) || v < 0 || v > max) {
      alert(`Введите целое от 0 до ${formatIntegerQty(row.qty_required)}`);
      return;
    }
    savingDeliveredId = row.id;
    try {
      await api.monthlyPlans.updatePlanPartDelivered(planId, row.id, String(v));
      await load({ quiet: true });
    } catch (e) {
      alert((e as Error).message);
    } finally {
      savingDeliveredId = null;
    }
  }

  async function unlinkLink(invoiceId: number, linkId: number) {
    if (!confirm('Отвязать счёт от этой детали в плане?')) return;
    try {
      await api.invoices.parts.delete(invoiceId, linkId);
      await load({ quiet: true });
    } catch (e) {
      alert((e as Error).message);
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

  function deliveryOk(p: MonthlyPlanPartWithCoverage) {
    if (p.delivery_complete != null) return p.delivery_complete;
    return Number(p.qty_delivered ?? 0) >= Number(p.qty_required);
  }

  function coverageOk(p: MonthlyPlanPartWithCoverage) {
    if (p.coverage_complete != null) return p.coverage_complete;
    return Number(p.qty_covered_total ?? 0) >= Number(p.qty_required);
  }

  function toggleInvoiceDetails(linkId: number) {
    expandedInvoiceLinks = { ...expandedInvoiceLinks, [linkId]: !expandedInvoiceLinks[linkId] };
  }

  function planMonthKey(plan: MonthlyPlan) {
    return String(plan.month).slice(0, 7);
  }

  function latestEffectivePlanId(list: MonthlyPlan[]) {
    if (list.length === 0) return null;
    const currentMonth = new Date().toISOString().slice(0, 7);
    const candidates = list.filter((plan) => planMonthKey(plan) <= currentMonth);
    const source = candidates.length > 0 ? candidates : list;
    return [...source].sort((a, b) => planMonthKey(b).localeCompare(planMonthKey(a)))[0]?.id ?? null;
  }

  function syncPlanExpansion(list: MonthlyPlan[]) {
    if (!planExpansionInitialized) {
      const latestId = latestEffectivePlanId(list);
      expandedPlans = latestId ? { [latestId]: true } : {};
      planExpansionInitialized = true;
      return;
    }

    const validIds = new Set(list.map((plan) => Number(plan.id)));
    const next: Record<number, boolean> = {};
    for (const [id, expanded] of Object.entries(expandedPlans)) {
      const numericId = Number(id);
      if (validIds.has(numericId)) next[numericId] = expanded;
    }
    expandedPlans = next;
  }

  function togglePlan(planId: number) {
    expandedPlans = { ...expandedPlans, [planId]: !expandedPlans[planId] };
  }

  function handlePlanHeaderKeydown(event: KeyboardEvent, planId: number) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      togglePlan(planId);
    }
  }

  function planPart(planId: number | null, partId: number) {
    if (!planId) return null;
    return plansDetail[planId]?.parts?.find((p) => p.part_id === partId) ?? null;
  }

  function initialQtyByPart(planId: number, partIds: number[]) {
    const next: Record<number, string> = {};
    for (const partId of partIds) {
      const row = planPart(planId, partId);
      const remaining = Math.max(Number(row?.qty_required ?? 0) - Number(row?.qty_covered_total ?? 0), 0);
      next[partId] = formatIntegerQty(remaining);
    }
    return next;
  }

  function emptyInvoiceForm(): InvoiceCreate {
    return {
      invoice_no: '',
      invoice_date: new Date().toISOString().slice(0, 10),
      supplier: null,
      total_amount: null,
      payment_date: null,
    };
  }

  function invoicePayload(form: InvoiceCreate): InvoiceCreate {
    return {
      ...form,
      supplier: form.supplier || null,
      total_amount: form.total_amount || null,
      payment_date: form.payment_date || null,
      description: form.description || null,
      note: form.note || null,
    };
  }

  function sortInvoicesNewestFirst(list: Invoice[]): Invoice[] {
    return [...list].sort((a, b) => {
      const dd = String(b.invoice_date).localeCompare(String(a.invoice_date));
      if (dd !== 0) return dd;
      const cd = String(b.created_at).localeCompare(String(a.created_at));
      if (cd !== 0) return cd;
      return b.id - a.id;
    });
  }

  function invoiceLinkSearchHaystack(inv: Invoice): string {
    return [inv.invoice_no, inv.supplier ?? '', inv.description ?? '', inv.invoice_date, String(inv.id)].join(' ').toLowerCase();
  }

  function invoicesFilteredForLink(query: string, sorted: Invoice[]): Invoice[] {
    const q = query.trim().toLowerCase();
    if (!q) return sorted;
    return sorted.filter((inv) => invoiceLinkSearchHaystack(inv).includes(q));
  }

  $: invoicesSortedNewest = sortInvoicesNewestFirst(invoices);
  $: invoicesLinkPickerList = invoicesFilteredForLink(linkInvoiceSearchQuery, invoicesSortedNewest);

  function invoicePickSubtitle(inv: Invoice): string {
    const pay = inv.payment_date ? 'оплачен' : 'без оплаты';
    return `${formatDate(inv.invoice_date)}${inv.supplier ? ` · ${inv.supplier}` : ''} · ${pay}`;
  }

  function selectedLinkInvoiceLabel(): string {
    const inv = invoices.find((x) => x.id === linkInvoiceId);
    if (!inv) return 'Счёт не выбран';
    return `№${inv.invoice_no} · ${invoicePickSubtitle(inv)}`;
  }

  function selectInvoiceForLink(inv: Invoice) {
    linkInvoiceId = inv.id;
  }

  function openLinkModal(planId: number, partIds: number[]) {
    if (invoices.length === 0) {
      alert('Сначала создайте счёт в разделе Счета');
      return;
    }
    const newest = sortInvoicesNewestFirst(invoices);
    linkPlanId = planId;
    linkPartIds = partIds;
    linkInvoiceSearchQuery = '';
    linkInvoiceId = newest[0]?.id ?? 0;
    linkQtyByPart = initialQtyByPart(planId, partIds);
    linkModalOpen = true;
  }

  async function saveLinks() {
    if (!linkPlanId) return;
    if (!linkInvoiceId) {
      alert('Выберите счёт из списка');
      return;
    }
    try {
      for (const partId of linkPartIds) {
        await api.invoices.parts.create(linkInvoiceId, {
          plan_id: linkPlanId,
          part_id: partId,
          qty_covered: linkQtyByPart[partId] || null,
        });
      }
      linkModalOpen = false;
      await load({ quiet: true });
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function openCreateInvoiceModal(planId: number, partIds: number[]) {
    createInvoicePlanId = planId;
    createInvoicePartIds = partIds;
    createInvoiceQtyByPart = initialQtyByPart(planId, partIds);
    createInvoiceForm = emptyInvoiceForm();
    if (createInvoiceFileInput) createInvoiceFileInput.value = '';
    createInvoiceModalOpen = true;
  }

  async function saveCreateInvoice() {
    if (!createInvoicePlanId || !createInvoiceFileInput?.files?.length) {
      alert('При создании счёта обязательно приложите файл');
      return;
    }
    try {
      const inv = await api.invoices.create(invoicePayload(createInvoiceForm), createInvoiceFileInput.files[0]);
      for (const partId of createInvoicePartIds) {
        await api.invoices.parts.create(inv.id, {
          plan_id: createInvoicePlanId,
          part_id: partId,
          qty_covered: createInvoiceQtyByPart[partId] || null,
        });
      }
      createInvoiceModalOpen = false;
      await load({ quiet: true });
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function openEditInvoiceModal(inv: PartInvoiceCoverage) {
    try {
      const full = await api.invoices.get(inv.invoice_id);
      editInvoiceId = full.id;
      editInvoiceLinkId = inv.link_id;
      editInvoiceForm = {
        invoice_no: full.invoice_no,
        invoice_date: full.invoice_date,
        supplier: full.supplier ?? null,
        total_amount: full.total_amount,
        payment_date: full.payment_date ?? null,
        description: full.description ?? null,
        note: full.note ?? null,
      };
      editInvoiceLinkQty = formatIntegerQty(inv.qty_covered);
      editInvoiceModalOpen = true;
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function saveEditInvoice() {
    if (!editInvoiceId || !editInvoiceLinkId) return;
    try {
      await api.invoices.update(editInvoiceId, invoicePayload(editInvoiceForm));
      await api.invoices.parts.update(editInvoiceId, editInvoiceLinkId, {
        qty_covered: editInvoiceLinkQty || null,
      });
      editInvoiceModalOpen = false;
      await load({ quiet: true });
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
  {:else if loadError}
    <div class="rounded-xl border border-red-900/60 bg-red-950/40 p-4 text-red-200 text-sm space-y-2">
      <p class="font-medium">Ошибка загрузки</p>
      <p>{loadError}</p>
      <button type="button" on:click={() => load()} class="px-3 py-1.5 bg-zinc-700 rounded-lg hover:bg-zinc-600 text-white">
        Повторить
      </button>
    </div>
  {:else}
    <div class="space-y-6">
      {#each plans as plan (plan.id)}
        {@const data = plansDetail[Number(plan.id)]}
        {@const expanded = expandedPlans[Number(plan.id)]}
        <div class="bg-surface-800 rounded-xl border border-zinc-700 overflow-hidden">
          <div
            class="px-6 py-3 flex justify-between items-center gap-3 cursor-pointer hover:bg-zinc-800/60 {expanded ? 'border-b border-zinc-700' : ''}"
            on:click={() => togglePlan(Number(plan.id))}
            on:keydown={(event) => handlePlanHeaderKeydown(event, Number(plan.id))}
            role="button"
            tabindex="0"
            aria-expanded={expanded}
          >
            <div class="flex min-w-0 items-center gap-3">
              <span class="font-mono text-zinc-400">{expanded ? '▾' : '▸'}</span>
              <h2 class="truncate text-lg font-semibold text-white">
                {new Date(plan.month).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })}
              </h2>
            </div>
            <button
              type="button"
              on:click|stopPropagation={() => updatePlan(plan)}
              disabled={updatingPlanId === plan.id}
              class="px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 disabled:opacity-50 text-sm"
            >
              {updatingPlanId === plan.id ? 'Обновление...' : 'Обновить'}
            </button>
          </div>

          {#if expanded && data}
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
                  {#each data.devices ?? [] as d}
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
                    <th class="px-4 py-3 font-medium">Покрытие счетами</th>
                    <th class="px-4 py-3 font-medium">Поставлено</th>
                  </tr>
                </thead>
                <tbody class="divide-y divide-zinc-800">
                  {#each data.parts ?? [] as p (p.id)}
                    <tr class="hover:bg-zinc-800/30">
                      <td class="px-4 py-3 font-mono text-sm align-top">{partId(p.part_id) ?? '—'}</td>
                      <td class="px-4 py-3 align-top">{partName(p.part_id)}</td>
                      <td class="px-4 py-3 font-mono align-top">{formatQty(p.qty_required)}</td>
                      <td class="px-4 py-3 align-top">
                        <div
                          class="mb-1 rounded border px-2 py-1 text-[11px] {coverageOk(p)
                            ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-200'
                            : 'bg-red-500/15 border-red-500/40 text-red-200'}"
                        >
                          Покрыто: <span class="font-mono">{formatIntegerQty(p.qty_covered_total)}</span>
                          из <span class="font-mono">{formatIntegerQty(p.qty_required)}</span>
                        </div>
                        {#if p.has_invoice}
                          <ul class="space-y-1 text-[11px]">
                            {#each p.invoices ?? [] as inv}
                              <li
                                class="rounded border px-2 py-1 {inv.payment_date
                                  ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-100'
                                  : 'bg-red-500/15 border-red-500/40 text-red-100'}"
                              >
                                <div class="flex items-center gap-2 min-w-0">
                                  <span class="font-mono shrink-0">№{inv.invoice_no}</span>
                                  <span class="min-w-0 flex-1 truncate text-zinc-300">{inv.supplier || 'без поставщика'}</span>
                                  <span class="font-mono shrink-0">покр. {formatIntegerQty(inv.qty_covered)}</span>
                                  <span class="shrink-0">опл. {formatDate(inv.payment_date)}</span>
                                  <button
                                    type="button"
                                    class="shrink-0 text-xs text-sky-300 hover:text-sky-200 underline"
                                    on:click={() => toggleInvoiceDetails(inv.link_id)}
                                  >
                                    {expandedInvoiceLinks[inv.link_id] ? 'Скрыть' : 'Детали'}
                                  </button>
                                  <button
                                    type="button"
                                    class="shrink-0 text-xs text-amber-300 hover:text-amber-200 underline"
                                    on:click={() => openEditInvoiceModal(inv)}
                                  >
                                    Изм.
                                  </button>
                                  <button
                                    type="button"
                                    class="shrink-0 text-xs text-red-300 hover:text-red-200 underline"
                                    on:click={() => unlinkLink(inv.invoice_id, inv.link_id)}
                                  >
                                    Отвязать
                                  </button>
                                </div>
                                {#if expandedInvoiceLinks[inv.link_id]}
                                  <div class="mt-1 space-y-0.5 border-t border-white/10 pt-1 text-zinc-300">
                                    <div class="font-mono">№{inv.invoice_no}</div>
                                    {#if inv.supplier}
                                      <div>{inv.supplier}</div>
                                    {/if}
                                    <div class="font-mono">Покрыто: {formatIntegerQty(inv.qty_covered)}</div>
                                    <div class={inv.payment_date ? 'text-emerald-300' : 'text-red-300'}>
                                      оплата: {formatDate(inv.payment_date)}
                                    </div>
                                  </div>
                                {/if}
                              </li>
                            {/each}
                          </ul>
                        {/if}
                        <div class="mt-2 flex flex-wrap gap-2">
                          <button
                            type="button"
                            on:click={() => openLinkModal(plan.id, [p.part_id])}
                            class="text-amber-500 hover:text-amber-400 text-sm"
                          >
                            {p.has_invoice ? 'Привязать доп. счёт' : 'Привязать счёт'}
                          </button>
                          <button
                            type="button"
                            on:click={() => openCreateInvoiceModal(plan.id, [p.part_id])}
                            class="text-emerald-500 hover:text-emerald-400 text-sm"
                          >
                            Создать счёт
                          </button>
                        </div>
                      </td>
                      <td
                        class="px-4 py-3 align-top {deliveryOk(p)
                          ? 'bg-emerald-500/15 border-l-2 border-emerald-500/40'
                          : 'bg-red-500/15 border-l-2 border-red-500/40'}"
                      >
                        {#if !p.has_invoice}
                          <span class="text-zinc-500 text-sm">После привязки счёта</span>
                        {:else}
                          <div class="flex flex-wrap items-end gap-2">
                            <div>
                              <label class="sr-only" for="del-{p.id}">Поставлено из {p.qty_required}</label>
                              <input
                                id="del-{p.id}"
                                type="number"
                                step="1"
                                min="0"
                                max={Number(p.qty_required)}
                                value={deliverDraft[p.id] ?? ''}
                                on:input={(e) => {
                                  const el = e.currentTarget;
                                  if (el instanceof HTMLInputElement) {
                                    deliverDraft = { ...deliverDraft, [p.id]: el.value };
                                  }
                                }}
                                class="w-28 px-2 py-1.5 bg-zinc-900 border border-zinc-600 rounded text-white text-sm font-mono"
                              />
                              <span class="text-zinc-500 text-xs ml-1">из {formatIntegerQty(p.qty_required)}</span>
                            </div>
                            <button
                              type="button"
                              disabled={savingDeliveredId === p.id}
                              on:click={() => submitDelivered(plan.id, p)}
                              class="px-2 py-1.5 bg-zinc-600 text-white rounded text-xs hover:bg-zinc-500 disabled:opacity-50"
                            >
                              {savingDeliveredId === p.id ? '…' : 'Сохранить'}
                            </button>
                          </div>
                        {/if}
                      </td>
                    </tr>
                  {/each}
                </tbody>
              </table>
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

{#if editInvoiceModalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => editInvoiceModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">Редактировать счёт</h2>
      <form on:submit|preventDefault={saveEditInvoice} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Номер счёта</label>
          <input bind:value={editInvoiceForm.invoice_no} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Поставщик</label>
          <input bind:value={editInvoiceForm.supplier} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Дата</label>
          <input type="date" bind:value={editInvoiceForm.invoice_date} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Дата оплаты</label>
          <input type="date" bind:value={editInvoiceForm.payment_date} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Сумма счёта</label>
          <input type="number" step="0.01" bind:value={editInvoiceForm.total_amount} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Покрыто</label>
          <input type="number" step="1" min="0" bind:value={editInvoiceLinkQty} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
          <button type="button" on:click={() => editInvoiceModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}

{#if linkModalOpen && linkPlanId}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => linkModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-lg border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">Привязать счёт к {linkPartIds.length} деталям</h2>
      <form on:submit|preventDefault={saveLinks} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Счёт</label>
          <input
            type="search"
            bind:value={linkInvoiceSearchQuery}
            placeholder="Номер счёта, поставщик, дата или id"
            class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
          />
          <div class="mt-2 rounded-lg border border-zinc-700 bg-zinc-950/70">
            <div class="border-b border-zinc-800 px-3 py-2 text-xs text-zinc-400">
              Выбрано: <span class="text-zinc-100">{selectedLinkInvoiceLabel()}</span>
            </div>
            <div class="max-h-64 overflow-y-auto p-1">
              {#if invoicesLinkPickerList.length === 0}
                <div class="px-3 py-2 text-sm text-zinc-500">Счета не найдены</div>
              {:else}
                {#each invoicesLinkPickerList as inv}
                  <button
                    type="button"
                    on:click={() => selectInvoiceForLink(inv)}
                    class="block w-full rounded-md px-3 py-2 text-left text-sm {linkInvoiceId === inv.id
                      ? 'bg-amber-500/20 text-amber-200'
                      : 'text-zinc-200 hover:bg-zinc-800'}"
                  >
                    <div class="font-mono">№{inv.invoice_no}</div>
                    <div class="text-xs text-zinc-500">{invoicePickSubtitle(inv)}</div>
                  </button>
                {/each}
              {/if}
            </div>
          </div>
        </div>
        <div class="space-y-2">
          <label class="block text-sm text-zinc-400">Покрываемый объем</label>
          {#each linkPartIds as partId}
            <div class="flex items-center gap-2">
              <span class="min-w-0 flex-1 text-sm text-zinc-300 truncate">{partName(partId)}</span>
              <input
                type="number"
                step="1"
                min="0"
                value={linkQtyByPart[partId] ?? ''}
                on:input={(e) => {
                  const el = e.currentTarget;
                  if (el instanceof HTMLInputElement) {
                    linkQtyByPart = { ...linkQtyByPart, [partId]: el.value };
                  }
                }}
                class="w-32 px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
              />
            </div>
          {/each}
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
          <label class="block text-sm text-zinc-400 mb-1">Номер счёта</label>
          <input bind:value={createInvoiceForm.invoice_no} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Поставщик</label>
          <input bind:value={createInvoiceForm.supplier} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Дата</label>
          <input type="date" bind:value={createInvoiceForm.invoice_date} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Дата оплаты</label>
          <input type="date" bind:value={createInvoiceForm.payment_date} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Сумма</label>
          <input type="number" step="0.01" bind:value={createInvoiceForm.total_amount} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div class="space-y-2">
          <label class="block text-sm text-zinc-400">Покрываемый объем</label>
          {#each createInvoicePartIds as partId}
            <div class="flex items-center gap-2">
              <span class="min-w-0 flex-1 text-sm text-zinc-300 truncate">{partName(partId)}</span>
              <input
                type="number"
                step="1"
                min="0"
                value={createInvoiceQtyByPart[partId] ?? ''}
                on:input={(e) => {
                  const el = e.currentTarget;
                  if (el instanceof HTMLInputElement) {
                    createInvoiceQtyByPart = { ...createInvoiceQtyByPart, [partId]: el.value };
                  }
                }}
                class="w-32 px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
              />
            </div>
          {/each}
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
