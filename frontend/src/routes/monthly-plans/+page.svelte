<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import { formatQty, formatIntegerQty, formatAmount, formatDate, formatDateTime, formatFileSize } from '$lib/format';
  import type { MonthlyPlan, MonthlyPlanDevice, MonthlyPlanPartWithCoverage, InvoiceCreate, Invoice, PartInvoiceCoverage, InvoiceFileInfo, PlanPartFile, RemaindersMatrix, RemainderPart, UndersupplyPart } from '$lib/api';

  type PlanDetail = { devices: MonthlyPlanDevice[]; parts: MonthlyPlanPartWithCoverage[] };

  const NO_TYPE_LABEL = 'Без типа';
  const PART_GROUPS_STORAGE_KEY = 'monthly-plans:expandedPartGroups:v2';
  const PART_NAME_COLLATOR = new Intl.Collator('ru', { sensitivity: 'base', numeric: true });

  let plans: MonthlyPlan[] = [];
  let selectedMonth: string = new Date().toISOString().slice(0, 7);
  let selectedPlanDetail: PlanDetail | null = null;
  let selectedPlanLoading = false;
  let initialized = false;

  let devices: { id: number; primary_name: string }[] = [];
  let parts: { id: number; name: string; part_type: string | null; supplier: string | null }[] = [];
  let invoices: Invoice[] = [];
  let expandedPartGroups: Record<string, boolean> = loadExpandedPartGroups();

  $: selectedPlan = plans.find((p) => planMonthKey(p) === selectedMonth) ?? null;

  function loadExpandedPartGroups(): Record<string, boolean> {
    if (typeof localStorage === 'undefined') return {};
    try {
      const raw = localStorage.getItem(PART_GROUPS_STORAGE_KEY);
      return raw ? JSON.parse(raw) : {};
    } catch {
      return {};
    }
  }

  function saveExpandedPartGroups() {
    if (typeof localStorage === 'undefined') return;
    try {
      localStorage.setItem(PART_GROUPS_STORAGE_KEY, JSON.stringify(expandedPartGroups));
    } catch {
      /* ignore */
    }
  }

  let remaindersModalOpen = false;
  let remaindersLoading = false;
  let remaindersError = '';
  let remaindersData: RemaindersMatrix | null = null;
  let expandedRemainderGroups: Record<string, boolean> = {};
  let expandedRemainderParts: Record<number, boolean> = {};

  let loading = true;
  let loadError = '';
  let generateModalOpen = false;
  let generateMonthInput = new Date().toISOString().slice(0, 7);
  let updatingPlanId: number | null = null;
  let exportingPlanId: number | null = null;

  let deliverDraft: Record<number, string> = {};
  let savingDeliveredId: number | null = null;

  let finalDraft: Record<number, string> = {};
  let savingFinalId: number | null = null;

  let uploadingFilesPartId: number | null = null;
  let planPartFileInputs: Record<number, HTMLInputElement> = {};

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
  let editInvoicePlanId = 0;
  let editInvoicePlanPartId = 0;
  let editInvoiceForm: InvoiceCreate = emptyInvoiceForm();
  let editInvoiceLinkQty = '';
  let expandedInvoiceLinks: Record<number, boolean> = {};
  let invoiceFilesCache: Record<number, InvoiceFileInfo[]> = {};
  let planPartRefreshVersions: Record<number, number> = {};

  function refreshDeliverDrafts() {
    const d: Record<number, string> = {};
    const f: Record<number, string> = {};
    selectedPlanDetail?.parts?.forEach((p) => {
      d[p.id] = formatIntegerQty(p.qty_delivered);
      f[p.id] = formatIntegerQty(p.qty_final);
    });
    deliverDraft = d;
    finalDraft = f;
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
    try {
      const [list, devs, pts, invs] = await Promise.all([
        api.monthlyPlans.list(),
        api.devices.list(),
        api.parts.list(true),
        api.invoices.list(),
      ]);
      devices = devs.map((d) => ({ id: d.id, primary_name: d.primary_name }));
      parts = pts.map((x) => ({
        id: x.id,
        name: x.name,
        part_type: x.part_type,
        supplier: x.supplier,
      }));
      invoices = invs;
      plans = list;

      if (!initialized) {
        const latestId = latestEffectivePlanId(list);
        if (latestId) {
          const latest = list.find((p) => p.id === latestId);
          if (latest) selectedMonth = planMonthKey(latest);
        }
        initialized = true;
      }

      const plan = list.find((p) => planMonthKey(p) === selectedMonth);
      if (plan) {
        await loadPlanDetail(plan.id);
      } else {
        selectedPlanDetail = null;
        deliverDraft = {};
      }
    } catch (e) {
      console.error(e);
      loadError = (e as Error).message || 'Не удалось загрузить данные';
      selectedPlanDetail = null;
    } finally {
      if (!quiet) loading = false;
    }
  }

  async function loadPlanDetail(planId: number) {
    selectedPlanLoading = true;
    try {
      const [devsList, partsList] = await Promise.all([
        api.monthlyPlans.devices(planId),
        api.monthlyPlans.partsWithCoverage(planId),
      ]);
      selectedPlanDetail = { devices: devsList, parts: partsList };
      refreshDeliverDrafts();
    } catch (e) {
      selectedPlanDetail = null;
    } finally {
      selectedPlanLoading = false;
    }
  }

  async function refreshPlanPartRows(
    planId: number,
    planPartIds: number[],
  ): Promise<MonthlyPlanPartWithCoverage[]> {
    const uniqueIds = [...new Set(planPartIds.filter((id) => id > 0))];
    if (uniqueIds.length === 0) return [];

    const requestVersions = new Map<number, number>();
    for (const id of uniqueIds) {
      const version = (planPartRefreshVersions[id] ?? 0) + 1;
      planPartRefreshVersions[id] = version;
      requestVersions.set(id, version);
    }

    const freshRows = uniqueIds.length === 1
      ? [await api.monthlyPlans.partWithCoverage(planId, uniqueIds[0])]
      : await api.monthlyPlans.partsWithCoverageByIds(planId, uniqueIds);

    // The user may have changed the month while the request was in flight.
    if (!selectedPlanDetail || currentPlanId !== planId) return [];

    const applicableRows = freshRows.filter(
      (row) => planPartRefreshVersions[row.id] === requestVersions.get(row.id),
    );
    const freshById = new Map<number, MonthlyPlanPartWithCoverage>();
    for (const row of applicableRows) freshById.set(row.id, row);
    if (freshById.size === 0) return [];

    // Keep the detail object and every unaffected keyed row stable in the DOM.
    selectedPlanDetail = {
      ...selectedPlanDetail,
      parts: selectedPlanDetail.parts.map((row) => freshById.get(row.id) ?? row),
    };
    return applicableRows;
  }

  function planPartIdsForParts(planId: number, partIds: number[]): number[] {
    if (!selectedPlanDetail || currentPlanId !== planId) return [];
    const wanted = new Set(partIds);
    return selectedPlanDetail.parts
      .filter((row) => wanted.has(row.part_id))
      .map((row) => row.id);
  }

  function planPartIdsForInvoice(planId: number, invoiceId: number): number[] {
    if (!selectedPlanDetail || currentPlanId !== planId) return [];
    return selectedPlanDetail.parts
      .filter((row) => row.invoices?.some((invoice) => invoice.invoice_id === invoiceId))
      .map((row) => row.id);
  }

  async function navigateTo(month: string) {
    selectedMonth = month;
    selectedPlanDetail = null;
    deliverDraft = {};
    const plan = plans.find((p) => planMonthKey(p) === month);
    if (plan) {
      await loadPlanDetail(plan.id);
    }
  }

  function prevMonth() {
    const [y, m] = selectedMonth.split('-').map(Number);
    const d = new Date(y, m - 2);
    navigateTo(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  }

  function nextMonth() {
    const [y, m] = selectedMonth.split('-').map(Number);
    const d = new Date(y, m);
    navigateTo(`${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`);
  }

  async function generate() {
    try {
      await api.monthlyPlans.generate({ month: generateMonthInput + '-01', replace: true });
      generateModalOpen = false;
      selectedMonth = generateMonthInput;
      await load({ quiet: true });
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function updatePlan() {
    if (!selectedPlan) return;
    if (!confirm(`Обновить план за ${monthLabel(selectedMonth)}? Данные будут пересчитаны по заказам.`)) return;
    updatingPlanId = selectedPlan.id;
    try {
      await api.monthlyPlans.generate({ month: selectedMonth + '-01', replace: true });
      await load({ quiet: true });
    } catch (e) {
      alert((e as Error).message);
    } finally {
      updatingPlanId = null;
    }
  }

  async function exportPlan() {
    if (!selectedPlan) return;
    exportingPlanId = selectedPlan.id;
    try {
      const { blob, filename } = await api.monthlyPlans.exportExcel(selectedPlan.id);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      exportingPlanId = null;
    }
  }

  function effectiveTarget(p: MonthlyPlanPartWithCoverage): number {
    return Number(p.qty_final ?? p.qty_required);
  }

  async function submitDelivered(planId: number, row: MonthlyPlanPartWithCoverage) {
    const raw = deliverDraft[row.id] ?? formatIntegerQty(row.qty_delivered);
    const v = Math.round(Number(raw));
    const max = effectiveTarget(row);
    if (!Number.isFinite(v) || v < 0 || v > max) {
      alert(`Введите целое от 0 до ${formatIntegerQty(String(max))}`);
      return;
    }
    savingDeliveredId = row.id;
    try {
      await api.monthlyPlans.updatePlanPartDelivered(planId, row.id, String(v));
      const [fresh] = await refreshPlanPartRows(planId, [row.id]);
      if (fresh) {
        deliverDraft = { ...deliverDraft, [fresh.id]: formatIntegerQty(fresh.qty_delivered) };
      }
    } catch (e) {
      alert((e as Error).message);
    } finally {
      savingDeliveredId = null;
    }
  }

  async function submitFinal(planId: number, row: MonthlyPlanPartWithCoverage) {
    const raw = finalDraft[row.id] ?? formatIntegerQty(row.qty_final);
    const v = Math.round(Number(raw));
    if (!Number.isFinite(v) || v < 0) {
      alert('Введите целое ≥ 0');
      return;
    }
    savingFinalId = row.id;
    try {
      await api.monthlyPlans.updatePlanPartFinal(planId, row.id, String(v));
      const [fresh] = await refreshPlanPartRows(planId, [row.id]);
      if (fresh) {
        finalDraft = { ...finalDraft, [fresh.id]: formatIntegerQty(fresh.qty_final) };
        deliverDraft = { ...deliverDraft, [fresh.id]: formatIntegerQty(fresh.qty_delivered) };
      }
    } catch (e) {
      alert((e as Error).message);
    } finally {
      savingFinalId = null;
    }
  }

  async function unlinkLink(invoiceId: number, linkId: number, planPartId: number) {
    if (!confirm('Отвязать счёт от этой детали в плане?')) return;
    const planId = currentPlanId;
    try {
      await api.invoices.parts.delete(invoiceId, linkId);
      await refreshPlanPartRows(planId, [planPartId]);
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
    return parts.find((p) => p.id === id)?.name ?? String(id);
  }
  function partId(id: number) {
    return parts.find((p) => p.id === id)?.id ?? id;
  }
  function partSupplier(id: number) {
    return parts.find((p) => p.id === id)?.supplier?.trim() || '—';
  }
  function partTypeOf(id: number): string {
    const t = (parts.find((p) => p.id === id)?.part_type ?? '').trim();
    return t || NO_TYPE_LABEL;
  }

  function groupPlanParts(items: MonthlyPlanPartWithCoverage[]): Record<string, MonthlyPlanPartWithCoverage[]> {
    const groups: Record<string, MonthlyPlanPartWithCoverage[]> = {};
    for (const p of items) {
      const key = partTypeOf(p.part_id);
      (groups[key] ??= []).push(p);
    }
    for (const group of Object.values(groups)) {
      group.sort(
        (a, b) =>
          PART_NAME_COLLATOR.compare(partName(a.part_id), partName(b.part_id)) ||
          a.part_id - b.part_id,
      );
    }
    return groups;
  }

  function comparePartGroupKeys(a: string, b: string) {
    if (a === NO_TYPE_LABEL) return 1;
    if (b === NO_TYPE_LABEL) return -1;
    return PART_NAME_COLLATOR.compare(a, b);
  }

  $: currentPlanId = selectedPlan ? Number(selectedPlan.id) : 0;
  $: planPartGroups = selectedPlanDetail ? groupPlanParts(selectedPlanDetail.parts ?? []) : {} as Record<string, MonthlyPlanPartWithCoverage[]>;
  $: planPartGroupKeys = Object.keys(planPartGroups).sort(comparePartGroupKeys);

  function partGroupStateKey(planId: number, key: string): string {
    return `${planId}:${key}`;
  }

  function isPartGroupExpanded(planId: number, key: string): boolean {
    return expandedPartGroups[partGroupStateKey(planId, key)] !== false;
  }

  function togglePartGroup(planId: number, key: string) {
    const stateKey = partGroupStateKey(planId, key);
    expandedPartGroups = { ...expandedPartGroups, [stateKey]: !isPartGroupExpanded(planId, key) };
    saveExpandedPartGroups();
  }

  function toggleAllPartGroups(planId: number, keys: string[]) {
    const anyExpanded = keys.some((k) => isPartGroupExpanded(planId, k));
    const next = !anyExpanded;
    const patch = Object.fromEntries(keys.map((k) => [partGroupStateKey(planId, k), next]));
    expandedPartGroups = { ...expandedPartGroups, ...patch };
    saveExpandedPartGroups();
  }

  async function openRemainders() {
    remaindersModalOpen = true;
    remaindersLoading = true;
    remaindersError = '';
    try {
      remaindersData = await api.monthlyPlans.remainders();
    } catch (e) {
      remaindersError = (e as Error).message || 'Не удалось загрузить остатки';
      remaindersData = null;
    } finally {
      remaindersLoading = false;
    }
  }

  function monthLabel(m: string): string {
    const parts2 = m.slice(0, 7).split('-');
    if (parts2.length < 2) return m;
    const d = new Date(Number(parts2[0]), Number(parts2[1]) - 1);
    return d.toLocaleDateString('ru-RU', { month: 'long', year: 'numeric' });
  }

  function typeOfPart(part_type: string | null): string {
    return (part_type ?? '').trim() || NO_TYPE_LABEL;
  }

  function isRemainderGroupExpanded(key: string): boolean {
    return expandedRemainderGroups[key] !== false;
  }

  function toggleRemainderGroup(key: string) {
    expandedRemainderGroups = { ...expandedRemainderGroups, [key]: !isRemainderGroupExpanded(key) };
  }

  function toggleRemainderPart(partId: number) {
    expandedRemainderParts = { ...expandedRemainderParts, [partId]: !expandedRemainderParts[partId] };
  }

  $: remainderGroups = (() => {
    if (!remaindersData) return [] as { type: string; parts: RemainderPart[] }[];
    const byType: Record<string, RemainderPart[]> = {};
    for (const p of remaindersData.remainders) (byType[typeOfPart(p.part_type)] ??= []).push(p);
    return Object.keys(byType).sort(comparePartGroupKeys).map((type) => ({
      type,
      parts: byType[type].sort(
        (a, b) => PART_NAME_COLLATOR.compare(a.name, b.name) || a.part_id - b.part_id,
      ),
    }));
  })();

  $: undersupplyGroups = (() => {
    if (!remaindersData) return [] as { type: string; parts: UndersupplyPart[] }[];
    const byType: Record<string, UndersupplyPart[]> = {};
    for (const p of remaindersData.undersupply) (byType[typeOfPart(p.part_type)] ??= []).push(p);
    return Object.keys(byType).sort(comparePartGroupKeys).map((type) => ({
      type,
      parts: byType[type].sort(
        (a, b) => PART_NAME_COLLATOR.compare(a.name, b.name) || a.part_id - b.part_id,
      ),
    }));
  })();

  function deliveryOk(p: MonthlyPlanPartWithCoverage) {
    if (p.delivery_complete != null) return p.delivery_complete;
    return Number(p.qty_delivered ?? 0) >= effectiveTarget(p);
  }

  function coverageOk(p: MonthlyPlanPartWithCoverage) {
    if (p.coverage_complete != null) return p.coverage_complete;
    return Number(p.qty_covered_total ?? 0) >= effectiveTarget(p);
  }

  async function toggleInvoiceDetails(inv: PartInvoiceCoverage) {
    const wasExpanded = expandedInvoiceLinks[inv.link_id];
    expandedInvoiceLinks = { ...expandedInvoiceLinks, [inv.link_id]: !wasExpanded };
    if (!wasExpanded && !(inv.invoice_id in invoiceFilesCache)) {
      try {
        const files = await api.invoices.files(inv.invoice_id);
        invoiceFilesCache = { ...invoiceFilesCache, [inv.invoice_id]: files };
      } catch {
        invoiceFilesCache = { ...invoiceFilesCache, [inv.invoice_id]: [] };
      }
    }
  }

  async function downloadFile(fileId: number, suggestedFilename?: string) {
    try {
      const blob = await api.files.downloadBlob(fileId);
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = suggestedFilename?.trim() || `file-${fileId}`;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    } catch (e) {
      alert((e as Error).message);
    }
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

  function planPart(planId: number | null, partId: number) {
    if (!planId) return null;
    return selectedPlanDetail?.parts?.find((p) => p.part_id === partId) ?? null;
  }

  function initialQtyByPart(planId: number, partIds: number[]) {
    const next: Record<number, string> = {};
    for (const pid of partIds) {
      const row = planPart(planId, pid);
      const target = row ? effectiveTarget(row) : 0;
      const remaining = Math.max(target - Number(row?.qty_covered_total ?? 0), 0);
      next[pid] = formatIntegerQty(remaining);
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
    const planId = linkPlanId;
    const planPartIds = planPartIdsForParts(planId, linkPartIds);
    try {
      for (const pid of linkPartIds) {
        await api.invoices.parts.create(linkInvoiceId, {
          plan_id: planId,
          part_id: pid,
          qty_covered: linkQtyByPart[pid] || null,
        });
      }
      linkModalOpen = false;
      await refreshPlanPartRows(planId, planPartIds);
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
    const planId = createInvoicePlanId;
    const planPartIds = planPartIdsForParts(planId, createInvoicePartIds);
    try {
      const inv = await api.invoices.create(invoicePayload(createInvoiceForm), createInvoiceFileInput.files[0]);
      invoices = [inv, ...invoices.filter((item) => item.id !== inv.id)];
      for (const pid of createInvoicePartIds) {
        await api.invoices.parts.create(inv.id, {
          plan_id: planId,
          part_id: pid,
          qty_covered: createInvoiceQtyByPart[pid] || null,
        });
      }
      createInvoiceModalOpen = false;
      await refreshPlanPartRows(planId, planPartIds);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function openEditInvoiceModal(inv: PartInvoiceCoverage, planPartId: number) {
    const planId = currentPlanId;
    try {
      const full = await api.invoices.get(inv.invoice_id);
      editInvoiceId = full.id;
      editInvoiceLinkId = inv.link_id;
      editInvoicePlanId = planId;
      editInvoicePlanPartId = planPartId;
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
    if (!editInvoiceId || !editInvoiceLinkId || !editInvoicePlanId || !editInvoicePlanPartId) return;
    const planId = editInvoicePlanId;
    const affectedPlanPartIds = [
      ...new Set([
        editInvoicePlanPartId,
        ...planPartIdsForInvoice(planId, editInvoiceId),
      ]),
    ];
    try {
      const updatedInvoice = await api.invoices.update(editInvoiceId, invoicePayload(editInvoiceForm));
      invoices = invoices.map((invoice) =>
        invoice.id === updatedInvoice.id ? updatedInvoice : invoice,
      );
      await api.invoices.parts.update(editInvoiceId, editInvoiceLinkId, {
        qty_covered: editInvoiceLinkQty || null,
      });
      editInvoiceModalOpen = false;
      await refreshPlanPartRows(planId, affectedPlanPartIds);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function uploadPlanPartFiles(planId: number, planPartId: number, files: FileList) {
    if (!files.length) return;
    uploadingFilesPartId = planPartId;
    try {
      await api.monthlyPlans.partFiles.upload(planId, planPartId, files);
      await refreshPlanPartRows(planId, [planPartId]);
    } catch (e) {
      alert((e as Error).message);
    } finally {
      uploadingFilesPartId = null;
      const inp = planPartFileInputs[planPartId];
      if (inp) inp.value = '';
    }
  }

  async function deletePlanPartFile(planId: number, planPartId: number, fileId: number) {
    if (!confirm('Удалить файл?')) return;
    try {
      await api.monthlyPlans.partFiles.delete(planId, planPartId, fileId);
      await refreshPlanPartRows(planId, [planPartId]);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function handlePlanPartFileInput(planId: number, planPartId: number, e: Event) {
    const files = (e.currentTarget as HTMLInputElement).files;
    if (files?.length) uploadPlanPartFiles(planId, planPartId, files);
  }
</script>

<div class="p-8">
  <!-- Header -->
  <div class="flex flex-wrap justify-between items-start gap-4 mb-6">
    <div>
      <h1 class="text-2xl font-bold text-white mb-4">Месячные планы</h1>
      <!-- Month navigator -->
      <div class="flex items-center gap-2">
        <button
          type="button"
          on:click={prevMonth}
          class="flex h-9 w-9 items-center justify-center rounded-lg bg-zinc-700 text-white hover:bg-zinc-600 transition-colors text-lg leading-none"
          aria-label="Предыдущий месяц"
        >‹</button>

        <div class="flex h-9 min-w-[200px] items-center justify-center rounded-lg border border-zinc-700 bg-zinc-800 px-4">
          <span class="text-sm font-semibold text-white capitalize">{monthLabel(selectedMonth)}</span>
        </div>

        <button
          type="button"
          on:click={nextMonth}
          class="flex h-9 w-9 items-center justify-center rounded-lg bg-zinc-700 text-white hover:bg-zinc-600 transition-colors text-lg leading-none"
          aria-label="Следующий месяц"
        >›</button>

        {#if selectedPlan}
          <span class="text-xs font-medium text-emerald-400">● план есть</span>
        {:else if !loading}
          <span class="text-xs text-zinc-500">нет плана</span>
        {/if}
      </div>
    </div>

    <div class="flex items-center gap-2 flex-wrap">
      {#if selectedPlan}
        <button
          type="button"
          on:click={exportPlan}
          disabled={exportingPlanId !== null}
          class="px-4 py-2 bg-sky-700 text-white font-medium rounded-lg hover:bg-sky-600 disabled:opacity-50 transition-colors text-sm"
        >
          {exportingPlanId !== null ? 'Готовим Excel…' : 'Выгрузить Excel'}
        </button>
        <button
          type="button"
          on:click={updatePlan}
          disabled={updatingPlanId !== null}
          class="px-4 py-2 bg-emerald-600 text-white font-medium rounded-lg hover:bg-emerald-500 disabled:opacity-50 transition-colors text-sm"
        >
          {updatingPlanId !== null ? 'Обновление...' : 'Обновить план'}
        </button>
      {/if}
      <button on:click={openRemainders} class="px-4 py-2 bg-zinc-700 text-white font-medium rounded-lg hover:bg-zinc-600 transition-colors text-sm">
        Остатки деталей
      </button>
    </div>
  </div>

  <!-- Main content -->
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
  {:else if !selectedPlan}
    <div class="rounded-xl border border-zinc-700 bg-zinc-800/40 p-8 text-center">
      <p class="text-zinc-400 mb-3">Нет плана за {monthLabel(selectedMonth)}</p>
      <button
        type="button"
        on:click={() => { generateMonthInput = selectedMonth; generateModalOpen = true; }}
        class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400 transition-colors text-sm"
      >
        Сгенерировать план
      </button>
    </div>
  {:else if selectedPlanLoading}
    <p class="text-zinc-400">Загрузка плана...</p>
  {:else if selectedPlanDetail}
    <!-- Devices -->
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
        {#each selectedPlanDetail.devices ?? [] as d}
          <tr class="hover:bg-zinc-800/50">
            <td class="px-4 py-3 font-mono text-sm">{deviceId(d.device_id) ?? '—'}</td>
            <td class="px-4 py-3">{deviceName(d.device_id)}</td>
            <td class="px-4 py-3 font-mono">{formatQty(d.qty_total)}</td>
          </tr>
        {/each}
      </tbody>
    </table>

    <!-- Parts grouped by type -->
    <div class="flex items-center justify-between mb-2">
      <h3 class="text-sm font-medium text-zinc-400">Детали</h3>
      {#if planPartGroupKeys.length > 0}
        <button
          type="button"
          on:click={() => toggleAllPartGroups(currentPlanId, planPartGroupKeys)}
          class="flex items-center gap-1.5 rounded-lg border border-zinc-700 bg-zinc-800 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-700 hover:text-white transition-colors"
        >
          {#if planPartGroupKeys.some((k) => expandedPartGroups[`${currentPlanId}:${k}`] !== false)}
            <span class="text-[10px] leading-none">▴▾</span> Свернуть все
          {:else}
            <span class="text-[10px] leading-none">▾▴</span> Развернуть все
          {/if}
        </button>
      {/if}
    </div>
    <div class="space-y-3">
      {#each planPartGroupKeys as groupKey (groupKey)}
        {@const groupParts = planPartGroups[groupKey] ?? []}

        <div class="overflow-hidden rounded-xl border border-zinc-700">
          <button
            type="button"
            on:click={() => togglePartGroup(currentPlanId, groupKey)}
            class="flex w-full items-center gap-2 bg-zinc-800 px-4 py-2.5 text-left hover:bg-zinc-700/80 transition-colors"
          >
            <span class="text-zinc-400 text-xs w-3">{expandedPartGroups[`${currentPlanId}:${groupKey}`] !== false ? '▾' : '▸'}</span>
            <span class="font-medium text-white text-sm flex-1">{groupKey}</span>
            <span class="text-xs text-zinc-400">({groupParts.length})</span>
            {#if groupParts.every(coverageOk)}
              <span class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">покрыто</span>
            {:else}
              <span class="text-[10px] px-1.5 py-0.5 rounded bg-red-500/15 text-red-300 border border-red-500/30">не покрыто</span>
            {/if}
            {#if groupParts.every(deliveryOk)}
              <span class="text-[10px] px-1.5 py-0.5 rounded bg-emerald-500/20 text-emerald-300 border border-emerald-500/30">доставлено</span>
            {/if}
          </button>

          {#if expandedPartGroups[`${currentPlanId}:${groupKey}`] !== false}
            <div class="overflow-x-auto">
            <table class="w-full min-w-[1180px] table-fixed">
              <colgroup>
                <col style="width: 5%" />
                <col style="width: 16%" />
                <col style="width: 12%" />
                <col style="width: 17%" />
                <col style="width: 29%" />
                <col style="width: 21%" />
              </colgroup>
              <thead class="bg-zinc-900 text-zinc-400">
                <tr>
                  <th class="px-3 py-3 font-medium text-center">ID</th>
                  <th class="px-4 py-3 font-medium text-left">Деталь</th>
                  <th class="px-4 py-3 font-medium text-left">Поставщик</th>
                  <th class="px-4 py-3 font-medium text-center">Итого к закупке</th>
                  <th class="px-4 py-3 font-medium text-center">Покрытие счетами</th>
                  <th class="px-4 py-3 font-medium text-center">Поставлено</th>
                </tr>
              </thead>
              <tbody class="divide-y divide-zinc-800">
                {#each groupParts as p (p.id)}
                  <tr class="hover:bg-zinc-800/30">
                    <td class="px-3 py-3 font-mono text-sm text-center align-top">{partId(p.part_id) ?? '—'}</td>
                    <td class="px-4 py-3 align-top">
                      <div class="break-words font-medium text-zinc-100" title={partName(p.part_id)}>
                        {partName(p.part_id)}
                      </div>
                    </td>
                    <td class="px-4 py-3 text-zinc-300 align-top">
                      <div class="break-words" title={partSupplier(p.part_id)}>{partSupplier(p.part_id)}</div>
                    </td>
                    <td class="px-3 py-3 text-center align-top">
                      <div class="mx-auto grid max-w-[220px] grid-cols-[minmax(0,1fr)_auto] items-center gap-2">
                        <input
                          type="number"
                          step="1"
                          min="0"
                          value={finalDraft[p.id] ?? ''}
                          on:input={(e) => {
                            const el = e.currentTarget;
                            if (el instanceof HTMLInputElement) {
                              finalDraft = { ...finalDraft, [p.id]: el.value };
                            }
                          }}
                          class="min-w-0 w-full px-2 py-1.5 bg-zinc-900 border border-zinc-600 rounded text-white text-sm font-mono"
                        />
                        <button
                          type="button"
                          disabled={savingFinalId === p.id}
                          on:click={() => submitFinal(currentPlanId, p)}
                          class="h-8 px-3 bg-zinc-600 text-white rounded text-xs font-medium hover:bg-zinc-500 disabled:opacity-50"
                        >
                          {savingFinalId === p.id ? '…' : 'Сохранить'}
                        </button>
                      </div>
                      {#if Number(p.qty_final) !== Number(p.qty_required)}
                        <div class="mt-1 text-[10px] text-zinc-500">расчёт по заказам: <span class="font-mono">{formatIntegerQty(p.qty_required)}</span></div>
                      {/if}
                    </td>
                    <td class="overflow-hidden px-3 py-3 text-center align-top">
                      <div
                        class="mb-2 rounded-lg border px-3 py-1.5 text-xs font-medium {coverageOk(p)
                          ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-200'
                          : 'bg-red-500/15 border-red-500/40 text-red-200'}"
                      >
                        Покрыто: <span class="font-mono">{formatIntegerQty(p.qty_covered_total)}</span>
                        из <span class="font-mono">{formatIntegerQty(p.qty_final)}</span>
                      </div>
                      {#if p.has_invoice}
                        <ul class="mt-2 space-y-1.5 text-left text-[11px]">
                          {#each p.invoices ?? [] as inv}
                            {@const isExpanded = !!expandedInvoiceLinks[inv.link_id]}
                            <li
                              class="overflow-hidden rounded-lg border {inv.payment_date
                                ? 'bg-emerald-500/15 border-emerald-500/40 text-emerald-100'
                                : 'bg-red-500/15 border-red-500/40 text-red-100'}"
                            >
                              <div class="px-2.5 py-2">
                                <button
                                  type="button"
                                  on:click={() => toggleInvoiceDetails(inv)}
                                  aria-expanded={isExpanded}
                                  class="grid w-full min-w-0 grid-cols-[auto_minmax(0,1fr)_minmax(80px,0.75fr)] items-center gap-2 rounded text-left focus:outline-none focus:ring-2 focus:ring-white/30"
                                >
                                  <span class="text-zinc-400 text-[10px]">{isExpanded ? '▾' : '▸'}</span>
                                  <span class="flex min-w-0 items-center gap-2 overflow-hidden">
                                    <span class="truncate font-mono font-semibold" title={`№${inv.invoice_no}`}>№{inv.invoice_no}</span>
                                    <span class="shrink-0 whitespace-nowrap text-zinc-400">от {formatDate(inv.invoice_date)}</span>
                                    {#if inv.is_carryover}
                                      <span class="shrink-0 rounded bg-sky-500/20 border border-sky-500/40 px-1.5 py-0.5 text-[9px] uppercase tracking-wide text-sky-200" title="Автоматический перенос остатка прошлых месяцев">перенос</span>
                                    {/if}
                                  </span>
                                  <span class="min-w-0 truncate text-right text-zinc-300" title={inv.supplier || 'Без поставщика'}>
                                    {inv.supplier || 'Без поставщика'}
                                  </span>
                                </button>

                                <div class="mt-2 flex min-w-0 flex-wrap items-center gap-1.5 border-t border-white/10 pt-2">
                                  <span class="whitespace-nowrap rounded bg-black/20 px-2 py-1 font-mono text-[10px]">
                                    Покрыто {formatIntegerQty(inv.qty_covered)}
                                  </span>
                                  <span class="whitespace-nowrap rounded bg-black/20 px-2 py-1 text-[10px] {inv.payment_date ? 'text-emerald-300' : 'text-red-300'}">
                                    {inv.payment_date ? `Оплата ${formatDate(inv.payment_date)}` : 'Не оплачен'}
                                  </span>
                                  {#if !inv.is_carryover}
                                    <span class="ml-auto flex flex-wrap items-center justify-end gap-1">
                                      <button
                                        type="button"
                                        class="h-7 rounded border border-amber-500/40 bg-amber-500/10 px-2 text-[10px] font-medium text-amber-200 hover:bg-amber-500/20"
                                        on:click={() => openEditInvoiceModal(inv, p.id)}
                                      >
                                        Изменить
                                      </button>
                                      <button
                                        type="button"
                                        class="h-7 rounded border border-red-500/40 bg-red-500/10 px-2 text-[10px] font-medium text-red-200 hover:bg-red-500/20"
                                        on:click={() => unlinkLink(inv.invoice_id, inv.link_id, p.id)}
                                      >
                                        Отвязать
                                      </button>
                                    </span>
                                  {/if}
                                </div>
                              </div>
                              {#if isExpanded}
                                <div class="border-t border-white/10 bg-black/10 px-3 py-2 space-y-2">
                                  <div class="grid grid-cols-2 gap-x-4 gap-y-0.5 text-[11px] text-zinc-300">
                                    <div><span class="text-zinc-500">Номер:</span> <span class="font-mono">№{inv.invoice_no}</span></div>
                                    {#if inv.supplier}<div class="col-span-2"><span class="text-zinc-500">Поставщик:</span> {inv.supplier}</div>{/if}
                                    <div><span class="text-zinc-500">Покрыто:</span> <span class="font-mono">{formatIntegerQty(inv.qty_covered)}</span></div>
                                    <div class="{inv.payment_date ? 'text-emerald-300' : 'text-red-300'}">
                                      <span class="text-zinc-500">Оплата:</span> {formatDate(inv.payment_date)}
                                    </div>
                                  </div>
                                  {#if invoiceFilesCache[inv.invoice_id] === undefined}
                                    <div class="text-[10px] text-zinc-500">Загрузка файлов…</div>
                                  {:else if invoiceFilesCache[inv.invoice_id].length === 0}
                                    <div class="text-[10px] text-zinc-500">Нет вложений</div>
                                  {:else}
                                    <div class="space-y-1">
                                      <div class="text-[10px] text-zinc-500 font-medium uppercase tracking-wide">Файлы</div>
                                      {#each invoiceFilesCache[inv.invoice_id] as f}
                                        <div class="flex items-center gap-2 rounded bg-black/20 px-2 py-1">
                                          <div class="min-w-0 flex-1">
                                            <div class="truncate text-[10px] text-zinc-200">{f.filename}</div>
                                            <div class="text-[9px] text-zinc-500">
                                              {formatDateTime(f.uploaded_at)}{f.size_bytes != null ? ` · ${formatFileSize(f.size_bytes)}` : ''}
                                            </div>
                                          </div>
                                          <button
                                            type="button"
                                            on:click|stopPropagation={() => downloadFile(f.id, f.filename)}
                                            class="shrink-0 px-2 py-0.5 text-[10px] bg-zinc-700 rounded hover:bg-zinc-600 text-white"
                                          >
                                            Скачать
                                          </button>
                                        </div>
                                      {/each}
                                    </div>
                                  {/if}
                                </div>
                              {/if}
                            </li>
                          {/each}
                        </ul>
                      {/if}
                      <div class="mt-2 flex flex-wrap justify-center gap-1.5">
                        <button
                          type="button"
                          on:click={() => openLinkModal(currentPlanId, [p.part_id])}
                          class="min-h-8 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-1.5 text-xs font-medium text-amber-300 hover:bg-amber-500/20"
                        >
                          {p.has_invoice ? 'Привязать ещё счёт' : 'Привязать счёт'}
                        </button>
                        <button
                          type="button"
                          on:click={() => openCreateInvoiceModal(currentPlanId, [p.part_id])}
                          class="min-h-8 rounded-lg border border-emerald-500/40 bg-emerald-500/10 px-3 py-1.5 text-xs font-medium text-emerald-300 hover:bg-emerald-500/20"
                        >
                          Создать счёт
                        </button>
                      </div>
                    </td>
                    <td
                      class="overflow-hidden px-3 py-3 text-center align-top {deliveryOk(p)
                        ? 'bg-emerald-950/20 border-l-2 border-emerald-500/40'
                        : 'bg-red-950/20 border-l-2 border-red-500/40'}"
                    >
                      {#if !p.has_invoice}
                        <div class="mx-auto max-w-[270px] rounded-lg border border-zinc-700/70 bg-black/10 px-3 py-2 text-xs text-zinc-500">
                          Поставка станет доступна после привязки счёта
                        </div>
                      {:else}
                        <div class="mx-auto grid max-w-[280px] grid-cols-[minmax(0,1fr)_auto] items-end gap-2 text-left">
                          <div class="min-w-0">
                            <label class="mb-1 block text-[10px] font-medium uppercase tracking-wide text-zinc-500" for="del-{p.id}">
                              Поставлено
                            </label>
                            <div class="flex min-w-0 items-center gap-1.5">
                            <input
                              id="del-{p.id}"
                              type="number"
                              step="1"
                              min="0"
                              max={effectiveTarget(p)}
                              value={deliverDraft[p.id] ?? ''}
                              on:input={(e) => {
                                const el = e.currentTarget;
                                if (el instanceof HTMLInputElement) {
                                  deliverDraft = { ...deliverDraft, [p.id]: el.value };
                                }
                              }}
                              class="min-w-0 w-full px-2 py-1.5 bg-zinc-900 border border-zinc-600 rounded text-white text-sm font-mono"
                            />
                              <span class="shrink-0 whitespace-nowrap text-xs text-zinc-500">из {formatIntegerQty(p.qty_final)}</span>
                            </div>
                          </div>
                          <button
                            type="button"
                            disabled={savingDeliveredId === p.id}
                            on:click={() => submitDelivered(currentPlanId, p)}
                            class="h-8 px-3 bg-zinc-600 text-white rounded text-xs font-medium hover:bg-zinc-500 disabled:opacity-50"
                          >
                            {savingDeliveredId === p.id ? '…' : 'Сохранить'}
                          </button>
                        </div>
                      {/if}

                      <!-- Delivery files -->
                      <div class="mx-auto mt-3 max-w-[280px]">
                        {#if (p.files ?? []).length > 0}
                          <div class="space-y-1 mb-2 text-left">
                            {#each p.files ?? [] as f (f.id)}
                              <div class="flex items-center gap-2 rounded bg-black/20 px-2 py-1 text-[11px]">
                                <div class="min-w-0 flex-1">
                                  <div class="truncate text-zinc-200">{f.filename}</div>
                                  <div class="text-[10px] text-zinc-500">{formatDate(f.uploaded_at)}{f.size_bytes != null ? ` · ${formatFileSize(f.size_bytes)}` : ''}</div>
                                </div>
                                <button
                                  type="button"
                                  on:click={() => downloadFile(f.id, f.filename)}
                                  class="shrink-0 px-2 py-0.5 text-[10px] bg-zinc-700 rounded hover:bg-zinc-600 text-white"
                                >
                                  Скачать
                                </button>
                                <button
                                  type="button"
                                  on:click={() => deletePlanPartFile(currentPlanId, p.id, f.id)}
                                  class="shrink-0 px-1.5 py-0.5 text-[10px] bg-red-900/60 rounded hover:bg-red-800 text-red-200"
                                  title="Удалить файл"
                                >
                                  ✕
                                </button>
                              </div>
                            {/each}
                          </div>
                        {/if}
                        <input
                          type="file"
                          multiple
                          class="hidden"
                          bind:this={planPartFileInputs[p.id]}
                          on:change={(e) => handlePlanPartFileInput(currentPlanId, p.id, e)}
                        />
                        <button
                          type="button"
                          disabled={uploadingFilesPartId === p.id}
                          on:click={() => planPartFileInputs[p.id]?.click()}
                          class="min-h-8 rounded-lg border border-zinc-600 bg-zinc-800/70 px-3 py-1.5 text-xs font-medium text-zinc-300 hover:bg-zinc-700 disabled:opacity-50"
                        >
                          {uploadingFilesPartId === p.id ? 'Загрузка…' : '+ Добавить файлы'}
                        </button>
                      </div>
                    </td>
                  </tr>
                {/each}
              </tbody>
            </table>
            </div>
          {/if}
        </div>
      {/each}
    </div>
  {/if}
</div>

<!-- Remainders modal -->
{#if remaindersModalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" on:click={() => remaindersModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl border border-zinc-700 w-full max-w-6xl max-h-[90vh] flex flex-col" on:click|stopPropagation role="dialog">
      <div class="flex items-center justify-between border-b border-zinc-700 px-6 py-4">
        <div>
          <h2 class="text-lg font-semibold text-white">Остатки деталей</h2>
          <p class="text-xs text-zinc-400 mt-0.5">Излишек заказа по счетам на последний рассчитанный план. Клик по детали — разбивка перезаказа по месяцам.</p>
        </div>
        <button type="button" on:click={() => remaindersModalOpen = false} class="text-zinc-400 hover:text-white text-xl leading-none px-2">×</button>
      </div>

      <div class="overflow-auto px-6 py-4">
        {#if remaindersLoading}
          <p class="text-zinc-400">Загрузка…</p>
        {:else if remaindersError}
          <p class="text-red-300 text-sm">{remaindersError}</p>
        {:else if !remaindersData || !remaindersData.current_month}
          <p class="text-zinc-400 text-sm">Нет данных: создайте месячные планы и привяжите счета.</p>
        {:else}
          <h3 class="text-sm font-semibold text-white mb-2">Остатки на конец {monthLabel(remaindersData.current_month)}</h3>
          {#if remainderGroups.length === 0}
            <p class="text-zinc-400 text-sm">Остатков нет — излишков заказа по счетам не осталось.</p>
          {:else}
            <div class="space-y-3">
              {#each remainderGroups as g (g.type)}
                <div class="overflow-hidden rounded-xl border border-zinc-700">
                  <button
                    type="button"
                    on:click={() => toggleRemainderGroup(g.type)}
                    class="flex w-full items-center gap-2 bg-zinc-800 px-4 py-2 text-left hover:bg-zinc-700/80"
                  >
                    <span class="text-zinc-400 text-xs">{isRemainderGroupExpanded(g.type) ? '▾' : '▸'}</span>
                    <span class="font-medium text-white text-sm">{g.type}</span>
                    <span class="text-xs text-zinc-400">({g.parts.length})</span>
                  </button>
                  {#if isRemainderGroupExpanded(g.type)}
                    <ul class="divide-y divide-zinc-800">
                      {#each g.parts as p (p.part_id)}
                        {@const months = Object.keys(p.overorders)}
                        <li>
                          <button
                            type="button"
                            on:click={() => toggleRemainderPart(p.part_id)}
                            class="flex w-full items-center gap-3 px-4 py-2 text-left text-sm hover:bg-zinc-800/40"
                          >
                            <span class="text-zinc-500 text-[10px] w-2">{months.length ? (expandedRemainderParts[p.part_id] ? '▾' : '▸') : ''}</span>
                            <span class="flex-1 text-zinc-100">{p.name}</span>
                            <span class="font-mono text-emerald-300">{formatIntegerQty(p.remainder)}</span>
                          </button>
                          {#if expandedRemainderParts[p.part_id]}
                            <div class="px-4 pb-3 pl-9">
                              <div class="text-[11px] text-zinc-500 mb-1">Перезаказано по месяцам:</div>
                              {#if months.length === 0}
                                <div class="text-[11px] text-zinc-500">нет данных</div>
                              {:else}
                                <ul class="space-y-0.5">
                                  {#each months as m}
                                    <li class="flex justify-between text-[11px] text-zinc-300 max-w-xs">
                                      <span>{monthLabel(m)}</span>
                                      <span class="font-mono text-emerald-300">+{formatIntegerQty(p.overorders[m])}</span>
                                    </li>
                                  {/each}
                                </ul>
                              {/if}
                            </div>
                          {/if}
                        </li>
                      {/each}
                    </ul>
                  {/if}
                </div>
              {/each}
            </div>
          {/if}

          <div class="mt-6">
            <h3 class="text-sm font-semibold text-white mb-1">
              Недозаказ за текущий месяц
              <span class="text-zinc-400 font-normal">— {monthLabel(remaindersData.current_month)}</span>
            </h3>
            <p class="text-xs text-zinc-500 mb-2">Потребность минус заказ по счетам за месяц, без учёта переносов остатков.</p>
            {#if undersupplyGroups.length === 0}
              <p class="text-emerald-300 text-sm">Недозаказа нет — все детали обеспечены счетами этого месяца.</p>
            {:else}
              <div class="space-y-3">
                {#each undersupplyGroups as g (g.type)}
                  <div class="rounded-xl border border-red-900/50 overflow-hidden">
                    <div class="bg-red-950/40 px-4 py-2 text-sm font-medium text-red-200">{g.type}</div>
                    <table class="w-full text-sm">
                      <tbody class="divide-y divide-zinc-800">
                        {#each g.parts as item (item.part_id)}
                          <tr class="hover:bg-zinc-800/40">
                            <td class="px-4 py-2 text-zinc-200">{item.name}</td>
                            <td class="px-4 py-2 text-right font-mono text-red-300 w-32">−{formatIntegerQty(item.qty)}</td>
                          </tr>
                        {/each}
                      </tbody>
                    </table>
                  </div>
                {/each}
              </div>
            {/if}
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}

<!-- Generate modal -->
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

<!-- Edit invoice modal -->
{#if editInvoiceModalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => editInvoiceModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-2xl max-h-[90vh] overflow-y-auto border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">Редактировать счёт</h2>
      <form on:submit|preventDefault={saveEditInvoice} class="space-y-4">
        <div class="grid gap-4 md:grid-cols-2">
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Номер счёта <span class="text-red-400">*</span></label>
            <input bind:value={editInvoiceForm.invoice_no} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
          </div>
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Поставщик</label>
            <input bind:value={editInvoiceForm.supplier} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Дата счёта <span class="text-red-400">*</span></label>
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
            <label class="block text-sm text-zinc-400 mb-1">Покрыто (деталей)</label>
            <input type="number" step="1" min="0" bind:value={editInvoiceLinkQty} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
          </div>
          <div class="md:col-span-2">
            <label class="block text-sm text-zinc-400 mb-1">Описание</label>
            <textarea bind:value={editInvoiceForm.description} rows="2" placeholder="Опционально" class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white resize-none"></textarea>
          </div>
          <div class="md:col-span-2">
            <label class="block text-sm text-zinc-400 mb-1">Заметка</label>
            <textarea bind:value={editInvoiceForm.note} rows="2" placeholder="Опционально" class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white resize-none"></textarea>
          </div>
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
          <button type="button" on:click={() => editInvoiceModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}

<!-- Link invoice modal -->
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
          {#each linkPartIds as pid}
            <div class="flex items-center gap-2">
              <span class="min-w-0 flex-1 text-sm text-zinc-300 truncate">{partName(pid)}</span>
              <input
                type="number"
                step="1"
                min="0"
                value={linkQtyByPart[pid] ?? ''}
                on:input={(e) => {
                  const el = e.currentTarget;
                  if (el instanceof HTMLInputElement) {
                    linkQtyByPart = { ...linkQtyByPart, [pid]: el.value };
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

<!-- Create invoice modal -->
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
          {#each createInvoicePartIds as pid}
            <div class="flex items-center gap-2">
              <span class="min-w-0 flex-1 text-sm text-zinc-300 truncate">{partName(pid)}</span>
              <input
                type="number"
                step="1"
                min="0"
                value={createInvoiceQtyByPart[pid] ?? ''}
                on:input={(e) => {
                  const el = e.currentTarget;
                  if (el instanceof HTMLInputElement) {
                    createInvoiceQtyByPart = { ...createInvoiceQtyByPart, [pid]: el.value };
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
