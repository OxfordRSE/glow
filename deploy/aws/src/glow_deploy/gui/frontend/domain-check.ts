// On the new-deployment form, asks the server whether the entered domain has
// a Route 53 hosted zone in this AWS account. If so, the cert/DNS setup can
// be fully automatic, so the "Certificate ARN" field is hidden in favour of
// a notice; otherwise the field stays visible (the standard case: hosting on
// someone else's domain, where a pasted ACM cert is required).
import type { DomainCheckResult } from "./types.js";
import { debugLog } from "./debug.js";

const DEBOUNCE_MS = 400;

async function checkDomain(domain: string): Promise<boolean> {
  const response = await fetch(
    `/deployments/check-domain?domain=${encodeURIComponent(domain)}`,
  );
  if (!response.ok) return false;
  const result = (await response.json()) as DomainCheckResult;
  debugLog("domain check", result);
  return result.auto;
}

function applyResult(auto: boolean): void {
  const certField = document.getElementById("cert-arn-field");
  const certInput = document.getElementById("certificate-arn-input") as HTMLInputElement | null;
  const notice = document.getElementById("auto-dns-notice");
  if (certField) certField.hidden = auto;
  // Clear any pasted ARN once the field is hidden, so it can't ride along
  // as a submitted value the user no longer sees.
  if (auto && certInput) certInput.value = "";
  if (notice) notice.hidden = !auto;
}

export function init(): void {
  const domainInput = document.getElementById("domain-input") as HTMLInputElement | null;
  if (!domainInput) return;
  let timer: number | undefined;
  domainInput.addEventListener("input", () => {
    const domain = domainInput.value.trim();
    window.clearTimeout(timer);
    if (!domain) {
      applyResult(false);
      return;
    }
    timer = window.setTimeout(() => {
      void checkDomain(domain).then((auto) => {
        // Discard a stale response if the domain changed while it was in flight.
        if (domainInput.value.trim() === domain) applyResult(auto);
      });
    }, DEBOUNCE_MS);
  });
}

if (!(globalThis as { __TEST__?: boolean }).__TEST__) init();
