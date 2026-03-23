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

  let deviceDateFrom = '';
  let deviceDateTo = '';
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

  function formatAxisDate(iso: string) {
    const [y, m, d] = iso.split('-');
    return `${d}.${m}.${y}`;
  }

  function chartJsDefaults(Chart: typeof import('chart.js').Chart) {
    Chart.defaults.color = '#a1a1aa';
    Chart.defaults.borderColor = '#3f3f46';
  }

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
          grid: { color: '#27272a' },
          offset: true,
        },
        y: {
          ticks: { color: '#a1a1aa' },
          grid: { color: '#27272a' },
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
        labels: payload.labels.map(formatAxisDate),
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
      options: buildChartOptions('Заказы приборов: количество по дате заказа'),
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
    if (!deviceDateFrom || !deviceDateTo) {
      deviceError = 'Укажите период';
      return;
    }
    deviceError = '';
    loadingDevices = true;
    try {
      const mod = await import('chart.js');
      const Chart = mod.Chart;
      const payload = await api.stats.ordersDevicesTimeseries(deviceDateFrom, deviceDateTo);
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
      const { from, to } = defaultDateRange();
      deviceDateFrom = from;
      deviceDateTo = to;
      partDateFrom = from;
      partDateTo = to;

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
      Сумма количества по строкам заказов (позиции с приборами) по дате заказа в выбранном периоде.
    </p>

    <div class="flex flex-wrap gap-4 items-end mb-6">
      <div>
        <label class="block text-sm text-zinc-400 mb-1">Дата с</label>
        <input
          type="date"
          bind:value={deviceDateFrom}
          class="px-3 py-2 bg-zinc-900 border border-zinc-700 rounded-lg text-white"
        />
      </div>
      <div>
        <label class="block text-sm text-zinc-400 mb-1">Дата по</label>
        <input
          type="date"
          bind:value={deviceDateTo}
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
    <p class="text-sm text-zinc-400 mb-4">Выберите деталь и период по дате заказа.</p>

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
