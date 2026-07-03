<script lang="ts">
  import { Bar, Line } from 'svelte-chartjs';
  import {
    Chart,
    CategoryScale,
    LinearScale,
    BarElement,
    LineElement,
    PointElement,
    Title,
    Tooltip,
    Legend
  } from 'chart.js';
  import DataTable from './DataTable.svelte';
  import { downloadCSV } from '$lib/csvUtils';
  import type { ChartJsData } from '$lib/chartUtils';
  import { createI18n, locale } from '$lib/i18n';

  Chart.register(
    CategoryScale,
    LinearScale,
    BarElement,
    LineElement,
    PointElement,
    Title,
    Tooltip,
    Legend
  );

  interface Props {
    title: string;
    type: 'bar' | 'line' | 'horizontalBar';
    data: ChartJsData;
    options?: Record<string, unknown>;
    csv: string;
    suppressions?: Record<string, Record<number, string>>;
    filename?: string;
    noNeighborData?: boolean;
  }

  let {
    title,
    type,
    data,
    options = {},
    csv,
    suppressions = {},
    filename = 'data',
    noNeighborData = false
  }: Props = $props();

  const i18n = $derived(createI18n($locale));
  let showTable = $state(true);

  function handleDownload() {
    downloadCSV(`${filename}.csv`, csv);
  }

  const chartOptions = $derived({
    responsive: true,
    maintainAspectRatio: false,
    indexAxis: type === 'horizontalBar' ? 'y' as const : 'x' as const,
    ...options
  });
</script>

<div class="card space-y-4">
  <!-- Header -->
  <div class="flex items-start justify-between gap-4">
    <h3 class="font-semibold text-gray-800">{title}</h3>
    <div class="flex items-center gap-2 shrink-0">
      {#if data.datasets.length > 0}
        <button
          class="btn-secondary btn-sm"
          onclick={() => (showTable = !showTable)}
          aria-pressed={showTable}
        >
          {showTable ? i18n.t('chart.hideTable') : i18n.t('chart.showTable')}
        </button>
      {/if}
      {#if csv}
        <button class="btn-secondary btn-sm" onclick={handleDownload} title={i18n.t('chart.downloadCsv')}>
          ↓ CSV
        </button>
      {/if}
    </div>
  </div>

  <!-- Chart -->
  {#if data.datasets.length > 0}
    <div class="relative h-64">
      {#if type === 'line'}
        <Line {data} options={chartOptions} />
      {:else}
        <Bar {data} options={chartOptions} />
      {/if}
    </div>
    {#if noNeighborData}
      <p class="text-xs text-gray-500 mt-2">
        Note: No neighbour data is available for this query.
      </p>
    {/if}
  {:else}
    <div class="flex items-center justify-center h-32 bg-gray-50 rounded-lg text-gray-400 text-sm flex-col gap-2">
      <p>{i18n.t('chart.noData')}</p>
      {#if Object.keys(suppressions).length > 0}
        <p class="text-xs text-amber-600 max-w-md text-center">
          {i18n.t('chart.suppressionNotice')}
        </p>
      {/if}
    </div>
  {/if}

  <!-- Suppression notice (only shown when data is available) -->
  {#if Object.keys(suppressions).length > 0 && data.datasets.length > 0}
    <p class="text-xs text-amber-600">
      {i18n.t('chart.suppressionNotice')}
    </p>
  {/if}

  <!-- Table -->
  {#if showTable && csv}
    <DataTable {csv} {suppressions} />
  {/if}
</div>
