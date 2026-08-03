// Mirrors the JSON shape returned by GET /jobs/{id}/status (see gui/jobs.py Job).
export interface JobStatus {
  id: string;
  status: "pending" | "running" | "succeeded" | "failed";
  lines: string[];
  error: string | null;
}
