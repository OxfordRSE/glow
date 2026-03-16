<script lang="ts">
  import { authStore } from '$lib/stores';
  import {
    queryFrequency,
    queryMeans,
    queryWaveChange,
    ApiError
  } from '$lib/api';
  import type { FrequencyResult, MeansResult, WaveChangeResult, QueryFilter } from '$lib/api';
  import ChartCard from './ChartCard.svelte';
  import { frequencyToChartData, meansToChartData } from '$lib/chartUtils';

  // Whitelist from API — keep in sync with api/src/ib_ox_api/query.py
  const CATEGORICAL_COLS = [
    'school', 'yearGroup', 'class', 'sex', 'ethnicity', 'wave', 'd_city', 'd_country'
  ];
  const NUMERIC_COLS = [
    'phq9_1', 'phq9_2', 'phq9_3', 'phq9_4', 'phq9_5',
    'phq9_6', 'phq9_7', 'phq9_8', 'phq9_9', 'd_age'
  ];

  interface Props {
    columns: string[];
  }

  let { columns }: Props = $props();

  // Available columns (intersection with whitelists)
  const availableCategorical = $derived(CATEGORICAL_COLS.filter((c) => columns.includes(c)));
  const availableNumeric = $derived(NUMERIC_COLS.filter((c) => columns.includes(c)));
  const availableWaves = $derived(
    columns.includes('wave') ? ['1', '2', '3', '4', '5'] : []
  );

  type QueryType = 'frequency' | 'means' | 'wave-change';
  let queryType = $state<QueryType>('frequency');
  let groupBy = $state<string[]>([]);
  let valueColumns = $state<string[]>([]);
  let valueColumn = $state('');
  let fromWave = $state('1');
  let toWave = $state('2');
  let filters = $state<QueryFilter[]>([]);

  // The current query promise — null means no query submitted yet
  type QueryResult = FrequencyResult | MeansResult | WaveChangeResult;
  let queryPromise = $state<Promise<QueryResult> | null>(null);

  function toggleGroupBy(col: string) {
    if (groupBy.includes(col)) {
      groupBy = groupBy.filter((c) => c !== col);
    } else {
      groupBy = [...groupBy, col];
    }
  }

  function toggleValueColumn(col: string) {
    if (valueColumns.includes(col)) {
      valueColumns = valueColumns.filter((c) => c !== col);
    } else {
      valueColumns = [...valueColumns, col];
    }
  }

  function addFilter() {
    filters = [...filters, { column: columns[0] ?? '', op: 'eq', value: '' }];
  }

  function removeFilter(idx: number) {
    filters = filters.filter((_, i) => i !== idx);
  }

  function runQuery() {
    const token = $authStore.token;
    if (!token) return;

    if (queryType === 'frequency') {
      queryPromise = queryFrequency(token, {
        group_by: groupBy,
        filters,
        value_column: valueColumn || undefined
      });
    } else if (queryType === 'means') {
      queryPromise = queryMeans(token, {
        group_by: groupBy,
        value_columns: valueColumns,
        filters
      });
    } else {
      queryPromise = queryWaveChange(token, {
        from_wave: fromWave,
        to_wave: toWave,
        value_columns: valueColumns,
        group_by: groupBy,
        filters
      });
    }
  }

  const isValid = $derived(
    (queryType === 'frequency' && true) ||
    ((queryType === 'means' || queryType === 'wave-change') && valueColumns.length > 0)
  );

  function isFrequencyResult(r: QueryResult): r is FrequencyResult {
    return 'csv' in r && !('count_csv' in r);
  }
  function hasCsv(r: QueryResult): r is MeansResult | WaveChangeResult {
    return 'count_csv' in r;
  }
</script>

