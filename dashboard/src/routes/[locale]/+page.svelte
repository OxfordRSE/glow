<script lang="ts">
  import { onMount } from 'svelte';
  import { authStore } from '$lib/stores';
  import { listSchools, safeQuery, describeData, type School, type SafeQueryResponse, type DescribeDataResponse, type VariableOption, type AggregationOption, type FilterOption } from '$lib/api';
  import ChartCard from '$lib/components/ChartCard.svelte';
  import type { ChartJsData } from '$lib/chartUtils';
  import { createI18n, locale } from '$lib/i18n';

  const i18n = $derived(createI18n($locale));

  let loading = $state(true);
  let error = $state<string | null>(null);
  let schools = $state<School[]>([]);
  let selectedSchoolId = $state<number | null>(null);
  let neighborType = $state<'geographical' | 'statistical'>('geographical');  // Always include neighbors, just choose type
  
  // Data description from API
  let dataDescription = $state<DescribeDataResponse | null>(null);
  
  // Query parameters - now loaded from API
  const variables = $derived(
    dataDescription?.variables.map(v => ({
      value: v.value,
      label: i18n.t(v.label_key)
    })) ?? []
  );
  
  const aggregationOptions = $derived(
    dataDescription?.aggregation_options.map(a => ({
      value: a.value,
      label: i18n.t(a.label_key)
    })) ?? []
  );
  
  const filterOptions = $derived(
    dataDescription?.filter_options
      .filter(f => f.value !== 'wave')  // Wave is now first-class, not a filter
      .map(f => ({
        value: f.value,
        label: i18n.t(f.label_key),
        values: f.values
      })) ?? []
  );
  
  const waveOptions = $derived(
    dataDescription?.filter_options
      .find(f => f.value === 'wave')?.values ?? []
  );
  
  let selectedVariable = $state('bw_wbeing_1');
  let selectedAggregations = $state<string[]>([]);
  let selectedFilters = $state<Record<string, string[]>>({});
  let selectedWaves = $state<string[]>([]);  // Wave is now first-class
  
  let queryResult = $state<SafeQueryResponse | null>(null);
  let queryLoading = $state(false);
  let queryError = $state<string | null>(null);

  onMount(async () => {
    const token = $authStore.token;
    if (!token) return;

    try {
      // Fetch both schools and data description
      const [schoolsData, dataDesc] = await Promise.all([
        listSchools(token),
        describeData(token)
      ]);
      
      schools = schoolsData;
      dataDescription = dataDesc;
      
      // Set default variable if available
      if (dataDescription.variables.length > 0) {
        selectedVariable = dataDescription.variables[0].value;
      }
      
      // Set default waves to all available waves
      const waveFilter = dataDescription.filter_options.find(f => f.value === 'wave');
      if (waveFilter && waveFilter.values.length > 0) {
        selectedWaves = [...waveFilter.values];
      }
      
      // Pre-select user's first school if available
      if ($authStore.user?.school_ids && $authStore.user.school_ids.length > 0) {
        selectedSchoolId = $authStore.user.school_ids[0];
      } else if (schools.length > 0) {
        selectedSchoolId = schools[0].id;
      }
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : i18n.t('dashboard.loadErrorHelp');
    } finally {
      loading = false;
    }
  });

  function toggleWave(value: string) {
    if (selectedWaves.includes(value)) {
      selectedWaves = selectedWaves.filter(w => w !== value);
    } else {
      selectedWaves = [...selectedWaves, value];
    }
  }

  function toggleAggregation(value: string) {
    if (selectedAggregations.includes(value)) {
      selectedAggregations = selectedAggregations.filter(a => a !== value);
    } else {
      selectedAggregations = [...selectedAggregations, value];
    }
  }

  function toggleFilter(dimension: string, value: string) {
    if (!selectedFilters[dimension]) {
      selectedFilters[dimension] = [];
    }
    
    if (selectedFilters[dimension].includes(value)) {
      selectedFilters[dimension] = selectedFilters[dimension].filter(v => v !== value);
      if (selectedFilters[dimension].length === 0) {
        delete selectedFilters[dimension];
      }
    } else {
      selectedFilters[dimension] = [...selectedFilters[dimension], value];
    }
    selectedFilters = { ...selectedFilters };
  }

  async function executeQuery() {
    const token = $authStore.token;
    if (!token || selectedSchoolId === null || selectedWaves.length === 0) return;

    queryLoading = true;
    queryError = null;
    queryResult = null;

    try {
      // Class aggregation not allowed with neighbors (and neighbors are always included)
      const aggregations = selectedAggregations.filter(a => a !== 'class');

      queryResult = await safeQuery(token, {
        school_id: selectedSchoolId,
        variable: selectedVariable,
        waves: selectedWaves,
        aggregations,
        filters: selectedFilters,
        include_neighbors: true,  // Always include neighbors
        neighbor_type: neighborType,
      });
    } catch (e: unknown) {
      queryError = e instanceof Error ? e.message : i18n.t('dashboard.loadErrorHelp');
    } finally {
      queryLoading = false;
    }
  }

  function safeQueryToChartData(response: SafeQueryResponse): ChartJsData {
    const { focus_school, neighbors, waves } = response;

    // If all waves are suppressed for focus school, return empty
    const hasAnyData = waves.some(wave => {
      const waveResult = focus_school.results[wave];
      return waveResult && !waveResult.suppressed && waveResult.results;
    });

    if (!hasAnyData) {
      return { labels: [], datasets: [] };
    }

    const aggregations = response.aggregations;
    const datasets: any[] = [];
    
    // For multiple waves: x-axis = waves, datasets = school-aggregation combinations
    // For single wave: x-axis = aggregation values (or school if no aggregations), datasets = schools
    
    if (waves.length > 1) {
      // Multiple waves: line chart with waves on x-axis
      const labels = waves;
      
      if (aggregations.length === 0) {
        // No aggregations: one dataset per school showing overall mean over time
        const focusData: number[] = [];
        waves.forEach(wave => {
          const waveData = focus_school.results[wave];
          if (waveData && !waveData.suppressed && waveData.results && waveData.results.length > 0) {
            focusData.push(waveData.results[0].mean as number);
          } else {
            focusData.push(NaN); // Missing data
          }
        });
        
        datasets.push({
          label: focus_school.school_name,
          data: focusData,
          backgroundColor: 'rgba(59, 130, 246, 0.8)',
          borderColor: 'rgba(59, 130, 246, 1)',
          borderWidth: 2,
          tension: 0.3,
          fill: false,
        });
        
        // Add neighbor datasets
        neighbors.forEach((neighbor, idx) => {
          const neighborData: number[] = [];
          waves.forEach(wave => {
            const waveData = neighbor.results[wave];
            if (waveData && !waveData.suppressed && waveData.results && waveData.results.length > 0) {
              neighborData.push(waveData.results[0].mean as number);
            } else {
              neighborData.push(NaN);
            }
          });
          
          const colors = [
            'rgba(156, 163, 175, 0.5)',
            'rgba(156, 163, 175, 0.4)',
            'rgba(156, 163, 175, 0.3)',
          ];
          const borderColors = [
            'rgba(156, 163, 175, 0.8)',
            'rgba(156, 163, 175, 0.7)',
            'rgba(156, 163, 175, 0.6)',
          ];
          
          datasets.push({
            label: neighbor.school_name,
            data: neighborData,
            backgroundColor: colors[idx % colors.length],
            borderColor: borderColors[idx % borderColors.length],
            borderWidth: 2,
            tension: 0.3,
            fill: false,
          });
        });
        
        return { labels, datasets };
      } else {
        // With aggregations: one dataset per school-aggregation combination
        // First, collect all unique aggregation value combinations from first wave
        const firstWave = waves[0];
        const firstWaveData = focus_school.results[firstWave];
        if (!firstWaveData || firstWaveData.suppressed || !firstWaveData.results) {
          return { labels: [], datasets: [] };
        }
        
        const aggValueCombinations = firstWaveData.results.map(r => 
          aggregations.map(agg => r[agg]).join(' - ')
        );
        
        // For each aggregation value combination in focus school
        aggValueCombinations.forEach((aggCombo, aggIdx) => {
          const data: number[] = [];
          
          waves.forEach(wave => {
            const waveData = focus_school.results[wave];
            if (waveData && !waveData.suppressed && waveData.results) {
              const matchingRow = waveData.results[aggIdx];
              if (matchingRow) {
                data.push(matchingRow.mean as number);
              } else {
                data.push(NaN);
              }
            } else {
              data.push(NaN);
            }
          });
          
          const colors = [
            'rgba(59, 130, 246, 0.8)',
            'rgba(16, 185, 129, 0.8)',
            'rgba(245, 158, 11, 0.8)',
            'rgba(236, 72, 153, 0.8)',
            'rgba(139, 92, 246, 0.8)',
          ];
          const borderColors = [
            'rgba(59, 130, 246, 1)',
            'rgba(16, 185, 129, 1)',
            'rgba(245, 158, 11, 1)',
            'rgba(236, 72, 153, 1)',
            'rgba(139, 92, 246, 1)',
          ];
          
          datasets.push({
            label: `${focus_school.school_name} - ${aggCombo}`,
            data,
            backgroundColor: colors[aggIdx % colors.length],
            borderColor: borderColors[aggIdx % borderColors.length],
            borderWidth: 2,
            tension: 0.3,
            fill: false,
          });
        });
        
        // Add neighbor datasets
        neighbors.forEach((neighbor, neighborIdx) => {
          aggValueCombinations.forEach((aggCombo, aggIdx) => {
            const data: number[] = [];
            
            waves.forEach(wave => {
              const waveData = neighbor.results[wave];
              if (waveData && !waveData.suppressed && waveData.results) {
                const matchingRow = waveData.results[aggIdx];
                if (matchingRow) {
                  data.push(matchingRow.mean as number);
                } else {
                  data.push(NaN);
                }
              } else {
                data.push(NaN);
              }
            });
            
            const colors = [
              'rgba(156, 163, 175, 0.5)',
              'rgba(156, 163, 175, 0.4)',
              'rgba(156, 163, 175, 0.3)',
            ];
            const borderColors = [
              'rgba(156, 163, 175, 0.8)',
              'rgba(156, 163, 175, 0.7)',
              'rgba(156, 163, 175, 0.6)',
            ];
            
            datasets.push({
              label: `${neighbor.school_name} - ${aggCombo}`,
              data,
              backgroundColor: colors[neighborIdx % colors.length],
              borderColor: borderColors[neighborIdx % borderColors.length],
              borderWidth: 2,
              tension: 0.3,
              fill: false,
            });
          });
        });
        
        return { labels, datasets };
      }
    } else {
      // Single wave: horizontal bar chart with aggregations on x-axis
      const wave = waves[0];
      const focusWaveData = focus_school.results[wave];
      
      if (!focusWaveData || focusWaveData.suppressed || !focusWaveData.results) {
        return { labels: [], datasets: [] };
      }
      
      const labels = focusWaveData.results.map(r => {
        if (aggregations.length === 0) {
          return focus_school.school_name;
        }
        return aggregations.map(agg => r[agg]).join(' - ');
      });
      
      const focusValues = focusWaveData.results.map(r => r.mean as number);
      
      datasets.push({
        label: focus_school.school_name,
        data: focusValues,
        backgroundColor: 'rgba(59, 130, 246, 0.8)',
        borderColor: 'rgba(59, 130, 246, 1)',
        borderWidth: 2,
      });
      
      // Add neighbor datasets
      neighbors.forEach((neighbor, idx) => {
        const neighborWaveData = neighbor.results[wave];
        if (neighborWaveData && !neighborWaveData.suppressed && neighborWaveData.results && neighborWaveData.results.length > 0) {
          const neighborValues = neighborWaveData.results.map(r => r.mean as number);
          const colors = [
            'rgba(156, 163, 175, 0.5)',
            'rgba(156, 163, 175, 0.4)',
            'rgba(156, 163, 175, 0.3)',
          ];
          const borderColors = [
            'rgba(156, 163, 175, 0.8)',
            'rgba(156, 163, 175, 0.7)',
            'rgba(156, 163, 175, 0.6)',
          ];

          datasets.push({
            label: neighbor.school_name,
            data: neighborValues,
            backgroundColor: colors[idx % colors.length],
            borderColor: borderColors[idx % borderColors.length],
            borderWidth: 2,
          });
        }
      });
      
      return { labels, datasets };
    }
  }

  function safeQueryToCSV(response: SafeQueryResponse): string {
    const { focus_school, neighbors, waves } = response;
    const aggregations = response.aggregations;

    // Build CSV header
    const headers = ['School', 'Wave', ...aggregations, 'Mean', 'Student count'];
    const rows = [headers.join(',')];

    // Add focus school rows for each wave
    waves.forEach(wave => {
      const waveData = focus_school.results[wave];
      if (waveData && !waveData.suppressed && waveData.results) {
        waveData.results.forEach(row => {
          const csvRow = [
            focus_school.school_name,
            wave,
            ...aggregations.map(agg => row[agg]),
            (row.mean as number).toFixed(2),
            row.student_n,
          ];
          rows.push(csvRow.join(','));
        });
      }
    });

    // Add neighbor rows for each wave
    neighbors.forEach(neighbor => {
      waves.forEach(wave => {
        const waveData = neighbor.results[wave];
        if (waveData && !waveData.suppressed && waveData.results) {
          waveData.results.forEach(row => {
            const csvRow = [
              neighbor.school_name,
              wave,
              ...aggregations.map(agg => row[agg]),
              (row.mean as number).toFixed(2),
              row.student_n,
            ];
            rows.push(csvRow.join(','));
          });
        }
      });
    });

    return rows.join('\n');
  }

  const chartData = $derived(queryResult ? safeQueryToChartData(queryResult) : { labels: [], datasets: [] });
  const chartCSV = $derived(queryResult ? safeQueryToCSV(queryResult) : '');
  const chartType = $derived.by(() => {
    if (!queryResult) return 'bar' as const;
    // Multiple waves use line chart, single wave uses horizontal bar
    return queryResult.waves.length > 1 ? 'line' as const : 'horizontalBar' as const;
  });

  const selectedSchoolName = $derived(
    schools.find(s => s.id === selectedSchoolId)?.name ?? ''
  );

  const variableLabel = $derived(
    variables.find(v => v.value === selectedVariable)?.label ?? selectedVariable
  );

