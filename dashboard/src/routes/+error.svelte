<script lang="ts">
  import { page } from "$app/stores";
  import { locale, createI18n } from "$lib/i18n";

  $: errorMessage = $page.error?.message || "An unexpected error occurred";
  $: errorStatus = $page.status || 500;
  $: i18n = createI18n($locale);
</script>

<svelte:head>
  <title>{errorStatus} - Error</title>
</svelte:head>

<main class="min-h-screen flex items-center justify-center bg-gray-50 px-4">
  <div class="max-w-md w-full text-center">
    <h1 class="text-6xl font-bold text-gray-900 mb-4">{errorStatus}</h1>
    <h2 class="text-2xl font-semibold text-gray-700 mb-4">
      {#if errorStatus === 404}
        Page Not Found
      {:else}
        Something went wrong
      {/if}
    </h2>
    <p class="text-gray-600 mb-8">{errorMessage}</p>
    <div class="space-y-4">
      <a
        href="/{$locale}"
        class="inline-block px-6 py-3 bg-blue-600 text-white font-medium rounded-lg hover:bg-blue-700 transition-colors"
      >
        {i18n.t("nav.home")}
      </a>
      <button
        onclick={() => window.location.reload()}
        class="block w-full px-6 py-3 bg-gray-200 text-gray-900 font-medium rounded-lg hover:bg-gray-300 transition-colors"
      >
        Reload Page
      </button>
    </div>
  </div>
</main>