<div class="space-y-6">
  <!-- Query type selector -->
  <div class="card">
    <div class="flex flex-wrap gap-4">
      <label class="flex items-center gap-2 cursor-pointer">
        <input type="radio" name="queryType" value="frequency" bind:group={queryType} class="text-blue-600" />
        <span class="font-medium">Frequency</span>
        <span class="text-xs text-gray-500">(count students)</span>
      </label>
      <label class="flex items-center gap-2 cursor-pointer">
        <input type="radio" name="queryType" value="means" bind:group={queryType} class="text-blue-600" />
        <span class="font-medium">Means</span>
        <span class="text-xs text-gray-500">(average scores)</span>
      </label>
      {#if availableWaves.length > 0}
        <label class="flex items-center gap-2 cursor-pointer">
          <input type="radio" name="queryType" value="wave-change" bind:group={queryType} class="text-blue-600" />
          <span class="font-medium">Wave Change</span>
          <span class="text-xs text-gray-500">(within-person longitudinal change)</span>
        </label>
      {/if}
    </div>
  </div>

  <!-- Wave Change: wave selectors -->
  {#if queryType === 'wave-change'}
    <div class="card space-y-3">
      <h3 class="font-semibold text-gray-700">Waves</h3>
      <p class="text-xs text-gray-500">
        Computes <em>(value at To wave) - (value at From wave)</em> for each student, then takes the mean.
      </p>
      <div class="flex items-center gap-4">
        <div>
          <label class="label text-xs" for="from-wave">From wave</label>
          <select id="from-wave" class="input w-28" bind:value={fromWave}>
            {#each availableWaves as w}
              <option value={w}>{w}</option>
            {/each}
          </select>
        </div>
        <span class="text-gray-400 mt-5">→</span>
        <div>
          <label class="label text-xs" for="to-wave">To wave</label>
          <select id="to-wave" class="input w-28" bind:value={toWave}>
            {#each availableWaves as w}
              <option value={w}>{w}</option>
            {/each}
          </select>
        </div>
      </div>
    </div>
  {/if}

  <!-- Group by -->
  <div class="card space-y-3">
    <h3 class="font-semibold text-gray-700">Group By <span class="text-gray-400 font-normal">(optional for frequency)</span></h3>
    <div class="flex flex-wrap gap-2">
      {#each availableCategorical as col}
        <button
          class="px-3 py-1.5 rounded-full text-sm border transition-colors
            {groupBy.includes(col)
              ? 'bg-blue-600 text-white border-blue-600'
              : 'bg-white text-gray-700 border-gray-300 hover:border-blue-400'}"
          onclick={() => toggleGroupBy(col)}
        >
          {col}
        </button>
      {/each}
      {#if availableCategorical.length === 0}
        <p class="text-sm text-gray-400 italic">No categorical columns available.</p>
      {/if}
    </div>
  </div>

  <!-- Value columns (means / wave-change) or pivot (frequency) -->
  {#if queryType === 'means' || queryType === 'wave-change'}
    <div class="card space-y-3">
      <h3 class="font-semibold text-gray-700">Value Columns</h3>
      <p class="text-xs text-gray-500">Select columns to {queryType === 'means' ? 'average' : 'compare across waves'}.</p>
      <div class="flex flex-wrap gap-2">
        {#each availableNumeric as col}
          <button
            class="px-3 py-1.5 rounded-full text-sm border transition-colors
              {valueColumns.includes(col)
                ? 'bg-green-600 text-white border-green-600'
                : 'bg-white text-gray-700 border-gray-300 hover:border-green-400'}"
            onclick={() => toggleValueColumn(col)}
          >
            {col}
          </button>
        {/each}
        {#if availableNumeric.length === 0}
          <p class="text-sm text-gray-400 italic">No numeric columns available.</p>
        {/if}
      </div>
    </div>
  {:else}
    <div class="card space-y-3">
      <h3 class="font-semibold text-gray-700">Pivot Column <span class="text-gray-400 font-normal">(optional)</span></h3>
      <p class="text-xs text-gray-500">Cross-tabulate by this column (creates one column per unique value).</p>
      <select class="input max-w-xs" bind:value={valueColumn}>
        <option value="">— None (simple count) —</option>
        {#each availableCategorical as col}
          <option value={col}>{col}</option>
        {/each}
      </select>
    </div>
  {/if}

  <!-- Filters -->
  <div class="card space-y-3">
    <div class="flex items-center justify-between">
      <h3 class="font-semibold text-gray-700">Filters <span class="text-gray-400 font-normal">(optional)</span></h3>
      <button class="btn-secondary btn-sm" onclick={addFilter}>+ Add Filter</button>
    </div>

    {#if filters.length === 0}
      <p class="text-sm text-gray-400 italic">No filters applied.</p>
    {:else}
      <div class="space-y-2">
        {#each filters as filter, fi}
          <div class="flex items-center gap-2">
            <select class="input flex-1" bind:value={filter.column}>
              {#each columns as col}
                <option value={col}>{col}</option>
              {/each}
            </select>
            <select class="input w-24" bind:value={filter.op}>
              <option value="eq">=</option>
              <option value="ne">≠</option>
              <option value="in">in</option>
              <option value="gt">&gt;</option>
              <option value="lt">&lt;</option>
              <option value="gte">≥</option>
              <option value="lte">≤</option>
            </select>
            <input
              type="text"
              class="input flex-1"
              bind:value={filter.value as string}
              placeholder="value"
            />
            <button class="text-red-400 hover:text-red-600 p-1" onclick={() => removeFilter(fi)} aria-label="Remove filter">×</button>
          </div>
        {/each}
      </div>
    {/if}
  </div>

  <!-- Submit -->
  <div class="flex items-center gap-3">
    <button class="btn-primary" onclick={runQuery} disabled={!isValid}>
      Run Query
    </button>
    {#if !isValid}
      <p class="text-sm text-gray-400">Select at least one Value Column.</p>
    {/if}
  </div>

  <!-- Results via {#await} -->
  {#if queryPromise !== null}
    {#await queryPromise}
      <div class="card flex items-center justify-center h-32 text-gray-400">
        <svg class="animate-spin h-6 w-6 mr-2" fill="none" viewBox="0 0 24 24">
          <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
          <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8H4z"></path>
        </svg>
        Running query…
      </div>
    {:then result}
      {@const freq = queryType === 'frequency' ? result as FrequencyResult : null}
      {@const chart = freq
        ? frequencyToChartData(freq, groupBy)
        : meansToChartData(result as MeansResult | WaveChangeResult, groupBy)}
      <ChartCard
        title={
          queryType === 'frequency'
            ? 'Frequency Result'
            : queryType === 'means'
              ? 'Means Result'
              : `Wave ${fromWave} → ${toWave} Change Result`
        }
        type="bar"
        data={chart.data}
        options={chart.options}
        csv={result.csv}
        suppressions={result.suppressions}
        filename={`${queryType}-result`}
      />
    {:catch error}
      <div class="card bg-red-50 border-red-200 text-red-700 text-sm">
        {error instanceof ApiError ? `API error ${error.status}: ${error.message}` : error instanceof Error ? error.message : 'Query failed'}
      </div>
    {/await}
  {/if}
</div>
