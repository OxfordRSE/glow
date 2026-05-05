import type { QueryResult } from "./api";
import { parseCSV } from "./csvUtils";

const PALETTE = [
  "#3B82F6",
  "#10B981",
  "#F59E0B",
  "#EF4444",
  "#8B5CF6",
  "#06B6D4",
  "#F97316",
  "#84CC16",
  "#EC4899",
  "#6366F1",
];

export interface ChartDataset {
  label: string;
  data: (number | null)[];
  backgroundColor: string;
  borderColor: string;
  borderWidth: number;
  tension?: number;
  fill?: boolean;
}

export interface ChartJsData {
  labels: string[];
  datasets: ChartDataset[];
}

export interface ChartOutput {
  data: ChartJsData;
  options: Record<string, unknown>;
}

function baseOptions(yLabel = "Count"): Record<string, unknown> {
  return {
    responsive: true,
    maintainAspectRatio: false,
    plugins: {
      legend: { position: "top" as const },
      tooltip: { mode: "index" as const, intersect: false },
    },
    scales: {
      y: {
        beginAtZero: true,
        title: { display: true, text: yLabel },
      },
    },
  };
}

/**
 * Convert a FrequencyResult to a bar-chart dataset.
 * If groupBy has one column: simple bar chart with that column as labels.
 * If groupBy has two columns: grouped bar chart (first col = x-axis, second = series).
 */
export function frequencyToChartData(
  result: { csv: string },
  groupBy: string[],
): ChartOutput {
  const { headers, rows } = parseCSV(result.csv);
  if (headers.length === 0 || rows.length === 0) {
    return { data: { labels: [], datasets: [] }, options: baseOptions() };
  }

  // Single group-by: labels = first col values, dataset = "n" or last numeric col
  if (groupBy.length <= 1) {
    const labelCol = headers[0];
    const valueCol = headers[headers.length - 1];
    const labels = rows.map((r) => String(r[0] ?? ""));
    const data = rows.map((r) => {
      const v = r[headers.indexOf(valueCol)];
      return v === "" || v === undefined ? null : Number(v);
    });
    return {
      data: {
        labels,
        datasets: [
          {
            label:
              valueCol === "n" || valueCol === "student_n" ? "Count" : valueCol,
            data,
            backgroundColor: PALETTE[0] + "CC",
            borderColor: PALETTE[0],
            borderWidth: 1,
          },
        ],
      },
      options: baseOptions(),
    };
  }

  // Two group-by columns: pivot on second column → grouped bars
  const [firstCol, secondCol] = groupBy;
  const firstIdx = headers.indexOf(firstCol);
  const secondIdx = headers.indexOf(secondCol);

  // All unique values for x-axis (first col) and series (second col)
  const xLabels = [...new Set(rows.map((r) => String(r[firstIdx] ?? "")))];
  const seriesLabels = [
    ...new Set(rows.map((r) => String(r[secondIdx] ?? ""))),
  ];

  // Value column = last column not in groupBy
  const valColIdx = headers.length - 1;

  const datasets: ChartDataset[] = seriesLabels.map((series, si) => {
    const data = xLabels.map((xLabel) => {
      const row = rows.find(
        (r) =>
          String(r[firstIdx]) === xLabel && String(r[secondIdx]) === series,
      );
      if (!row) return null;
      const v = row[valColIdx];
      return v === "" || v === undefined ? null : Number(v);
    });
    return {
      label: series,
      data,
      backgroundColor: PALETTE[si % PALETTE.length] + "CC",
      borderColor: PALETTE[si % PALETTE.length],
      borderWidth: 1,
    };
  });

  return {
    data: { labels: xLabels, datasets },
    options: baseOptions(),
  };
}

/**
 * Convert a FrequencyResult to a line-chart dataset (for trend data).
 * xCol = the column to use as the x-axis (e.g. "wave").
 */
export function frequencyToLineData(
  result: { csv: string },
  groupBy: string[],
  xCol: string,
): ChartOutput {
  const base = frequencyToChartData(result, groupBy);
  // Convert datasets to line style
  const datasets = base.data.datasets.map((ds, i) => ({
    ...ds,
    tension: 0.3,
    fill: false,
    backgroundColor: PALETTE[i % PALETTE.length],
    borderColor: PALETTE[i % PALETTE.length],
    borderWidth: 2,
  }));
  const options = {
    ...base.options,
    scales: {
      ...(base.options.scales as Record<string, unknown>),
      x: { title: { display: true, text: xCol } },
    },
  };
  return { data: { ...base.data, datasets }, options };
}

/**
 * Convert a means-like result to a bar-chart dataset.
 */
export function meansToChartData(
  result: { csv: string },
  groupBy: string[],
): ChartOutput {
  const { headers, rows } = parseCSV(result.csv);
  if (headers.length === 0 || rows.length === 0) {
    return { data: { labels: [], datasets: [] }, options: baseOptions("Mean") };
  }

  // First column(s) are group-by, rest are value columns
  const groupCount = groupBy.length;
  const valueHeaders = headers.slice(groupCount);
  const labels = rows.map((r) =>
    groupBy.map((_, gi) => String(r[gi] ?? "")).join(" / "),
  );

  const datasets: ChartDataset[] = valueHeaders.map((vh, vi) => {
    const data = rows.map((r) => {
      const v = r[groupCount + vi];
      return v === "" || v === undefined ? null : Number(v);
    });
    return {
      label: vh,
      data,
      backgroundColor: PALETTE[vi % PALETTE.length] + "CC",
      borderColor: PALETTE[vi % PALETTE.length],
      borderWidth: 1,
    };
  });

  return {
    data: { labels, datasets },
    options: baseOptions("Mean"),
  };
}

export function queryToChartData(
  result: QueryResult,
  groupBy: string[],
): ChartOutput {
  return meansToChartData(result, groupBy);
}
