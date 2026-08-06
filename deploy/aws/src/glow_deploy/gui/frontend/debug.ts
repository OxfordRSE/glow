// Strips token/secret-like keys before anything reaches console.debug.
// Account IDs are not secret and are intentionally left alone.
const SECRET_KEY_PATTERN = /token|secret|password|credential/i;

export function redact(value: unknown): unknown {
  if (Array.isArray(value)) {
    return value.map(redact);
  }
  if (value !== null && typeof value === "object") {
    const result: Record<string, unknown> = {};
    for (const [key, val] of Object.entries(value as Record<string, unknown>)) {
      result[key] = SECRET_KEY_PATTERN.test(key) ? "[redacted]" : redact(val);
    }
    return result;
  }
  return value;
}

export function debugLog(label: string, value: unknown): void {
  console.debug(label, redact(value));
}
