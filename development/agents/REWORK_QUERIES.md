# REWORK_QUERIES Resume State

## Purpose

Machine-oriented handoff note for resuming the REWORK_QUERIES grilling session later.

## Status

- Output-shape grilling is well advanced.
- Request-shape grilling is partially advanced.
- Auth/discovery changes are now in scope.
- No code has been implemented yet in this session.

## Confirmed Decisions

### Transport and top-level response

- Use rich JSON, not CSV payloads.
- Do not use `Record<FilteredQueryString, ...>`.
- Use a top-level envelope with query-level metadata.
- Include a normalized `query` echo in the response.
- Use `dimensions` terminology throughout.
- Keep API JSON field casing aligned with current API style, which is snake_case.

### Period model

- Replace wave-led thinking with API-derived collection periods.
- Derive `period_id` from submission timestamps.
- Expose a dedicated top-level `periods` list with explicit boundaries.
- Keep `period_id` separate from normal dimensions.
- Include open/current periods.
- Period boundary rule should be deployment-configurable by timezone and cutoff.

### Suppression model

- Suppression reasons should be canonical machine-readable codes.
- `period_id` is a privileged suppression boundary.
- Blanket suppression runs independently within each period, across other requested dimensions in that period.
- Partial suppression must be representable, so some periods for a variable may be suppressed while others are present.
- Incompatible versions should use the same suppression mechanism.

### Cell/value model

- Organise variable results by period.
- Cells carry only non-period coordinates.
- Coordinates are scalar values or `null`, never arrays.
- Return observed cells only, not full Cartesian products.
- For general queries with no focus school, omit focus-school values entirely.
- Keep exact focus-school `n` values.
- Keep whole-sample `n` values.

### Deduplication and derived totals

- Deduplicate per variable.
- Rule: latest non-null value per `uid` per school-period bucket.
- Compute derived totals from deduped item values.

### Version handling

- Assume same variable name with compatible declared limits is comparable.
- If limits differ but can be trivially unified, linearly rescale narrower to wider limits.
- If trivial unification is not possible, suppress the affected period with an incompatible-version reason.
- Metadata should include vague machine-readable notes such as `values-rescaled`.
- Metadata should include sample-wide `question_versions` counts.

### Request model

- Backend should not support a filter concept.
- Backend should always return all periods.
- Minimal request shape is heading toward:

```typescript
type QueryRequest = {
  school_id?: number;
  variables: string[];
  dimensions?: string[];
};
```

### Auth and discovery

- Anonymous general queries are in scope.
- School-targeted queries remain authorization-checked against the user's allowed schools.
- `/me` should replace the current dashboard bootstrap use of `/admin/me`.
- `/me` should include auth-state information and available schools.
- `/schools` should be removed.
- `/dimensions` should be added for query discovery.
- `/dimensions` is school-scoped when a school is supplied, dataset-scoped otherwise.

### Determinism and caching

- Response ordering must be deterministic.
- ETag functionality is in scope for this rework.

## Current Recommended Human-Level Shapes

### Response

```typescript
type QueryResponse = {
  query: {
    school_id?: number;
    variables: string[];
    dimensions: string[];
  };
  dimensions: QueryDimensionDefinition[];
  periods: QueryPeriod[];
  variables: Record<string, VariableResponse>;
};

type QueryDimensionDefinition = {
  key: string;
  type: "string" | "number";
  role?: "grouping" | "time";
};

type QueryPeriod = {
  id: string;
  starts_at: string;
  ends_before: string;
};

type VariableResponse = {
  metadata: {
    limits?: { min?: number; max?: number };
    notes?: string[];
    question_versions?: Record<string, number>;
  };
  periods: Record<string, PeriodSlice>;
};

type PeriodSlice = {
  metadata?: {
    suppression?: { reason: string };
  };
  data?: QueryCell[];
};

type QueryCell = {
  coordinates: Record<string, string | number | null>;
  focus?: {
    value: number | null;
    n: number;
  };
  sample: {
    mean: number | null;
    sd: number | null;
    n: number;
  };
};
```

### Request

```typescript
type QueryRequest = {
  school_id?: number;
  variables: string[];
  dimensions?: string[];
};
```

## Important Codebase Findings Already Established

- `api/src/glow_api/models.py` is still wave-first and neighbor-era.
- `api/src/glow_api/routers/query.py` still expects a single variable and explicit waves.
- `api/src/glow_api/blanket_suppression.py` suppresses per wave in the current design.
- `api/src/glow_api/data.py` currently performs no normalization for periods, deduplication, or version-aware transforms.
- `api/src/glow_api/odk_client.py` currently fetches the current form XML only.
- `api/src/glow_api/routers/schools.py` currently mixes school listing with query discovery.
- `dashboard/src/routes/[locale]/+page.svelte` is tightly coupled to neighbor comparison and the old response shape.
- Storybook contract examples currently mirror the old shape.

## Open Questions Still Outstanding

### Endpoint shapes

- Exact `/me` response model.
  - Need to choose the explicit discriminator field name.
  - Candidate question asked but dismissed: `is_authenticated` vs `kind`.
- Exact `/dimensions` response model.
  - Need to confirm whether it returns only variable/dimension names or also limits metadata.

### ODK integration unknowns

- Exact submission timestamp column name in the ODK CSV export.
- Exact mechanism for retrieving historical form definitions across versions.
- Whether those should be treated as explicit implementation-discovery tasks was asked but not confirmed because that question bundle was dismissed.

### Caching

- User wants ETag support included now.
- Full `If-None-Match` / `304` semantics were proposed but not explicitly reconfirmed after the final question bundle was dismissed.

### Suppression/code details

- Exact canonical suppression reason code list still needs to be fixed.
- Exact placement of rescale notes may still need confirming if rescaling occurs only in some periods.

## Suggested Next Questions To Resume With

1. Lock the exact `/me` contract.
2. Lock the exact `/dimensions` contract.
3. Confirm whether implementation should assume ODK exposes a known timestamp/system field or treat that as a discovery task.
4. Confirm full ETag semantics for `/query`.
5. Then move from grilling into a precise implementation plan that follows `AGENTS.md` TDD and verification rules.

## Scope Reminder For Future Resume

This rework now covers at least:

- API request/response contract rewrite
- period-based normalization and suppression redesign
- deduplication logic
- version-aware rescaling/blocking
- anonymous general-query support
- `/me` and `/dimensions` contract changes
- `/schools` removal
- neighbor-code removal across API, metadata DB surfaces, dashboard, Storybook, and contract examples
- deterministic ordering and likely ETag support