</script>

<div class="max-w-7xl mx-auto space-y-6">
  <div>
    <h1 class="text-3xl font-bold">{i18n.t('explore.title')}</h1>
    <p class="text-gray-500 mt-1">{i18n.t('explore.subtitle')}</p>
  </div>

  {#if loading}
    <div class="card motion-safe:animate-pulse h-64 bg-gray-100"></div>
  {:else if error}
    <div class="card bg-red-50 border-red-200">
      <p class="text-red-700">{error}</p>
    </div>
  {:else}
    <div class="grid grid-cols-1 lg:grid-cols-3 gap-6">
      <!-- Sidebar: Query Builder -->
      <div class="lg:col-span-1 space-y-4">
        <div class="card">
          <h2 class="text-lg font-semibold mb-4">{i18n.t('explore.queryParameters')}</h2>

          <!-- School Selector -->
          <div class="mb-4">
            <label for="school-select" class="block text-sm font-medium text-gray-700 mb-2">{i18n.t('explore.school')}</label>
            <select
              id="school-select"
              bind:value={selectedSchoolId}
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {#each schools as school}
                <option value={school.id}>{school.name}</option>
              {/each}
            </select>
          </div>

          <!-- Variable Selector -->
          <div class="mb-4">
            <label for="variable-select" class="block text-sm font-medium text-gray-700 mb-2">{i18n.t('explore.variable')}</label>
            <select
              id="variable-select"
              bind:value={selectedVariable}
              class="w-full px-3 py-2 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            >
              {#each variables as variable}
                <option value={variable.value}>{variable.label}</option>
              {/each}
            </select>
          </div>

          <!-- Aggregations -->
          <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">{i18n.t('explore.groupBy')}</label>
            <div class="space-y-2">
              {#each aggregationOptions as option}
                <label class="flex items-center">
                  <input
                    type="checkbox"
                    checked={selectedAggregations.includes(option.value)}
                    onchange={() => toggleAggregation(option.value)}
                    class="mr-2"
                  />
                  <span class="text-sm">{option.label}</span>
                </label>
              {/each}
            </div>
          </div>

          <!-- Wave Selector -->
          <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">{i18n.t('explore.waves')}</label>
            <div class="flex flex-wrap gap-2">
              {#each waveOptions as wave}
                <button
                  type="button"
                  class="px-3 py-1.5 text-sm rounded-md border transition-colors {selectedWaves.includes(wave)
                    ? 'bg-blue-500 text-white border-blue-600'
                    : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}"
                  onclick={() => toggleWave(wave)}
                >
                  Wave {wave}
                </button>
              {/each}
            </div>
          </div>

          <!-- Filters -->
          <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">{i18n.t('explore.filters')}</label>
            {#each filterOptions as filter}
              <div class="mb-3">
                <p class="text-xs font-medium text-gray-600 mb-1">{filter.label}</p>
                <div class="flex flex-wrap gap-2">
                  {#each filter.values as value}
                    <button
                      type="button"
                      class="px-2 py-1 text-xs rounded-md border transition-colors {selectedFilters[filter.value]?.includes(value)
                        ? 'bg-blue-500 text-white border-blue-600'
                        : 'bg-white text-gray-700 border-gray-300 hover:bg-gray-50'}"
                      onclick={() => toggleFilter(filter.value, value)}
                    >
                      {value}
                    </button>
                  {/each}
                </div>
              </div>
            {/each}
          </div>

          <!-- Neighbor Type Selection (always active) -->
          <div class="mb-4">
            <label class="block text-sm font-medium text-gray-700 mb-2">{i18n.t('explore.neighborType')}</label>
            <div class="space-y-2">
              <label class="flex items-center">
                <input
                  type="radio"
                  value="geographical"
                  bind:group={neighborType}
                  class="mr-2"
                />
                <span class="text-sm">{i18n.t('explore.geographical')}</span>
              </label>
              <label class="flex items-center">
                <input
                  type="radio"
                  value="statistical"
                  bind:group={neighborType}
                  class="mr-2"
                />
                <span class="text-sm">{i18n.t('explore.statistical')}</span>
              </label>
            </div>
          </div>

          {#if selectedAggregations.includes('class')}
            <div class="mb-4 p-3 bg-yellow-50 border border-yellow-200 rounded-md">
              <p class="text-xs text-yellow-800">
                {i18n.t('explore.classAggregationNote')}
              </p>
            </div>
          {/if}

          <!-- Execute Button -->
          <button
            type="button"
            onclick={executeQuery}
            disabled={queryLoading || selectedSchoolId === null}
            class="w-full px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 disabled:bg-gray-400 disabled:cursor-not-allowed transition-colors"
          >
            {queryLoading ? i18n.t('explore.querying') : i18n.t('explore.runQuery')}
          </button>
        </div>
      </div>

      <!-- Main: Results -->
      <div class="lg:col-span-2 space-y-4">
        {#if queryError}
          <div class="card bg-red-50 border-red-200">
            <p class="text-red-700">{queryError}</p>
          </div>
        {:else if queryResult}
          <!-- Check if all waves are suppressed -->
          {#if queryResult.waves.every(wave => queryResult.focus_school.results[wave]?.suppressed)}
            <div class="card bg-yellow-50 border border-yellow-200">
              <p class="text-yellow-800 font-medium text-center">
                {queryResult.focus_school.results[queryResult.waves[0]]?.suppression_message || 'Results cannot be displayed due to small group sizes.'}
              </p>
              <p class="text-sm text-yellow-700 mt-2 text-center">
                {i18n.t('explore.tryAdjustingFilters')}
              </p>
            </div>
          {:else}
            <ChartCard
              title="{variableLabel} - {queryResult.focus_school.school_name}"
              type={chartType}
              data={chartData}
              csv={chartCSV}
              filename="explore-results"
              noNeighborData={queryResult.neighbors.length === 0}
            />

            {#if queryResult.neighbors.length > 0}
              <div class="card p-3 bg-blue-50 border border-blue-200">
                <p class="text-sm text-blue-800">
                  {i18n.t('explore.showingComparison', { 
                    count: queryResult.neighbors.length, 
                    plural: queryResult.neighbors.length > 1 ? 's' : '' 
                  })}
                </p>
              </div>
            {/if}
          {/if}
        {:else}
          <div class="card text-center py-12">
            <p class="text-gray-500 mb-2">{i18n.t('explore.selectQueryParams')}</p>
            <p class="text-sm text-gray-400">{i18n.t('explore.privacyProtection')}</p>
          </div>
        {/if}
      </div>
    </div>
  {/if}
</div>

<style>
  :global(body) {
    @apply bg-gray-50;
  }

  .card {
    @apply bg-white rounded-lg shadow-sm border border-gray-200 p-6;
  }

  h1 {
    @apply text-2xl font-bold text-gray-900;
  }

  h2 {
    @apply text-xl font-semibold text-gray-900;
  }
</style>
