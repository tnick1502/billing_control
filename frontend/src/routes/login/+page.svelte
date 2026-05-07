<script lang="ts">
  import { api } from '$lib/api';

  let username = 'admin';
  let password = 'admin';
  let loading = false;
  let error = '';

  async function submit() {
    error = '';
    loading = true;
    try {
      await api.auth.login({ username, password });
      window.location.replace(`${window.location.origin}/monthly-plans`);
    } catch (e) {
      error = (e as Error).message;
    } finally {
      loading = false;
    }
  }
</script>

<div class="flex min-h-screen items-center justify-center bg-zinc-950 p-6">
  <div class="w-full max-w-md rounded-2xl border border-zinc-800 bg-surface-800 p-6 shadow-xl">
    <h1 class="mb-1 text-2xl font-bold text-white">Вход</h1>
    <p class="mb-6 text-sm text-zinc-400">Введите логин и пароль пользователя.</p>

    <form class="space-y-4" on:submit|preventDefault={submit}>
      <div>
        <label class="mb-1 block text-sm text-zinc-400">Логин</label>
        <input bind:value={username} required class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white" />
      </div>
      <div>
        <label class="mb-1 block text-sm text-zinc-400">Пароль</label>
        <input type="password" bind:value={password} required class="w-full rounded-lg border border-zinc-700 bg-zinc-900 px-3 py-2 text-white" />
      </div>

      {#if error}
        <div class="rounded-lg border border-red-500/50 bg-red-950/60 px-3 py-2 text-sm text-red-100">{error}</div>
      {/if}

      <button type="submit" disabled={loading} class="w-full rounded-lg bg-amber-500 px-4 py-2 font-medium text-black hover:bg-amber-400 disabled:opacity-50">
        {loading ? 'Вход...' : 'Войти'}
      </button>
    </form>
  </div>
</div>
