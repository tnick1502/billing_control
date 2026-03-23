<script lang="ts">
  import { onMount, onDestroy, tick } from 'svelte';
  import { api } from '$lib/api';
  import type { Part, StatsChartPayload } from '$lib/api';
  import type { Chart as ChartType } from 'chart.js';

  let deviceCanvas: HTMLCanvasElement;
  let partCanvas: HTMLCanvasElement;

  let deviceChart: ChartType | null = null;
  let partChart: ChartType | null = null;

  let parts: Part[] = [];
  /** Строка — как value у &lt;option&gt;, иначе bind ломается */
  let selectedPartId = '';

  /** Период для графика приборов: YYYY-MM */
  let deviceMonthFrom = '';
  let deviceMonthTo = '';
  let partDateFrom = '';
  let partDateTo = '';

  let loadingDevices = true;
  /** Нет строк в ответе за период */
  let devicesEmpty = true;
  let deviceError = '';

  let loadingPart = false;
  let partError = '';
  let partSeriesEmpty = false;

  function defaultDateRange() {
    const today = new Date();
    const to = today.toISOString().slice(0, 10);
    const f = new Date(today);
    f.setFullYear(f.getFullYear() - 1);
    const from = f.toISOString().slice(0, 10);
    return { from, to };
  }

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

  function formatAxisDate(iso: string) {
    const [y, m, d] = iso.split('-');
    return `${d}.${m}.${y}`;
  }

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
        legend: { position: 'top', labels: { color: '#d4d4d8' } },
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

  async function renderDeviceChart(payload: StatsChartPayload, Chart: typeof import('chart.js').Chart) {
    devicesEmpty = payload.labels.length === 0;
    const n = payload.labels.length;
    const pr = pointRadiusForCount(n);

    await tick();
    if (!deviceCanvas) return;
    deviceChart?.destroy();
    deviceChart = null;
    if (devicesEmpty) return;

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
    partSeriesEmpty = payload.labels.length === 0;
    const n = payload.labels.length;
    const pr = pointRadiusForCount(n);

    await tick();
    if (!partCanvas) return;
    partChart?.destroy();
    partChart = null;
    if (partSeriesEmpty) return;

    const ds = payload.datasets[0];
    partChart = new Chart(partCanvas, {
      type: 'line',
      data: {
        labels: payload.labels.map(formatAxisDate),
        datasets: [
          {
            label: ds.label,
            data: ds.data,
            borderColor: ds.borderColor ?? 'rgb(245, 158, 11)',
            backgroundColor: ds.backgroundColor ?? 'rgba(245, 158, 11, 0.15)',
            fill: true,
            tension: n <= 1 ? 0 : 0.25,
            pointRadius: pr,
            pointHoverRadius: pr + 2,
            borderWidth: 2,
          },
        ],
      },
      options: buildChartOptions(`Деталь «${(payload as { part_name: string }).part_name}»: заказано по датам`),
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
      await renderDeviceChart(payload, Chart);
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
    if (!selectedPartId || !partDateFrom || !partDateTo) {
      partError = 'Выберите деталь и период';
      return;
    }
    partError = '';
    loadingPart = true;
    try {
      const mod = await import('chart.js');
      const Chart = mod.Chart;
      const payload = await api.stats.ordersPartsTimeseries(Number(selectedPartId), partDateFrom, partDateTo);
      await renderPartChart(payload, Chart);
    } catch (e) {
      partError = (e as Error).message;
      partChart?.destroy();
      partChart = null;
    } finally {
      loadingPart = false;
    }
  }

  onMount(() => {
    (async () => {
      const { from: df, to: dt } = defaultDateRange();
      const { from: mf, to: mt } = defaultMonthRange();
      deviceMonthFrom = mf;
      deviceMonthTo = mt;
      partDateFrom = df;
      partDateTo = dt;

      try {
        parts = await api.parts.list();
        if (parts.length) selectedPartId = String(parts[0].id);
      } catch {
        parts = [];
      }

      await tick();

      const mod = await import('chart.js');
      mod.Chart.register(...mod.registerables);
      chartJsDefaults(mod.Chart);

      await loadDeviceSeries();

      await tick();
      if (parts.length && selectedPartId) {
        await loadPartSeries();
      }
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
      По каждому прибору суммируется количество за календарный месяц (все заказы за март и т.д.). Если заказы были только в одном
      месяце — на графике одна точка.
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
    </div>

    {#if deviceError}
      <p class="text-red-400 text-sm mb-4">{deviceError}</p>
    {/if}

    {#if loadingDevices}
      <p class="text-zinc-400 mb-4">Загрузка…</p>
    {:else if devicesEmpty && !deviceError}
      <p class="text-zinc-400 mb-4">Нет данных по заказам приборов за выбранный период.</p>
    {/if}

    <!-- canvas всегда в DOM, иначе при первой загрузке bind:this не срабатывает -->
    <div class="h-80 w-full" class:hidden={devicesEmpty && !loadingDevices && !deviceError}>
      <canvas bind:this={deviceCanvas} class="w-full h-full"></canvas>
    </div>
  </section>

  <section class="bg-surface-800 border border-zinc-700 rounded-xl p-6">
    <h2 class="text-lg font-semibold text-white mb-4">Заказы деталей (прямые позиции в заказе)</h2>
    <p class="text-sm text-zinc-400 mb-4">
      Сумма по дате заказа: прямые позиции «деталь в заказе» + расход по спецификации (BOM) из заказов приборов.
    </p>

    <div class="flex flex-wrap gap-4 items-end mb-6">
      <div>
        <label class="block text-sm text-zinc-400 mb-1">Деталь</label>
        <select
          bind:value={selectedPartId}
          class="min-w-[220px] px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
        >
          {#each parts as p}
            <option value={String(p.id)}>{p.name}</option>
          {/each}
        </select>
      </div>
      <div>
        <label class="block text-sm text-zinc-400 mb-1">Дата с</label>
        <input type="date" bind:value={partDateFrom} class="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
      </div>
      <div>
        <label class="block text-sm text-zinc-400 mb-1">Дата по</label>
        <input type="date" bind:value={partDateTo} class="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white" />
      </div>
      <button
        type="button"
        on:click={loadPartSeries}
        disabled={loadingPart || !parts.length}
        class="px-4 py-2 bg-amber-500 text-black font-medium rounded-lg hover:bg-amber-400 disabled:opacity-50"
      >
        {loadingPart ? 'Загрузка…' : 'Показать'}
      </button>
    </div>

    {#if partError}
      <p class="text-red-400 text-sm mb-4">{partError}</p>
    {/if}

    {#if !parts.length}
      <p class="text-zinc-400">Нет деталей в справочнике.</p>
    {:else}
      {#if partSeriesEmpty && !loadingPart && !partError}
        <p class="text-zinc-400">Нет заказов выбранной детали за этот период.</p>
      {/if}
      <div class="h-80 w-full" class:hidden={partSeriesEmpty && !loadingPart && !partError}>
        <canvas bind:this={partCanvas} class="w-full h-full"></canvas>
      </div>
    {/if}
  </section>
</div>
