<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { api } from '$lib/api';
  import type { StatsChartPayload } from '$lib/api';
  import type { Chart as ChartType } from 'chart.js';

  let deviceCanvas: HTMLCanvasElement;
  let partCanvas: HTMLCanvasElement;

  let deviceChart: ChartType | null = null;
  let partChart: ChartType | null = null;

  /** Период для графика приборов: YYYY-MM */
  let deviceMonthFrom = '';
  let deviceMonthTo = '';
  let partMonthFrom = '';
  let partMonthTo = '';

  let loadingDevices = true;
  /** Нет строк в ответе за период */
  let devicesEmpty = true;
  let deviceError = '';

  let loadingPart = false;
  let partError = '';
  let partSeriesEmpty = false;
  let devicePayload: StatsChartPayload | null = null;
  let partPayload: StatsChartPayload | null = null;
  let selectedDeviceIds: number[] = [];
  let selectedPartIds: number[] = [];
  let selectorModal: 'devices' | 'parts' | null = null;
  let selectorSearch = '';

  $: selectorPayload = selectorModal === 'devices' ? devicePayload : selectorModal === 'parts' ? partPayload : null;
  $: selectorOptions = selectorPayload?.datasets ?? [];
  $: selectorFilteredOptions = filterSelectorOptions(selectorOptions, selectorSearch);
  $: selectorSelectedIds = selectorModal === 'devices' ? selectedDeviceIds : selectedPartIds;

  /** Последние 12 календарных месяцев (включая текущий) */
  function defaultMonthRange() {
    const today = new Date();
    const to = `${today.getFullYear()}-${String(today.getMonth() + 1).padStart(2, '0')}`;
    const f = new Date(today.getFullYear(), today.getMonth() - 11, 1);
    const from = `${f.getFullYear()}-${String(f.getMonth() + 1).padStart(2, '0')}`;
    return { from, to };
  }

  /** Переводит диапазон месяцев в date_from / date_to для API */
  function monthRangeToApiDates(fromYm: string, toYm: string): { dateFrom: string; dateTo: string } {
    const [fy, fm] = fromYm.split('-').map(Number);
    const [ty, tm] = toYm.split('-').map(Number);
    const dateFrom = `${fy}-${String(fm).padStart(2, '0')}-01`;
    const lastDay = new Date(ty, tm, 0).getDate();
    const dateTo = `${ty}-${String(tm).padStart(2, '0')}-${String(lastDay).padStart(2, '0')}`;
    return { dateFrom, dateTo };
  }

  const MONTHS_RU = ['янв.', 'фев.', 'мар.', 'апр.', 'май', 'июн.', 'июл.', 'авг.', 'сен.', 'окт.', 'ноя.', 'дек.'];

  /** Подпись оси для месячных меток (YYYY-MM-01 с бэкенда) */
  function formatAxisMonth(iso: string) {
    const [y, m] = iso.split('-').map(Number);
    if (!y || !m) return iso;
    return `${MONTHS_RU[m - 1]} ${y}`;
  }

  function chartJsDefaults(Chart: typeof import('chart.js').Chart) {
    Chart.defaults.color = '#a1a1aa';
    Chart.defaults.borderColor = '#3f3f46';
  }

  /** Тонкая сетка (Chart.js v4: grid.lineWidth + полупрозрачный цвет) */
  const thinGrid = {
    color: 'rgba(113, 113, 122, 0.38)',
    lineWidth: 1,
    borderDash: [2, 3] as [number, number],
  };

  function buildChartOptions(title: string): import('chart.js').ChartOptions<'line'> {
    return {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: 'index', intersect: false },
      plugins: {
        legend: { display: false },
        title: { display: true, text: title, color: '#fafafa', font: { size: 14 } },
      },
      scales: {
        x: {
          ticks: { color: '#a1a1aa', maxRotation: 45 },
          grid: { ...thinGrid },
          border: { dash: [2, 2] as [number, number], color: 'rgba(113, 113, 122, 0.55)' },
          offset: true,
        },
        y: {
          ticks: { color: '#a1a1aa' },
          grid: { ...thinGrid },
          border: { dash: [2, 2] as [number, number], color: 'rgba(113, 113, 122, 0.55)' },
          beginAtZero: true,
        },
      },
    };
  }

  function pointRadiusForCount(n: number) {
    return n <= 1 ? 10 : 4;
  }

  function datasetId(kind: 'devices' | 'parts', ds: StatsChartPayload['datasets'][number]) {
    return kind === 'devices' ? ds.device_id : ds.part_id;
  }

  function selectedIdsFor(kind: 'devices' | 'parts') {
    return kind === 'devices' ? selectedDeviceIds : selectedPartIds;
  }

  function setSelectedIds(kind: 'devices' | 'parts', ids: number[]) {
    if (kind === 'devices') {
      selectedDeviceIds = ids;
    } else {
      selectedPartIds = ids;
    }
  }

  function allDatasetIds(kind: 'devices' | 'parts', payload: StatsChartPayload | null) {
    return (payload?.datasets ?? [])
      .map((ds) => datasetId(kind, ds))
      .filter((id): id is number => typeof id === 'number');
  }

  function syncSelection(kind: 'devices' | 'parts', payload: StatsChartPayload) {
    const available = allDatasetIds(kind, payload);
    const current = selectedIdsFor(kind).filter((id) => available.includes(id));
    setSelectedIds(kind, current.length > 0 ? current : available);
  }

  function filteredPayload(kind: 'devices' | 'parts', payload: StatsChartPayload | null): StatsChartPayload {
    if (!payload) return { labels: [], datasets: [] };
    const selected = new Set(selectedIdsFor(kind));
    return {
      labels: payload.labels,
      datasets: payload.datasets.filter((ds) => {
        const id = datasetId(kind, ds);
        return typeof id === 'number' && selected.has(id);
      }),
    };
  }

  function filterSelectorOptions(items: StatsChartPayload['datasets'], query: string) {
    const needle = query.trim().toLowerCase();
    if (!needle) return items;
    return items.filter((ds) => ds.label.toLowerCase().includes(needle));
  }

  function openSelector(kind: 'devices' | 'parts') {
    selectorModal = kind;
    selectorSearch = '';
  }

  function closeSelector() {
    selectorModal = null;
    selectorSearch = '';
  }

  function toggleSelectorItem(kind: 'devices' | 'parts', id: number, checked: boolean) {
    const current = selectedIdsFor(kind);
    if (checked) {
      setSelectedIds(kind, current.includes(id) ? current : [...current, id]);
    } else {
      setSelectedIds(kind, current.filter((x) => x !== id));
    }
    void rerenderChart(kind);
  }

  function selectAll(kind: 'devices' | 'parts') {
    const payload = kind === 'devices' ? devicePayload : partPayload;
    setSelectedIds(kind, allDatasetIds(kind, payload));
    void rerenderChart(kind);
  }

  function clearAll(kind: 'devices' | 'parts') {
    setSelectedIds(kind, []);
    void rerenderChart(kind);
  }

  async function rerenderChart(kind: 'devices' | 'parts') {
    const mod = await import('chart.js');
    const Chart = mod.Chart;
    if (kind === 'devices') {
      await renderDeviceChart(filteredPayload('devices', devicePayload), Chart);
    } else {
      await renderPartChart(filteredPayload('parts', partPayload), Chart);
    }
  }

  async function renderDeviceChart(payload: StatsChartPayload, Chart: typeof import('chart.js').Chart) {
    devicesEmpty = payload.labels.length === 0 || payload.datasets.length === 0;
    const n = payload.labels.length;
    const pr = pointRadiusForCount(n);

    await tick();
    if (!deviceCanvas) return;
    deviceChart?.destroy();
    deviceChart = null;
    if (devicesEmpty || payload.datasets.length === 0) return;

    deviceChart = new Chart(deviceCanvas, {
      type: 'line',
      data: {
        labels: payload.labels.map(formatAxisMonth),
        datasets: payload.datasets.map((ds) => ({
          label: ds.label,
          data: ds.data,
          borderColor: ds.borderColor ?? 'rgb(245, 158, 11)',
          backgroundColor: ds.backgroundColor,
          fill: false,
          tension: n <= 1 ? 0 : 0.25,
          pointRadius: pr,
          pointHoverRadius: pr + 2,
          borderWidth: 2,
        })),
      },
      options: buildChartOptions('Заказы приборов: сумма по календарным месяцам'),
    });
  }

  async function renderPartChart(payload: StatsChartPayload, Chart: typeof import('chart.js').Chart) {
    partSeriesEmpty = payload.labels.length === 0 || payload.datasets.length === 0;
    const n = payload.labels.length;
    const pr = pointRadiusForCount(n);

    await tick();
    if (!partCanvas) return;
    partChart?.destroy();
    partChart = null;
    if (partSeriesEmpty) return;

    partChart = new Chart(partCanvas, {
      type: 'line',
      data: {
        labels: payload.labels.map(formatAxisMonth),
        datasets: payload.datasets.map((ds) => ({
          label: ds.label,
          data: ds.data,
          borderColor: ds.borderColor ?? 'rgb(245, 158, 11)',
          backgroundColor: ds.backgroundColor,
          fill: false,
          tension: n <= 1 ? 0 : 0.25,
          pointRadius: pr,
          pointHoverRadius: pr + 2,
          borderWidth: 2,
        })),
      },
      options: buildChartOptions('Заказы деталей: сумма по календарным месяцам'),
    });
  }

  async function loadDeviceSeries() {
    if (!deviceMonthFrom || !deviceMonthTo) {
      deviceError = 'Укажите период (месяцы)';
      return;
    }
    if (deviceMonthFrom > deviceMonthTo) {
      deviceError = 'Месяц «с» не может быть позже «по»';
      return;
    }
    deviceError = '';
    loadingDevices = true;
    try {
      const mod = await import('chart.js');
      const Chart = mod.Chart;
      const { dateFrom, dateTo } = monthRangeToApiDates(deviceMonthFrom, deviceMonthTo);
      const payload = await api.stats.ordersDevicesTimeseries(dateFrom, dateTo);
      devicePayload = payload;
      syncSelection('devices', payload);
      await renderDeviceChart(filteredPayload('devices', devicePayload), Chart);
    } catch (e) {
      console.error(e);
      deviceError = (e as Error).message;
      devicesEmpty = true;
      deviceChart?.destroy();
      deviceChart = null;
    } finally {
      loadingDevices = false;
    }
  }

  async function loadPartSeries() {
    if (!partMonthFrom || !partMonthTo) {
      partError = 'Укажите период (месяцы)';
      return;
    }
    if (partMonthFrom > partMonthTo) {
      partError = 'Месяц «с» не может быть позже «по»';
      return;
    }
    partError = '';
    loadingPart = true;
    try {
      const mod = await import('chart.js');
      const Chart = mod.Chart;
      const { dateFrom, dateTo } = monthRangeToApiDates(partMonthFrom, partMonthTo);
      const payload = await api.stats.ordersPartsMonthlyTimeseries(dateFrom, dateTo);
      partPayload = payload;
      syncSelection('parts', payload);
      await renderPartChart(filteredPayload('parts', partPayload), Chart);
    } catch (e) {
      partError = (e as Error).message;
      partChart?.destroy();
      partChart = null;
    } finally {
      loadingPart = false;
    }
  }

  $: legendDeviceDatasets = devicePayload
    ? devicePayload.datasets.filter((ds) => {
        const id = ds.device_id;
        return typeof id === 'number' && selectedDeviceIds.includes(id);
      })
    : [];

  $: legendPartDatasets = partPayload
    ? partPayload.datasets.filter((ds) => {
        const id = ds.part_id;
        return typeof id === 'number' && selectedPartIds.includes(id);
      })
    : [];

  onMount(() => {
    (async () => {
      const { from: mf, to: mt } = defaultMonthRange();
      deviceMonthFrom = mf;
      deviceMonthTo = mt;
      partMonthFrom = mf;
      partMonthTo = mt;

      await tick();

      const mod = await import('chart.js');
      mod.Chart.register(...mod.registerables);
      chartJsDefaults(mod.Chart);

      await loadDeviceSeries();
      await loadPartSeries();
    })();
  });

  onDestroy(() => {
    deviceChart?.destroy();
    partChart?.destroy();
  });
