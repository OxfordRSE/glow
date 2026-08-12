// Polls /jobs/{id}/status and updates the progress display in place, instead
// of the <meta http-equiv="refresh"> full-page reload (kept as a <noscript>
// fallback). Deploys run 5-20+ minutes, so ~1.5s latency is plenty.
import type { JobStatus } from "./types.js";
import { debugLog } from "./debug.js";

const POLL_INTERVAL_MS = 1500;

function startElapsedTimer(): void {
  const el = document.getElementById("job-elapsed");
  if (!el) return;
  const startedAt = Date.now();
  const tick = () => {
    const totalSeconds = Math.floor((Date.now() - startedAt) / 1000);
    const minutes = Math.floor(totalSeconds / 60);
    const seconds = totalSeconds % 60;
    el.textContent = `(still running, ${minutes}:${String(seconds).padStart(2, "0")} elapsed)`;
  };
  tick();
  window.setInterval(tick, 1000);
}

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
  // job.lines is pre-rendered HTML (ANSI colour codes turned into <span>s server-side).
  if (linesEl) linesEl.innerHTML = job.lines.join("\n");
  // job.error is pre-rendered HTML (ANSI colour codes turned into <span>s server-side).
  if (errorEl) errorEl.innerHTML = job.error ?? "";

  if (job.status === "succeeded" || job.status === "failed") {
    // The terminal-state page (confirm form / "view deployment" link) is
    // server-rendered from job.meta, which this JSON endpoint doesn't carry —
    // a full reload is simpler than duplicating that logic in JS.
    window.location.reload();
    return;
  }

  window.setTimeout(() => void poll(jobId), POLL_INTERVAL_MS);
}

export function init(): void {
  const jobId = jobIdFromPath();
  // document.currentScript is always null for type="module" scripts, so the
  // initial status can't ride in via a dataset attribute on this script tag —
  // read it off the server-rendered status badge instead.
  const initialStatus = document.getElementById("job-status")?.textContent?.trim();
  // Terminal-state pages carry their own final render; polling here would
  // just reload the page again on every load, looping forever.
  if (jobId && initialStatus !== "succeeded" && initialStatus !== "failed") {
    void poll(jobId);
    startElapsedTimer();
  } else if (initialStatus === "succeeded") {
    // Scroll after layout/paint settles (details/pre content, fonts) — doing it
    // immediately on module load lets a late reflow cut the smooth-scroll short.
    requestAnimationFrame(() => {
      requestAnimationFrame(() => {
        document.querySelector(".button")?.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    });
  }
}

if (!(globalThis as { __TEST__?: boolean }).__TEST__) init();
