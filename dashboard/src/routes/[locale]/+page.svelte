<script lang="ts">
  import { onMount } from 'svelte';
  import { authStore, isAuthenticated, currentSchools } from '$lib/stores';
  import { 
    getDimensions,
    queryPeriodBased,
    me,
    type MeResponse,
    type SchoolSummary,
    type DimensionsResponse,
    type NewQueryResponse,
    type VariableDefinition,
    type DimensionDefinition
  } from '$lib/api';
  import ChartCard from '$lib/components/ChartCard.svelte';
  import { newQueryToChartData, newQueryToCSVWithLabels } from '$lib/chartUtils';
  import { createI18n, locale } from '$lib/i18n';

  const i18n = $derived(createI18n($locale));

  let loading = $state(true);
  let error = $state<string | null>(null);
  let meResponse = $state<MeResponse | null>(null);
  let schools = $state<SchoolSummary[]>([]);
  let selectedSchoolId = $state<number | null>(null);
  
  // Dimensions from the API
  let dimensions = $state<DimensionsResponse | null>(null);
  
  // Query options derived from dimensions
  const availableVariables = $derived(dimensions?.variables ?? []);
  const availableDimensions = $derived(dimensions?.dimensions ?? []);
  
  // Query parameters
  let selectedVariables = $state<string[]>([]);
  let selectedDimensions = $state<string[]>([]);
  
  let queryResult = $state<NewQueryResponse | null>(null);
  let queryLoading = $state(false);
  let queryError = $state<string | null>(null);

  onMount(async () => {
    try {
      // Get user identity (works for both anonymous and authenticated)
      const token = $authStore.token;
      meResponse = await me(token);
      
      // Extract schools from authenticated response
      if (meResponse.kind === "authenticated") {
        schools = meResponse.schools;
        
        // Pre-select user's first school if available
        if ($currentSchools && $currentSchools.length > 0) {
          selectedSchoolId = $currentSchools[0];
        } else if (schools.length > 0) {
          selectedSchoolId = schools[0].id;
        }
      }
      
      // Fetch dimensions - works for both anonymous and authenticated
      // If authenticated with a selected school, get school-specific dimensions
      const school_id = selectedSchoolId ?? undefined;
      
      dimensions = await getDimensions({ school_id, token });
      
      // Set default variable if available
      if (dimensions.variables.length > 0) {
        selectedVariables = [dimensions.variables[0].key];
      }
    } catch (e: unknown) {
      error = e instanceof Error ? e.message : i18n.t('dashboard.loadErrorHelp');
    } finally {
      loading = false;
    }
  });

  // Refetch dimensions when school selection changes
  $effect(() => {
    if (!loading && meResponse?.kind === "authenticated") {
      const school_id = selectedSchoolId ?? undefined;
      const token = $authStore.token;
      
      // Refetch dimensions for the new school scope
      getDimensions({ school_id, token })
        .then(newDimensions => {
          dimensions = newDimensions;
          
          // Clear current selections if they're no longer valid
          if (selectedVariables.length > 0) {
            const validVars = new Set(newDimensions.variables.map(v => v.key));
            selectedVariables = selectedVariables.filter(v => validVars.has(v));
            
            // If no variables remain selected, select first available
            if (selectedVariables.length === 0 && newDimensions.variables.length > 0) {
              selectedVariables = [newDimensions.variables[0].key];
            }
          }
          
          // Clear query results when school changes
          queryResult = null;
        })
        .catch(e => {
          error = e instanceof Error ? e.message : i18n.t('dashboard.loadErrorHelp');
        });
    }
  });

  function toggleVariable(key: string) {
    if (selectedVariables.includes(key)) {
      selectedVariables = selectedVariables.filter(v => v !== key);
    } else {
      selectedVariables = [...selectedVariables, key];
    }
  }

  function toggleDimension(key: string) {
    if (selectedDimensions.includes(key)) {
      selectedDimensions = selectedDimensions.filter(d => d !== key);
    } else {
      selectedDimensions = [...selectedDimensions, key];
    }
  }

  async function executeQuery() {
    if (selectedVariables.length === 0) {
      queryError = i18n.t("explore.selectAtLeastOneVariable");
      return;
    }

    queryLoading = true;
    queryError = null;
    queryResult = null;

    try {
      const token = $authStore.token;
      const school_id = selectedSchoolId ?? undefined;
      
      queryResult = await queryPeriodBased({
        v: selectedVariables,
        d: selectedDimensions,
        school_id,
        token,
      });
    } catch (e: unknown) {
      queryError = e instanceof Error ? e.message : i18n.t('dashboard.loadErrorHelp');
    } finally {
      queryLoading = false;
    }
  }

  // Chart rendering using utility functions
  const chartData = $derived(queryResult ? newQueryToChartData(queryResult, i18n.chartFormatters).data : { labels: [], datasets: [] });
  const chartCSV = $derived(queryResult ? newQueryToCSVWithLabels(queryResult, i18n.chartFormatters) : '');
  const chartType = $derived.by(() => {
    if (!queryResult) return 'bar' as const;
    const output = newQueryToChartData(queryResult, i18n.chartFormatters);
    return output.type ?? 'bar';
  });

  const selectedSchoolName = $derived(
    schools.find(s => s.id === selectedSchoolId)?.name ?? ''
  );

  const variableLabels = $derived(
    selectedVariables.map(v => i18n.columnLabel(v)).join(', ')
  );

  const queryNotes = $derived.by(() => {
    if (!queryResult) return [] as string[];

    let hasRescaled = false;
    let hasMultipleVersions = false;

    for (const variableSlice of queryResult.variables) {
      for (const periodSlice of Object.values(variableSlice.periods)) {
        if (periodSlice.notes?.includes('values-rescaled')) {
          hasRescaled = true;
        }
        if (periodSlice.question_versions && Object.keys(periodSlice.question_versions).length > 1) {
          hasMultipleVersions = true;
        }
      }
    }

    const notes: string[] = [];
    if (hasMultipleVersions) {
      notes.push(i18n.t('explore.multipleCompatibleVersionsNote'));
    }
    if (hasRescaled) {
      notes.push(i18n.t('explore.rescaledValuesNote'));
    }
    return notes;
  });

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

          <!-- School Selector (only for authenticated users) -->
          {#if meResponse?.kind === "authenticated" && schools.length > 0}
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
          {/if}

          <!-- Variable Selector (multi-select checkboxes) -->
          <div class="mb-4">
            <p class="block text-sm font-medium text-gray-700 mb-2">{i18n.t('explore.variables')}</p>
            <div class="space-y-2 max-h-48 overflow-y-auto">
              {#each availableVariables as variable}
                <label class="flex items-center">
                  <input
                    type="checkbox"
                    checked={selectedVariables.includes(variable.key)}
                    onchange={() => toggleVariable(variable.key)}
                    class="mr-2"
                  />
                  <span class="text-sm">{i18n.columnLabel(variable.key)} [{variable.key}]</span>
                </label>
              {/each}
            </div>
          </div>

          <!-- Dimension Selector (optional grouping) -->
          <div class="mb-4">
            <p class="block text-sm font-medium text-gray-700 mb-2">{i18n.t('explore.groupBy')}</p>
            <div class="space-y-2">
              {#each availableDimensions as dimension}
                <label class="flex items-center">
                  <input
                    type="checkbox"
                    checked={selectedDimensions.includes(dimension.key)}
                    onchange={() => toggleDimension(dimension.key)}
                    class="mr-2"
                  />
                  <span class="text-sm">{i18n.t(`api.${dimension.key}`)}</span>
                </label>
              {/each}
            </div>
          </div>

          <!-- Execute Button -->
          <button
            type="button"
            onclick={executeQuery}
            disabled={queryLoading || selectedVariables.length === 0}
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
          <!-- Display period information -->
          <div class="card">
            <p class="text-sm text-gray-600">
              <strong>{i18n.t('explore.periodsObserved')}:</strong> {queryResult.periods.join(', ')}
            </p>
            <p class="text-sm text-gray-600 mt-1">
              <strong>{i18n.t('explore.variablesSelected')}:</strong> {variableLabels}
            </p>
            {#if queryNotes.length > 0}
              <div class="mt-3 space-y-1">
                {#each queryNotes as note}
                  <p class="text-xs text-gray-500">(i) {note}</p>
                {/each}
              </div>
            {/if}
          </div>

          <!-- Check if all periods are suppressed for all variables -->
          {#if queryResult.variables.every(v => queryResult.periods.every(p => v.periods[p]?.suppressed))}
            <div class="card bg-yellow-50 border border-yellow-200">
              <p class="text-yellow-800 font-medium text-center">
                {i18n.t('explore.allDataSuppressed')}
              </p>
              <p class="text-sm text-yellow-700 mt-2 text-center">
                {i18n.t('explore.tryAdjustingFilters')}
              </p>
            </div>
          {:else}
            <ChartCard
              title={variableLabels}
              type={chartType}
              data={chartData}
              csv={chartCSV}
              filename="explore-results"
            />
          {/if}
        {:else if queryLoading}
          <div class="card text-center py-12">
            <p class="text-gray-500 mb-2">{i18n.t('explore.querying')}...</p>
            <p class="text-sm text-gray-400">{i18n.t('explore.privacyProtection')}</p>
          </div>
        {:else}
          <div class="card text-center py-12">
            <p class="text-gray-500 mb-2">{i18n.t('explore.selectQueryParams')}</p>
            <p class="text-sm text-gray-400">{i18n.t('explore.privacyProtection')}</p>
          </div>
        {/if}

        <!-- Partner Logos -->
        <div class="flex justify-center items-center gap-8 mt-8 flex-wrap">
          <a
            href="https://www.ox.ac.uk/"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="University of Oxford"
          >
            <img
              src="/img/university_of_oxford.svg"
              alt="University of Oxford"
              class="logo"
            />
          </a>
          <a
            href="https://wellbeing.hmc.ox.ac.uk/"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Wellbeing Research Centre"
          >
            <img
              src="/img/wellbeing_research_centre.svg"
              alt="Wellbeing Research Centre"
              class="logo"
            />
          </a>
          <a
            href="https://www.rse.ox.ac.uk/"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="Oxford RSE"
          >
            <img
              src="/img/oxford_rse.svg"
              alt="Oxford RSE"
              class="logo"
            />
          </a>
        </div>
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

  .logo {
    height: 100px;
    width: auto;
    transition: opacity 0.2s;
  }

  .logo:hover {
    opacity: 0.8;
  }
</style>