</script>

<div class="p-8 max-w-6xl mx-auto space-y-10">
  <h1 class="text-2xl font-bold text-white">Статистика</h1>

  <section class="bg-surface-800 border border-zinc-700 rounded-xl p-6">
    <h2 class="text-lg font-semibold text-white mb-4">Заказы приборов</h2>
    <p class="text-sm text-zinc-400 mb-4">
      По каждому прибору суммируется количество за календарный месяц
    </p>

    <div class="flex flex-wrap gap-4 items-end mb-6">
      <div>
        <label class="block text-sm text-zinc-400 mb-1">Месяц с</label>
        <input
          type="month"
          bind:value={deviceMonthFrom}
          class="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
        />
      </div>
      <div>
        <label class="block text-sm text-zinc-400 mb-1">Месяц по</label>
        <input
          type="month"
          bind:value={deviceMonthTo}
          class="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
        />
      </div>
      <button
        type="button"
        on:click={loadDeviceSeries}
        disabled={loadingDevices}
        class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400 disabled:opacity-50"
      >
        {loadingDevices ? 'Загрузка…' : 'Показать'}
      </button>
      <button
        type="button"
        on:click={() => openSelector('devices')}
        disabled={!devicePayload?.datasets.length}
        class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600 disabled:opacity-50"
      >
        Приборы: {selectedDeviceIds.length}/{devicePayload?.datasets.length ?? 0}
      </button>
    </div>

    {#if deviceError}
      <p class="text-red-400 text-sm mb-4">{deviceError}</p>
    {/if}

    {#if loadingDevices}
      <p class="text-zinc-400 mb-4">Загрузка…</p>
    {:else if selectedDeviceIds.length === 0 && devicePayload?.datasets.length}
      <p class="text-zinc-400 mb-4">Не выбраны приборы для отображения.</p>
    {:else if devicesEmpty && !deviceError}
      <p class="text-zinc-400 mb-4">Нет данных по заказам приборов за выбранный период.</p>
    {/if}

    <!-- canvas всегда в DOM, иначе при первой загрузке bind:this не срабатывает -->
    <div class="h-80 w-full" class:hidden={devicesEmpty && !loadingDevices && !deviceError}>
      <canvas bind:this={deviceCanvas} class="w-full h-full"></canvas>
    </div>
    {#if legendDeviceDatasets.length > 0}
      <div class="mt-3 max-h-32 overflow-y-auto rounded-lg border border-zinc-700/50 bg-zinc-900/40 px-3 py-2">
        <div class="flex flex-wrap gap-x-5 gap-y-1.5">
          {#each legendDeviceDatasets as ds}
            <div class="flex min-w-0 items-center gap-2">
              <span class="h-0.5 w-5 shrink-0 rounded-full" style="background-color: {ds.borderColor ?? '#888'}"></span>
              <span class="truncate text-xs text-zinc-300" title={ds.label}>{ds.label}</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </section>

  <section class="bg-surface-800 border border-zinc-700 rounded-xl p-6">
    <h2 class="text-lg font-semibold text-white mb-4">Заказы деталей</h2>
    <p class="text-sm text-zinc-400 mb-4">
      По каждой детали суммируется количество за календарный месяц
    </p>

    <div class="flex flex-wrap gap-4 items-end mb-6">
      <div>
        <label class="block text-sm text-zinc-400 mb-1">Месяц с</label>
        <input type="month" bind:value={partMonthFrom} class="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
      </div>
      <div>
        <label class="block text-sm text-zinc-400 mb-1">Месяц по</label>
        <input type="month" bind:value={partMonthTo} class="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
      </div>
      <button
        type="button"
        on:click={loadPartSeries}
        disabled={loadingPart}
        class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400 disabled:opacity-50"
      >
        {loadingPart ? 'Загрузка…' : 'Показать'}
      </button>
      <button
        type="button"
        on:click={() => openSelector('parts')}
        disabled={!partPayload?.datasets.length}
        class="px-4 py-2 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600 disabled:opacity-50"
      >
        Детали: {selectedPartIds.length}/{partPayload?.datasets.length ?? 0}
      </button>
    </div>

    {#if partError}
      <p class="text-red-400 text-sm mb-4">{partError}</p>
    {/if}

    {#if loadingPart}
      <p class="text-zinc-400 mb-4">Загрузка…</p>
    {:else if selectedPartIds.length === 0 && partPayload?.datasets.length}
      <p class="text-zinc-400">Не выбраны детали для отображения.</p>
    {:else if partSeriesEmpty && !partError}
      <p class="text-zinc-400">Нет заказов деталей за выбранный период.</p>
    {/if}
    <div class="h-80 w-full" class:hidden={partSeriesEmpty && !loadingPart && !partError}>
      <canvas bind:this={partCanvas} class="w-full h-full"></canvas>
    </div>
    {#if legendPartDatasets.length > 0}
      <div class="mt-3 max-h-32 overflow-y-auto rounded-lg border border-zinc-700/50 bg-zinc-900/40 px-3 py-2">
        <div class="flex flex-wrap gap-x-5 gap-y-1.5">
          {#each legendPartDatasets as ds}
            <div class="flex min-w-0 items-center gap-2">
              <span class="h-0.5 w-5 shrink-0 rounded-full" style="background-color: {ds.borderColor ?? '#888'}"></span>
              <span class="truncate text-xs text-zinc-300" title={ds.label}>{ds.label}</span>
            </div>
          {/each}
        </div>
      </div>
    {/if}
  </section>
</div>

{#if selectorModal}
  <div class="fixed inset-0 z-50 flex items-center justify-center bg-black/60" on:click={closeSelector} role="button" tabindex="0">
    <div class="w-full max-w-xl rounded-xl border border-zinc-700 bg-surface-800 p-6 shadow-xl" on:click|stopPropagation role="dialog">
      <div class="mb-4 flex items-center justify-between gap-3">
        <div>
          <h2 class="text-lg font-semibold text-white">
            {selectorModal === 'devices' ? 'Выбор приборов' : 'Выбор деталей'}
          </h2>
          <p class="text-sm text-zinc-400">
            Выбрано {selectorSelectedIds.length} из {selectorOptions.length}
          </p>
        </div>
        <button type="button" on:click={closeSelector} class="px-3 py-1.5 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">
          Закрыть
        </button>
      </div>

      <input
        bind:value={selectorSearch}
        placeholder={selectorModal === 'devices' ? 'Поиск прибора...' : 'Поиск детали...'}
        class="mb-3 w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white"
      />

      <div class="mb-3 flex flex-wrap gap-2">
        <button type="button" on:click={() => selectAll(selectorModal)} class="px-3 py-1.5 bg-emerald-700 text-white rounded-lg hover:bg-emerald-600">
          Выбрать все
        </button>
        <button type="button" on:click={() => clearAll(selectorModal)} class="px-3 py-1.5 bg-zinc-700 text-white rounded-lg hover:bg-zinc-600">
          Снять все
        </button>
      </div>

      <div class="max-h-[55vh] overflow-auto rounded-lg border border-zinc-700">
        {#if selectorFilteredOptions.length === 0}
          <div class="px-4 py-6 text-center text-zinc-400">Ничего не найдено.</div>
        {:else}
          <div class="divide-y divide-zinc-800">
            {#each selectorFilteredOptions as ds}
              {@const id = datasetId(selectorModal, ds)}
              {#if typeof id === 'number'}
                <label class="flex cursor-pointer items-center gap-3 px-4 py-2 hover:bg-zinc-800/60">
                  <input
                    type="checkbox"
                    checked={selectorSelectedIds.includes(id)}
                    on:change={(event) => {
                      const el = event.currentTarget;
                      if (el instanceof HTMLInputElement && selectorModal) {
                        toggleSelectorItem(selectorModal, id, el.checked);
                      }
                    }}
                    class="h-4 w-4"
                  />
                  <span class="min-w-0 flex-1 truncate text-zinc-100">{ds.label}</span>
                </label>
              {/if}
            {/each}
          </div>
        {/if}
      </div>
    </div>
  </div>
{/if}
