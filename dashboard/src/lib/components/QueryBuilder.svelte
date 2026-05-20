<script lang="ts">
  import { replaceState } from '$app/navigation';
  import { onMount } from 'svelte';
  import { authStore } from '$lib/stores';
  import { ApiError, query } from '$lib/api';
  import type {
    QueryCatalog,
    QueryFilter,
    QueryMetric,
    QueryPlan,
    QueryResult
  } from '$lib/api';
  import { queryToChartData } from '$lib/chartUtils';
  import ChartCard from './ChartCard.svelte';
  import { createI18n, locale } from '$lib/i18n';

  interface Props {
    catalog: QueryCatalog;
  }

  let { catalog }: Props = $props();
  const i18n = $derived(createI18n($locale));

  type StepType =
    | 'filter'
    | 'derive_score'
    | 'pair_waves'
    | 'bucket_school_size'
    | 'aggregate';

  type MetricEditor = {
    kind: 'count_students' | 'mean';
    column: string;
    as_column: string;
  };

  type RowGrain = 'student_wave' | 'student_pair' | 'aggregate';

  type StructureSnapshot = {
    rowGrain: RowGrain;
    dimensions: string[];
    measures: string[];
    internalColumns: string[];
    note: string;
  };

  type ShareableBuilderState = {
    v: 1;
    steps: StepEditor[];
  };

  type StepEditor =
    | {
        type: 'filter';
        column: string;
        op: QueryFilter['op'];
        value: string;
      }
    | {
        type: 'derive_score';
        score: 'bw_wbeing_total';
      }
    | {
        type: 'pair_waves';
        from_wave: string;
        to_wave: string;
        measures_text: string;
      }
    | {
        type: 'bucket_school_size';
        output_column: string;
        small_max: string;
        medium_min: string;
        medium_max: string;
        large_min: string;
      }
    | {
        type: 'aggregate';
        group_by_text: string;
        metrics: MetricEditor[];
      };

  let steps = $state<StepEditor[]>([
    {
      type: 'aggregate',
      group_by_text: 'school',
      metrics: [{ kind: 'count_students', column: '', as_column: '' }]
    }
  ]);
  let resultPromise = $state<Promise<QueryResult> | null>(null);
  let resultGroupBy = $state<string[]>(['school']);
  let builderError = $state<string | null>(null);
  let shareMessage = $state<string | null>(null);

  const HASH_PLAN_KEY = 'plan';
  let isApplyingHashState = false;
  let shareMessageTimeout: ReturnType<typeof setTimeout> | null = null;

  const filterableColumns = $derived(
    Array.from(
      new Set([
        ...catalog.dimensions,
        ...catalog.measures,
        ...catalog.scores,
        ...catalog.measures.flatMap((m) => [`baseline_${m}`, `comparison_${m}`, `change_${m}`]),
        ...catalog.scores.flatMap((s) => [`baseline_${s}`, `comparison_${s}`, `change_${s}`]),
        'school_size_bucket'
      ])
    ).sort()
  );

  const groupableColumns = $derived(
    Array.from(new Set([...catalog.dimensions, 'school_size_bucket'])).sort()
  );

  const measurableColumns = $derived(
    Array.from(
      new Set([
        ...catalog.measures,
        ...catalog.scores,
        ...catalog.measures.flatMap((m) => [`baseline_${m}`, `comparison_${m}`, `change_${m}`]),
        ...catalog.scores.flatMap((s) => [`baseline_${s}`, `comparison_${s}`, `change_${s}`])
      ])
    ).sort()
  );

  function createStep(type: StepType): StepEditor {
    if (type === 'filter') {
      return {
        type,
        column: catalog.dimensions[0] ?? 'school',
        op: 'eq',
        value: ''
      };
    }
    if (type === 'derive_score') {
      return { type, score: 'bw_wbeing_total' };
    }
    if (type === 'pair_waves') {
      return {
        type,
        from_wave: catalog.waves[0] ?? '1',
        to_wave: catalog.waves[1] ?? catalog.waves[0] ?? '2',
        measures_text: catalog.scores[0] ?? catalog.measures[0] ?? 'bw_wbeing_total'
      };
    }
    if (type === 'bucket_school_size') {
      return {
        type,
        output_column: 'school_size_bucket',
        small_max: '4',
        medium_min: '5',
        medium_max: '9',
        large_min: '10'
      };
    }
    return {
      type,
      group_by_text: 'school',
      metrics: [{ kind: 'count_students', column: '', as_column: '' }]
    };
  }

  function defaultSteps(): StepEditor[] {
    return [
      {
        type: 'aggregate',
        group_by_text: 'school',
        metrics: [{ kind: 'count_students', column: '', as_column: '' }]
      }
    ];
  }

  function addStep(type: StepType = 'filter') {
    if (steps.length > 0 && steps[steps.length - 1].type === 'aggregate') {
      steps = [...steps.slice(0, -1), createStep(type), steps[steps.length - 1]];
      return;
    }
    steps = [...steps, createStep(type)];
  }

  function insertStepAfter(index: number, type: StepType) {
    const newStep = createStep(type);
    const step = steps[index];

    if (step?.type === 'aggregate') {
      steps = [...steps.slice(0, index), newStep, ...steps.slice(index)];
      return;
    }

    steps = [...steps.slice(0, index + 1), newStep, ...steps.slice(index + 1)];
  }

  function removeStep(index: number) {
    steps = steps.filter((_, i) => i !== index);
  }

  function changeStepType(index: number, type: StepType) {
    steps[index] = createStep(type);
    steps = [...steps];
  }

  function addMetric(stepIndex: number) {
    const step = steps[stepIndex];
    if (step.type !== 'aggregate') return;
    step.metrics = [...step.metrics, { kind: 'mean', column: '', as_column: '' }];
    steps = [...steps];
  }

  function removeMetric(stepIndex: number, metricIndex: number) {
    const step = steps[stepIndex];
    if (step.type !== 'aggregate') return;
    step.metrics = step.metrics.filter((_, index) => index !== metricIndex);
    steps = [...steps];
  }

  function splitCsv(value: string): string[] {
    return value
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean);
  }

  function columnLabel(column: string): string {
    return i18n.columnLabel(column);
  }

  function columnText(value: string): string {
    return i18n.columnText(value);
  }

  function metricOutputName(metric: MetricEditor): string {
    if (metric.as_column.trim()) {
      return metric.as_column.trim();
    }
    if (metric.kind === 'count_students') {
      return 'student_n';
    }
    return metric.column.trim() || '<choose output column>';
  }

  function setShareFeedback(message: string) {
    shareMessage = message;
    if (shareMessageTimeout) {
      clearTimeout(shareMessageTimeout);
    }
    shareMessageTimeout = setTimeout(() => {
      shareMessage = null;
      shareMessageTimeout = null;
    }, 3000);
  }

  function encodeBase64Url(value: string): string {
    const bytes = new TextEncoder().encode(value);
    let binary = '';
    for (const byte of bytes) {
      binary += String.fromCharCode(byte);
    }
    return btoa(binary).replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/g, '');
  }

  function decodeBase64Url(value: string): string {
    const normalized = value.replace(/-/g, '+').replace(/_/g, '/');
    const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
    const binary = atob(padded);
    const bytes = Uint8Array.from(binary, (char) => char.charCodeAt(0));
    return new TextDecoder().decode(bytes);
  }

  function normalizeMetric(metric: unknown): MetricEditor {
    const source = typeof metric === 'object' && metric !== null ? metric as Record<string, unknown> : {};
    return {
      kind: source.kind === 'mean' ? 'mean' : 'count_students',
      column: typeof source.column === 'string' ? source.column : '',
      as_column: typeof source.as_column === 'string' ? source.as_column : ''
    };
  }

  function normalizeStep(step: unknown): StepEditor | null {
    const source = typeof step === 'object' && step !== null ? step as Record<string, unknown> : {};
    if (source.type === 'filter') {
      return {
        type: 'filter',
        column: typeof source.column === 'string' ? source.column : catalog.dimensions[0] ?? 'school',
        op: ['eq', 'ne', 'in', 'gt', 'lt', 'gte', 'lte'].includes(String(source.op)) ? source.op as QueryFilter['op'] : 'eq',
        value: typeof source.value === 'string' ? source.value : source.value == null ? '' : String(source.value)
      };
    }
    if (source.type === 'derive_score') {
      return {
        type: 'derive_score',
          score: source.score === 'bw_wbeing_total' ? 'bw_wbeing_total' : 'bw_wbeing_total'
      };
    }
    if (source.type === 'pair_waves') {
      return {
        type: 'pair_waves',
        from_wave: typeof source.from_wave === 'string' ? source.from_wave : catalog.waves[0] ?? '1',
        to_wave: typeof source.to_wave === 'string' ? source.to_wave : catalog.waves[1] ?? catalog.waves[0] ?? '2',
        measures_text: typeof source.measures_text === 'string' ? source.measures_text : catalog.scores[0] ?? catalog.measures[0] ?? 'bw_wbeing_total'
      };
    }
    if (source.type === 'bucket_school_size') {
      return {
        type: 'bucket_school_size',
        output_column: typeof source.output_column === 'string' ? source.output_column : 'school_size_bucket',
        small_max: typeof source.small_max === 'string' ? source.small_max : '4',
        medium_min: typeof source.medium_min === 'string' ? source.medium_min : '5',
        medium_max: typeof source.medium_max === 'string' ? source.medium_max : '9',
        large_min: typeof source.large_min === 'string' ? source.large_min : '10'
      };
    }
    if (source.type === 'aggregate') {
      const metrics = Array.isArray(source.metrics) ? source.metrics.map(normalizeMetric) : [];
      return {
        type: 'aggregate',
        group_by_text: typeof source.group_by_text === 'string' ? source.group_by_text : 'school',
        metrics: metrics.length > 0 ? metrics : [{ kind: 'count_students', column: '', as_column: '' }]
      };
    }
    return null;
  }

  function loadStateFromHash(hash: string): boolean {
    const raw = hash.startsWith('#') ? hash.slice(1) : hash;
    const params = new URLSearchParams(raw);
    const encoded = params.get(HASH_PLAN_KEY);
    if (!encoded) {
      steps = defaultSteps();
      return false;
    }

    const parsed = JSON.parse(decodeBase64Url(encoded)) as Partial<ShareableBuilderState>;
    if (parsed.v !== 1 || !Array.isArray(parsed.steps)) {
      throw new Error('Unsupported shared query format.');
    }

    const normalizedSteps = parsed.steps.map(normalizeStep).filter((step): step is StepEditor => step !== null);
    steps = normalizedSteps.length > 0 ? normalizedSteps : defaultSteps();
    return true;
  }

  function syncHashFromState() {
    if (typeof window === 'undefined' || isApplyingHashState) {
      return;
    }

    const params = new URLSearchParams(window.location.hash.slice(1));
    const encoded = encodeBase64Url(JSON.stringify({ v: 1, steps } satisfies ShareableBuilderState));
    params.set(HASH_PLAN_KEY, encoded);
    const nextHash = params.toString();

    if (window.location.hash.slice(1) === nextHash) {
      return;
    }

    replaceState(`${window.location.pathname}${window.location.search}#${nextHash}`, {});
  }

  function describeRowGrain(rowGrain: RowGrain): string {
    if (rowGrain === 'student_wave') {
      return 'One row per student per wave.';
    }
    if (rowGrain === 'student_pair') {
      return 'One row per matched student pair across two waves.';
    }
    return 'One row per aggregate group returned to the user.';
  }

  function initialStructure(): StructureSnapshot {
    return {
      rowGrain: 'student_wave',
      dimensions: [...catalog.dimensions].sort(),
      measures: [...catalog.measures].sort(),
      internalColumns: ['uid'],
      note: 'The scoped source table starts at student-wave grain. `uid` is present internally for suppression and wave pairing, but it is never a public output column.'
    };
  }

  function applyStepToStructure(
    structure: StructureSnapshot,
    step: StepEditor
  ): StructureSnapshot {
    if (structure.rowGrain === 'aggregate') {
      return {
        ...structure,
        note: 'Aggregation is terminal. The server rejects row-level steps after this point.'
      };
    }

    if (step.type === 'filter') {
      return {
        ...structure,
        note: `Filtering changes which rows survive, but the schema stays the same until a later step adds or removes columns.`
      };
    }

    if (step.type === 'derive_score') {
      const measures = Array.from(new Set([...structure.measures, step.score])).sort();
      return {
        ...structure,
        measures,
        note: `This adds the approved derived measure \`${step.score}\` to the current row-level structure.`
      };
    }

    if (step.type === 'pair_waves') {
      const selectedMeasures = splitCsv(step.measures_text);
      const pairedMeasures = selectedMeasures.flatMap((measure) => [
        `baseline_${measure}`,
        `comparison_${measure}`,
        `change_${measure}`
      ]);
      return {
        rowGrain: 'student_pair',
        dimensions: structure.dimensions.filter((dimension) => dimension !== 'wave'),
        measures: Array.from(new Set(pairedMeasures)).sort(),
        internalColumns: ['uid'],
        note: 'Pairing waves removes the public `wave` dimension and replaces the selected measures with baseline/comparison/change columns for each matched student.'
      };
    }

    if (step.type === 'bucket_school_size') {
      const outputColumn = step.output_column.trim() || 'school_size_bucket';
      return {
        ...structure,
        dimensions: Array.from(new Set([...structure.dimensions, outputColumn])).sort(),
        note: `This adds the derived grouping column \`${outputColumn}\` while keeping the current row grain unchanged.`
      };
    }

    const groupBy = splitCsv(step.group_by_text);
    const metricOutputs = step.metrics.map(metricOutputName);
    return {
      rowGrain: 'aggregate',
      dimensions: groupBy,
      measures: metricOutputs,
      internalColumns: [],
      note: 'This is the table shape returned to the user. The server still uses hidden `uid` lineage internally to compute suppression, but that identifier is not included in the result.'
    };
  }

  const structureSnapshots = $derived.by(() => {
    const snapshots: StructureSnapshot[] = [initialStructure()];
    for (const step of steps) {
      snapshots.push(applyStepToStructure(snapshots[snapshots.length - 1], step));
    }
    return snapshots;
  });

  const finalStructure = $derived.by(
    () => structureSnapshots[structureSnapshots.length - 1] ?? initialStructure()
  );

  function structuresMatch(left: StructureSnapshot, right: StructureSnapshot): boolean {
    return (
      left.rowGrain === right.rowGrain &&
      left.dimensions.join('|') === right.dimensions.join('|') &&
      left.measures.join('|') === right.measures.join('|') &&
      left.internalColumns.join('|') === right.internalColumns.join('|')
    );
  }

  function buildPlan(): QueryPlan {
    const builtSteps = steps.map((step) => {
      if (step.type === 'filter') {
        return {
          type: 'filter' as const,
          column: step.column.trim(),
          op: step.op,
          value: step.value.trim()
        };
      }

      if (step.type === 'derive_score') {
        return { type: 'derive_score' as const, score: step.score };
      }

      if (step.type === 'pair_waves') {
        const measures = splitCsv(step.measures_text);
        if (measures.length === 0) {
          throw new Error('pair_waves requires at least one measure.');
        }
        return {
          type: 'pair_waves' as const,
          from_wave: step.from_wave.trim(),
          to_wave: step.to_wave.trim(),
          measures
        };
      }

      if (step.type === 'bucket_school_size') {
        return {
          type: 'bucket_school_size' as const,
          output_column: step.output_column.trim(),
          bands: [
            { label: 'small', min_students: 0, max_students: Number(step.small_max) },
            {
              label: 'medium',
              min_students: Number(step.medium_min),
              max_students: Number(step.medium_max)
            },
            { label: 'large', min_students: Number(step.large_min) }
          ]
        };
      }

      const groupBy = splitCsv(step.group_by_text);
      const metrics: QueryMetric[] = step.metrics.map((metric) => ({
        kind: metric.kind,
        column: metric.kind === 'mean' ? metric.column.trim() : undefined,
        as_column: metric.as_column.trim() || undefined
      }));
      if (metrics.length === 0) {
        throw new Error('aggregate requires at least one metric.');
      }
      return {
        type: 'aggregate' as const,
        group_by: groupBy,
        metrics
      };
    });

    return { steps: builtSteps };
  }

  const planPreview = $derived.by(() => {
    try {
      return JSON.stringify(buildPlan(), null, 2);
    } catch (error) {
      return String(error instanceof Error ? error.message : error);
    }
  });

  function applyTemplate(name: 'simple' | 'longitudinal' | 'bucketed') {
    if (name === 'simple') {
      steps = [
        {
          type: 'aggregate',
          group_by_text: 'school',
          metrics: [{ kind: 'count_students', column: '', as_column: '' }]
        }
      ];
      return;
    }

    if (name === 'longitudinal') {
      steps = [
        { type: 'derive_score', score: 'bw_wbeing_total' },
        {
          type: 'pair_waves',
          from_wave: catalog.waves[0] ?? '1',
          to_wave: catalog.waves[1] ?? '2',
          measures_text: 'bw_wbeing_total'
        },
        {
          type: 'filter',
          column: 'baseline_bw_wbeing_total',
          op: 'gte',
          value: '3'
        },
        {
          type: 'aggregate',
          group_by_text: 'school',
          metrics: [
            { kind: 'mean', column: 'change_bw_wbeing_total', as_column: 'avg_change' },
            { kind: 'count_students', column: '', as_column: '' }
          ]
        }
      ];
      return;
    }

    steps = [
      { type: 'derive_score', score: 'bw_wbeing_total' },
      {
        type: 'bucket_school_size',
        output_column: 'school_size_bucket',
        small_max: '4',
        medium_min: '5',
        medium_max: '9',
        large_min: '10'
      },
      {
        type: 'aggregate',
        group_by_text: 'school_size_bucket, yearGroup',
        metrics: [{ kind: 'mean', column: 'bw_wbeing_total', as_column: '' }]
      }
    ];
  }

  async function copyShareUrl() {
    if (typeof window === 'undefined') {
      return;
    }

    const url = window.location.href;
    try {
      await navigator.clipboard.writeText(url);
      setShareFeedback('Copied query link to clipboard. It shares the query definition, not the result.');
    } catch {
      const input = document.createElement('input');
      input.value = url;
      document.body.appendChild(input);
      input.select();
      document.execCommand('copy');
      document.body.removeChild(input);
      setShareFeedback('Copied query link to clipboard. It shares the query definition, not the result.');
    }
  }

  async function runPlan() {
    builderError = null;
    const token = $authStore.token;
    if (!token) return;

    try {
      const plan = buildPlan();
      const finalStep = plan.steps[plan.steps.length - 1];
      resultGroupBy = finalStep.type === 'aggregate' ? finalStep.group_by : [];
      resultPromise = query(token, plan);
    } catch (error) {
      builderError = error instanceof Error ? error.message : 'Failed to build query plan.';
      resultPromise = null;
    }
  }

  function filterSuggestionsFor(column: string): string[] {
    return catalog.value_suggestions[column] ?? [];
  }

  onMount(() => {
    if (typeof window === 'undefined') {
      return;
    }

    const applyHashState = () => {
      isApplyingHashState = true;
      try {
        loadStateFromHash(window.location.hash);
      } catch (error) {
        steps = defaultSteps();
        builderError = error instanceof Error ? error.message : 'Failed to restore query from the URL.';
      } finally {
        isApplyingHashState = false;
      }
    };

    applyHashState();
    const onHashChange = () => applyHashState();
    window.addEventListener('hashchange', onHashChange);

    return () => {
      window.removeEventListener('hashchange', onHashChange);
      if (shareMessageTimeout) {
        clearTimeout(shareMessageTimeout);
      }
    };
  });

  $effect(() => {
    steps;
    syncHashFromState();
  });
