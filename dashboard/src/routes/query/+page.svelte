<script lang="ts">
  import { onMount } from 'svelte';
  import { authStore } from '$lib/stores';
  import { getQueryCatalog } from '$lib/api';
  import type { QueryCatalog } from '$lib/api';
  import QueryBuilder from '$lib/components/QueryBuilder.svelte';

  let loading = $state(true);
  let error = $state<string | null>(null);
  let catalog = $state<QueryCatalog | null>(null);

  onMount(async () => {
    const token = $authStore.token;
    if (!token) return;
    try {
      catalog = await getQueryCatalog(token);
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : 'Failed to load query catalog';
    } finally {
      loading = false;
    }
  });
</script>

<svelte:head>
  <title>Query Builder — IB-Oxford Dashboard</title>
</svelte:head>

<div class="space-y-6">
  <div>
    <h1>Query Builder</h1>
    <p class="text-gray-500 mt-1">
      Compose safe analytical plans that can filter, derive scores, pair waves, bucket cohorts, and
      aggregate with built-in suppression.
    </p>
  </div>

  {#if loading}
    <div class="card flex items-center justify-center h-40 text-gray-400">
      <svg class="animate-spin h-8 w-8 mr-2" fill="none" viewBox="0 0 24 24">
        <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
        <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
      </svg>
      Loading query catalog…
    </div>
  {:else if error}
    <div class="card bg-red-50 border-red-200 text-red-700">{error}</div>
  {:else if catalog}
    <QueryBuilder {catalog} />
  {/if}
</div>
