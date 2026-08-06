// Polls /jobs/{id}/status and updates the progress display in place, instead
// of the <meta http-equiv="refresh"> full-page reload (kept as a <noscript>
// fallback). Deploys run 5-20+ minutes, so ~1.5s latency is plenty.
import type { JobStatus } from "./types.js";
import { debugLog } from "./debug.js";

const POLL_INTERVAL_MS = 1500;

function jobIdFromPath(): string | null {
  const match = window.location.pathname.match(/^\/jobs\/([^/]+)$/);
  return match ? match[1] : null;
}

async function poll(jobId: string): Promise<void> {
  const response = await fetch(`/jobs/${jobId}/status`);
  if (!response.ok) {
    window.setTimeout(() => void poll(jobId), POLL_INTERVAL_MS);
    return;
  }

  const job = (await response.json()) as JobStatus;
  debugLog("job status", job);

  const statusEl = document.getElementById("job-status");
  const linesEl = document.getElementById("job-lines");
  const errorEl = document.getElementById("job-error");
  if (statusEl) statusEl.textContent = job.status;
  if (linesEl) linesEl.textContent = job.lines.join("\n");
  if (errorEl) errorEl.textContent = job.error ?? "";

  if (job.status === "succeeded" || job.status === "failed") {
    // The terminal-state page (confirm form / "view deployment" link) is
    // server-rendered from job.meta, which this JSON endpoint doesn't carry —
    // a full reload is simpler than duplicating that logic in JS.
    window.location.reload();
    return;
  }

  window.setTimeout(() => void poll(jobId), POLL_INTERVAL_MS);
}

const jobId = jobIdFromPath();
if (jobId) void poll(jobId);
