<script lang="ts">
  import { onMount } from 'svelte';
  import { authStore, columnsStore } from '$lib/stores';
  import { getColumns, queryFrequency } from '$lib/api';
  import ChartCard from '$lib/components/ChartCard.svelte';
  import { frequencyToChartData, frequencyToLineData } from '$lib/chartUtils';
  import type { FrequencyResult } from '$lib/api';

  let loading = $state(true);
  let error = $state<string | null>(null);

  let countBySchool = $state<FrequencyResult | null>(null);
  let countBySex = $state<FrequencyResult | null>(null);
  let countByWave = $state<FrequencyResult | null>(null);

  onMount(async () => {
    const token = $authStore.token;
    if (!token) return;

    try {
      // Load columns if not cached
      if ($columnsStore.length === 0) {
        const cols = await getColumns(token);
        columnsStore.set(cols);
      }

      const cols = $columnsStore;
      const hasSchool = cols.includes('school');
      const hasSex = cols.includes('sex');
      const hasWave = cols.includes('wave');

      // Build overview charts from available columns
      const groupByCols = cols.filter(
        (c) => !c.startsWith('bw_') && c !== 'uid'
      );

      // Chart 1: Count by school (or first available categorical)
      if (hasSchool) {
        countBySchool = await queryFrequency(token, { group_by: ['school'], filters: [] });
      } else if (groupByCols[0]) {
        countBySchool = await queryFrequency(token, { group_by: [groupByCols[0]], filters: [] });
      }

      // Chart 2: Count by sex
      if (hasSex) {
        countBySex = await queryFrequency(token, {
          group_by: hasSex && hasSchool ? ['school', 'sex'] : ['sex'],
          filters: []
        });
      }

      // Chart 3: Count by wave (trend)
      if (hasWave) {
        countByWave = await queryFrequency(token, {
          group_by: hasSchool ? ['wave', 'school'] : ['wave'],
          filters: []
        });
      }
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : 'Failed to load dashboard';
    } finally {
      loading = false;
    }
  });

  let schoolChart = $derived(
    countBySchool
      ? frequencyToChartData(countBySchool, $columnsStore.includes('school') ? ['school'] : [$columnsStore.find((c) => c !== 'uid') ?? ''])
      : null
  );

  let sexChart = $derived(
    countBySex
      ? (() => {
          const hasSex = $columnsStore.includes('sex');
          const hasSchool = $columnsStore.includes('school');
          const gb = hasSex && hasSchool ? ['school', 'sex'] : ['sex'];
          return frequencyToChartData(countBySex!, gb);
        })()
      : null
  );

  let waveChart = $derived(
    countByWave
      ? frequencyToLineData(
          countByWave,
          $columnsStore.includes('school') ? ['wave', 'school'] : ['wave'],
          'wave'
        )
      : null
  );
</script>

<div class="space-y-6">
  <div>
    <h1>Dashboard</h1>
    <p class="text-gray-500 mt-1">Overview of IB-Oxford longitudinal questionnaire data.</p>
  </div>

  {#if loading}
    <div class="grid grid-cols-1 md:grid-cols-3 gap-6">
      {#each [1, 2, 3] as _}
        <div class="card animate-pulse h-64 bg-gray-100"></div>
      {/each}
    </div>
  {:else if error}
    <div class="card bg-red-50 border-red-200">
      <p class="text-red-700">{error}</p>
      <p class="text-sm text-gray-500 mt-2">
        If no data is loaded on the server, charts will be unavailable. Contact an administrator to ensure the dataset is configured correctly.
      </p>
    </div>
  {:else}
    <div class="grid grid-cols-1 lg:grid-cols-2 gap-6">
      {#if schoolChart}
        <ChartCard
          title="Participant Count by School"
          type="bar"
          data={schoolChart.data}
          options={schoolChart.options}
          csv={countBySchool?.csv ?? ''}
          suppressions={countBySchool?.suppressions ?? {}}
        />
      {/if}

      {#if sexChart}
        <ChartCard
          title="Participant Count by Sex"
          type="bar"
          data={sexChart.data}
          options={sexChart.options}
          csv={countBySex?.csv ?? ''}
          suppressions={countBySex?.suppressions ?? {}}
        />
      {/if}

      {#if waveChart}
        <div class="lg:col-span-2">
          <ChartCard
            title="Participants per Wave (Trend)"
            type="line"
            data={waveChart.data}
            options={waveChart.options}
            csv={countByWave?.csv ?? ''}
            suppressions={countByWave?.suppressions ?? {}}
          />
        </div>
      {/if}

      {#if !schoolChart && !sexChart && !waveChart}
        <div class="lg:col-span-2 card text-center text-gray-500 py-12">
          <p class="text-lg mb-2">No data available yet.</p>
          <p class="text-sm">The server may not have a dataset loaded. Check API configuration.</p>
        </div>
      {/if}
    </div>
  {/if}

  <!-- Getting started card -->
  <div class="card bg-blue-50 border-blue-200">
    <h2 class="text-blue-900 mb-2">Getting Started</h2>
    <ul class="text-sm text-blue-800 space-y-1 list-disc list-inside">
      <li>Charts support "Show Table" for a tabular view and "↓ CSV" to download data.</li>
      <li>Suppressed cells (small sample sizes) are shown as — to protect privacy.</li>
      {#if $authStore.user?.is_admin}
        <li>As an admin, you can <a href="/admin" class="underline font-medium">manage users</a> and their pre-filters.</li>
      {/if}
    </ul>
  </div>
</div>
