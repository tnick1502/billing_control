<script lang="ts">
  import { goto } from '$app/navigation';
  import { currentUser, firstAllowedPath } from '$lib/permissions';

  // Стартовая страница зависит от роли: ведём в первый доступный раздел.
  $: target = $currentUser ? firstAllowedPath($currentUser) : null;
  $: if (target) goto(target, { replaceState: true });
</script>

{#if $currentUser && !target}
  <div class="p-8">
    <div class="max-w-lg rounded-xl border border-zinc-700 bg-surface-800 p-6">
      <h1 class="text-lg font-semibold text-white">Нет доступных разделов</h1>
      <p class="mt-2 text-sm text-zinc-400">
        Вашей роли пока не открыт ни один раздел. Обратитесь к администратору.
      </p>
    </div>
  </div>
{/if}
