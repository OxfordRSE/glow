/**
 * Parse a CSV string into headers and rows.
 */
export function parseCSV(csv: string): {
  headers: string[];
  rows: (string | number)[][];
} {
  const lines = csv.trim().split("\n");
  if (lines.length === 0) return { headers: [], rows: [] };
  const headers = lines[0].split(",").map((h) => h.trim());
  const rows = lines.slice(1).map((line) =>
    line.split(",").map((cell) => {
      const trimmed = cell.trim();
      const num = Number(trimmed);
      return trimmed !== "" && !isNaN(num) ? num : trimmed;
    }),
  );
  return { headers, rows };
}

/**
 * Convert parsed CSV rows into array of objects keyed by headers.
 */
export function csvToObjects(csv: string): Record<string, string | number>[] {
  const { headers, rows } = parseCSV(csv);
  return rows.map((row) =>
    Object.fromEntries(headers.map((h, i) => [h, row[i] ?? ""])),
  );
}

/**
 * Trigger a browser download of a CSV string.
 */
export function downloadCSV(filename: string, csv: string): void {
  const blob = new Blob([csv], { type: "text/csv;charset=utf-8;" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.style.display = "none";
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}
