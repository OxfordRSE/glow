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
    type: 'bar' | 'line';
    data: ChartJsData;
    options?: Record<string, unknown>;
    csv: string;
    suppressions?: Record<string, Record<number, string>>;
    filename?: string;
  }

  let {
    title,
    type,
    data,
    options = {},
    csv,
    suppressions = {},
    filename = 'data'
  }: Props = $props();

  const i18n = $derived(createI18n($locale));
  let showTable = $state(false);

  function handleDownload() {
    downloadCSV(`${filename}.csv`, csv);
  }

  const chartOptions = $derived({
    responsive: true,
    maintainAspectRatio: false,
    ...options
  });
</script>

<div class="card space-y-4">
  <!-- Header -->
  <div class="flex items-start justify-between gap-4">
    <h3 class="font-semibold text-gray-800">{title}</h3>
    <div class="flex items-center gap-2 shrink-0">
      <button
        class="btn-secondary btn-sm"
        onclick={() => (showTable = !showTable)}
        aria-pressed={showTable}
      >
        {showTable ? i18n.t('chart.hideTable') : i18n.t('chart.showTable')}
      </button>
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
  {:else}
    <div class="flex items-center justify-center h-32 bg-gray-50 rounded-lg text-gray-400 text-sm">
      {i18n.t('chart.noData')}
    </div>
  {/if}

  <!-- Suppression notice -->
  {#if Object.keys(suppressions).length > 0}
    <p class="text-xs text-amber-600">
      {i18n.t('chart.suppressionNotice')}
    </p>
  {/if}

  <!-- Table -->
  {#if showTable && csv}
    <DataTable {csv} {suppressions} />
  {/if}
</div>
