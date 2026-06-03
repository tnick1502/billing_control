<script lang="ts">
  import { onMount } from 'svelte';
  import { api } from '$lib/api';
  import type { ImportResult, User } from '$lib/api';

  let file: File | null = null;
  let updateExisting = false;
  let busy = false;
  let error = '';
  let result: ImportResult | null = null;
  let resultIsDryRun = false;
  let exportingBom = false;
  let dumpingDb = false;
  let currentUser: User | null = null;
  let userLoaded = false;

  onMount(async () => {
    try {
      currentUser = await api.auth.me();
    } catch {
      currentUser = null;
    } finally {
      userLoaded = true;
    }
  });

  $: isAdmin = currentUser?.role === 'admin';

  function onFileChange(e: Event) {
    const input = e.target as HTMLInputElement;
    file = input.files && input.files.length ? input.files[0] : null;
    result = null;
    error = '';
  }

  async function run(dryRun: boolean) {
    if (!file) {
      error = 'Сначала выберите JSON-файл.';
      return;
    }
    busy = true;
    error = '';
    result = null;
    try {
      result = await api.imports.uploadBom(file, { dryRun, updateExisting });
      resultIsDryRun = dryRun;
    } catch (e) {
      error = (e as Error).message;
    } finally {
      busy = false;
    }
  }

  function triggerDownload(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    a.remove();
    URL.revokeObjectURL(url);
  }

  async function exportBom() {
    exportingBom = true;
    error = '';
    try {
      const { blob, filename } = await api.imports.exportBom();
      triggerDownload(blob, filename);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      exportingBom = false;
    }
  }

  async function dumpDb() {
    dumpingDb = true;
    error = '';
    try {
      const { blob, filename } = await api.imports.dumpDb();
      triggerDownload(blob, filename);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      dumpingDb = false;
    }
  }
</script>

