<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import { formatQty, formatDate } from '$lib/format';
  import type { Invoice, InvoiceCreate, InvoicePartLink, InvoicePartLinkCreate, InvoiceFileInfo } from '$lib/api';

  let invoices: Invoice[] = [];
  let plans: { id: number; month: string }[] = [];
  let parts: { id: number; name: string }[] = [];
  let loading = true;
  let modalOpen = false;
  let form: InvoiceCreate = { invoice_no: '', invoice_date: new Date().toISOString().slice(0, 10), currency: 'RUB', status: 'received' };
  let editingId: number | null = null;
  let selectedInvoice: Invoice | null = null;
  let invoiceParts: InvoicePartLink[] = [];
  let invoiceFiles: InvoiceFileInfo[] = [];
  let partModalOpen = false;
  let partForm: InvoicePartLinkCreate = { plan_id: 0, part_id: 0, qty_covered: null, amount_allocated: null };
  let partFileInput: HTMLInputElement;
  let createFileInput: HTMLInputElement;

  onMount(load);

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

  function openCreate() {
    editingId = null;
    form = { invoice_no: '', invoice_date: new Date().toISOString().slice(0, 10), currency: 'RUB', status: 'received' };
    if (createFileInput) createFileInput.value = '';
    modalOpen = true;
  }

  function openEdit(i: Invoice) {
    editingId = i.id;
    form = { invoice_no: i.invoice_no, invoice_date: i.invoice_date, currency: i.currency, total_amount: i.total_amount, status: i.status, note: i.note };
    modalOpen = true;
  }

  async function save() {
    try {
      if (editingId) {
        await api.invoices.update(editingId, form);
      } else {
        if (!createFileInput?.files?.length) {
          alert('При создании счёта обязательно приложите файл');
          return;
        }
        const inv = await api.invoices.create(form);
        await api.invoices.upload(inv.id, createFileInput.files[0]);
      }
      modalOpen = false;
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function remove(id: number) {
    if (!confirm('Удалить счёт?')) return;
    try {
      await api.invoices.delete(id);
      load();
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function openInvoice(i: Invoice) {
    selectedInvoice = i;
    [invoiceParts, invoiceFiles] = await Promise.all([
      api.invoices.parts.list(i.id),
      api.invoices.files(i.id),
    ]);
  }

  function openAddPart() {
    if (!selectedInvoice) return;
    partForm = { plan_id: plans[0]?.id ?? 0, part_id: parts[0]?.id ?? 0, qty_covered: null, amount_allocated: null };
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
    <h1 class="text-2xl font-bold text-white">Счета</h1>
    <button on:click={openCreate} class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400 transition-colors">
      Добавить
    </button>
  </div>

  {#if loading}
    <p class="text-zinc-400">Загрузка...</p>
  {:else}
    <div class="overflow-x-auto rounded-xl border border-zinc-700">
      <table class="w-full">
        <thead class="bg-surface-800 text-zinc-400 text-left">
          <tr>
            <th class="px-4 py-3 font-medium">№ счёта</th>
            <th class="px-4 py-3 font-medium">Дата</th>
            <th class="px-4 py-3 font-medium">Сумма</th>
            <th class="px-4 py-3 font-medium">Статус</th>
            <th class="px-4 py-3 w-32"></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-zinc-800">
          {#each invoices as i}
            <tr class="hover:bg-zinc-800/50">
              <td class="px-4 py-3 font-mono">{i.invoice_no}</td>
              <td class="px-4 py-3">{formatDate(i.invoice_date)}</td>
              <td class="px-4 py-3">{formatQty(i.total_amount)}</td>
              <td class="px-4 py-3"><span class="px-2 py-0.5 rounded text-sm bg-zinc-700">{i.status}</span></td>
              <td class="px-4 py-3">
                <button on:click={() => openInvoice(i)} class="text-emerald-500 hover:text-emerald-400 mr-2">Детали</button>
                <button on:click={() => openEdit(i)} class="text-amber-500 hover:text-amber-400 mr-2">Изм.</button>
                <button on:click={() => remove(i.id)} class="text-red-400 hover:text-red-300">Удал.</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
    </div>
  {/if}
</div>

{#if selectedInvoice}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => selectedInvoice = null} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-2xl max-h-[80vh] overflow-auto border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">Счёт {selectedInvoice.invoice_no}</h2>
      <div class="mb-4">
        <h3 class="text-sm text-zinc-400 mb-2">Файлы счёта</h3>
        <div class="flex flex-wrap gap-2 items-center mb-2">
          {#each invoiceFiles as f}
            <button on:click={() => downloadFile(f.id)} class="px-3 py-1.5 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600 text-sm">
              Скачать
            </button>
          {/each}
          <input type="file" bind:this={partFileInput} class="text-sm text-zinc-400" />
          <button on:click={uploadFile} class="px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 text-sm">Загрузить</button>
        </div>
      </div>
      <button on:click={openAddPart} class="mb-4 px-3 py-1.5 bg-amber-600 text-white rounded-lg hover:bg-amber-500 text-sm">Привязать к детали</button>
      <table class="w-full">
        <thead class="text-zinc-400 text-left text-sm">
          <tr>
            <th class="px-3 py-2">План</th>
            <th class="px-3 py-2">Деталь</th>
            <th class="px-3 py-2">Кол-во</th>
            <th class="px-3 py-2">Сумма</th>
            <th></th>
          </tr>
        </thead>
        <tbody class="divide-y divide-zinc-700">
          {#each invoiceParts as lp}
            <tr>
              <td class="px-3 py-2">{planLabel(lp.plan_id)}</td>
              <td class="px-3 py-2">{partName(lp.part_id)}</td>
              <td class="px-3 py-2 font-mono">{formatQty(lp.qty_covered)}</td>
              <td class="px-3 py-2 font-mono">{formatQty(lp.amount_allocated)}</td>
              <td>
                <button on:click={() => removePart(lp.id)} class="text-red-400 text-sm">Удал.</button>
              </td>
            </tr>
          {/each}
        </tbody>
      </table>
      <button on:click={() => selectedInvoice = null} class="mt-4 px-4 py-2 bg-zinc-700 rounded-lg hover:bg-zinc-600">Закрыть</button>
    </div>
  </div>
{/if}

{#if modalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-[60]" on:click={() => modalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">{editingId ? 'Редактировать' : 'Новый счёт'}</h2>
      <form on:submit|preventDefault={save} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">№ счёта</label>
          <input bind:value={form.invoice_no} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Дата</label>
          <input type="date" bind:value={form.invoice_date} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Сумма</label>
          <input type="number" step="0.01" bind:value={form.total_amount} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Статус</label>
          <input bind:value={form.status} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        {#if !editingId}
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Файл счёта <span class="text-red-400">*</span></label>
            <input type="file" bind:this={createFileInput} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white text-sm" required />
          </div>
        {/if}
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
          <button type="button" on:click={() => modalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
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
          <input type="number" step="0.000001" bind:value={partForm.qty_covered} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Сумма</label>
          <input type="number" step="0.01" bind:value={partForm.amount_allocated} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
          <button type="button" on:click={() => partModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}
