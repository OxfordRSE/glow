<script lang="ts">
  import { parseCSV } from '$lib/csvUtils';
  import { createI18n, locale } from '$lib/i18n';

  interface Props {
    csv: string;
    suppressions?: Record<string, Record<number, string>>;
  }

  let { csv, suppressions = {} }: Props = $props();

  const i18n = $derived(createI18n($locale));
  const parsed = $derived(parseCSV(csv));

  function isSuppressed(col: string, rowIdx: number): boolean {
    return suppressions[col]?.[rowIdx] !== undefined;
  }

  function displayValue(
    value: string | number,
    col: string,
    rowIdx: number
  ): string {
    if (isSuppressed(col, rowIdx)) return '—';
    if (value === '' || value === null || value === undefined) return '—';
    return String(value);
  }

  let sortCol = $state<number | null>(null);
  let sortDir = $state<'asc' | 'desc'>('asc');

  function toggleSort(colIdx: number) {
    if (sortCol === colIdx) {
      sortDir = sortDir === 'asc' ? 'desc' : 'asc';
    } else {
      sortCol = colIdx;
      sortDir = 'asc';
    }
  }

  const sortedRows = $derived(() => {
    if (sortCol === null) return parsed.rows;
    return [...parsed.rows].sort((a, b) => {
      const av = a[sortCol!] ?? '';
      const bv = b[sortCol!] ?? '';
      if (typeof av === 'number' && typeof bv === 'number') {
        return sortDir === 'asc' ? av - bv : bv - av;
      }
      return sortDir === 'asc'
        ? String(av).localeCompare(String(bv))
        : String(bv).localeCompare(String(av));
    });
  });
</script>

<div class="overflow-x-auto rounded-lg border border-gray-200">
  {#if parsed.headers.length === 0}
    <p class="text-sm text-gray-500 p-4">{i18n.t('table.noData')}</p>
  {:else}
    <table class="min-w-full text-sm divide-y divide-gray-200">
      <thead class="bg-gray-50">
        <tr>
          {#each parsed.headers as header, ci}
            <th
              class="px-4 py-2 text-left font-medium text-gray-600 whitespace-nowrap cursor-pointer hover:bg-gray-100 select-none"
              onclick={() => toggleSort(ci)}
              title={i18n.t('table.sortBy', { label: i18n.columnLabel(header) })}
            >
              <span title={header}>{i18n.columnLabel(header)}</span>
              {#if sortCol === ci}
                <span class="ml-1 text-blue-500">{sortDir === 'asc' ? '↑' : '↓'}</span>
              {/if}
            </th>
          {/each}
        </tr>
      </thead>
      <tbody class="bg-white divide-y divide-gray-100">
        {#each sortedRows() as row, ri}
          <tr class="hover:bg-gray-50">
            {#each parsed.headers as header, ci}
              {@const val = displayValue(row[ci], header, ri)}
              <td class="px-4 py-2 whitespace-nowrap {val === '—' ? 'text-gray-400 italic' : 'text-gray-800'}">
                {val}
              </td>
            {/each}
          </tr>
        {/each}
      </tbody>
    </table>
  {/if}
</div>