<div class="p-8 max-w-3xl">
  <div class="mb-6">
    <h1 class="text-2xl font-bold text-white">Загрузка спецификаций</h1>
    <p class="mt-1 text-sm text-zinc-400">
      Загрузите подготовленный JSON-файл — программа заведёт приборы, детали и спецификации (BOM).
      Детали не дублируются: совпадение проверяется по наименованию и артикулу.
    </p>
  </div>

  {#if userLoaded && !isAdmin}
    <div class="rounded-xl border border-red-800/80 bg-red-950/60 p-5 text-sm text-red-100">
      <span class="font-semibold">Доступ ограничен.</span>
      Загрузка и выгрузка спецификаций, а также скачивание дампа БД доступны только администратору.
    </div>
  {:else if !userLoaded}
    <p class="text-sm text-zinc-400">Проверка прав…</p>
  {:else}

  <div class="rounded-xl border border-zinc-700 bg-surface-800 p-5 space-y-4">
    <div>
      <label class="block text-xs text-zinc-400 mb-1" for="import-file">Файл импорта (.json)</label>
      <input
        id="import-file"
        type="file"
        accept="application/json,.json"
        on:change={onFileChange}
        class="block w-full text-sm text-zinc-300 file:mr-3 file:rounded-lg file:border-0 file:bg-amber-500 file:px-4 file:py-2 file:text-black file:font-medium hover:file:bg-amber-400"
      />
      {#if file}
        <p class="mt-1 text-xs text-zinc-500">Выбран: {file.name} ({(file.size / 1024).toFixed(1)} КБ)</p>
      {/if}
    </div>

    <label class="flex items-center gap-2 text-sm text-zinc-300 cursor-pointer select-none">
      <input type="checkbox" bind:checked={updateExisting} class="w-4 h-4 accent-amber-500" />
      Пересобирать состав уже существующих спецификаций
    </label>

    <div class="flex gap-3 pt-1">
      <button
        on:click={() => run(true)}
        disabled={busy || !file}
        class="px-4 py-2 rounded-lg border border-zinc-600 text-zinc-200 font-medium hover:bg-zinc-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Проверить (без записи)
      </button>
      <button
        on:click={() => run(false)}
        disabled={busy || !file}
        class="px-4 py-2 rounded-lg bg-amber-500 text-black font-medium hover:bg-amber-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        Загрузить в базу
      </button>
    </div>

    {#if busy}
      <p class="text-sm text-zinc-400">Обработка...</p>
    {/if}
  </div>

  {#if error}
    <div class="mt-4 rounded-xl border border-red-800/80 bg-red-950/60 p-4 text-sm text-red-100">
      <span class="font-semibold">Ошибка:</span> {error}
    </div>
  {/if}

  <div class="mt-4 rounded-xl border border-zinc-700 bg-surface-800 p-5">
    <h2 class="text-lg font-semibold text-white mb-1">Выгрузка из базы</h2>
    <p class="text-sm text-zinc-400 mb-4">
      Скачать текущее состояние БД — JSON в том же формате, что и загрузка, или полный SQL-дамп.
    </p>
    <div class="flex flex-wrap gap-3">
      <button
        type="button"
        on:click={exportBom}
        disabled={exportingBom}
        class="px-4 py-2 rounded-lg border border-zinc-600 text-zinc-200 font-medium hover:bg-zinc-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {exportingBom ? 'Готовим JSON…' : 'Скачать JSON спецификаций'}
      </button>
      <button
        type="button"
        on:click={dumpDb}
        disabled={dumpingDb}
        class="px-4 py-2 rounded-lg border border-zinc-600 text-zinc-200 font-medium hover:bg-zinc-700 transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
      >
        {dumpingDb ? 'Готовим дамп…' : 'Скачать SQL-дамп БД'}
      </button>
    </div>
  </div>

  {#if result}
    <div class="mt-4 rounded-xl border border-zinc-700 bg-surface-800 p-5">
      <div class="mb-3 flex items-center gap-2">
        <h2 class="text-lg font-semibold text-white">
          {resultIsDryRun ? 'Результат проверки' : 'Загрузка завершена'}
        </h2>
        {#if resultIsDryRun}
          <span class="px-2 py-0.5 text-[11px] rounded bg-zinc-700 text-zinc-300">в базу не записано</span>
        {:else}
          <span class="px-2 py-0.5 text-[11px] rounded bg-emerald-900/80 text-emerald-200">сохранено</span>
        {/if}
      </div>

      <div class="grid grid-cols-2 sm:grid-cols-3 gap-3 text-sm">
        <div class="rounded-lg bg-zinc-900/60 p-3">
          <div class="text-zinc-400 text-xs">Детали</div>
          <div class="text-zinc-100">создано {result.parts_created} · найдено {result.parts_reused}</div>
        </div>
        <div class="rounded-lg bg-zinc-900/60 p-3">
          <div class="text-zinc-400 text-xs">Приборы</div>
          <div class="text-zinc-100">создано {result.devices_created} · найдено {result.devices_reused}</div>
        </div>
        <div class="rounded-lg bg-zinc-900/60 p-3">
          <div class="text-zinc-400 text-xs">Спецификации</div>
          <div class="text-zinc-100">
            создано {result.boms_created} · обновлено {result.boms_updated} · пропущено {result.boms_skipped}
          </div>
        </div>
        <div class="rounded-lg bg-zinc-900/60 p-3">
          <div class="text-zinc-400 text-xs">Позиции BOM</div>
          <div class="text-zinc-100">создано {result.items_created} · пропущено {result.items_skipped}</div>
        </div>
      </div>

      {#if result.warnings.length}
        <div class="mt-4">
          <div class="text-sm font-medium text-amber-400 mb-1">Предупреждения ({result.warnings.length})</div>
          <ul class="list-disc pl-5 space-y-1 text-sm text-zinc-300">
            {#each result.warnings as w}
              <li>{w}</li>
            {/each}
          </ul>
        </div>
      {/if}
    </div>
  {/if}
  {/if}
</div>
