# Rework Query Interface

## Summary

We have moved away from the original neighbor-focused sketch and now have a much clearer direction.

The API should move to a rich JSON query contract designed for messy longitudinal data rather than a wave-led or neighbor-led model. The key design decision is that time is no longer treated as a normal grouping dimension. Instead, the API will derive its own collection `period_id` values from submission timestamps, return all periods, and treat periods as a privileged boundary for suppression.

The frontend will then receive enough structured information to cache a response and explore it locally without asking the backend to distinguish between filters and groupings.

## Direction Agreed So Far

### Core API shape

- The response should be rich JSON, not CSV-in-a-string.
- The response should use a top-level envelope rather than a bare variable map.
- The response should include query-level schema and period definitions.
- The response should echo the normalized query the API actually executed.
- The response should use `dimensions` terminology throughout.

Current intended shape, at a human level:

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
```

### Periods and time

- The API should derive `period_id` from submission timestamps.
- Period definitions should be exposed explicitly with boundaries.
- Period boundaries should be deployment-configurable by timezone and cutoff rule.
- Open/current periods should be included.
- `period_id` should be kept separate from normal dimensions in the response.

### Suppression

- Suppression remains blanket suppression using canonical machine-readable reasons.
- Because open periods must be included, `period_id` should be a privileged suppression boundary.
- That means suppression is evaluated independently within each period, across the other requested dimensions inside that period.
- A variable may therefore be available for some periods and suppressed for others.
- Suppressed or incompatible variables/periods should still be represented explicitly rather than silently omitted.

### Variable data

- Variable results should be organised by period.
- Each period slice should either contain aggregate cells or a suppression reason.
- Aggregate cells should carry only non-period coordinates.
- Coordinate values should be scalar values or `null`, not arrays.
- The API should return observed cells only, not full Cartesian grids.
- General queries with no focus school should omit focus-school values entirely.

### Focus and sample statistics

- School-targeted queries should return both focus-school values and whole-sample reference values.
- General queries should return only whole-sample values.
- Exact counts are still wanted because the frontend needs them for weighted recombination.

### Deduplication and totals

- Deduplication should happen per variable.
- The rule is: take the latest non-null value for each `uid` within each school-period bucket.
- Derived totals should be computed from those deduped item values.

### Version handling

- We assume that unchanged variable names with compatible declared limits are comparable.
- If limits differ but are trivially compatible, values should be linearly rescaled from the narrower range to the wider range.
- If trivial unification is not possible, the affected period should be suppressed with an incompatible-version reason.
- The response should include vague machine-readable notes such as `values-rescaled` rather than detailed provenance.
- The response should include sample-wide `question_versions` counts in metadata.

### Request shape

- The backend should not have a concept of filters.
- The request should be minimal and dimension-driven.
- The backend should always return all periods.

Human-level request sketch:

```typescript
type QueryRequest = {
  school_id?: number;
  variables: string[];
  dimensions?: string[];
};
```

### Auth and discovery

- Anonymous general queries are in scope.
- School-targeted queries must still check that the requested `school_id` is in the user's allowed schools.
- `/me` should replace the current bootstrap use of `/admin/me`.
- `/me` should include auth state and available schools.
- `/schools` should be removed.
- Query discovery should move to `/dimensions`.
- `/dimensions` should be school-scoped when a school is supplied, dataset-scoped otherwise.

### Determinism and caching

- Response ordering should be deterministic.
- ETag support should be included as part of this rework.

## Important Codebase Reality Checks

These are design-relevant facts from the current implementation:

- The current query API is still wave-first, single-variable, and neighbor-focused.
- The current dashboard page is tightly coupled to that old shape.
- `/schools` currently mixes school listing with query-schema discovery.
- The data-loading path currently has no explicit normalization for periods, duplicate submissions, or version-aware rescaling.
- The current ODK client only fetches the current form XML, not historical form definitions.

## Remaining Open Questions

These still need to be nailed down before implementation starts in earnest:

- The exact `/me` response shape and discriminator field name.
- The exact `/dimensions` response shape beyond variables, dimensions, and likely limits metadata.
- The exact canonical suppression reason codes.
- The exact ODK-export timestamp field name used for period derivation.
- The exact ODK mechanism for retrieving historical form definitions for version comparison.
- The exact ETag behaviour to ship immediately, though deterministic canonicalization is already agreed.

## Implementation Consequences

This is no longer a small tweak.

The rework now implies:

- replacing the query request and response models
- rewriting query execution and suppression logic around period slices
- introducing a normalization layer ahead of query execution
- removing neighbor logic from API, DB metadata, admin surfaces, dashboard code, stories, and contract examples
- replacing `/schools`-driven query discovery with `/me` plus `/dimensions`
- updating dashboard data access and page structure to use multi-variable period-organised responses

The next step should be to turn this into an implementation plan that follows the project rules in `AGENTS.md`, especially the API and dashboard testing requirements.
