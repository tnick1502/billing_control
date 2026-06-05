<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { Device, Part, BomVersion, BomItem, BomVersionCreate, BomItemCreate } from '$lib/api';

  let devices: Device[] = [];
  let parts: Part[] = [];
  let selectedDevice: Device | null = null;
  let boms: BomVersion[] = [];
  let selectedBom: BomVersion | null = null;
  let bomItems: BomItem[] = [];
  let loading = true;
  let bomModalOpen = false;
  let bomForm: BomVersionCreate = { name: null, description: null, version: 1, status: 'current' };

  // Item modal state
  let itemModalOpen = false;
  let editingItemId: number | null = null;
  let itemFormType: 'part' | 'sub_device' = 'part';
  let itemQty = 1;
  let itemNote: string | null = null;
  // For part items
  let selectedPartId: number | null = null;
  let partSearchQuery = '';
  // For sub-device items
  let subDeviceId: number | null = null;
  let subBomVersionId: number | null = null;
  let bomsForSubDevice: BomVersion[] = [];
  let subDeviceSearchQuery = '';

  $: filteredParts = filterParts(partSearchQuery);
  $: filteredSubDevices = filterSubDevices(subDeviceSearchQuery);
  $: groupedBomItems = groupBomItems(bomItems, parts);

  onMount(load);

  async function load() {
    loading = true;
    try {
      [devices, parts] = await Promise.all([api.devices.list(), api.parts.list()]);
    } catch (e) {
      console.error(e);
    } finally {
      loading = false;
    }
  }

  async function selectDevice(d: Device) {
    selectedDevice = d;
    selectedBom = null;
    bomItems = [];
    try {
      boms = await api.bom.list(d.id);
      const activeBom = boms.find((b) => b.status === 'active') ?? boms.find((b) => b.status === 'current') ?? boms[0];
      if (activeBom) {
        selectedBom = activeBom;
        bomItems = await api.bom.items.list(activeBom.id);
      }
    } catch (e) {
      console.error(e);
    }
  }

  async function selectBom(b: BomVersion) {
    selectedBom = b;
    try {
      bomItems = await api.bom.items.list(b.id);
    } catch (e) {
      console.error(e);
    }
  }

  function openCreateBom() {
    if (!selectedDevice) return;
    bomForm = { name: null, description: null, version: boms.length + 1, status: 'current' };
    bomModalOpen = true;
  }

  async function saveBom() {
    if (!selectedDevice) return;
    try {
      await api.bom.create(selectedDevice.id, bomForm);
      bomModalOpen = false;
      boms = await api.bom.list(selectedDevice.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function setBomStatus(bomId: number, status: string) {
    try {
      await api.bom.update(bomId, { status });
      if (selectedDevice) boms = await api.bom.list(selectedDevice.id);
      if (selectedBom?.id === bomId) selectedBom = { ...selectedBom, status };
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function openAddItem() {
    if (!selectedBom) return;
    editingItemId = null;
    itemFormType = 'part';
    itemQty = 1;
    itemNote = null;
    selectedPartId = null;
    partSearchQuery = '';
    subDeviceId = null;
    subBomVersionId = null;
    bomsForSubDevice = [];
    subDeviceSearchQuery = '';
    itemModalOpen = true;
  }

  function openEditItem(item: BomItem) {
    editingItemId = item.id;
    itemFormType = item.item_type;
    const q = typeof item.qty_per_device === 'string' ? parseInt(item.qty_per_device, 10) : item.qty_per_device;
    itemQty = Number.isFinite(q) && q >= 1 ? q : 1;
    itemNote = item.note;
    if (item.item_type === 'part') {
      selectedPartId = item.part_id;
      partSearchQuery = item.part_id ? (partLabel(parts.find((p) => p.id === item.part_id)!) ?? '') : '';
      subDeviceId = null;
      subBomVersionId = null;
      bomsForSubDevice = [];
      subDeviceSearchQuery = '';
    } else {
      subDeviceId = item.sub_device_id;
      subBomVersionId = item.sub_bom_version_id;
      subDeviceSearchQuery = '';
      selectedPartId = null;
      partSearchQuery = '';
      if (item.sub_device_id) {
        api.bom.list(item.sub_device_id).then((list) => { bomsForSubDevice = list; }).catch(() => {});
      }
    }
    itemModalOpen = true;
  }

  async function onSubDeviceChange(deviceId: number | null) {
    subDeviceId = deviceId;
    subBomVersionId = null;
    bomsForSubDevice = [];
    if (deviceId) {
      try {
        bomsForSubDevice = await api.bom.list(deviceId);
      } catch {
        bomsForSubDevice = [];
      }
    }
  }

  async function saveItem() {
    if (!selectedBom) return;
    const qty = Math.trunc(Number(itemQty));
    if (!Number.isFinite(qty) || qty < 1) {
      alert('Количество на прибор — целое число не меньше 1');
      return;
    }
    let payload: BomItemCreate;
    if (itemFormType === 'part') {
      if (!selectedPartId) {
        alert('Выберите деталь');
        return;
      }
      payload = { part_id: selectedPartId, qty_per_device: qty, note: itemNote };
    } else {
      if (!subDeviceId) {
        alert('Выберите подприбор');
        return;
      }
      payload = {
        sub_device_id: subDeviceId,
        sub_bom_version_id: subBomVersionId ?? null,
        qty_per_device: qty,
        note: itemNote,
      };
    }
    try {
      if (editingItemId) {
        await api.bom.items.update(selectedBom.id, editingItemId, { qty_per_device: qty, note: itemNote });
      } else {
        await api.bom.items.create(selectedBom.id, payload);
      }
      itemModalOpen = false;
      bomItems = await api.bom.items.list(selectedBom.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  async function removeCurrentItem() {
    if (!editingItemId) return;
    if (!selectedBom || !confirm('Удалить позицию?')) return;
    try {
      await api.bom.items.delete(selectedBom.id, editingItemId);
      itemModalOpen = false;
      bomItems = await api.bom.items.list(selectedBom.id);
    } catch (e) {
      alert((e as Error).message);
    }
  }

  function handleItemRowKeydown(event: KeyboardEvent, item: BomItem) {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      openEditItem(item);
    }
  }

  function partSearchText(part: Part) {
    return [part.name, part.article, part.cipher, part.description].filter(Boolean).join(' ').toLowerCase();
  }

  function partLabel(part: Part | undefined) {
    if (!part) return '';
    return [part.name, part.article ? `арт. ${part.article}` : null, part.cipher ? `шифр ${part.cipher}` : null]
      .filter(Boolean)
      .join(' · ');
  }

  function selectedPartLabel() {
    const part = parts.find((p) => p.id === selectedPartId);
    return part ? partLabel(part) : 'Деталь не выбрана';
  }

  function filterParts(query: string) {
    const q = query.trim().toLowerCase();
    const source = q ? parts.filter((part) => partSearchText(part).includes(q)) : parts;
    return source.slice(0, 30);
  }

  function selectPart(part: Part) {
    selectedPartId = part.id;
    partSearchQuery = partLabel(part);
  }

  function filterSubDevices(query: string) {
    const q = query.trim().toLowerCase();
    const available = devices.filter((d) => d.id !== selectedDevice?.id);
    if (!q) return available;
    return available.filter((d) =>
      `${d.primary_name} ${d.model ?? ''}`.toLowerCase().includes(q)
    );
  }

  function deviceName(id: number | null) {
    if (!id) return '—';
    return devices.find((d) => d.id === id)?.primary_name ?? String(id);
  }

  function bomVersionLabel(bomId: number | null) {
    if (!bomId) return 'Авто (активная)';
    const b = bomsForSubDevice.find((bv) => bv.id === bomId);
    return b ? `v${b.version}${b.name ? ` · ${b.name}` : ''} (${statusLabel(b.status)})` : `BOM #${bomId}`;
  }

  function groupBomItems(items: BomItem[], partsList: Part[]) {
    const subDevices = items.filter((i) => i.item_type === 'sub_device');
    const partItems = items.filter((i) => i.item_type === 'part');
    const byType = new Map<string, BomItem[]>();
    for (const item of partItems) {
      const part = partsList.find((p) => p.id === item.part_id);
      const key = part?.part_type?.trim() || 'Прочие';
      if (!byType.has(key)) byType.set(key, []);
      byType.get(key)!.push(item);
    }
    const groups: { label: string; items: BomItem[]; isSubDevice: boolean }[] = [];
    if (subDevices.length > 0) groups.push({ label: 'Подприборы', items: subDevices, isSubDevice: true });
    for (const [label, typeItems] of [...byType.entries()].sort((a, b) => a[0].localeCompare(b[0], 'ru'))) {
      groups.push({ label, items: typeItems, isSubDevice: false });
    }
    return groups;
  }

  function itemRowLabel(item: BomItem): string {
    if (item.item_type === 'sub_device') return deviceName(item.sub_device_id);
    if (item.part_id) return partLabel(parts.find((p) => p.id === item.part_id)) || String(item.part_id);
    return '—';
  }

  const BOM_STATUSES: { value: string; label: string }[] = [
    { value: 'active', label: 'Активная' },
    { value: 'current', label: 'Рабочая' },
    { value: 'archived', label: 'Архивная' },
  ];
  function statusLabel(s: string) {
    return BOM_STATUSES.find((x) => x.value === s)?.label ?? s;
  }
</script>

<div class="p-8">
  <h1 class="text-2xl font-bold text-white mb-6">Спецификации (BOM)</h1>

  <div class="flex gap-6">
    <div class="w-64 shrink-0">
      <h2 class="text-sm font-medium text-zinc-400 mb-2">Приборы</h2>
      <div class="space-y-1">
        {#each devices as d}
          <button
            on:click={() => selectDevice(d)}
            class="block w-full text-left px-3 py-2 rounded-lg {selectedDevice?.id === d.id ? 'bg-amber-500/20 text-amber-400' : 'hover:bg-zinc-800 text-zinc-300'}"
          >
            {d.primary_name}
          </button>
        {/each}
      </div>
    </div>

    <div class="flex-1">
      {#if selectedDevice}
        <div class="mb-4 flex justify-between items-center">
          <h2 class="text-lg text-white">BOM для {selectedDevice.primary_name}</h2>
          <button on:click={openCreateBom} class="px-3 py-1.5 bg-amber-500 text-black rounded-lg hover:bg-amber-400 text-sm">Новая версия</button>
        </div>
        <div class="space-y-2 mb-4">
          {#each boms as b}
            <div
              role="button"
              tabindex="0"
              on:click={() => selectBom(b)}
              on:keydown={(e) => e.key === 'Enter' && selectBom(b)}
              class="w-full flex items-center gap-4 p-3 bg-surface-800 rounded-lg border text-left cursor-pointer {selectedBom?.id === b.id ? 'border-amber-500' : 'border-zinc-700'}"
            >
              <span class="font-mono">v{b.version}</span>
              {#if b.name}
                <span class="text-white">{b.name}</span>
              {/if}
              {#if b.description}
                <span class="text-zinc-400 text-sm truncate max-w-[200px]" title={b.description}>{b.description}</span>
              {/if}
              <span class="px-2 py-0.5 rounded text-sm {b.status === 'active' ? 'bg-emerald-600' : b.status === 'current' ? 'bg-amber-600' : 'bg-zinc-700'}">{statusLabel(b.status)}</span>
              <div class="flex gap-1 ml-auto" role="presentation" on:click|stopPropagation>
                {#if b.status !== 'active'}
                  <button on:click={() => setBomStatus(b.id, 'active')} class="text-emerald-500 text-sm px-2">Активная</button>
                {/if}
                {#if b.status !== 'current'}
                  <button on:click={() => setBomStatus(b.id, 'current')} class="text-amber-400 text-sm px-2">Рабочая</button>
                {/if}
                {#if b.status !== 'archived'}
                  <button on:click={() => setBomStatus(b.id, 'archived')} class="text-zinc-400 text-sm px-2">Архивная</button>
                {/if}
              </div>
            </div>
          {/each}
        </div>

        {#if selectedBom}
          <div>
            <button on:click={openAddItem} class="mb-4 px-3 py-1.5 bg-emerald-600 text-white rounded-lg hover:bg-emerald-500 text-sm">+ Добавить компонент</button>
            {#if bomItems.length === 0}
              <div class="rounded-xl border border-zinc-700 px-4 py-6 text-center text-zinc-500">
                Нет компонентов. Добавьте деталь или подприбор.
              </div>
            {:else}
              <div class="space-y-4">
                {#each groupedBomItems as group}
                  <div class="rounded-xl border border-zinc-700 overflow-hidden">
                    <div class="px-4 py-2 text-xs font-semibold uppercase tracking-wide {group.isSubDevice ? 'bg-blue-950/60 text-blue-300 border-b border-blue-800/50' : 'bg-zinc-900 text-zinc-400 border-b border-zinc-700'}">
                      {group.label}
                      <span class="ml-2 font-normal normal-case tracking-normal text-zinc-500">{group.items.length} поз.</span>
                    </div>
                    <table class="w-full">
                      <thead class="bg-surface-800 text-zinc-400 text-left">
                        <tr>
                          <th class="px-4 py-2 font-medium text-sm">Компонент</th>
                          <th class="px-4 py-2 font-medium text-sm">Кол-во на прибор</th>
                        </tr>
                      </thead>
                      <tbody class="divide-y divide-zinc-800">
                        {#each group.items as i}
                          <tr
                            class="cursor-pointer hover:bg-zinc-800/50"
                            role="button"
                            tabindex="0"
                            on:click={() => openEditItem(i)}
                            on:keydown={(event) => handleItemRowKeydown(event, i)}
                          >
                            <td class="px-4 py-3">{itemRowLabel(i)}</td>
                            <td class="px-4 py-3 font-mono">{i.qty_per_device}</td>
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
      {:else}
        <p class="text-zinc-400">Выберите прибор</p>
      {/if}
    </div>
  </div>
</div>

{#if bomModalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => bomModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">Новая версия BOM</h2>
      <form on:submit|preventDefault={saveBom} class="space-y-4">
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Наименование</label>
          <input type="text" bind:value={bomForm.name} placeholder="Опционально (по умолчанию: Спецификация vN)" class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Описание</label>
          <textarea bind:value={bomForm.description} rows="2" placeholder="Опционально" class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Версия</label>
          <input type="number" bind:value={bomForm.version} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Статус</label>
          <select bind:value={bomForm.status} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white">
            {#each BOM_STATUSES as s}
              <option value={s.value}>{s.label}</option>
            {/each}
          </select>
        </div>
        <div class="flex gap-2 pt-2">
          <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Создать</button>
          <button type="button" on:click={() => bomModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
        </div>
      </form>
    </div>
  </div>
{/if}

{#if itemModalOpen}
  <div class="fixed inset-0 bg-black/60 flex items-center justify-center z-50" on:click={() => itemModalOpen = false} role="button" tabindex="0">
    <div class="bg-surface-800 rounded-xl p-6 w-full max-w-md border border-zinc-700 max-h-[90vh] overflow-y-auto" on:click|stopPropagation role="dialog">
      <h2 class="text-lg font-semibold text-white mb-4">{editingItemId ? 'Редактировать' : 'Добавить'} компонент</h2>
      <form on:submit|preventDefault={saveItem} class="space-y-4">

        <!-- Type toggle — only visible when creating a new item -->
        {#if !editingItemId}
          <div>
            <label class="block text-sm text-zinc-400 mb-2">Тип компонента</label>
            <div class="flex gap-2">
              <button
                type="button"
                on:click={() => { itemFormType = 'part'; }}
                class="flex-1 py-2 rounded-lg text-sm border {itemFormType === 'part' ? 'bg-amber-500 text-black border-amber-500 font-medium' : 'bg-zinc-800 text-zinc-300 border-zinc-600 hover:bg-zinc-700'}"
              >
                Деталь
              </button>
              <button
                type="button"
                on:click={() => { itemFormType = 'sub_device'; }}
                class="flex-1 py-2 rounded-lg text-sm border {itemFormType === 'sub_device' ? 'bg-blue-600 text-white border-blue-500 font-medium' : 'bg-zinc-800 text-zinc-300 border-zinc-600 hover:bg-zinc-700'}"
              >
                Подприбор
              </button>
            </div>
          </div>
        {/if}

        {#if itemFormType === 'part'}
          <!-- Part selector -->
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Деталь <span class="text-red-400">*</span></label>
            <input
              type="search"
              bind:value={partSearchQuery}
              placeholder="Введите название, артикул, шифр или описание"
              class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
              disabled={!!editingItemId}
            />
            {#if !editingItemId}
              <div class="mt-2 rounded-lg border border-zinc-700 bg-zinc-950/70">
                <div class="border-b border-zinc-800 px-3 py-2 text-xs text-zinc-400">
                  Выбрано: <span class="text-zinc-100">{selectedPartLabel()}</span>
                </div>
                <div class="max-h-48 overflow-y-auto p-1">
                  {#if filteredParts.length === 0}
                    <div class="px-3 py-2 text-sm text-zinc-500">Детали не найдены</div>
                  {:else}
                    {#each filteredParts as p}
                      <button
                        type="button"
                        on:click={() => selectPart(p)}
                        class="block w-full rounded-md px-3 py-2 text-left text-sm {selectedPartId === p.id ? 'bg-amber-500/20 text-amber-200' : 'text-zinc-200 hover:bg-zinc-800'}"
                      >
                        <div>{p.name}</div>
                        <div class="text-xs text-zinc-500">
                          {p.article ? `арт. ${p.article}` : 'без артикула'}{p.cipher ? ` · шифр ${p.cipher}` : ''}
                        </div>
                      </button>
                    {/each}
                  {/if}
                </div>
              </div>
            {:else}
              <div class="mt-1 text-sm text-zinc-300">{selectedPartLabel()}</div>
            {/if}
          </div>

        {:else}
          <!-- Sub-device selector -->
          <div>
            <label class="block text-sm text-zinc-400 mb-1">Подприбор <span class="text-red-400">*</span></label>
            {#if !editingItemId}
              <input
                type="search"
                bind:value={subDeviceSearchQuery}
                placeholder="Поиск по названию или модели"
                class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white mb-2"
              />
              <div class="rounded-lg border border-zinc-700 bg-zinc-950/70">
                <div class="border-b border-zinc-800 px-3 py-2 text-xs text-zinc-400">
                  Выбрано: <span class="text-zinc-100">{subDeviceId ? deviceName(subDeviceId) : 'Подприбор не выбран'}</span>
                </div>
                <div class="max-h-48 overflow-y-auto p-1">
                  {#if filteredSubDevices.length === 0}
                    <div class="px-3 py-2 text-sm text-zinc-500">Приборы не найдены</div>
                  {:else}
                    {#each filteredSubDevices as d}
                      <button
                        type="button"
                        on:click={() => onSubDeviceChange(d.id)}
                        class="block w-full rounded-md px-3 py-2 text-left text-sm {subDeviceId === d.id ? 'bg-blue-600/20 text-blue-200' : 'text-zinc-200 hover:bg-zinc-800'}"
                      >
                        <div>{d.primary_name}</div>
                        {#if d.model}<div class="text-xs text-zinc-500">{d.model}</div>{/if}
                      </button>
                    {/each}
                  {/if}
                </div>
              </div>
            {:else}
              <div class="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-300 text-sm">{deviceName(subDeviceId)}</div>
            {/if}
          </div>

          <!-- Sub-device BOM version -->
          {#if subDeviceId || editingItemId}
            <div>
              <label class="block text-sm text-zinc-400 mb-1">Спецификация подприбора</label>
              <select
                bind:value={subBomVersionId}
                class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
                disabled={!!editingItemId}
              >
                <option value={null}>Авто (активная на момент генерации плана)</option>
                {#each bomsForSubDevice as bv}
                  <option value={bv.id}>v{bv.version}{bv.name ? ` · ${bv.name}` : ''} ({statusLabel(bv.status)})</option>
                {/each}
              </select>
              <p class="text-xs text-zinc-500 mt-1">
                «Авто» — при генерации плана будет использована активная спецификация подприбора на тот момент
              </p>
            </div>
          {/if}
        {/if}

        <!-- Qty -->
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Кол-во на прибор <span class="text-red-400">*</span></label>
          <input type="number" step="1" min="1" bind:value={itemQty} class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" required />
        </div>

        <!-- Note -->
        <div>
          <label class="block text-sm text-zinc-400 mb-1">Примечание</label>
          <textarea bind:value={itemNote} rows="2" class="w-full px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
        </div>

        <div class="flex flex-wrap items-center justify-between gap-2 pt-2">
          <div class="flex gap-2">
            <button type="submit" class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400">Сохранить</button>
            <button type="button" on:click={() => itemModalOpen = false} class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">Отмена</button>
          </div>
          {#if editingItemId}
            <button type="button" on:click={removeCurrentItem} class="px-4 py-2 rounded-lg bg-red-950 text-red-100 ring-1 ring-red-700/60 hover:bg-red-900">
              Удалить
            </button>
          {/if}
        </div>
      </form>
    </div>
  </div>
{/if}
