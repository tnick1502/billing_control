<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import { formatIntegerQty, formatDate, formatAmount } from '$lib/format';
  import type { Invoice, InvoiceCreate, InvoicePartLink, InvoicePartLinkCreate, InvoiceFileInfo } from '$lib/api';

  type CalendarDay = {
    date: string;
    day: number;
    inCurrentMonth: boolean;
    isToday: boolean;
    invoices: Invoice[];
  };

  let invoices: Invoice[] = [];
  let plans: { id: number; month: string }[] = [];
  let parts: { id: number; name: string }[] = [];
  let loading = true;
  let modalOpen = false;
  let form: InvoiceCreate = {
    invoice_no: '',
    invoice_date: new Date().toISOString().slice(0, 10),
    supplier: null,
    payment_date: null,
    description: null,
  };
  let editingId: number | null = null;
  let selectedInvoice: Invoice | null = null;
  let invoiceParts: InvoicePartLink[] = [];
  let invoiceFiles: InvoiceFileInfo[] = [];
  let partModalOpen = false;
  let partForm: InvoicePartLinkCreate = { plan_id: 0, part_id: 0, qty_covered: null };
  let partFileInput: HTMLInputElement;
  let createFileInput: HTMLInputElement;
  let calendarMonth = monthKey(new Date());
  let selectedDayDate: string | null = null;
  let viewMode: 'calendar' | 'list' = 'calendar';
  let invoiceSortDir: 'asc' | 'desc' = 'desc';
  let invoiceDateFrom = '';
  let invoiceDateTo = '';
  let invoiceSupplierFilter = '';
  let invoiceListPage = 1;
  let invoiceFormSnapshot = '';
  let invoiceSaveMessage = '';
  let invoiceSaveOk = true;

  const PAGE_SIZE = 50;
  const weekDays = ['Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб', 'Вс'];

  $: calendarDays = buildCalendarDays(calendarMonth, invoices);
  $: calendarMonthLabel = monthLabel(calendarMonth);
  $: selectedDayInvoices = selectedDayDate ? invoicesForDate(selectedDayDate) : [];
  $: filteredInvoices = filterAndSortInvoices(invoices, invoiceDateFrom, invoiceDateTo, invoiceSupplierFilter, invoiceSortDir);
  $: invoiceTotalPages = Math.max(1, Math.ceil(filteredInvoices.length / PAGE_SIZE));
  $: invoiceListPage = Math.min(Math.max(invoiceListPage, 1), invoiceTotalPages);
  $: pagedInvoices = filteredInvoices.slice((invoiceListPage - 1) * PAGE_SIZE, invoiceListPage * PAGE_SIZE);
  $: invoiceFormDirty = modalOpen && serializeInvoiceForm(form) !== invoiceFormSnapshot;

  onMount(load);

  function pad2(n: number) {
    return String(n).padStart(2, '0');
  }

  function isoDate(d: Date) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}-${pad2(d.getDate())}`;
  }

  function monthKey(d: Date) {
    return `${d.getFullYear()}-${pad2(d.getMonth() + 1)}`;
  }

  function dateFromIso(date: string) {
    const [year, month, day] = date.split('-').map(Number);
    return new Date(year, month - 1, day);
  }

  function addMonths(month: string, delta: number) {
    const [year, monthNo] = month.split('-').map(Number);
    return monthKey(new Date(year, monthNo - 1 + delta, 1));
  }

  function monthLabel(month: string) {
    const [year, monthNo] = month.split('-').map(Number);
    return new Date(year, monthNo - 1, 1).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
  }

  function dayLabel(date: string) {
    return dateFromIso(date).toLocaleDateString('ru-RU', { day: 'numeric', month: 'long', year: 'numeric' });
  }

  function invoicesForDate(date: string) {
    return invoices.filter((i) => i.invoice_date === date);
  }

  function buildCalendarDays(month: string, items: Invoice[]): CalendarDay[] {
    const [year, monthNo] = month.split('-').map(Number);
    const firstDay = new Date(year, monthNo - 1, 1);
    const mondayOffset = (firstDay.getDay() + 6) % 7;
    const start = new Date(year, monthNo - 1, 1 - mondayOffset);
    const today = isoDate(new Date());
    const byDate: Record<string, Invoice[]> = {};

    for (const invoice of items) {
      (byDate[invoice.invoice_date] ??= []).push(invoice);
    }

    return Array.from({ length: 42 }, (_, idx) => {
      const d = new Date(start);
      d.setDate(start.getDate() + idx);
      const date = isoDate(d);
      const dayInvoices = [...(byDate[date] ?? [])].sort((a, b) => a.invoice_no.localeCompare(b.invoice_no, 'ru'));

      return {
        date,
        day: d.getDate(),
        inCurrentMonth: d.getMonth() === monthNo - 1,
        isToday: date === today,
        invoices: dayInvoices,
      };
    });
  }

  function filterAndSortInvoices(items: Invoice[], dateFrom: string, dateTo: string, supplierFilter: string, sortDir: 'asc' | 'desc') {
    const supplierNeedle = supplierFilter.trim().toLowerCase();
    return [...items]
      .filter((invoice) => !dateFrom || invoice.invoice_date >= dateFrom)
      .filter((invoice) => !dateTo || invoice.invoice_date <= dateTo)
      .filter((invoice) => {
        if (!supplierNeedle) return true;
        const haystack = `${invoice.supplier ?? ''} ${invoice.description ?? ''} ${invoice.invoice_no ?? ''}`.toLowerCase();
        return haystack.includes(supplierNeedle);
      })
      .sort((a, b) => {
        const byDate = a.invoice_date.localeCompare(b.invoice_date);
        if (byDate !== 0) return sortDir === 'asc' ? byDate : -byDate;
        return a.invoice_no.localeCompare(b.invoice_no, 'ru');
      });
  }

  function resetInvoiceListPage() {
    invoiceListPage = 1;
  }

  function serializeInvoiceForm(data: InvoiceCreate) {
    return JSON.stringify({
      invoice_no: data.invoice_no || '',
      invoice_date: data.invoice_date || '',
      supplier: data.supplier || null,
      total_amount: data.total_amount || null,
      payment_date: data.payment_date || null,
      description: data.description || null,
      note: data.note || null,
    });
  }

  function setInvoiceFormSnapshot() {
    invoiceFormSnapshot = serializeInvoiceForm(form);
  }

  function showPrevMonth() {
    calendarMonth = addMonths(calendarMonth, -1);
  }

  function showNextMonth() {
    calendarMonth = addMonths(calendarMonth, 1);
  }

  function showCurrentMonth() {
    calendarMonth = monthKey(new Date());
  }

  async function load() {
    loading = true;
    try {
      invoices = await api.invoices.list();
      const p = await api.monthlyPlans.list();
      plans = p.map((x) => ({ id: x.id, month: x.month }));
      const partsList = await api.parts.list();
      parts = partsList.map((x) => ({ id: x.id, name: x.name }));
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  function openCreate(date = isoDate(new Date())) {
    editingId = null;
    selectedInvoice = null;
    invoiceParts = [];
    invoiceFiles = [];
    form = {
      invoice_no: '',
      invoice_date: date,
      supplier: null,
      payment_date: null,
      description: null,
    };
    setInvoiceFormSnapshot();
    invoiceSaveMessage = '';
    if (createFileInput) createFileInput.value = '';
    modalOpen = true;
  }

  function openDayModal(date: string) {
    selectedDayDate = date;
  }

  function invoicePayload(): InvoiceCreate {
    return {
      ...form,
      supplier: form.supplier || null,
      payment_date: form.payment_date || null,
      total_amount: form.total_amount || null,
      description: form.description || null,
    };
  }

  async function save() {
    try {
      let current: Invoice;
      if (editingId) {
        current = await api.invoices.update(editingId, invoicePayload());
      } else {
        if (!createFileInput?.files?.length) {
          invoiceSaveOk = false;
          invoiceSaveMessage = 'При создании счёта обязательно приложите файл';
          return;
        }
        current = await api.invoices.create(invoicePayload());
        await api.invoices.upload(current.id, createFileInput.files[0]);
      }
      await load();
      await openInvoice(current, { preserveMessage: true });
      invoiceSaveOk = true;
      invoiceSaveMessage = 'Счёт сохранён';
    } catch (e) {
      invoiceSaveOk = false;
      invoiceSaveMessage = 'Не удалось сохранить счёт: ' + (e as Error).message;
    }
  }

  async function remove(id: number) {
    if (!confirm('Удалить счёт?')) return;
    try {
      await api.invoices.delete(id);
      if (editingId === id || selectedInvoice?.id === id) {
        modalOpen = false;
        selectedInvoice = null;
        editingId = null;
        invoiceParts = [];
        invoiceFiles = [];
        partModalOpen = false;
        invoiceSaveMessage = '';
        invoiceFormSnapshot = '';
      }
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function openInvoice(i: Invoice, opts?: { preserveMessage?: boolean }) {
    selectedDayDate = null;
    selectedInvoice = i;
    editingId = i.id;
    form = {
      invoice_no: i.invoice_no,
      invoice_date: i.invoice_date,
      supplier: i.supplier ?? null,
      total_amount: i.total_amount,
      payment_date: i.payment_date ?? null,
      description: i.description ?? null,
      note: i.note ?? null,
    };
    setInvoiceFormSnapshot();
    if (!opts?.preserveMessage) invoiceSaveMessage = '';
    modalOpen = true;
    [invoiceParts, invoiceFiles] = await Promise.all([
      api.invoices.parts.list(i.id),
      api.invoices.files(i.id),
    ]);
  }

  function closeInvoiceModal() {
    if (invoiceFormDirty && !confirm('Изменения не сохранятся. Закрыть без сохранения?')) {
      return;
    }
    modalOpen = false;
    selectedInvoice = null;
    editingId = null;
    invoiceParts = [];
    invoiceFiles = [];
    partModalOpen = false;
    invoiceSaveMessage = '';
    invoiceFormSnapshot = '';
  }

  function openAddPart() {
    if (!selectedInvoice) return;
    partForm = { plan_id: plans[0]?.id ?? 0, part_id: parts[0]?.id ?? 0, qty_covered: null };
    partModalOpen = true;
  }

  async function savePart() {
    if (!selectedInvoice) return;
    try {
      await api.invoices.parts.create(selectedInvoice.id, partForm);
      partModalOpen = false;
      invoiceParts = await api.invoices.parts.list(selectedInvoice.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function removePart(linkId: number) {
    if (!selectedInvoice || !confirm('Удалить привязку?')) return;
    try {
      await api.invoices.parts.delete(selectedInvoice.id, linkId);
      invoiceParts = await api.invoices.parts.list(selectedInvoice.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function uploadFile() {
    if (!selectedInvoice || !partFileInput?.files?.length) return;
    try {
      await api.invoices.upload(selectedInvoice.id, partFileInput.files[0]);
      partFileInput.value = '';
      invoiceFiles = await api.invoices.files(selectedInvoice.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function downloadFile(fileId: number) {
    try {
      const { url } = await api.files.presignedUrl(fileId);
      window.open(url, '_blank');
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function planLabel(id: number) {
    const p = plans.find((x) => x.id === id);
    return p ? new Date(p.month).toLocaleDateString('ru-RU', { month: 'short', year: 'numeric' }) : id;
  }
  function partName(id: number) {
    return parts.find((p) => p.id === id)?.name ?? id;
  }
</script>

<div class="p-8">
  <div class="flex justify-between items-center mb-6">
    <div>
      <h1 class="text-2xl font-bold text-white">Счета</h1>
      <p class="text-sm text-zinc-400">Календарь по дате счёта</p>
    </div>
    <div class="flex flex-wrap items-center gap-2">
      <div class="flex rounded-lg border border-zinc-700 bg-zinc-900 p-0.5">
        <button
          type="button"
          on:click={() => viewMode = 'calendar'}
          class="rounded-md px-3 py-1.5 {viewMode === 'calendar' ? 'bg-amber-500 text-black' : 'text-zinc-300 hover:bg-zinc-700'}"
        >
          Календарь
        </button>
        <button
          type="button"
          on:click={() => viewMode = 'list'}
          class="rounded-md px-3 py-1.5 {viewMode === 'list' ? 'bg-amber-500 text-black' : 'text-zinc-300 hover:bg-zinc-700'}"
        >
          Список
        </button>
      </div>
      {#if viewMode === 'calendar'}
        <button type="button" on:click={showPrevMonth} class="px-3 py-1.5 bg-zinc-800 text-white rounded-lg hover:bg-zinc-700">
          ←
        </button>
        <button type="button" on:click={showCurrentMonth} class="px-3 py-1.5 bg-zinc-800 text-white rounded-lg hover:bg-zinc-700">
          Сегодня
        </button>
        <button type="button" on:click={showNextMonth} class="px-3 py-1.5 bg-zinc-800 text-white rounded-lg hover:bg-zinc-700">
          →
        </button>
      {/if}
      <button type="button" on:click={() => openCreate()} class="px-4 py-1.5 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400 transition-colors">
        Добавить
      </button>
    </div>
  </div>

  {#if loading}
    <p class="text-zinc-400">Загрузка...</p>
  {:else if viewMode === 'calendar'}
    <div class="rounded-xl border border-zinc-600 overflow-hidden bg-zinc-950 shadow-lg shadow-black/25">
      <div class="flex items-center justify-between border-b border-zinc-700 bg-surface-800 px-4 py-2">
        <h2 class="text-lg font-semibold capitalize text-white">{calendarMonthLabel}</h2>
        <div class="flex items-center gap-3 text-xs text-zinc-300">
          <span class="inline-flex items-center gap-1 rounded bg-emerald-950 px-2 py-1 text-emerald-100"><span class="h-2 w-2 rounded-full bg-emerald-400"></span>Оплачен</span>
          <span class="inline-flex items-center gap-1 rounded bg-red-950 px-2 py-1 text-red-100"><span class="h-2 w-2 rounded-full bg-red-400"></span>Без оплаты</span>
        </div>
      </div>
      <div class="grid grid-cols-7 border-b border-zinc-700 bg-zinc-900 text-center text-xs font-semibold uppercase tracking-wide text-zinc-200">
        {#each weekDays as day}
          <div class="px-2 py-2">{day}</div>
        {/each}
      </div>
      <div class="grid grid-cols-7">
        {#each calendarDays as day}
          <div
            class="min-h-36 border-r border-b border-zinc-700 p-2 shadow-inner {day.inCurrentMonth ? 'bg-surface-800/90' : 'bg-zinc-950 text-zinc-600'}"
          >
            {#if day.inCurrentMonth}
              <div class="mb-2 flex items-center justify-between gap-1 rounded-md bg-zinc-950/70 px-1.5 py-1 ring-1 ring-zinc-700/60">
                <button
                  type="button"
                  on:click={() => openDayModal(day.date)}
                  class="h-8 min-w-8 rounded px-1 text-left font-mono text-lg font-bold leading-none {day.isToday ? 'bg-amber-400 text-black' : 'text-zinc-50 hover:bg-zinc-700'}"
                >
                  {day.day}
                </button>
                <button
                  type="button"
                  on:click={() => openCreate(day.date)}
                  class="rounded bg-zinc-700 px-1.5 py-0.5 text-[10px] font-medium text-zinc-100 hover:bg-amber-400 hover:text-black"
                >
                  + Счёт
                </button>
              </div>

              {#if day.invoices.length > 0}
                <div class="space-y-1 overflow-hidden">
                  {#each day.invoices.slice(0, 3) as invoice}
                    <button
                      type="button"
                      on:click={() => openInvoice(invoice)}
                      class="block w-full rounded border-l-4 border-y border-r px-2 py-1 text-left text-[11px] leading-tight shadow-sm transition-colors {invoice.payment_date
                        ? 'border-emerald-400 bg-emerald-950/75 text-emerald-50 hover:bg-emerald-900/80'
                        : 'border-red-400 bg-red-950/80 text-red-50 hover:bg-red-900/80'}"
                    >
                      <div class="flex items-center justify-between gap-1">
                        <span class="min-w-0 truncate font-mono">№{invoice.invoice_no}</span>
                        <span class="shrink-0 font-mono">{formatAmount(invoice.total_amount)}</span>
                      </div>
                      <div class="mt-0.5 flex items-center justify-between gap-1">
                        <span class="min-w-0 truncate text-zinc-100">{invoice.supplier || invoice.description || 'без описания'}</span>
                        <span class="shrink-0 rounded bg-black/30 px-1 text-[10px]">
                          {invoice.payment_date ? 'оплачен' : 'нет оплаты'}
                        </span>
                      </div>
                    </button>
                  {/each}
                  {#if day.invoices.length > 3}
                    <button
                      type="button"
                      on:click={() => openDayModal(day.date)}
                      class="w-full rounded bg-amber-950/60 px-2 py-1 text-left text-[11px] font-medium text-amber-100 hover:bg-amber-900/70"
                    >
                      +{day.invoices.length - 3} ещё
                    </button>
                  {/if}
                </div>
              {/if}
            {/if}
          </div>
        {/each}
      </div>
    </div>
  {:else}
    <div class="space-y-4">
      <div class="rounded-xl border border-zinc-700 bg-surface-800 p-4">
        <div class="grid gap-3 md:grid-cols-5">
          <div>
            <label class="block text-xs text-zinc-400 mb-1">Дата от</label>
            <input type="date" bind:value={invoiceDateFrom} on:input={resetInvoiceListPage} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div>
            <label class="block text-xs text-zinc-400 mb-1">Дата до</label>
            <input type="date" bind:value={invoiceDateTo} on:input={resetInvoiceListPage} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div>
            <label class="block text-xs text-zinc-400 mb-1">Поставщик / счет</label>
            <input bind:value={invoiceSupplierFilter} on:input={resetInvoiceListPage} placeholder="Поиск..." class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div>
            <label class="block text-xs text-zinc-400 mb-1">Сортировка даты</label>
            <select bind:value={invoiceSortDir} on:change={resetInvoiceListPage} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white">
              <option value="desc">Сначала новые</option>
              <option value="asc">Сначала старые</option>
            </select>
          </div>
          <div class="flex items-end">
            <button
              type="button"
              on:click={() => {
                invoiceDateFrom = '';
                invoiceDateTo = '';
                invoiceSupplierFilter = '';
                invoiceSortDir = 'desc';
                resetInvoiceListPage();
              }}
              class="w-full px-3 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600"
            >
              Сбросить
            </button>
          </div>
        </div>
      </div>

      <div class="overflow-x-auto rounded-xl border border-zinc-700 bg-surface-800">
        <table class="w-full">
          <thead class="bg-zinc-900 text-zinc-300 text-left">
            <tr>
              <th class="px-4 py-3 font-medium">Дата</th>
              <th class="px-4 py-3 font-medium">Номер счёта</th>
              <th class="px-4 py-3 font-medium">Поставщик</th>
              <th class="px-4 py-3 font-medium">Дата оплаты</th>
              <th class="px-4 py-3 font-medium">Сумма</th>
              <th class="px-4 py-3 font-medium">Описание</th>
            </tr>
          </thead>
          <tbody class="divide-y divide-zinc-800">
            {#each pagedInvoices as invoice}
              <tr on:click={() => openInvoice(invoice)} class="cursor-pointer hover:bg-zinc-800/60 {invoice.payment_date ? 'bg-emerald-950/30' : 'bg-red-950/35'}">
                <td class="px-4 py-3">{formatDate(invoice.invoice_date)}</td>
                <td class="px-4 py-3 font-mono">№{invoice.invoice_no}</td>
                <td class="px-4 py-3">{invoice.supplier || '—'}</td>
                <td class="px-4 py-3">{formatDate(invoice.payment_date)}</td>
                <td class="px-4 py-3 font-mono">{formatAmount(invoice.total_amount)}</td>
                <td class="px-4 py-3 text-zinc-400 max-w-xs truncate">{invoice.description || '—'}</td>
              </tr>
            {/each}
          </tbody>
        </table>
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-zinc-700 bg-surface-800 px-4 py-3 text-sm text-zinc-300">
        <div>
          Показано {pagedInvoices.length} из {filteredInvoices.length}, страница {invoiceListPage} из {invoiceTotalPages}
        </div>
        <div class="flex gap-2">
          <button type="button" disabled={invoiceListPage <= 1} on:click={() => invoiceListPage -= 1} class="px-3 py-1.5 bg-zinc-700 rounded-lg hover:bg-zinc-600 disabled:opacity-40">
            Назад
          </button>
          <button type="button" disabled={invoiceListPage >= invoiceTotalPages} on:click={() => invoiceListPage += 1} class="px-3 py-1.5 bg-zinc-700 rounded-lg hover:bg-zinc-600 disabled:opacity-40">
            Вперед
          </button>
        </div>
      </div>
    </div>
  {/if}
</div>

{#if selectedDayDate}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-40" on:click={() => selectedDayDate = null} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-3xl max-h-[80vh] overflow-auto border border-zinc-700" on:click|stopPropagation role="dialog">
      <div class="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-white">Счета за {dayLabel(selectedDayDate)}</h2>
          <p class="text-sm text-zinc-400">Всего: {selectedDayInvoices.length}</p>
        </div>
        <button
          type="button"
          on:click={() => {
            const date = selectedDayDate ?? isoDate(new Date());
            selectedDayDate = null;
            openCreate(date);
          }}
          class="px-3 py-1.5 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400"
        >
          + Счёт
        </button>
      </div>

      {#if selectedDayInvoices.length === 0}
        <div class="rounded-xl border border-dashed border-zinc-700 p-6 text-center text-zinc-400">
          На этот день счетов нет.
        </div>
      {:else}
        <div class="space-y-2">
          {#each selectedDayInvoices as invoice}
            <div
              class="rounded-xl border p-3 {invoice.payment_date
                ? 'border-emerald-400/70 bg-emerald-950/75'
                : 'border-red-400/70 bg-red-950/80'}"
            >
              <div class="flex flex-wrap items-center gap-2">
                <span class="font-mono text-white">№{invoice.invoice_no}</span>
                <span class="min-w-0 flex-1 truncate text-zinc-300">{invoice.supplier || invoice.description || 'без описания'}</span>
                <span class="font-mono text-zinc-200">{formatAmount(invoice.total_amount)}</span>
                <span class="rounded px-2 py-0.5 font-medium {invoice.payment_date ? 'bg-emerald-500/20 text-emerald-100' : 'bg-red-500/25 text-red-100'}">
                  оплата: {formatDate(invoice.payment_date)}
                </span>
              </div>
              <div class="mt-2 flex flex-wrap gap-2 text-sm">
                <button
                  type="button"
                  on:click={() => {
                    selectedDayDate = null;
                    openInvoice(invoice);
                  }}
                  class="text-emerald-300 hover:text-emerald-200 underline"
                >
                  Открыть
                </button>
              </div>
            </div>
          {/each}
        </div>
      {/if}

      <button on:click={() => selectedDayDate = null} class="mt-4 px-4 py-2 bg-zinc-700 rounded-lg hover:bg-zinc-600">Закрыть</button>
    </div>
  </div>
{/if}

{#if modalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-[60]" on:click={closeInvoiceModal} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-5xl max-h-[86vh] overflow-auto border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">{editingId ? `Счёт №${form.invoice_no}` : 'Новый счёт'}</h2>

      <form on:submit|preventDefault={save} class="rounded-xl border border-zinc-700 bg-zinc-900/35 p-4">
        <div class="grid gap-4 md:grid-cols-2">
          {#if editingId}
            <div>
              <label class="block text-sm text-zinc-400 mb-1">Порядковый номер</label>
              <input value={String(editingId)} readonly class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-zinc-400" />
            </div>
          {/if}
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Номер счёта</label>
            <input bind:value={form.invoice_no} class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-white" required />
          </div>
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Поставщик</label>
            <input bind:value={form.supplier} class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Дата</label>
            <input type="date" bind:value={form.invoice_date} class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-white" required />
          </div>
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Дата оплаты</label>
            <input type="date" bind:value={form.payment_date} class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Сумма</label>
            <input type="number" step="0.01" bind:value={form.total_amount} class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div class="md:col-span-2">
            <label class="block text-sm text-zinc-400 mb-1">Описание</label>
            <textarea
              bind:value={form.description}
              rows="2"
              placeholder="Опционально"
              class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-white"
            ></textarea>
          </div>
        </div>

        {#if !editingId}
          <div class="mt-4">
            <label class="block text-sm text-zinc-400 mb-1">Файл счёта <span class="text-red-400">*</span></label>
            <input type="file" bind:this={createFileInput} class="w-full px-3 py-2 bg-zinc-950 border border-zinc-700 rounded-lg text-white text-sm" required />
          </div>
        {/if}

        <div class="flex flex-wrap gap-2 pt-4">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">
            {selectedInvoice ? 'Сохранить счёт' : 'Создать счёт'}
          </button>
          <button type="button" on:click={closeInvoiceModal} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Закрыть</button>
          {#if selectedInvoice}
            <button type="button" on:click={() => remove(selectedInvoice.id)} class="ml-auto px-4 py-2 bg-red-700 text-white rounded-lg hover:bg-red-600">Удалить</button>
          {/if}
        </div>
        {#if invoiceSaveMessage}
          <div class="mt-3 rounded-lg border px-3 py-2 text-sm {invoiceSaveOk ? 'border-emerald-500/50 bg-emerald-950/60 text-emerald-100' : 'border-red-500/50 bg-red-950/60 text-red-100'}">
            {invoiceSaveMessage}
          </div>
        {/if}
      </form>

      <div class="mt-5 rounded-xl border border-zinc-700 bg-zinc-950/30 p-4">
        <div class="mb-4 flex flex-wrap items-center justify-between gap-2">
          <h3 class="text-base font-semibold text-white">Файлы и привязки счёта</h3>
          {#if selectedInvoice}
            <button on:click={openAddPart} class="px-3 py-1.5 bg-amber-600 text-white rounded-lg hover:bg-amber-500 text-sm">Привязать к детали</button>
          {/if}
        </div>

        {#if !selectedInvoice}
          <div class="rounded-lg border border-dashed border-zinc-700 p-4 text-zinc-400">
            Сначала создайте счёт, затем в этом же окне появятся файлы и привязки к деталям.
          </div>
        {:else}
          <div class="mb-4">
            <h4 class="text-sm text-zinc-400 mb-2">Файлы счёта</h4>
            <div class="flex flex-wrap gap-2 items-center">
              {#each invoiceFiles as f}
                <button on:click={() => downloadFile(f.id)} class="px-3 py-1.5 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600 text-sm">
                  Скачать
                </button>
              {/each}
              <input type="file" bind:this={partFileInput} class="text-sm text-zinc-400" />
              <button on:click={uploadFile} class="px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 text-sm">Загрузить</button>
            </div>
          </div>

          <h4 class="text-sm text-zinc-400 mb-2">Привязки к деталям</h4>
          <table class="w-full">
            <thead class="text-zinc-400 text-left text-sm">
              <tr>
                <th class="px-3 py-2">План</th>
                <th class="px-3 py-2">Деталь</th>
                <th class="px-3 py-2">Кол-во</th>
                <th></th>
              </tr>
            </thead>
            <tbody class="divide-y divide-zinc-700">
              {#each invoiceParts as lp}
                <tr>
                  <td class="px-3 py-2">{planLabel(lp.plan_id)}</td>
                  <td class="px-3 py-2">{partName(lp.part_id)}</td>
                  <td class="px-3 py-2 font-mono">{formatIntegerQty(lp.qty_covered)}</td>
                  <td>
                    <button on:click={() => removePart(lp.id)} class="text-red-400 text-sm">Удал.</button>
                  </td>
                </tr>
              {/each}
            </tbody>
          </table>
        {/if}
      </div>
    </div>
  </div>
{/if}

{#if partModalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-[70]" on:click={() => partModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">Привязать к детали</h2>
      <form on:submit|preventDefault={savePart} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">План</label>
          <select bind:value={partForm.plan_id} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required>
            {#each plans as p}
              <option value={p.id}>{new Date(p.month).toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' })}</option>
            {/each}
          </select>
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Деталь</label>
          <select bind:value={partForm.part_id} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required>
            {#each parts as p}
              <option value={p.id}>{p.name}</option>
            {/each}
          </select>
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Кол-во покрыто</label>
          <input type="number" step="1" bind:value={partForm.qty_covered} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
          <button type="button" on:click={() => partModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}