</script>

<div class="space-y-6">
  <div class="card space-y-4">
    <div>
      <h2 class="text-xl font-semibold text-gray-800">Query Builder</h2>
      <p class="text-sm text-gray-600 mt-1">
        Build a query pipeline over the scoped student-wave table. The server keeps `uid`
        lineage hidden, computes exact distinct-student Ns for every result cell, and suppresses
        small cohorts automatically.
      </p>
    </div>

    <div class="grid md:grid-cols-2 gap-4 text-sm text-gray-600">
      <div class="rounded-xl border border-slate-200 bg-slate-50 p-4">
        <h3 class="font-semibold text-slate-800">How to think in steps</h3>
        <p class="mt-2">1. Filter the scoped source data.</p>
        <p>2. Derive approved scores such as `bw_wbeing_total`.</p>
        <p>3. Pair waves when you need within-student change columns.</p>
        <p>4. Add approved derived dimensions such as school size buckets.</p>
        <p>5. Aggregate to counts or means. This is the only step that exposes results.</p>
      </div>
      <div class="rounded-xl border border-amber-200 bg-amber-50 p-4">
        <h3 class="font-semibold text-amber-800">Safety rules</h3>
        <p class="mt-2">Raw identifiers such as `uid` are never public query fields.</p>
        <p>Unsupported columns and unsafe groupings are rejected even if earlier steps are valid.</p>
        <p>After aggregation, no more row-level operations are allowed.</p>
        <p>Every displayed value carries a contributing distinct-student N and can be suppressed.</p>
      </div>
    </div>

    <div class="flex flex-wrap gap-2">
      <button class="btn-secondary btn-sm" onclick={() => applyTemplate('simple')}>
        Load Count Template
      </button>
      <button class="btn-secondary btn-sm" onclick={() => applyTemplate('longitudinal')}>
        Load Longitudinal Template
      </button>
      <button class="btn-secondary btn-sm" onclick={() => applyTemplate('bucketed')}>
        Load School Size Template
      </button>
      <button class="btn-secondary btn-sm" onclick={copyShareUrl}>
        Share
      </button>
    </div>
    {#if shareMessage}
      <p class="text-sm text-emerald-700">{shareMessage}</p>
    {/if}
  </div>

  <div class="card space-y-4">
    <div class="flex flex-wrap items-center justify-between gap-3">
      <h3 class="font-semibold text-gray-800">Plan Steps</h3>
      <div class="flex flex-wrap gap-2">
        <button class="btn-secondary btn-sm" onclick={() => addStep('filter')}>+ Filter</button>
        <button class="btn-secondary btn-sm" onclick={() => addStep('derive_score')}>+ Score</button>
        <button class="btn-secondary btn-sm" onclick={() => addStep('pair_waves')}>+ Pair Waves</button>
        <button class="btn-secondary btn-sm" onclick={() => addStep('bucket_school_size')}>+ Bucket</button>
      </div>
    </div>

    <div class="rounded-2xl border border-blue-200 bg-blue-50 p-4 space-y-3">
      <div>
        <h3 class="font-semibold text-blue-900">Starting Structure</h3>
        <p class="text-sm text-blue-800 mt-1">
          {describeRowGrain(structureSnapshots[0].rowGrain)} {structureSnapshots[0].note}
        </p>
      </div>
      <div class="overflow-x-auto border border-blue-200 bg-white">
        <table class="min-w-full text-sm">
          <thead>
            <tr class="bg-blue-100 text-blue-900">
              {#if structureSnapshots[0].internalColumns.length > 0}
                <th class="px-3 py-2 text-left font-semibold" colspan={structureSnapshots[0].internalColumns.length}></th>
              {/if}
              <th class="border-s border-blue-200 px-3 py-2 text-left font-semibold" colspan={Math.max(structureSnapshots[0].dimensions.length, 1)}>Dimensions</th>
              <th class="border-s border-blue-200 px-3 py-2 text-left font-semibold" colspan={Math.max(structureSnapshots[0].measures.length, 1)}>Measures</th>
            </tr>
            <tr class="text-blue-800">
              {#each structureSnapshots[0].internalColumns as column}
                <th class="px-3 py-2 text-left font-medium" title={columnLabel(column)}>{column}</th>
              {/each}
              {#if structureSnapshots[0].dimensions.length === 0}
                <th class="border-s border-blue-100 px-3 py-2 text-left font-medium text-blue-400">None</th>
              {:else}
                {#each structureSnapshots[0].dimensions as column}
                  <th class="border-s border-blue-100 px-3 py-2 text-left font-medium" title={columnLabel(column)}>{column}</th>
                {/each}
              {/if}
              {#if structureSnapshots[0].measures.length === 0}
                <th class="border-s border-blue-100 px-3 py-2 text-left font-medium text-blue-400">None</th>
              {:else}
                {#each structureSnapshots[0].measures as column}
                  <th class="border-s border-blue-100 px-3 py-2 text-left font-medium" title={columnLabel(column)}>{column}</th>
                {/each}
              {/if}
            </tr>
          </thead>
        </table>
      </div>
    </div>

    <datalist id="query-columns">
      {#each filterableColumns as column}
        <option value={column} label={`${column} [${columnLabel(column)}]`}></option>
      {/each}
    </datalist>
    <datalist id="query-group-columns">
      {#each groupableColumns as column}
        <option value={column} label={`${column} [${columnLabel(column)}]`}></option>
      {/each}
    </datalist>
    <datalist id="query-measures">
      {#each measurableColumns as column}
        <option value={column} label={`${column} [${columnLabel(column)}]`}></option>
      {/each}
    </datalist>
    <datalist id="query-waves">
      {#each catalog.waves as wave}
        <option value={wave}></option>
      {/each}
    </datalist>

    {#each steps as step, index}
      <div class="rounded-2xl border border-slate-200 p-4 space-y-4">
        <div class="flex flex-wrap items-center justify-between gap-3">
          <div class="flex items-center gap-3">
            <span class="inline-flex h-8 w-8 items-center justify-center rounded-full bg-slate-100 text-sm font-semibold text-slate-700">
              {index + 1}
            </span>
            <select
              class="input w-56"
              value={step.type}
              onchange={(event) => changeStepType(index, (event.currentTarget as HTMLSelectElement).value as StepType)}
            >
              <option value="filter">Filter</option>
              <option value="derive_score">Derive Score</option>
              <option value="pair_waves">Pair Waves</option>
              <option value="bucket_school_size">Bucket School Size</option>
              <option value="aggregate">Aggregate</option>
            </select>
          </div>
          {#if steps.length > 1}
            <button class="btn-secondary btn-sm" onclick={() => removeStep(index)}>Remove</button>
          {/if}
        </div>

        {#if step.type === 'filter'}
          <div class="grid md:grid-cols-3 gap-3">
            <label>
              <span class="label text-xs">Column</span>
              <input class="input" list="query-columns" bind:value={step.column} />
              {#if step.column.trim()}
                <p class="mt-1 text-xs text-gray-500" title={columnLabel(step.column)}>{step.column}</p>
              {/if}
            </label>
            <label>
              <span class="label text-xs">Operator</span>
              <select class="input" bind:value={step.op}>
                <option value="eq">=</option>
                <option value="ne">!=</option>
                <option value="in">in</option>
                <option value="gt">&gt;</option>
                <option value="gte">≥</option>
                <option value="lt">&lt;</option>
                <option value="lte">≤</option>
              </select>
            </label>
            <label>
              <span class="label text-xs">Value</span>
              <input class="input" list={`query-filter-values-${index}`} bind:value={step.value} />
              <datalist id={`query-filter-values-${index}`}>
                {#each filterSuggestionsFor(step.column) as value}
                  <option value={value}></option>
                {/each}
              </datalist>
            </label>
          </div>
        {:else if step.type === 'derive_score'}
          <label>
            <span class="label text-xs">Approved score</span>
            <select class="input max-w-sm" bind:value={step.score}>
              {#each catalog.scores as score}
                <option value={score}>{`${score} (${columnLabel(score)})`}</option>
              {/each}
            </select>
          </label>
        {:else if step.type === 'pair_waves'}
          <div class="grid md:grid-cols-3 gap-3">
            <label>
              <span class="label text-xs">From wave</span>
              <input class="input" list="query-waves" bind:value={step.from_wave} />
            </label>
            <label>
              <span class="label text-xs">To wave</span>
              <input class="input" list="query-waves" bind:value={step.to_wave} />
            </label>
            <label>
              <span class="label text-xs">Measures (comma separated)</span>
              <input class="input" list="query-measures" bind:value={step.measures_text} />
              {#if step.measures_text.trim()}
                <p class="mt-1 text-xs text-gray-500">{columnText(step.measures_text)}</p>
              {/if}
            </label>
          </div>
          <p class="text-xs text-gray-500">
            This creates `baseline_*`, `comparison_*`, and `change_*` columns for each selected measure.
            The baseline is the original value (from the 'From wave'),
            the comparison is the later value (from the 'To wave'),
            and the change is the difference (comparison - baseline).
          </p>
        {:else if step.type === 'bucket_school_size'}
          <div class="grid md:grid-cols-5 gap-3">
            <label>
              <span class="label text-xs">Output column</span>
              <input class="input" bind:value={step.output_column} />
              {#if step.output_column.trim()}
                <p class="mt-1 text-xs text-gray-500" title={columnLabel(step.output_column)}>{step.output_column}</p>
              {/if}
            </label>
            <label>
              <span class="label text-xs">Small max</span>
              <input class="input" type="number" bind:value={step.small_max} />
            </label>
            <label>
              <span class="label text-xs">Medium min</span>
              <input class="input" type="number" bind:value={step.medium_min} />
            </label>
            <label>
              <span class="label text-xs">Medium max</span>
              <input class="input" type="number" bind:value={step.medium_max} />
            </label>
            <label>
              <span class="label text-xs">Large min</span>
              <input class="input" type="number" bind:value={step.large_min} />
            </label>
          </div>
        {:else if step.type === 'aggregate'}
          <div class="space-y-3">
            <label class="block">
              <span class="label text-xs">Group by (comma separated)</span>
              <input class="input" list="query-group-columns" bind:value={step.group_by_text} />
              {#if step.group_by_text.trim()}
                <p class="mt-1 text-xs text-gray-500">{columnText(step.group_by_text)}</p>
              {/if}
            </label>

            <div class="space-y-2">
              <div class="flex items-center justify-between gap-3">
                <span class="label text-xs">Metrics</span>
                <button class="btn-secondary btn-sm" onclick={() => addMetric(index)}>+ Metric</button>
              </div>

              {#each step.metrics as metric, metricIndex}
                <div class="grid md:grid-cols-[12rem,1fr,1fr,auto] gap-3 items-end">
                  <label>
                    <span class="label text-xs">Kind</span>
                    <select class="input" bind:value={metric.kind}>
                      <option value="count_students">count_students</option>
                      <option value="mean">mean</option>
                    </select>
                  </label>
                  <label>
                    <span class="label text-xs">Column</span>
                    <input
                      class="input"
                      list="query-measures"
                      bind:value={metric.column}
                      disabled={metric.kind === 'count_students'}
                    />
                    {#if metric.kind === 'mean' && metric.column.trim()}
                      <p class="mt-1 text-xs text-gray-500" title={columnLabel(metric.column)}>{metric.column}</p>
                    {/if}
                  </label>
                  <label>
                    <span class="label text-xs">Output name (optional)</span>
                    <input class="input" bind:value={metric.as_column} placeholder="avg_change" />
                  </label>
                  <button class="btn-secondary btn-sm" onclick={() => removeMetric(index, metricIndex)}>
                    Remove
                  </button>
                </div>
              {/each}
            </div>
          </div>
        {/if}

        <div class="border-t border-slate-200 pt-4">
          <div class="flex flex-wrap items-center gap-2">
            <span class="text-xs font-medium uppercase tracking-wide text-slate-500">
              Insert After
            </span>
            <button class="btn-secondary btn-sm" onclick={() => insertStepAfter(index, 'filter')}>
              + Filter
            </button>
            <button class="btn-secondary btn-sm" onclick={() => insertStepAfter(index, 'derive_score')}>
              + Score
            </button>
            <button class="btn-secondary btn-sm" onclick={() => insertStepAfter(index, 'pair_waves')}>
              + Pair Waves
            </button>
            <button class="btn-secondary btn-sm" onclick={() => insertStepAfter(index, 'bucket_school_size')}>
              + Bucket
            </button>
            {#if step.type === 'aggregate'}
              <p class="text-xs text-slate-500">
                Because aggregation is terminal, this inserts the new step immediately before the final aggregate.
              </p>
            {/if}
          </div>
        </div>
      </div>

      {@const nextStructure = structureSnapshots[index + 1]}
      {@const isLastStep = index === steps.length - 1}
      {#if !isLastStep && !structuresMatch(structureSnapshots[index], nextStructure)}
        <div class="rounded-2xl border border-slate-200 bg-slate-50 p-4 space-y-3">
          <div>
            <h4 class="font-semibold text-slate-800">Resulting Structure</h4>
            <p class="text-sm text-slate-600 mt-1">
              {describeRowGrain(nextStructure.rowGrain)} {nextStructure.note}
            </p>
          </div>
          <div class="overflow-x-auto border border-slate-200 bg-white">
            <table class="min-w-full text-sm">
              <thead>
                <tr class="bg-slate-100 text-slate-800">
                  {#if nextStructure.internalColumns.length > 0}
                    <th class="px-3 py-2 text-left font-semibold" colspan={nextStructure.internalColumns.length}></th>
                  {/if}
                  <th class="border-s border-slate-200 px-3 py-2 text-left font-semibold" colspan={Math.max(nextStructure.dimensions.length, 1)}>Dimensions</th>
                  <th class="border-s border-slate-200 px-3 py-2 text-left font-semibold" colspan={Math.max(nextStructure.measures.length, 1)}>Measures</th>
                </tr>
                <tr class="text-slate-700">
                  {#each nextStructure.internalColumns as column}
                    <th class="px-3 py-2 text-left font-medium" title={columnLabel(column)}>{column}</th>
                  {/each}
                  {#if nextStructure.dimensions.length === 0}
                    <th class="border-s border-slate-100 px-3 py-2 text-left font-medium text-slate-400">None</th>
                  {:else}
                    {#each nextStructure.dimensions as column}
                      <th class="border-s border-slate-100 px-3 py-2 text-left font-medium" title={columnLabel(column)}>{column}</th>
                    {/each}
                  {/if}
                  {#if nextStructure.measures.length === 0}
                    <th class="border-s border-slate-100 px-3 py-2 text-left font-medium text-slate-400">None</th>
                  {:else}
                    {#each nextStructure.measures as column}
                      <th class="border-s border-slate-100 px-3 py-2 text-left font-medium" title={columnLabel(column)}>{column}</th>
                    {/each}
                  {/if}
                </tr>
              </thead>
            </table>
          </div>
        </div>
      {/if}
    {/each}

    <div class="rounded-2xl border border-emerald-200 bg-emerald-50 p-4 space-y-3">
      <div>
        <h3 class="font-semibold text-emerald-900">Final Output Structure</h3>
        <p class="text-sm text-emerald-800 mt-1">
          {describeRowGrain(finalStructure.rowGrain)} {finalStructure.note}
        </p>
      </div>
      <div class="overflow-x-auto border border-emerald-200 bg-white">
        <table class="min-w-full text-sm">
          <thead>
            <tr class="bg-emerald-100 text-emerald-900">
              <th class="border-s border-emerald-200 px-3 py-2 text-left font-semibold" colspan={Math.max(finalStructure.dimensions.length, 1)}>Dimensions</th>
              <th class="border-s border-emerald-200 px-3 py-2 text-left font-semibold" colspan={Math.max(finalStructure.measures.length, 1)}>Measures</th>
            </tr>
            <tr class="text-emerald-800">
              {#if finalStructure.dimensions.length === 0}
                <th class="border-s border-emerald-100 px-3 py-2 text-left font-medium text-emerald-400">None</th>
              {:else}
                {#each finalStructure.dimensions as column}
                  <th class="border-s border-emerald-100 px-3 py-2 text-left font-medium" title={columnLabel(column)}>{column}</th>
                {/each}
              {/if}
              {#if finalStructure.measures.length === 0}
                <th class="border-s border-emerald-100 px-3 py-2 text-left font-medium text-emerald-400">None</th>
              {:else}
                {#each finalStructure.measures as column}
                  <th class="border-s border-emerald-100 px-3 py-2 text-left font-medium" title={columnLabel(column)}>{column}</th>
                {/each}
              {/if}
            </tr>
          </thead>
        </table>
      </div>
      <div class="text-sm text-emerald-800">
        `uid` is not part of the returned table. It is kept server-side only to calculate contributing distinct-student counts for suppression.
      </div>
    </div>

    <div class="flex items-center gap-3">
      <button class="btn-primary" onclick={runPlan}>Run Query</button>
      {#if builderError}
        <p class="text-sm text-red-600">{builderError}</p>
      {/if}
    </div>
  </div>

  <div class="card space-y-3">
    <h3 class="font-semibold text-gray-800">Plan Preview</h3>
    <p class="text-xs text-gray-500">
      This is the exact JSON plan sent to the API. It is often the easiest way to explain a query
      to another developer or to copy it into tests.
    </p>
    <pre class="overflow-x-auto rounded-xl bg-slate-950 p-4 text-xs text-slate-100">{planPreview}</pre>
  </div>

  {#if resultPromise}
    {#await resultPromise}
      <div class="card flex items-center justify-center h-32 text-gray-400">
        Running query…
      </div>
    {:then result}
      {@const chartResult = queryToChartData(result, resultGroupBy, i18n.chartFormatters)}
      <div class="space-y-4">
        <ChartCard
          title={i18n.t('queryBuilder.resultTitle')}
          type="bar"
          data={chartResult.data}
          options={chartResult.options}
          csv={result.csv}
          suppressions={result.suppressions}
          filename="query-result"
        />

        <div class="card space-y-2">
          <h3 class="font-semibold text-gray-800">{i18n.t('queryBuilder.executionProvenance')}</h3>
          {#if result.provenance.length === 0}
            <p class="text-sm text-gray-500">No provenance steps were returned.</p>
          {:else}
            {#each result.provenance as item}
              <p class="text-sm text-gray-600">• {item}</p>
            {/each}
          {/if}
        </div>
      </div>
    {:catch error}
      <div class="card bg-red-50 border-red-200 text-red-700">
        {error instanceof ApiError ? error.message : 'Failed to run query.'}
      </div>
    {/await}
  {/if}
</div>
